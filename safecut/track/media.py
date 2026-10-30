"""The bundled ffmpeg (``imageio-ffmpeg``): packet timestamps, frame counts and stream facts (PRE-A §5b).

``imageio-ffmpeg`` ships no ffprobe, so timestamps come from ``-c copy -f framemd5`` (exact integer ``pts`` in the
stream's own time base) and stream facts from the header ffmpeg prints for ``-i`` (imageio-ffmpeg's parser).
"""

from __future__ import annotations

import importlib
import re
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import imageio_ffmpeg

#: The parser ``imageio_ffmpeg.read_frames`` uses for ffmpeg's ``-i`` header, run here under the probe limits.
parse_ffmpeg_header = cast(
    Callable[[str], dict[str, Any]], importlib.import_module("imageio_ffmpeg._parsing").parse_ffmpeg_header
)
#: Uploads are MP4 or MOV (the API and the web app take nothing else), read only by the mov demuxer: never a
#: playlist (an ``.m3u8`` makes ffmpeg's HLS demuxer open the local files it names) or any other demuxer.
SAFE_INPUT = ("-format_whitelist", "mov,mp4,m4a,3gp,3g2,mj2")
#: Generous: a 60 s, 150 MB upload transcodes in well under this on one CPU.
FFMPEG_TIMEOUT_S = 600.0
_TB = re.compile(r"^#tb (\d+): (\d+)/(\d+)$")


class MediaError(RuntimeError):
    """ffmpeg couldn't read or write a clip (unreadable input, a missing stream, a failed encode)."""


@dataclass(frozen=True)
class Packets:
    """One stream's packets, sorted by presentation time."""

    time_base: Fraction
    pts: tuple[int, ...]
    last_duration: int

    @property
    def count(self) -> int:
        return len(self.pts)

    def seconds(self, index: int) -> Fraction:
        """Packet ``index``'s time on the stream's own clock (first packet at 0), exact."""
        return (self.pts[index] - self.pts[0]) * self.time_base

    def from_time(self, start: Fraction) -> Packets:
        """Only the packets at or after ``start`` (seconds): an MP4 edit list (a stream-copy trim, an iOS Photos
        trim) keeps hidden frames before its start, which demux as packets but never decode."""
        kept = tuple(p for p in self.pts if p * self.time_base >= start)
        if not kept:
            raise MediaError("no packets at or after the stream's first decoded frame")
        last = self.last_duration if kept[-1] == self.pts[-1] else 0
        return Packets(time_base=self.time_base, pts=kept, last_duration=last)

    @property
    def start(self) -> Fraction:
        return self.pts[0] * self.time_base

    @property
    def span(self) -> Fraction:
        """First packet start to last packet end, in seconds."""
        return (self.pts[-1] + self.last_duration - self.pts[0]) * self.time_base


@dataclass(frozen=True)
class StreamFacts:
    """What ``read_frames``' meta item says about a clip (after rotation, when ``rotate`` is set)."""

    fps: float
    size: tuple[int, int]
    rotate: int
    audio: bool
    duration: float


def ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


#: The address space an ffmpeg child that reads an upload's index may use. A crafted MP4 under the size limit can
#: declare tens of millions of samples, and ffmpeg indexes them all before printing anything (2 GB for 80M); a
#: real 60 s clip needs a few MB. Over it, ffmpeg fails and the upload is refused as bad media.
PROBE_MEMORY_BYTES = 2 << 30
#: The address space for the transcode of an upload (decode up to the pixel cap, scale, encode ≤ 1280 px), with
#: its thread counts fixed so a many-core host doesn't multiply it.
TRANSCODE_MEMORY_BYTES = 6 << 30
TRANSCODE_THREADS = ("-threads", "4", "-filter_threads", "2")
#: The encoder's own thread count (an output option: the input-side -threads only bounds the decoder).
ENCODE_THREADS = ("-threads", "4")
#: Probe decodes (one frame) on one thread: ffmpeg's default is about two filter threads per core.
PROBE_THREADS = ("-threads", "1", "-filter_threads", "1")


