"""The bundled ffmpeg (``imageio-ffmpeg``): packet timestamps, frame counts and stream facts (PRE-A §5b).

``imageio-ffmpeg`` ships no ffprobe, so timestamps come from ``-c copy -f framemd5`` (exact integer ``pts`` in the
stream's own time base) and stream facts from ``imageio_ffmpeg.read_frames``' first (meta) item.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import imageio_ffmpeg

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


def run(args: list[str], *, timeout: float = FFMPEG_TIMEOUT_S) -> str:
    """Run the bundled ffmpeg; its stdout, or ``MediaError`` with the tail of stderr."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", *args]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603 -- bundled ffmpeg, list argv
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
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", *SAFE_INPUT, "-i", str(path), "-map",
           f"0:{stream}", "-c", "copy", "-f", "framemd5", "-"]  # fmt: skip
    with tempfile.TemporaryFile() as err, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True) as proc:  # noqa: S603 -- bundled ffmpeg, list argv
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


def decoded_start(path: Path, stream: str = "a:0") -> Fraction:
    """The first *decoded* frame's time, in seconds. It can differ from the first packet's: AAC's priming samples
    and an MP4 edit list's hidden video frames (packets at a negative pts) are discarded by the decoder."""
    # ``demux``: the stream's own time base, so the time is exact (a decoder's default, 1/fps, would round it).
    out = run([*SAFE_INPUT, "-i", str(path), "-map", f"0:{stream}", "-frames:" + stream[0], "1",
               "-enc_time_base:" + stream[0], "demux", "-f", "framemd5", "-"])  # fmt: skip
    time_base: Fraction | None = None
    for line in out.splitlines():
        if line.startswith("#"):
            match = _TB.match(line)
            if match:
                time_base = Fraction(int(match.group(2)), int(match.group(3)))
            continue
        fields = [f.strip() for f in line.split(",")]
        if time_base is not None and len(fields) >= 6:
            return int(fields[2]) * time_base
    raise MediaError(f"no decodable {stream} frame in {path.name}")


def frame_count(path: Path) -> int:
    """Frames ffmpeg actually wrote into an encoded clip (PRE-A §5b step 5: read back, never computed)."""
    return packets(path).count


def facts(path: Path) -> StreamFacts:
    gen = imageio_ffmpeg.read_frames(str(path), input_params=list(SAFE_INPUT))
    try:
        meta = cast(dict[str, Any], next(gen))
    except (RuntimeError, OSError, StopIteration) as exc:
        raise MediaError(f"can't read {path.name}: {exc}") from exc
    finally:
        gen.close()
    size = cast(tuple[int, int], tuple(meta.get("size") or (0, 0)))
    return StreamFacts(
        fps=float(meta.get("fps") or 0.0),
        size=(int(size[0]), int(size[1])),
        rotate=int(meta.get("rotate") or 0),
        audio=bool(meta.get("audio_codec")),
        duration=float(meta.get("duration") or 0.0),
    )
