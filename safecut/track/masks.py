"""SAM's box-sized masks → frame-sized COCO compressed RLE (PRE-A §1.5, §12: placed at the box origin)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import numpy as np
from meta_sam_parser import SegmentationMask, decode_mask_to_raster
from meta_sam_parser._mask_codec import (  # pyright: ignore[reportPrivateUsage] -- the decoder without a re-check
    _decode_raster,  # pyright: ignore[reportPrivateUsage] -- see above; the payload was validated while parsing
)
from numpy.typing import NDArray

from safecut.contracts import Rle
from safecut.meta import parallel
from safecut.meta.sam import Detection


def raster(mask: SegmentationMask) -> NDArray[np.uint8]:
    """The mask's ``height × width`` raster (1 = object)."""
    flat = np.frombuffer(decode_mask_to_raster(mask), dtype=np.uint8)
    return flat.reshape(mask.height, mask.width)


def place(local: NDArray[np.uint8], left: int, top: int, height: int, width: int) -> NDArray[np.uint8]:
    """A ``height × width`` frame with ``local`` placed at ``(left, top)``, clipped to the frame."""
    frame = np.zeros((height, width), dtype=np.uint8)
    y0, x0 = max(top, 0), max(left, 0)
    y1, x1 = min(top + local.shape[0], height), min(left + local.shape[1], width)
    if y1 > y0 and x1 > x0:
        frame[y0:y1, x0:x1] = local[y0 - top : y1 - top, x0 - left : x1 - left]
    return frame


def runs(frame: NDArray[np.uint8]) -> list[int]:
    """Column-major (COCO) run lengths, starting with a run of background."""
    flat = frame.ravel(order="F").astype(np.int8)
    edges = np.flatnonzero(np.diff(flat)) + 1
    bounds = np.concatenate(([0], edges, [flat.size]))
    lengths = np.diff(bounds).tolist()
    return [0, *lengths] if flat.size and flat[0] == 1 else lengths


def counts_string(lengths: list[int]) -> str:
    """cocoapi ``rleToString``: 5-bit groups, low first; from the third run on, a delta on the run two back."""
    out: list[str] = []
    for i, value in enumerate(lengths):
        x = value - lengths[i - 2] if i > 2 else value
        more = True
        while more:
            c = x & 0x1F
            x >>= 5
            more = x != -1 if c & 0x10 else x != 0
            if more:
                c |= 0x20
            out.append(chr(c + 48))
    return "".join(out)


def frame_rle(mask: SegmentationMask, box: tuple[int, int, int, int], height: int, width: int) -> Rle | None:
    """The SAM mask placed at its box origin as a frame-sized RLE; ``None`` when it has no pixel in the frame."""
    frame = place(raster(mask), box[0], box[1], height, width)
    if not frame.any():
        return None
    return Rle(size=(height, width), counts=counts_string(runs(frame)))


#: Decoded mask pixels per SAM request. Meta's decoder is pure Python (≈ 1 µs a pixel), so a busy 60 s clip could
#: spend minutes here; past this budget masks are kept on every n-th anchor of each object (boxes stay on every
#: frame, so hiding never depends on a mask; masks only tighten whole-person renders).
MASK_PIXEL_BUDGET = 24_000_000


#: Below this many pixels to decode, a pool costs more than it saves.
PARALLEL_PIXELS = 1_500_000


def _decode(mask: SegmentationMask) -> bytes:
    """A raster for a mask Meta's parser has already decoded and checked as canonical while parsing the stream, so
    it isn't checked a second time (that would double the cost); a lossless mask goes through the public API."""
    if mask.encoding == "one_bit":
        return _decode_raster(mask.payload, mask.width, mask.height)
    return decode_mask_to_raster(mask)


def stride(sizes: Mapping[tuple[int, str], int], budget: int = MASK_PIXEL_BUDGET) -> int:
    """Keep every ``stride``-th anchor's mask so the decoded pixels fit ``budget`` (≥ 1)."""
    total = sum(sizes.values())
    return max(1, -(-total // budget)) if budget > 0 else 1


def mask_table(
    detections: Sequence[Detection], height: int, width: int, *, budget: int = MASK_PIXEL_BUDGET
) -> dict[tuple[int, str], Rle]:
    """Frame-sized RLEs for the detections whose masks are kept, keyed by ``(proxy frame, object id)``.

    Identical payloads decode once; many decode in a process pool. Each object keeps its first and last anchor's
    mask and every ``stride``-th between.
    """
    with_mask = [d for d in detections if d.mask is not None]
    sizes = {(d.frame, d.object_id): cast(SegmentationMask, d.mask).width * cast(SegmentationMask, d.mask).height
             for d in with_mask}  # fmt: skip
    step = stride(sizes, budget)
    by_object: dict[str, list[Detection]] = {}
    for d in sorted(with_mask, key=lambda d: d.frame):
        by_object.setdefault(d.object_id, []).append(d)
    keep = [d for ds in by_object.values() for i, d in enumerate(ds) if i % step == 0 or i == len(ds) - 1]
    unique: dict[tuple[str, int, int], SegmentationMask] = {}
    for d in keep:
        m = cast(SegmentationMask, d.mask)
        unique.setdefault((m.payload, m.width, m.height), m)
    masks = list(unique.values())
    rasters = parallel.map_in_pool(_decode, masks, parallel=sum(m.width * m.height for m in masks) >= PARALLEL_PIXELS)
    decoded = dict(zip(unique, rasters, strict=True))
    out: dict[tuple[int, str], Rle] = {}
    for d in keep:
        m = cast(SegmentationMask, d.mask)
        local = np.frombuffer(decoded[(m.payload, m.width, m.height)], dtype=np.uint8).reshape(m.height, m.width)
        frame = place(local, d.box[0], d.box[1], height, width)
        if frame.any():
            out[(d.frame, d.object_id)] = Rle(size=(height, width), counts=counts_string(runs(frame)))
    return out
