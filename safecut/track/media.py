"""The bundled ffmpeg (``imageio-ffmpeg``): packet timestamps, frame counts and stream facts (PRE-A §5b).

``imageio-ffmpeg`` ships no ffprobe, so timestamps come from ``-c copy -f framemd5`` (exact integer ``pts`` in the
stream's own time base) and stream facts from ``imageio_ffmpeg.read_frames``' first (meta) item.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import imageio_ffmpeg

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


def packets(path: Path, stream: str = "v:0") -> Packets:
    """``-map 0:<stream> -c copy -f framemd5``: one line per packet (decode order), sorted here by ``pts``."""
    out = run(["-i", str(path), "-map", f"0:{stream}", "-c", "copy", "-f", "framemd5", "-"])
    time_base: Fraction | None = None
    rows: list[tuple[int, int]] = []
    for line in out.splitlines():
        if line.startswith("#"):
            match = _TB.match(line)
            if match:
                time_base = Fraction(int(match.group(2)), int(match.group(3)))
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 6:
            continue
        rows.append((int(fields[2]), int(fields[3])))
    if time_base is None or not rows:
        raise MediaError(f"no {stream} packets in {path.name}")
    rows.sort()
    return Packets(time_base=time_base, pts=tuple(p for p, _ in rows), last_duration=rows[-1][1])


def frame_count(path: Path) -> int:
    """Frames ffmpeg actually wrote into an encoded clip (PRE-A §5b step 5: read back, never computed)."""
    return packets(path).count


def facts(path: Path) -> StreamFacts:
    gen = imageio_ffmpeg.read_frames(str(path))
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
