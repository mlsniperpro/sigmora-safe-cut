"""Read the prepared clip, redact every frame, encode H.264 with the original audio, and cut thumbnails.

Frames stream one at a time (memory stays one frame deep, whatever the clip's length) from OpenCV into the
bundled ffmpeg (``imageio-ffmpeg``) over a pipe. Thumbnails are cut from the redacted frames only, so a thumbnail
never shows anything the video hides.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from safecut.contracts import DecisionItem, Decisions, Job, Plan, Track, Tracks
from safecut.decide.geometry import BoxT, box_at, clamp, union
from safecut.render.draw import Frame

#: x264 quality: visually lossless for review, small enough to download (CRF 18, ffmpeg's "visually lossless").
CRF = "18"
THUMB_MAX_SIDE = 240
THUMB_MIN_SIDE = 64
#: Seconds the encoder may take beyond the frames themselves before the render is called stuck.
ENCODE_TIMEOUT_S = 600


class RenderError(RuntimeError):
    """The clip couldn't be read or encoded as the job describes it."""


def read_frames(path: Path, job: Job) -> Iterator[Frame]:
    """Every frame of ``path`` as BGR, checked against the job's size and frame count."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RenderError(f"can't open {path.name}")
    count = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[:2] != (job.height, job.width):
                raise RenderError(f"{path.name} frame {count} is {frame.shape[1]}x{frame.shape[0]}, not the job's")
            count += 1
            if count > job.frames:
                raise RenderError(f"{path.name} has more than the job's {job.frames} frames")
            yield np.ascontiguousarray(frame, dtype=np.uint8)
    finally:
        capture.release()
    if count != job.frames:
        raise RenderError(f"{path.name} has {count} frames, the job {job.frames}")


@contextmanager
def h264_writer(out: Path, job: Job, audio_from: Path | None) -> Generator[Callable[[Frame], None]]:
    """A ``write(frame)`` that pipes raw BGR frames into x264 at the job's frame rate; with ``audio_from``, its first
    audio stream is muxed back (AAC). The file appears only when the encode succeeded."""
    if job.width % 2 or job.height % 2:
        raise RenderError(f"H.264 4:2:0 needs even sides, the job is {job.width}x{job.height}")
    partial = out.with_name(f".{out.name}.partial.mp4")
    argv = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{job.width}x{job.height}", "-r", str(job.fps), "-i", "-",
    ]  # fmt: skip
    if audio_from is not None:
        argv += ["-i", str(audio_from), "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac", "-b:a", "160k"]
    argv += ["-c:v", "libx264", "-preset", "veryfast", "-crf", CRF, "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(partial)]  # fmt: skip
    # stderr goes to a file, not a pipe: a chatty encoder can then never block on a full pipe while frames stream in.
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stderr=log)  # noqa: S603 -- fixed argv, bundled ffmpeg
        stdin = process.stdin
        if stdin is None:  # Popen with stdin=PIPE always has one
            raise RenderError("ffmpeg has no stdin")

        def write(frame: Frame) -> None:
            try:
                stdin.write(frame.tobytes())
            except BrokenPipeError:
                raise RenderError("ffmpeg stopped reading frames") from None

        try:
            yield write
            stdin.close()
            process.wait(timeout=ENCODE_TIMEOUT_S)
        except BaseException:
            process.kill()
            process.wait()
            partial.unlink(missing_ok=True)
            raise
        if process.returncode != 0:
            partial.unlink(missing_ok=True)
            log.seek(0)
            err = log.read().decode("utf-8", "replace")[-400:]
            raise RenderError(f"ffmpeg failed ({process.returncode}): {err}")
    partial.replace(out)


@dataclass(frozen=True)
class ThumbSpec:
    item_id: str
    frame: int
    box: BoxT


def thumb_specs(decisions: Decisions, tracks: Tracks, plan: Plan, job: Job) -> list[ThumbSpec]:
    """One thumbnail per item: its first evidence frame (or the middle of its span), framed on where it is."""
    by_id = {t.track_id: t for t in tracks.tracks}
    specs: list[ThumbSpec] = []
    for item in decisions.items:
        spec = _thumb_spec(item, by_id, plan, job)
        if spec is not None:
            specs.append(spec)
    return specs


def _thumb_spec(item: DecisionItem, by_id: dict[str, Track], plan: Plan, job: Job) -> ThumbSpec | None:
    ts = [by_id[tid] for tid in item.track_ids if tid in by_id]
    if item.box is not None and item.first is not None and item.last is not None:
        frame = item.evidence_frames[0] if item.evidence_frames else item.first
        return ThumbSpec(item.item_id, frame, item.box)
    if not ts:
        return None
    present = sorted({f for t in ts for f in range(t.first, t.last + 1)})
    alive = set(present)
    frame = next((f for f in item.evidence_frames if f in alive), present[len(present) // 2])
    boxes = [b for t in ts if (b := box_at(t, frame)) is not None]
    planned = [e.box for e in plan.frames.get(frame, []) if e.item_id == item.item_id]
    region = union(boxes + planned) if boxes or planned else (0, 0, job.width, job.height)
    return ThumbSpec(item.item_id, frame, region)


def cut_thumb(frame: Frame, box: BoxT) -> Frame:
    """A crop around ``box`` with half its size again as context, at least 64 px, at most 240 px on its long side."""
    height, width = frame.shape[:2]
    w, h = max(box[2] - box[0], THUMB_MIN_SIDE), max(box[3] - box[1], THUMB_MIN_SIDE)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    crop = clamp((cx - w * 0.75, cy - h * 0.75, cx + w * 0.75, cy + h * 0.75), width, height)
    x1, y1, x2, y2 = crop if crop is not None else (0, 0, width, height)
    out = frame[y1:y2, x1:x2]
    scale = THUMB_MAX_SIDE / max(out.shape[0], out.shape[1])
    if scale < 1:
        size = (max(1, round(out.shape[1] * scale)), max(1, round(out.shape[0] * scale)))
        out = cv2.resize(out, size, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(out, dtype=np.uint8)


def probe_streams(path: Path) -> list[str]:
    """The codec of each stream in ``path``, in order (e.g. ``["video:h264", "audio:aac"]``), from ffmpeg's header."""
    argv = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)]
    err = subprocess.run(argv, capture_output=True, check=False, timeout=60).stderr.decode("utf-8", "replace")  # noqa: S603 -- fixed argv, bundled ffmpeg
    out: list[str] = []
    for raw in err.splitlines():
        line = raw.strip()
        if line.startswith("Stream #"):
            for kind in ("Video", "Audio"):
                marker = f"{kind}: "
                if marker in line:
                    codec = line.split(marker, 1)[1].split()[0].rstrip(",")
                    out.append(f"{kind.lower()}:{codec}")
    return out
