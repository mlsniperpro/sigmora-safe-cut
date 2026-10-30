"""``prepare``: an upload → ``prepared.mp4`` + ``job.json`` + 1 fps keyframes (WP1 step 1, PRE-A §5b).

The prepared clip is constant frame rate at ``job.fps = min(30, round(source average fps))``, H.264,
``+faststart``, long edge ≤ 1280 px, with audio kept in sync on the same origin. ``job.times[n]`` is the
source-clock time of the source frame prepared frame ``n`` shows, computed exactly from integer packet
timestamps with ffmpeg's own ``fps``-filter slot rule, so every consumer that recomputes it gets the same
doubles bit for bit.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal

from safecut import config
from safecut.contracts import Intake, Job, dump, load, now_utc
from safecut.track import media
from safecut.track.axes import round_half_up

log = logging.getLogger(__name__)

PREPARED = "prepared.mp4"
JOB = "job.json"
INTAKE = "intake.json"
KEYFRAMES = "keyframes"
#: Where the upload sits in a job directory: exactly one file, under its own name.
SOURCE_DIR = "source"
MAX_FPS = 30
MAX_EDGE = 1280
_HASH_CHUNK = 1 << 20

#: The API's and UI's codes (WP5, UI-SPEC §10.2); ``no_source`` is a job directory without its upload.
Reason = Literal["too_long", "too_large", "bad_media", "no_source"]


class PrepareError(ValueError):
    """The upload can't be prepared. ``reason`` is the API's and UI's error code (WP5, PR #2 UI-SPEC);
    ``duration_s`` and ``size_bytes`` are set where they are known (the API shows them)."""

    def __init__(
        self, reason: Reason, message: str, *, duration_s: float | None = None, size_bytes: int | None = None
    ) -> None:
        super().__init__(message)
        self.reason: Reason = reason
        self.duration_s = duration_s
        self.size_bytes = size_bytes


@dataclass(frozen=True)
class SourceProbe:
    """What prepare needs to know about an upload before transcoding it. ``audio_start`` is the first decoded
    audio frame's time (AAC priming excluded), on the same container clock as the video packets."""

    video: media.Packets
    audio: media.Packets | None
    audio_start: Fraction | None
    fps: int
    duration: Fraction
    size_bytes: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


#: The most pixels a source frame may have: 8K (7680×4320, 33 Mpx) passes, a decoding bomb doesn't.
MAX_SOURCE_PIXELS = 40_000_000
#: The fewest frames an upload may have.
MIN_FRAMES = 2


def job_fps(video: media.Packets) -> int:
    """``min(30, round(source average fps))`` from the packet count over the stream's exact span (≥ 1)."""
    span = video.span
    if span <= 0:
        return 1
    return max(1, min(MAX_FPS, round_half_up(Fraction(video.count) / span)))


def frame_times(video: media.Packets, fps: int, frames: int) -> list[float]:
    """``times[n]``: the source time of the last source frame whose slot ``round_half_up(t × fps)`` is ``≤ n``.

    An empty slot repeats the previous frame, so ``times`` is non-decreasing, not strictly increasing; frames
    in one slot but the last are dropped (PRE-A §5b step 3, vectors T6a–T6c).
    """
    shown: list[float] = []
    k = 0
    for n in range(frames):
        while k + 1 < video.count and round_half_up(video.seconds(k + 1) * fps) <= n:
            k += 1
        shown.append(float(video.seconds(k)))
    return shown


def probe(source: Path) -> SourceProbe:
    """Limits first (size, then duration), so an over-limit upload is refused before any transcode."""
    size = source.stat().st_size
    if size > config.MAX_UPLOAD_BYTES:
        raise PrepareError("too_large", f"{size} bytes is over the {config.MAX_UPLOAD_BYTES}-byte upload limit",
                           size_bytes=size)  # fmt: skip
    try:
        facts = media.facts(source)
    except media.MediaError as exc:
        raise PrepareError("bad_media", f"can't read the video stream: {exc}", size_bytes=size) from exc
    width, height = facts.size
    if width * height > MAX_SOURCE_PIXELS:  # before any full decode (8K is 33 Mpx)
        raise PrepareError("bad_media", f"{width}x{height} is over the {MAX_SOURCE_PIXELS // 1_000_000} Mpx limit",
                           size_bytes=size)  # fmt: skip
    # The header's duration first, so an over-long upload is refused as too_long before its packets are read.
    if facts.duration > config.MAX_CLIP_SECONDS:
        raise PrepareError("too_long", f"{facts.duration:.2f} s is over the {config.MAX_CLIP_SECONDS} s limit",
                           duration_s=facts.duration, size_bytes=size)  # fmt: skip
    try:
        # The video clock starts at the first *decoded* frame (§5b steps 2–3): hidden edit-list frames are dropped.
        video = media.packets(source, "v:0").from_time(media.decoded_start(source, "v:0"))
    except media.MediaError as exc:
        raise PrepareError("bad_media", f"can't read the video stream: {exc}", size_bytes=size) from exc
    if video.count < MIN_FRAMES:
        # A single picture has no motion to track and makes a zero-frame SAM proxy (§5b: at least one frame).
        raise PrepareError("bad_media", f"{video.count} frame: a video needs at least {MIN_FRAMES}", size_bytes=size)
    audio: media.Packets | None = None
    audio_start: Fraction | None = None
    if facts.audio:
        try:
            audio = media.packets(source, "a:0")
            audio_start = media.decoded_start(source, "a:0")
        except media.MediaError:
            audio = None
            log.warning("audio stream announced but unreadable; prepared without audio", extra={"source": source.name})
    duration = max(video.span, Fraction(facts.duration).limit_denominator(1_000_000))
    if duration > Fraction(str(config.MAX_CLIP_SECONDS)):
        raise PrepareError("too_long", f"{float(duration):.2f} s is over the {config.MAX_CLIP_SECONDS} s limit",
                           duration_s=float(duration), size_bytes=size)  # fmt: skip
    return SourceProbe(video=video, audio=audio, audio_start=audio_start, fps=job_fps(video), duration=duration,
                       size_bytes=size)  # fmt: skip


