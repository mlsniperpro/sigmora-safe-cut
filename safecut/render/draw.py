"""Draw one frame's redactions (DESIGN §2.7): what the renderer paints, and exactly which pixels it changes.

One look for every cover (owner, 2026-11-04): **frosted**, like a production blur. Each connected blob of covers
takes the source's average colour over the blob, lifted slightly toward a light haze, plus a fixed grey grain per
cell (the item's locked grid for a face, else about 4 cells across the region); then the covered pixels become a
strong blur of those cells alone, and the edge is feathered outward. No cell carries any of the region's own detail
(two regions with the same average render identically), a still object renders the same pixels frame after frame,
and nothing is ever a dark block: faces, plates, screens, documents, whole persons, crowd fills and audit patches.

An entry never paints inside its ``keep_clear`` boxes (kept participants' faces, DESIGN §2.6). :func:`hidden_mask`
is the union of the regions (the feathered ring outside them only softens the edge), so the coverage metric
(``coverage.py``) scores exactly what the video hides.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np
from numpy.typing import NDArray

from safecut.contracts import CrowdFill, PlanEntry
from safecut.decide.geometry import BoolMask, decode

Frame = NDArray[np.uint8]

#: Per-cell noise amplitude, in levels per channel (DESIGN §2.7: "plus per-block noise").
NOISE = 24


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


#: The frosted finish (owner, 2026-11-04): Gaussian sigma over the mosaic inside a cover, and the outward feather of
#: its edge, in pixels. Inside the cover every pixel is the blurred mosaic; only the ring outside softens.
FROST_SIGMA = 4.0
FEATHER_SIGMA = 3.0
#: A cover without a locked grid (an object, a whole person, a crowd fill, an audit patch) gets this many cells
#: across its shorter side; every cell is the region's mean colour plus its noise, so no text or detail survives.
OBJECT_BLOCKS = 4
#: The haze: each cover's colour is this share of the way from its region's mean to a light grey (frosted glass).
HAZE, HAZE_LEVEL = 0.2, 225.0


def _frosted(
    out: NDArray[np.int16],
    region: BoolMask,
    *,
    at: tuple[slice, slice],
    grid: tuple[int, int, int] | None,
    item_id: str,
) -> None:
    """Paint one cover's grain: a fixed grey value per cell on its grid (the item's locked grid, else one anchored at
    the box). The colour under it is set per covered blob in :func:`apply`."""
    if region.size == 0 or not bool(region.any()):
        return
    ys, xs = at
    x_lo, x_hi, y_lo, y_hi = int(xs.start), int(xs.stop), int(ys.start), int(ys.stop)
    if grid is None:
        cell = max(2, -(-min(x_hi - x_lo, y_hi - y_lo) // OBJECT_BLOCKS))
        grid = (x_lo, y_lo, cell)
    gx, gy, cell = grid
    col0, col1 = (x_lo - gx) // cell, (x_hi - 1 - gx) // cell
    row0, row1 = (y_lo - gy) // cell, (y_hi - 1 - gy) // cell
    cols = np.arange(col0, col1 + 1, dtype=np.int64)
    rows = np.arange(row0, row1 + 1, dtype=np.int64)
    grain = _cell_noise(item_id, rows, cols)[:, :, 0].astype(np.int16)  # one grey value per cell: grain, not colour
    yy = (np.arange(y_lo, y_hi, dtype=np.int64) - gy) // cell - row0
    xx = (np.arange(x_lo, x_hi, dtype=np.int64) - gx) // cell - col0
    view = out[ys, xs]
    view[region] = grain[yy[:, None], xx[None, :]][region]


def apply(frame: Frame, entries: list[PlanEntry], fills: list[CrowdFill]) -> Frame:
    """The redacted copy of a BGR ``frame``: every cover frosted (owner, 2026-11-04). Each connected blob of covers
    takes the source's average colour over the whole blob (overlapping covers share one colour: no seam inside a
    blob traces what is under it; a cell's own average would keep a face's light and dark), lifted slightly toward a
    light haze, plus a fixed grey grain per cell; then the covered pixels are replaced by a strong blur of those
    cells alone, with the edge feathered outward. Nothing inside a cover keeps any of its source's detail."""
    height, width = frame.shape[:2]
    if not entries and not fills:
        return frame.copy()
    grain = np.zeros((height, width), dtype=np.int16)
    covered = np.zeros((height, width), dtype=np.bool_)
    kept = np.zeros((height, width), dtype=np.bool_)  # kept faces: not even the feathered edge reaches them
    for entry in entries:
        for x1, y1, x2, y2 in entry.keep_clear:
            kept[max(0, y1) : max(0, y2), max(0, x1) : max(0, x2)] = True
        ys, xs, region = region_mask(entry, height, width)
        grid = entry.grid if entry.style == "pixelate" else None
        _frosted(grain, region, at=(ys, xs), grid=grid, item_id=entry.item_id)
        covered[ys, xs] |= region
    for n, fill in enumerate(fills):
        ys, xs = slice(fill.box[1], fill.box[3]), slice(fill.box[0], fill.box[2])
        region = np.ones((max(0, fill.box[3] - fill.box[1]), max(0, fill.box[2] - fill.box[0])), dtype=np.bool_)
        _frosted(grain, region, at=(ys, xs), grid=None, item_id=f"crowd_{n}")
        covered[ys, xs] = True
    if not covered.any():
        return frame.copy()
    count, found = cv2.connectedComponents(covered.astype(np.uint8), connectivity=8)
    labels = np.asarray(found, dtype=np.int64)
    flat: NDArray[np.int64] = labels.ravel()
    sizes = np.bincount(flat, minlength=int(count)).astype(np.float64)
    channels = frame.reshape(-1, 3).astype(np.float64)
    sums = np.stack([np.bincount(flat, weights=channels[:, ch], minlength=int(count)) for ch in range(3)], axis=1)
    means = sums / np.maximum(sizes, 1.0)[:, None]
    base = (1 - HAZE) * means + HAZE * HAZE_LEVEL
    out = np.clip(np.rint(base[labels]) + grain[:, :, None], 0, 255).astype(np.uint8)
    out = np.where(covered[:, :, None], out, frame)
    # A normalised blur of the cells alone: no source pixel from around a cover bleeds into it.
    cells = np.where(covered[:, :, None], out, 0).astype(np.float32)
    inside = covered.astype(np.float32)
    frost = (
        cv2.GaussianBlur(cells, (0, 0), FROST_SIGMA)
        / np.maximum(cv2.GaussianBlur(inside, (0, 0), FROST_SIGMA), 1e-6)[:, :, None]
    )
    weight = cv2.GaussianBlur(inside, (0, 0), FEATHER_SIGMA)
    ring_colour = cv2.GaussianBlur(cells, (0, 0), FEATHER_SIGMA) / np.maximum(weight, 1e-6)[:, :, None]
    a = np.where(kept & ~covered, 0.0, np.clip(weight, 0.0, 1.0))[:, :, None]
    source = frame.astype(np.float32)
    result = np.where(covered[:, :, None], frost, source * (1 - a) + ring_colour * a)
    return np.clip(np.rint(result), 0, 255).astype(np.uint8)
