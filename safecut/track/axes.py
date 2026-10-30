"""The two clocks and the SAM proxy mapping (PRE-A §5b), in exact integer arithmetic.

Every prepared clip is constant frame rate at ``job.fps``; the SAM proxy is encoded from it with ffmpeg's
``fps`` filter at ``sam_fps_eff = min(SAFECUT_SAM_FPS, job.fps)``. The filter gives a frame at time ``t`` the
slot ``round_half_up(t × rate)`` and output frame ``n`` shows the last input frame whose slot is ``≤ n``.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence
from fractions import Fraction

#: SAM 3/3.1 confirms a new object only after this many frames of its own input (``hotstart_delay``).
SAM_HOTSTART_FRAMES = 15


def round_half_up(value: Fraction) -> int:
    """``floor(value + 1/2)``: Meta's and ffmpeg's ``near`` rounding for the non-negative values used here."""
    return math.floor(value + Fraction(1, 2))


def slot(index: int, *, rate_in: int, rate_out: int) -> int:
    """The output slot of input frame ``index`` when ``rate_in`` fps is resampled to ``rate_out`` fps."""
    return (2 * index * rate_out + rate_in) // (2 * rate_in)


def sam_fps_eff(job_fps: int, sam_fps: int) -> int:
    """The proxy rate: never above the prepared rate (never upsample)."""
    if job_fps < 1 or sam_fps < 1:
        raise ValueError("frame rates are positive")
    return min(sam_fps, job_fps)


def from_proxy_table(frames: int, job_fps: int, proxy_fps: int, proxy_frames: int) -> list[int]:
    """``from_proxy(j)`` for every proxy frame ``j``: the prepared frame proxy frame ``j`` shows.

    ``max{i < frames : slot(i) ≤ j}``. ``proxy_frames`` is read back from the encoded proxy (ffmpeg may not emit
    the last slot); a ``j`` past every slot shows the last prepared frame.
    """
    if frames < 1 or proxy_frames < 1:
        raise ValueError("a clip and its proxy have at least one frame")
    if proxy_fps > job_fps:
        raise ValueError("the proxy is never faster than the prepared clip")
    table: list[int] = []
    i = 0
    for j in range(proxy_frames):
        while i + 1 < frames and slot(i + 1, rate_in=job_fps, rate_out=proxy_fps) <= j:
            i += 1
        table.append(i)
    return table


def to_proxy(frame: int, table: Sequence[int]) -> int:
    """``argmin_j |from_proxy(j) − frame|``, ties to the smaller ``j`` (object prompts on prepared frames)."""
    if not table:
        raise ValueError("empty proxy table")
    k = bisect_left(table, frame)
    if k == 0:
        return 0
    if k == len(table):
        return len(table) - 1
    below, above = table[k - 1], table[k]
    # The first j at the lower value wins ties; table is non-decreasing, so walk back to its first occurrence.
    j = k - 1 if frame - below <= above - frame else k
    while j > 0 and table[j - 1] == table[j]:
        j -= 1
    return j


def player_frame(media_time: float, job_fps: int, frames: int) -> int:
    """The web player's frame (PR #2 UI-SPEC §3.6): ``clamp(floor(t × fps + 0.25), 0, frames − 1)``."""
    return _clamp(math.floor(Fraction(media_time) * job_fps + Fraction(1, 4)), frames)


def time_to_frame(seconds: float, job_fps: int, frames: int) -> int:
    """A prepared-clock time (a transcript turn) to its frame: ``clamp(floor(t × fps), 0, frames − 1)``."""
    return _clamp(math.floor(Fraction(seconds) * job_fps), frames)


def backfill_frames(job_fps: int, proxy_fps: int) -> int:
    """SAM's hot-start delay in prepared frames: ``ceil(15 × job.fps / sam_fps_eff)`` (T10)."""
    return math.ceil(Fraction(SAM_HOTSTART_FRAMES * job_fps, proxy_fps))


def crowded_span(j: int, table: Sequence[int], frames: int) -> range:
    """The prepared frames a crowded proxy frame ``j`` stands for (T11): between its neighbours' frames."""
    if not 0 <= j < len(table):
        raise ValueError(f"proxy frame {j} out of range")
    start = 0 if j == 0 else table[j - 1] + 1
    stop = frames if j == len(table) - 1 else table[j + 1]
    return range(start, max(stop, start))


def _clamp(value: int, frames: int) -> int:
    return min(max(value, 0), frames - 1)
