"""Muse's 0–1000 grid → prepared-clip pixels: the single mapping rule of PRE-A §5 (vectors G1–G14).

Images are sent at the prepared size with a ``bar_h`` black frame-number bar added above, so the sent image is
``W × (H + bar_h)`` and the grid refers to that whole image. Grid values are clamped to [0, 1000], scaled with
Meta's documented ``round(v × size / 1000)`` (half up), and moved down out of the bar.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Literal

from safecut.track.axes import round_half_up

BAR_H = 40
GRID = 1000
#: A red-team box under 2 px in either dimension becomes this square (fail closed: it still gets patched).
DEGENERATE_SIDE = 32
_LABEL = re.compile(r"^F[0-9]+$")

Box = tuple[int, int, int, int]
BoxKind = Literal["miss", "redteam"]


def _clamp_grid(value: float) -> Fraction:
    return Fraction(min(max(Fraction(value), Fraction(0)), Fraction(GRID)))


def to_sent(value: float, side: int) -> int:
    """One grid value to sent-image pixels (unclamped to the last pixel; boxes use the exclusive edge)."""
    return round_half_up(_clamp_grid(value) * side / GRID)


def point(x: float, y: float, width: int, height: int, bar_h: int = BAR_H) -> tuple[int, int] | None:
    """A grid point to frame pixels; ``None`` when it lands in the frame-number bar (G2, G5)."""
    sent_h = height + bar_h
    x_img = min(to_sent(x, width), width - 1)
    y_img = min(to_sent(y, sent_h), sent_h - 1)
    y_frame = y_img - bar_h
    return None if y_frame < 0 else (x_img, y_frame)


def is_frame_label(text: str) -> bool:
    """The red-team read our own bar label (``F 000090``), spaces ignored."""
    return bool(_LABEL.fullmatch(text.replace(" ", "")))


def box(
    grid_box: tuple[float, float, float, float],
    width: int,
    height: int,
    *,
    kind: BoxKind,
    finding: str = "",
    text: str = "",
    bar_h: int = BAR_H,
) -> Box | None:
    """A grid box to a half-open frame box (§5 step 4).

    In-bar boxes: a red-team ``text`` finding that reads the frame label is dropped; any other red-team in-bar box
    is a misplaced real finding and becomes the whole frame (G8b); a miss-loop box in the bar is dropped (G9).
    Degenerate (< 2 px) boxes: red-team → a 32 px square centred on it (G10, G14); miss-loop → dropped.
    """
    x1, y1, x2, y2 = grid_box
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    sent_h = height + bar_h
    if to_sent(y2, sent_h) <= bar_h:
        if kind == "miss" or (finding == "text" and is_frame_label(text)):
            return None
        return (0, 0, width, height)
    left = min(max(to_sent(x1, width), 0), width)
    right = min(max(to_sent(x2, width), 0), width)
    top = min(max(to_sent(y1, sent_h) - bar_h, 0), height)
    bottom = min(max(to_sent(y2, sent_h) - bar_h, 0), height)
    if right - left >= 2 and bottom - top >= 2:
        return (left, top, right, bottom)
    if kind == "miss":
        return None
    cx, cy = (left + right) // 2, (top + bottom) // 2
    half = DEGENERATE_SIDE // 2
    return (max(cx - half, 0), max(cy - half, 0), min(cx + half, width), min(cy + half, height))


def to_grid(px: int, side: int) -> float:
    """Frame-pixel coordinate back onto the grid (for tests and synthetic answers)."""
    return math.floor(Fraction(px * GRID, side) + Fraction(1, 2))
