"""Box and mask helpers shared by decide, guard, render and audit.

Boxes are half-open ``(x1, y1, x2, y2)`` ints in prepared-clip pixels (ARCHITECTURE §3). Masks are frame-sized
COCO compressed RLE (``contracts.Rle``), column-major; they are decoded and encoded here with numpy, so no stage
depends on pycocotools' untyped C extension.
"""

from __future__ import annotations

import bisect
import importlib
import math
from collections.abc import Callable
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from safecut.contracts import Rle, Track

BoxT = tuple[int, int, int, int]
BoolMask = NDArray[np.bool_]


_LinearSumAssignment = Callable[..., tuple[NDArray[np.intp], NDArray[np.intp]]]
# scipy ships no type information; the one function used is typed here (scipy.optimize.linear_sum_assignment).
_lsa = cast(_LinearSumAssignment, importlib.import_module("scipy.optimize").linear_sum_assignment)


def assign(score: NDArray[np.float64]) -> list[tuple[int, int]]:
    """The Hungarian assignment (rows to columns) that maximises the total ``score``."""
    rows, cols = _lsa(score, maximize=True)
    return list(zip((int(r) for r in rows), (int(c) for c in cols), strict=True))


def area(box: BoxT) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection(a: BoxT, b: BoxT) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a: BoxT, b: BoxT) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union else 0.0


def contains(outer: BoxT, inner: BoxT) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def union(boxes: list[BoxT]) -> BoxT:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def clamp(box: tuple[float, float, float, float], width: int, height: int) -> BoxT | None:
    """Round outward to ints and clip to the frame; None when nothing of the box is left inside it."""
    x1, y1 = max(0, math.floor(box[0])), max(0, math.floor(box[1]))
    x2, y2 = min(width, math.ceil(box[2])), min(height, math.ceil(box[3]))
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def grow(box: BoxT, ratio: float, px: int, width: int, height: int) -> BoxT:
    """``box`` grown by ``ratio`` of its width (height) on each side plus ``px``, clamped to the frame.

    This is the guard's reading of DESIGN §2.6's "faces 15 % + 8 px": the full ratio per side, which contains the
    contract checker's minimum reading (half the ratio per side) and matches the web app's overlay padding."""
    dx = math.ceil(ratio * (box[2] - box[0])) + px
    dy = math.ceil(ratio * (box[3] - box[1])) + px
    grown = clamp((box[0] - dx, box[1] - dy, box[2] + dx, box[3] + dy), width, height)
    if grown is None:  # a valid box inside the frame always keeps itself
        raise ValueError(f"box {list(box)} lies outside the {width}x{height} frame")
    return grown


def point_box_distance(x: float, y: float, box: BoxT) -> float:
    """Euclidean distance from a pixel centre to a half-open box (0 inside it)."""
    dx = max(box[0] - x, 0.0, x - (box[2] - 1))
    dy = max(box[1] - y, 0.0, y - (box[3] - 1))
    return math.hypot(dx, dy)


def box_at(track: Track, frame: int) -> BoxT | None:
    """The track's box on ``frame``: its own, linearly interpolated between the neighbouring anchors inside its
    span, or None outside ``first..last``."""
    if frame in track.boxes:
        return track.boxes[frame]
    if not track.first <= frame <= track.last:
        return None
    keys = sorted(track.boxes)
    i = bisect.bisect_left(keys, frame)
    before, after = keys[i - 1], keys[i]  # first and last are anchors (contract), so both exist
    a, b = track.boxes[before], track.boxes[after]
    w = (frame - before) / (after - before)
    x1, y1, x2, y2 = (a[k] + (b[k] - a[k]) * w for k in range(4))
    return (round(x1), round(y1), max(round(x2), round(x1) + 1), max(round(y2), round(y1) + 1))


# ---------------------------------------------------------------------------------------------------- masks


def decode(rle: Rle) -> BoolMask:
    """A COCO RLE mask as an ``(H, W)`` bool array."""
    height, width = rle.size
    runs = rle.runs()
    values = np.zeros(runs.size, dtype=np.bool_)
    values[1::2] = True
    flat = np.repeat(values, runs)
    return flat.reshape(width, height).T


def decode_crop(rle: Rle) -> tuple[BoolMask, int, int] | None:
    """A COCO RLE mask as its foreground's crop and the crop's top-left ``(x, y)``, or None when it is empty; only
    the foreground's columns are ever laid out as a 2-D array."""
    height = rle.size[0]
    runs = rle.runs()
    ends = np.cumsum(runs)
    fg = np.flatnonzero(runs[1::2]) * 2 + 1  # non-empty foreground runs
    if fg.size == 0:
        return None
    start, stop = int(ends[fg[0]] - runs[fg[0]]), int(ends[fg[-1]])
    c1, c2 = start // height, (stop - 1) // height + 1
    values = np.zeros(runs.size, dtype=np.bool_)
    values[1::2] = True
    cols = np.repeat(values, runs)[c1 * height : c2 * height].reshape(c2 - c1, height).T
    rows = np.flatnonzero(cols.any(axis=1))
    y1, y2 = int(rows[0]), int(rows[-1]) + 1
    return cols[y1:y2], c1, y1


