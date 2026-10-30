"""Point → track binding (DESIGN §2.4, WP3 step 1).

A model sometimes names a thing by a point instead of a Set-of-Mark number (the miss loop's ``missed[].point``,
``role-pass.md`` "Points"). Binding maps each point to a SAM track, or to nothing:

1. On one frame, a point inside a track's mask dilated by 10 % (5 % of the box's larger side each way) binds to
   it. Inside several dilated masks, the one whose own mask holds the point wins; still ambiguous, no vote.
2. With no mask hit, the nearest track box within 0.1 x the frame diagonal binds; an equal-distance tie, no vote.
3. Across keyframes, each key (one thing the model pointed at, seen on several frames) collects votes per track.
   Conflicts between keys are settled by a Hungarian assignment that maximises total votes. A key binds only to
   its own strict favourite: an equal-vote rival, a favourite taken by another key, or no vote at all binds it to
   nothing (``unsure``).

Binding to nothing is the safe answer: an unbound miss gets its own SAM sweep or static box, hidden by default.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from safecut.contracts import Track
from safecut.decide.geometry import BoolMask, assign, box_at, decode, point_box_distance

#: DESIGN §2.4: the mask is dilated by 10 % (read as 10 % of its size in total, half of it each way).
MASK_DILATION = 0.10
#: DESIGN §2.4: the nearest box counts only within this share of the frame diagonal.
NEAREST_SHARE = 0.10


@dataclass(frozen=True)
class Sighting:
    """One model point: ``key`` names the thing pointed at (one key may be seen on several keyframes)."""

    key: str
    frame: int
    x: int
    y: int


def _near_mask(mask: BoolMask, x: int, y: int, radius: int) -> bool:
    """Whether any foreground pixel of ``mask`` lies within ``radius`` of ``(x, y)`` (a disk dilation)."""
    height, width = mask.shape
    x1, x2 = max(0, x - radius), min(width, x + radius + 1)
    y1, y2 = max(0, y - radius), min(height, y + radius + 1)
    window = mask[y1:y2, x1:x2]
    if not bool(window.any()):
        return False
    ys, xs = np.nonzero(window)
    d2 = (xs + x1 - x) ** 2 + (ys + y1 - y) ** 2
    return bool((d2 <= radius * radius).any())


def match_point(x: int, y: int, frame: int, tracks: Iterable[Track], *, width: int, height: int) -> str | None:
    """The track a point on ``frame`` names, or None (no candidate, or an ambiguous one)."""
    present = [t for t in tracks if t.first <= frame <= t.last]
    in_dilated: list[tuple[str, bool]] = []
    for track in present:
        rle = track.masks.get(frame)
        box = box_at(track, frame)
        if rle is None or box is None:
            continue
        mask = decode(rle)
        radius = math.ceil(MASK_DILATION / 2 * max(box[2] - box[0], box[3] - box[1]))
        if _near_mask(mask, x, y, radius):
            inside = 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and bool(mask[y, x])
            in_dilated.append((track.track_id, inside))
    if len(in_dilated) == 1:
        return in_dilated[0][0]
    if in_dilated:
        exact = [track_id for track_id, inside in in_dilated if inside]
        return exact[0] if len(exact) == 1 else None
    limit = NEAREST_SHARE * math.hypot(width, height)
    distances = sorted(
        (point_box_distance(x, y, box), track.track_id)
        for track in present
        if (box := box_at(track, frame)) is not None
    )
    if not distances or distances[0][0] > limit:
        return None
    if len(distances) > 1 and distances[1][0] == distances[0][0]:
        return None
    return distances[0][1]


def bind(sightings: Sequence[Sighting], tracks: Sequence[Track], *, width: int, height: int) -> dict[str, str | None]:
    """Bind every key to one track by votes across its keyframes; ties and conflicts lost → None."""
    keys = sorted({s.key for s in sightings})
    votes: dict[str, Counter[str]] = {key: Counter() for key in keys}
    for s in sightings:
        track_id = match_point(s.x, s.y, s.frame, tracks, width=width, height=height)
        if track_id is not None:
            votes[s.key][track_id] += 1
    result: dict[str, str | None] = dict.fromkeys(keys)
    candidates = sorted({t for counter in votes.values() for t in counter})
    if not candidates:
        return result
    score = np.array([[votes[k][t] for t in candidates] for k in keys], dtype=np.float64)
    for row, col in assign(score):
        key, track_id = keys[row], candidates[col]
        got = votes[key][track_id]
        # Only the key's own clear favourite binds: a key that lost its favourite to another key, or whose favourite
        # ties, binds to nothing rather than to a runner-up (a wrong bind would drop a real miss).
        if got > 0 and all(n < got for t, n in votes[key].items() if t != track_id):
            result[key] = track_id
    return result