def _video_filter(fps: int) -> str:
    # Start at 0 first (T9), then ffmpeg's fps slots, then the long edge to ≤ 1280 px with even sides.
    # autorotate runs before this chain, so iw/ih are the displayed (rotated) sides.
    edge = f"trunc(min({MAX_EDGE},iw)/2)*2"
    scale = f"scale=w='if(gte(iw,ih),{edge},-2)':h='if(gte(iw,ih),-2,trunc(min({MAX_EDGE},ih)/2)*2)'"
    return f"setpts=PTS-STARTPTS,fps={fps},{scale}"


def _audio_filter(video: media.Packets, audio_start: Fraction) -> str:
    """Put the audio on the video's origin: trim what plays before the first video frame, or delay it."""
    lead = video.start - audio_start  # > 0: audio starts first
    chain = "asetpts=PTS-STARTPTS"
    if lead > 0:
        return f"{chain},atrim=start={float(lead):.6f},asetpts=PTS-STARTPTS"
    if lead < 0:
        return f"{chain},adelay={float(-lead) * 1000:.3f}:all=1"
    return chain


def transcode(source: Path, out: Path, probe_result: SourceProbe) -> None:
    args = ["-y", *media.SAFE_INPUT, *media.TRANSCODE_THREADS, "-i", str(source), "-map", "0:v:0", "-vf",
            _video_filter(probe_result.fps)]  # fmt: skip
    if probe_result.audio is not None and probe_result.audio_start is not None:
        args += ["-map", "0:a:0", "-af", _audio_filter(probe_result.video, probe_result.audio_start), "-c:a", "aac",
                 "-b:a", "128k"]  # fmt: skip
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", *media.ENCODE_THREADS, "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-g", str(2 * probe_result.fps), "-movflags", "+faststart", "-map_metadata", "-1", str(out)]  # fmt: skip
    media.run(args, memory=media.TRANSCODE_MEMORY_BYTES)


def extract_keyframes(prepared: Path, out_dir: Path, *, fps: int, frames: int) -> list[int]:
    """Prepared frames ``0, fps, 2·fps, …`` as ``keyframes/<frame:06d>.jpg`` (1 fps; JPEG quality ≈ 95)."""
    wanted = list(range(0, frames, fps))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    media.run(["-y", "-i", str(prepared), "-vf", f"select='not(mod(n\\,{fps}))'", "-fps_mode", "passthrough",
               "-q:v", "2", str(out_dir / "kf%06d.jpg")])  # fmt: skip
    written = sorted(out_dir.glob("kf*.jpg"))
    if len(written) != len(wanted):
        raise media.MediaError(f"expected {len(wanted)} keyframes, ffmpeg wrote {len(written)}")
    for path, frame in zip(written, wanted, strict=True):
        path.rename(out_dir / f"{frame:06d}.jpg")
    return wanted


def find_source(job_dir: Path) -> Path:
    """The upload: the one file in ``<job>/source/``."""
    files = (
        sorted(p for p in (job_dir / SOURCE_DIR).glob("*") if p.is_file()) if (job_dir / SOURCE_DIR).is_dir() else []
    )
    if len(files) != 1:
        raise PrepareError("no_source", f"{job_dir / SOURCE_DIR} must hold exactly one upload, found {len(files)}")
    return files[0]


def prepare(source: Path, job_dir: Path, intake: Intake | None = None) -> Path:
    """Prepare ``source`` into ``job_dir`` and write ``job.json``; returns its path. ``intake`` (the pipeline's
    ``intake.json``) supplies the upload's name, the job's creation time and its consent flag."""
    job_dir.mkdir(parents=True, exist_ok=True)
    found = probe(source)
    prepared = job_dir / PREPARED
    partial = job_dir / f".{PREPARED}.partial.mp4"
    try:
        transcode(source, partial, found)
        frames = media.frame_count(partial)
        out_facts = media.facts(partial)
    except media.MediaError as exc:
        partial.unlink(missing_ok=True)
        raise PrepareError("bad_media", f"transcode failed: {exc}") from exc
    partial.replace(prepared)
    try:
        extract_keyframes(prepared, job_dir / KEYFRAMES, fps=found.fps, frames=frames)
    except media.MediaError as exc:
        raise PrepareError("bad_media", f"keyframes failed: {exc}") from exc
    job = Job(
        job_id=job_dir.name,
        source=intake.source if intake is not None else source.name,
        source_sha256=sha256_file(source),
        prepared=PREPARED,
        fps=found.fps,
        width=out_facts.size[0],
        height=out_facts.size[1],
        frames=frames,
        times=frame_times(found.video, found.fps, frames),
        audio=found.audio is not None and out_facts.audio,
        created_at=intake.created_at if intake is not None else now_utc(),
        consented=intake.consented if intake is not None else False,
    )
    log.info("prepared", extra={"job_id": job.job_id, "fps": job.fps, "frames": frames, "audio": job.audio})
    return dump(job, job_dir / JOB)


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The stage entry point. ``replay`` changes nothing: prepare makes no model calls."""
    del replay
    intake = load(job_dir / INTAKE, Intake) if (job_dir / INTAKE).exists() else None
    source = find_source(job_dir)
    if intake is not None and intake.source != source.name:
        raise PrepareError("no_source", f"intake.json names {intake.source!r}, but source/ holds {source.name!r}")
    return prepare(source, job_dir, intake)