def encode(mask: BoolMask) -> Rle:
    """An ``(H, W)`` bool array as a COCO compressed RLE (``rleToString``)."""
    height, width = mask.shape
    cols = np.flatnonzero(mask.any(axis=0))
    if cols.size == 0:
        return encode_crop(np.zeros((0, 0), dtype=np.bool_), 0, 0, height=height, width=width)
    c1, c2 = int(cols[0]), int(cols[-1]) + 1
    return encode_crop(mask[:, c1:c2], c1, 0, height=height, width=width)


def encode_crop(crop: BoolMask, x: int, y: int, *, height: int, width: int) -> Rle:
    """A frame-sized COCO RLE of ``crop`` placed at ``(x, y)`` (inside the frame), everything else background.

    Only the crop's columns are walked, so a mask costs its own area, not the frame's. The result is built without
    re-validating it: this encoder's output is round-trip property-tested, and the guard writes thousands of masks
    per clip (every later reader of ``plan.json`` validates them on load)."""
    ch, cw = crop.shape
    if not ch or not cw or not bool(crop.any()):
        runs = [height * width]
    else:
        block = np.zeros((cw, height), dtype=np.bool_)
        block[:, y : y + ch] = crop.T
        flat = block.reshape(-1)
        change = np.flatnonzero(flat[1:] != flat[:-1]) + 1
        runs = np.diff(np.concatenate(([0], change, [flat.size]))).tolist()
        lead, tail = x * height, (width - x - cw) * height
        if flat[0]:
            runs = [lead, *runs]  # COCO runs start with background
        else:
            runs[0] += lead
        if flat[-1]:
            if tail:
                runs.append(tail)
        else:
            runs[-1] += tail
    return Rle.model_construct(size=(height, width), counts=_counts(np.asarray(runs, dtype=np.int64)))


#: Enough 5-bit chunks for any run count of a frame up to 8192 x 8192 (and its difference to the run two back).
_CHUNKS = 8


def _counts(runs: NDArray[np.int64]) -> str:
    """COCO's ``rleToString`` for every run at once: each run (minus the run two back, from the fourth on) as
    little-endian 5-bit chunks, bit 0x20 marking "more follows", offset by 48."""
    values = runs.copy()
    values[3:] -= runs[1:-2]
    chars = np.zeros((values.size, _CHUNKS), dtype=np.uint8)
    valid = np.zeros((values.size, _CHUNKS), dtype=np.bool_)
    active = np.ones(values.size, dtype=np.bool_)
    for k in range(_CHUNKS):
        c = values & 0x1F
        values = values >> 5  # arithmetic: a negative difference ends at -1
        negative = (c & 0x10) != 0
        more = (negative & (values != -1)) | (~negative & (values != 0))
        chars[:, k] = (c + 0x20 * more + 48).astype(np.uint8)
        valid[:, k] = active
        active = active & more
    return chars[valid].tobytes().decode("ascii")


def mask_bbox(mask: BoolMask) -> BoxT | None:
    """The half-open bounding box of a mask's foreground, or None when it is empty."""
    cols = np.flatnonzero(mask.any(axis=0))
    if cols.size == 0:
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def dilate(mask: BoolMask, rx: int, ry: int) -> BoolMask:
    """Grow a mask by ``rx`` x ``ry`` pixels each way (work done on the foreground's crop only).

    The kernel is a rectangle: it contains the ``rx`` x ``ry`` ellipse, so the result is a superset of the elliptical
    dilation (the guard pads outward, never inward), and OpenCV runs rectangular dilation in near-constant time per
    pixel, whatever the radius (an elliptical kernel the size of a person's padding costs milliseconds a frame)."""
    box = mask_bbox(mask)
    if box is None or (rx <= 0 and ry <= 0):
        return mask.copy()
    height, width = mask.shape
    x1, y1 = max(0, box[0] - rx), max(0, box[1] - ry)
    x2, y2 = min(width, box[2] + rx), min(height, box[3] + ry)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * max(0, rx) + 1, 2 * max(0, ry) + 1))
    grown = cv2.dilate(mask[y1:y2, x1:x2].astype(np.uint8), kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0)
    out = np.zeros_like(mask)
    out[y1:y2, x1:x2] = grown.astype(np.bool_)
    return out | mask


__all__ = [
    "BoolMask",
    "BoxT",
    "area",
    "assign",
    "box_at",
    "clamp",
    "contains",
    "decode",
    "decode_crop",
    "dilate",
    "encode",
    "encode_crop",
    "grow",
    "intersection",
    "iou",
    "mask_bbox",
    "point_box_distance",
    "union",
]
