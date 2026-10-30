"""Where one hidden track is drawn on one frame (DESIGN §2.6), as a padded box or a padded mask.

Every region is padded outward by the kind's spatial padding: faces 15 % of the box's size on each side plus 8 px,
everything else 8 % plus 8 px. Outside the frames SAM saw the object, the guard holds a box:

* **anchors** (a box from SAM): the padded box, or the padded SAM mask when one exists;
* **between anchors**, within SAM's own sampling step: the interpolated box, or both neighbouring masks shifted to
  it (API-NOTES §12), padded;
* **gaps** (SAM lost the object between anchors): the last box held and grown 2 % a frame, joined with the
  interpolated box, so a box that moved during the gap is still covered;
* **back-fill** (``backfill`` frames before the first detection, SAM's late confirmation) and **extend** (8 frames
  after the last): the edge box held, grown 2 % a frame, and swept along the track's own motion at its edge (an
  object SAM confirmed late was usually already moving the same way).

A mask region must still span its track box the way the contract checks it (80 % of its width and height, a
quarter of its area); a mask that doesn't (an empty or sliver SAM mask, PRE-A §2.6) falls back to the box.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from safecut.contracts import Rle, Track
from safecut.decide.geometry import BoolMask, BoxT, box_at, clamp, decode, dilate, encode_crop, grow, mask_bbox, union

#: DESIGN §2.6: a held box grows 2 % of its size per frame on each side...
GROW_PER_FRAME = 0.02
#: ...up to its own size again on each side, so a long hold stays a region, not the whole frame.
MAX_GROWTH = 1.0
#: The fastest edge motion the sweep follows, as a share of the box's size per frame (noise beyond it is capped).
MAX_SPEED = 0.25
#: How far inward the edge velocity is measured (frames).
VELOCITY_SPAN = 8


@dataclass(frozen=True)
class Region:
    box: BoxT
    mask: Rle | None = None


def ratio_for(concept: str, face: float, default: float) -> float:
    return face if concept == "face" else default


def _expand(box: BoxT, share: float, width: int, height: int) -> BoxT:
    dx, dy = share * (box[2] - box[0]), share * (box[3] - box[1])
    out = clamp((box[0] - dx, box[1] - dy, box[2] + dx, box[3] + dy), width, height)
    return out if out is not None else box


def edge_velocity(track: Track, at_start: bool) -> tuple[float, float]:
    """The track's (dx, dy) per frame at its first (or last) anchor, measured over up to 8 frames inward and capped
    at a quarter of the box's size per frame."""
    keys = sorted(track.boxes)
    edge = keys[0] if at_start else keys[-1]
    target = edge + VELOCITY_SPAN if at_start else edge - VELOCITY_SPAN
    inward = [k for k in keys if k != edge and (k <= target if at_start else k >= target)]
    if not inward:
        inward = [k for k in keys if k != edge]
    if not inward:
        return 0.0, 0.0
    other = inward[-1] if at_start else inward[0]
    a, b = track.boxes[edge], track.boxes[other]
    span = other - edge
    cx = ((b[0] + b[2]) - (a[0] + a[2])) / 2 / span
    cy = ((b[1] + b[3]) - (a[1] + a[3])) / 2 / span
    w, h = a[2] - a[0], a[3] - a[1]
    return max(-MAX_SPEED * w, min(MAX_SPEED * w, cx)), max(-MAX_SPEED * h, min(MAX_SPEED * h, cy))


def held_box(edge: BoxT, distance: int, velocity: tuple[float, float], width: int, height: int) -> BoxT:
    """The edge box swept ``distance`` frames along ``velocity`` (signed: back in time for back-fill), joined with
    itself and grown 2 % a frame (capped)."""
    dx, dy = velocity[0] * distance, velocity[1] * distance
    moved = clamp((edge[0] + dx, edge[1] + dy, edge[2] + dx, edge[3] + dy), width, height)
    swept = union([edge, moved]) if moved is not None else edge
    return _expand(swept, min(GROW_PER_FRAME * distance, MAX_GROWTH), width, height)


def mask_ok(mask: BoolMask, box: BoxT) -> bool:
    """The contract's span test (``_mask_spans``): inside ``box`` the foreground spans 80 % of its width and height
    and fills a quarter of its area."""
    crop = mask[box[1] : box[3], box[0] : box[2]]
    extent = mask_bbox(crop)
    if extent is None:
        return False
    w, h = box[2] - box[0], box[3] - box[1]
    spans = extent[2] - extent[0] >= 0.8 * w and extent[3] - extent[1] >= 0.8 * h
    return spans and int(crop.sum()) >= 0.8 * 0.3125 * w * h