def limited(cmd: list[str], memory: int | None = None) -> list[str]:
    """``cmd`` under a memory limit (default: the probe's), through ``sh``'s ``ulimit`` (no ``preexec_fn``: the
    API runs this in worker threads). Where the limit can't be set (macOS), the command still runs."""
    kib = (memory or PROBE_MEMORY_BYTES) // 1024
    return ["/bin/sh", "-c", 'ulimit -v "$0" 2>/dev/null; exec "$@"', str(kib), *cmd]


def run(args: list[str], *, timeout: float = FFMPEG_TIMEOUT_S, probe: bool = False, memory: int | None = None) -> str:
    """Run the bundled ffmpeg; its stdout, or ``MediaError`` with the tail of stderr. ``probe``: it reads an upload,
    so it runs under the probe memory limit (or ``memory``)."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", *args]
    cmd = limited(cmd, memory) if probe or memory else cmd
    try:
        # errors="replace": an upload's metadata can hold any bytes; a message must never be a UnicodeDecodeError.
        done = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)  # noqa: S603 -- bundled ffmpeg, list argv
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffmpeg timed out after {timeout:.0f} s") from exc
    if done.returncode != 0:
        raise MediaError(f"ffmpeg failed ({done.returncode}): {done.stderr.strip()[-400:]}")
    return done.stdout


#: The most packets a stream may have (read incrementally, so a hostile upload of millions of tiny frames is
#: refused before it fills memory): 60 s of 240 fps video is 14,400; audio packets are bigger (AAC: 47 a second).
MAX_PACKETS = 20_000


def _read_packets(proc: subprocess.Popen[str], limit: int) -> tuple[Fraction | None, list[tuple[int, int]]]:
    """framemd5 lines as (pts, duration), stopping as soon as there are more than ``limit``."""
    time_base: Fraction | None = None
    rows: list[tuple[int, int]] = []
    assert proc.stdout is not None  # noqa: S101 -- stdout=PIPE always sets it
    for line in proc.stdout:
        if line.startswith("#"):
            match = _TB.match(line.strip())
            if match:
                time_base = Fraction(int(match.group(2)), int(match.group(3)))
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) >= 6:
            rows.append((int(fields[2]), int(fields[3])))
            if len(rows) > limit:
                break
    return time_base, rows


def packets(path: Path, stream: str = "v:0", *, limit: int = MAX_PACKETS) -> Packets:
    """``-map 0:<stream> -c copy -f framemd5``: one line per packet (decode order), sorted here by ``pts``.
    More than ``limit`` packets is a ``MediaError`` (ffmpeg is stopped as soon as the count passes it)."""
    cmd = limited([ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", *SAFE_INPUT, "-i", str(path), "-map",
                   f"0:{stream}", "-c", "copy", "-f", "framemd5", "-"])  # fmt: skip
    with (
        tempfile.TemporaryFile() as err,
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True, errors="replace") as proc,  # noqa: S603 -- bundled ffmpeg, list argv
    ):
        watchdog = threading.Timer(FFMPEG_TIMEOUT_S, proc.kill)  # ffmpeg may stall without printing a line
        watchdog.start()
        try:
            time_base, rows = _read_packets(proc, limit)
        finally:
            watchdog.cancel()
        if len(rows) > limit:
            proc.kill()
            proc.wait()
            raise MediaError(f"{stream} of {path.name}: more than {limit} packets")
        if proc.wait() != 0:
            err.seek(0)
            tail = err.read().decode("utf-8", "replace").strip()[-400:]
            raise MediaError(f"ffmpeg failed ({proc.returncode}): {tail or 'killed after the timeout'}")
    if time_base is None or not rows:
        raise MediaError(f"no {stream} packets in {path.name}")
    rows.sort()
    return Packets(time_base=time_base, pts=tuple(p for p, _ in rows), last_duration=rows[-1][1])


@dataclass(frozen=True)
class FirstFrame:
    """A stream's first *decoded* frame: its time (seconds) and its decoded size in bytes (for video, decoded as
    one byte a pixel, so ``size`` is width × height whatever the header claims)."""

    start: Fraction
    size: int


def first_frame(path: Path, stream: str = "a:0") -> FirstFrame:
    """The first decoded frame. Its time can differ from the first packet's: AAC's priming samples and an MP4 edit
    list's hidden video frames (packets at a negative pts) are discarded by the decoder."""
    # ``demux``: the stream's own time base, so the time is exact (a decoder's default, 1/fps, would round it).
    gray = ["-pix_fmt", "gray"] if stream.startswith("v") else []
    out = run([*SAFE_INPUT, *PROBE_THREADS, "-i", str(path), "-map", f"0:{stream}", "-frames:" + stream[0], "1",
               *gray, "-enc_time_base:" + stream[0], "demux", "-f", "framemd5", "-"], probe=True)  # fmt: skip
    time_base: Fraction | None = None
    for line in out.splitlines():
        if line.startswith("#"):
            match = _TB.match(line)
            if match:
                time_base = Fraction(int(match.group(2)), int(match.group(3)))
            continue
        fields = [f.strip() for f in line.split(",")]
        if time_base is not None and len(fields) >= 6:
            return FirstFrame(start=int(fields[2]) * time_base, size=int(fields[4]))
    raise MediaError(f"no decodable {stream} frame in {path.name}")


