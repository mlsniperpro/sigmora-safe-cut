"""Draw one frame's redactions (DESIGN §2.7): what the renderer paints, and exactly which pixels it changes.

* ``solid`` and ``person_solid``: an opaque fill over the region (the box, or the mask when the entry has one).
* ``pixelate``: a mosaic on the item's locked grid (``[x0, y0, cell]``): every cell takes the mean colour of the
  whole cell in the source frame plus a fixed per-cell noise, so a still object renders identical cells frame
  after frame (a shifting grid leaks detail, DESIGN §2.7) and the cell means can't be read back exactly.
* crowd fills: opaque, drawn last.

An entry never paints inside its ``keep_clear`` boxes (kept participants' faces, DESIGN §2.6).

Solid regions are drawn after mosaics, so where both overlap the stronger one wins. :func:`hidden_mask` is the
same union of regions, so the coverage metric (``coverage.py``) scores exactly what the video shows.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np
from numpy.typing import NDArray

from safecut.contracts import CrowdFill, PlanEntry
from safecut.decide.geometry import BoolMask, decode

Frame = NDArray[np.uint8]

#: The fill colour, BGR (a dark slate: reads as "removed", never as a shadow or a dark garment).
FILL_BGR = (40, 32, 28)
#: Per-cell noise amplitude, in levels per channel (DESIGN §2.7: "plus per-block noise").
NOISE = 12


def region_mask(entry: PlanEntry, height: int, width: int) -> tuple[slice, slice, BoolMask]:
    """The entry's box as slices and the pixels it covers inside that box: its mask (or the whole box), less the kept
    faces it leaves clear (``keep_clear``, DESIGN §2.6)."""
    x1, y1 = max(0, entry.box[0]), max(0, entry.box[1])
    x2, y2 = min(width, entry.box[2]), min(height, entry.box[3])
    ys, xs = slice(y1, y2), slice(x1, x2)
    if entry.mask is None:
        region = np.ones((max(0, y2 - y1), max(0, x2 - x1)), dtype=np.bool_)
    else:
        region = decode(entry.mask)[ys, xs].copy()
    for cx1, cy1, cx2, cy2 in entry.keep_clear:
        region[max(0, cy1 - y1) : max(0, cy2 - y1), max(0, cx1 - x1) : max(0, cx2 - x1)] = False
    return ys, xs, region


def hidden_mask(entries: list[PlanEntry], fills: list[CrowdFill], height: int, width: int) -> BoolMask:
    """Every pixel the renderer changes on a frame with these entries and crowd fills."""
    out = np.zeros((height, width), dtype=np.bool_)
    for entry in entries:
        ys, xs, region = region_mask(entry, height, width)
        out[ys, xs] |= region
    for fill in fills:
        out[fill.box[1] : fill.box[3], fill.box[0] : fill.box[2]] = True
    return out


def _cell_noise(item_id: str, rows: NDArray[np.int64], cols: NDArray[np.int64]) -> NDArray[np.int64]:
    """Deterministic noise per (item, cell, channel) in ``[-NOISE, NOISE]``: fixed over time, so averaging frames
    never cancels it (noise that changed per frame would average back to the true cell mean)."""
    seed = int.from_bytes(hashlib.sha256(item_id.encode("utf-8")).digest()[:8], "little")
    r = rows.astype(np.uint64)[:, None, None]
    c = cols.astype(np.uint64)[None, :, None]
    ch = np.arange(3, dtype=np.uint64)[None, None, :]
    with np.errstate(over="ignore"):
        x = (
            np.uint64(seed)
            ^ (r * np.uint64(0x9E3779B97F4A7C15))
            ^ (c * np.uint64(0xC2B2AE3D27D4EB4F))
            ^ (ch * np.uint64(0x165667B19E3779F9))
        )
        x ^= x >> np.uint64(33)
        x *= np.uint64(0xFF51AFD7ED558CCD)
        x ^= x >> np.uint64(33)
    return (x % np.uint64(2 * NOISE + 1)).astype(np.int64) - NOISE


def _pixelate(out: Frame, source_integral: NDArray[np.float64], entry: PlanEntry) -> None:
    grid = entry.grid
    if grid is None:
        return
    height, width = out.shape[:2]
    ys, xs, region = region_mask(entry, height, width)
    if region.size == 0 or not bool(region.any()):
        return
    gx, gy, cell = grid
    x_lo, x_hi, y_lo, y_hi = int(xs.start), int(xs.stop), int(ys.start), int(ys.stop)
    col0, col1 = (x_lo - gx) // cell, (x_hi - 1 - gx) // cell
    row0, row1 = (y_lo - gy) // cell, (y_hi - 1 - gy) // cell
    cols = np.arange(col0, col1 + 1, dtype=np.int64)
    rows = np.arange(row0, row1 + 1, dtype=np.int64)
    cx0 = np.clip(gx + cols * cell, 0, width)
    cx1 = np.clip(gx + (cols + 1) * cell, 0, width)
    cy0 = np.clip(gy + rows * cell, 0, height)
    cy1 = np.clip(gy + (rows + 1) * cell, 0, height)
    integral = source_integral
    sums = (
        integral[cy1[:, None], cx1[None, :]]
        - integral[cy0[:, None], cx1[None, :]]
        - integral[cy1[:, None], cx0[None, :]]
        + integral[cy0[:, None], cx0[None, :]]
    )
    counts = ((cy1 - cy0)[:, None] * (cx1 - cx0)[None, :]).astype(np.float64)
    means = sums / np.maximum(counts, 1.0)[:, :, None]
    colours = np.clip(np.rint(means) + _cell_noise(entry.item_id, rows, cols), 0, 255).astype(np.uint8)
    yy = (np.arange(y_lo, y_hi, dtype=np.int64) - gy) // cell - row0
    xx = (np.arange(x_lo, x_hi, dtype=np.int64) - gx) // cell - col0
    painted = colours[yy[:, None], xx[None, :]]
    view = out[ys, xs]
    view[region] = painted[region]


def apply(frame: Frame, entries: list[PlanEntry], fills: list[CrowdFill]) -> Frame:
    """The redacted copy of a BGR ``frame``: mosaics first (from the untouched source), then solids, then crowds."""
    out = frame.copy()
    height, width = frame.shape[:2]
    mosaics = [e for e in entries if e.style == "pixelate"]
    if mosaics:
        integral = np.asarray(cv2.integral(frame, sdepth=cv2.CV_64F), dtype=np.float64)
        for entry in mosaics:
            _pixelate(out, integral, entry)
    for entry in entries:
        if entry.style == "pixelate":
            continue
        ys, xs, region = region_mask(entry, height, width)
        view = out[ys, xs]
        view[region] = FILL_BGR
    for fill in fills:
        out[fill.box[1] : fill.box[3], fill.box[0] : fill.box[2]] = FILL_BGR
    return out