@dataclass(frozen=True)
class Patch:
    """A mask as its foreground's crop and the crop's top-left in frame pixels: moving it is free, and every step
    works on the object's own area, never the whole frame."""

    crop: BoolMask
    x: int
    y: int

    @classmethod
    def of(cls, mask: BoolMask) -> Patch | None:
        bbox = mask_bbox(mask)
        if bbox is None:
            return None
        return cls(mask[bbox[1] : bbox[3], bbox[0] : bbox[2]], bbox[0], bbox[1])

    def moved(self, dx: int, dy: int) -> Patch:
        return Patch(self.crop, self.x + dx, self.y + dy)

    @property
    def box(self) -> BoxT:
        return (self.x, self.y, self.x + self.crop.shape[1], self.y + self.crop.shape[0])

    def window(self, box: BoxT) -> BoolMask:
        """The patch's foreground inside ``box``, as a ``box``-sized array."""
        out = np.zeros((box[3] - box[1], box[2] - box[0]), dtype=np.bool_)
        x1, y1 = max(box[0], self.x), max(box[1], self.y)
        x2, y2 = min(box[2], self.box[2]), min(box[3], self.box[3])
        if x2 > x1 and y2 > y1:
            source = self.crop[y1 - self.y : y2 - self.y, x1 - self.x : x2 - self.x]
            out[y1 - box[1] : y2 - box[1], x1 - box[0] : x2 - box[0]] = source
        return out


def join(patches: list[Patch]) -> Patch:
    canvas = union([p.box for p in patches])
    return Patch(np.logical_or.reduce([p.window(canvas) for p in patches]), canvas[0], canvas[1])


class TrackRegions:
    """Regions for one track, frame by frame (masks decoded once per anchor)."""

    def __init__(self, track: Track, *, ratio: float, px: int, width: int, height: int, interp_gap: int) -> None:
        self.track = track
        self.ratio, self.px = ratio, px
        self.width, self.height = width, height
        self.interp_gap = interp_gap
        self.keys = sorted(track.boxes)
        self.mask_keys = sorted(track.masks)
        self.start_v = edge_velocity(track, at_start=True)
        self.end_v = edge_velocity(track, at_start=False)
        self._decoded = lru_cache(maxsize=8)(self._decode)

    def _decode(self, frame: int) -> Patch | None:
        return Patch.of(decode(self.track.masks[frame]))

    def _pad(self, box: BoxT) -> BoxT:
        return grow(box, self.ratio, self.px, self.width, self.height)

    def _padded_mask(self, patch: Patch | None, box: BoxT) -> Region | None:
        # The span test runs on SAM's own (or the shifted) mask, before padding: dilation would grow a stray pixel
        # in a small box into a disk that "spans" it while most of the object stays bare.
        if patch is None or not mask_ok(patch.window(box), (0, 0, box[2] - box[0], box[3] - box[1])):
            return None
        rx = math.ceil(self.ratio * (box[2] - box[0])) + self.px
        ry = math.ceil(self.ratio * (box[3] - box[1])) + self.px
        canvas = np.zeros((patch.crop.shape[0] + 2 * ry, patch.crop.shape[1] + 2 * rx), dtype=np.bool_)
        canvas[ry : ry + patch.crop.shape[0], rx : rx + patch.crop.shape[1]] = patch.crop
        grown = Patch(dilate(canvas, rx, ry), patch.x - rx, patch.y - ry)
        frame = (0, 0, self.width, self.height)
        clipped = Patch.of(grown.window(frame))
        if clipped is None:
            return None
        return Region(box=clipped.box, mask=encode_crop(clipped.crop, clipped.x, clipped.y, height=self.height,
                                                        width=self.width))  # fmt: skip

    def _shifted_mask(self, frame: int, box: BoxT) -> Patch | None:
        """The neighbouring anchors' masks, each moved to ``box`` (API-NOTES §12), joined."""
        i = bisect.bisect_left(self.mask_keys, frame)
        near = [k for k in self.mask_keys[max(0, i - 1) : i + 1] if abs(k - frame) <= self.interp_gap]
        moved: list[Patch] = []
        for k in near:
            anchor, patch = self.track.boxes.get(k), self._decoded(k)
            if anchor is not None and patch is not None:
                moved.append(patch.moved(box[0] - anchor[0], box[1] - anchor[1]))
        return join(moved) if moved else None

    def at(self, frame: int) -> Region:
        """The region on ``frame`` (which the caller keeps inside ``first - backfill … last + extend``)."""
        t = self.track
        if frame < t.first:
            box = held_box(t.boxes[t.first], t.first - frame, (-self.start_v[0], -self.start_v[1]), self.width,
                           self.height)  # fmt: skip
            return Region(self._pad(box))
        if frame > t.last:
            box = held_box(t.boxes[t.last], frame - t.last, self.end_v, self.width, self.height)
            return Region(self._pad(box))
        box = t.boxes.get(frame)
        if box is not None:
            if frame in t.masks:
                region = self._padded_mask(self._decoded(frame), box)
                if region is not None:
                    return region
            elif self.mask_keys:
                shifted = self._shifted_mask(frame, box)
                region = self._padded_mask(shifted, box) if shifted is not None else None
                if region is not None:
                    return region
            return Region(self._pad(box))
        i = bisect.bisect_left(self.keys, frame)
        before, after = self.keys[i - 1], self.keys[i]
        interpolated = box_at(t, frame) or t.boxes[before]  # inside first..last, so never the fallback
        if after - before - 1 <= self.interp_gap:
            if self.mask_keys:
                shifted = self._shifted_mask(frame, interpolated)
                region = self._padded_mask(shifted, interpolated) if shifted is not None else None
                if region is not None:
                    return region
            return Region(self._pad(interpolated))
        held = held_box(t.boxes[before], frame - before, (0.0, 0.0), self.width, self.height)
        return Region(self._pad(union([held, interpolated])))