def decoded_start(path: Path, stream: str = "a:0") -> Fraction:
    """The first decoded frame's time, in seconds (see :func:`first_frame`)."""
    return first_frame(path, stream).start


def frame_count(path: Path) -> int:
    """Frames ffmpeg actually wrote into an encoded clip (PRE-A §5b step 5: read back, never computed)."""
    return packets(path).count


def facts(path: Path) -> StreamFacts:
    """The stream header ffmpeg prints for ``-i`` (read under the probe memory limit), parsed by ``imageio-ffmpeg``."""
    cmd = limited([ffmpeg(), "-nostdin", "-hide_banner", *SAFE_INPUT, "-i", str(path)])
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=FFMPEG_TIMEOUT_S,  # noqa: S603 -- bundled ffmpeg, list argv
                              check=False)  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffmpeg timed out after {FFMPEG_TIMEOUT_S:.0f} s reading {path.name}") from exc
    # split("\n"), not splitlines(): ffmpeg ends lines with \n only, and a metadata value may hold U+2028 or \x1e,
    # which splitlines() would turn into forged "  Stream #…" lines.
    lines = [line.rstrip("\r") for line in done.stderr.split("\n") if line.strip()]
    if not any("Video:" in line for line in lines):  # ffmpeg exits 1 without an output; the header is the answer
        last = lines[-1].strip() if lines else f"ffmpeg exited {done.returncode}"
        raise MediaError(f"can't read {path.name}: {last[:300]}")
    # Only ffmpeg's own header lines (metadata is printed indented below them): a title saying "Duration: 00:00:01"
    # or " Video: " must never be read as the clip's.
    header = [line for line in lines if line.startswith(("Input #", "  Duration:", "  Stream #"))]
    # The first video stream only: it is the one every read maps (0:v:0); imageio would take the last one.
    videos = [line for line in header if " Video: " in line]
    header = [line for line in header if " Video: " not in line or line is videos[0]] if videos else header
    try:
        meta = parse_ffmpeg_header("\n".join(header))
    except (ValueError, IndexError, KeyError, AttributeError, TypeError) as exc:  # a stream line it can't read
        raise MediaError(f"can't read {path.name}: {exc}") from exc
    size = cast(tuple[int, int], tuple(meta.get("size") or (0, 0)))
    return StreamFacts(
        fps=float(meta.get("fps") or 0.0),
        size=(int(size[0]), int(size[1])),
        rotate=int(meta.get("rotate") or 0),
        audio=bool(meta.get("audio_codec")),
        duration=float(meta.get("duration") or 0.0),
    )
