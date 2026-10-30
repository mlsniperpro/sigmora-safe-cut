"""SAM's box-sized masks → frame-sized COCO compressed RLE (PRE-A §1.5, §12: placed at the box origin)."""

from __future__ import annotations

import numpy as np
from meta_sam_parser import SegmentationMask, decode_mask_to_raster
from numpy.typing import NDArray

from safecut.contracts import Rle


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
