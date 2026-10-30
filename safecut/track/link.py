"""SAM detections → ``tracks.json`` tracks (WP1 step 4–5; PRE-A §5b, §12). Pure: no I/O, no clock.

- Detections are on **proxy** frames; anchor ``j`` lands on prepared frame ``from_proxy(j)``.
- An object's detections split wherever more than ``gap_merge_frames`` proxy frames are missing (counted on the
  proxy, before densify). Each piece after the first is a **new** track whose ``reentry_of`` names the piece
  before it: a hint only, it starts hidden like any other (DESIGN §2.5).
- Between two anchors every prepared frame gets a box interpolated linearly and rounded outward (fail closed).
- Track IDs are ``<concept>:<n>`` with ``n`` the next free integer for that concept across the whole job.
- A proxy frame where one request reached SAM's 16-object cap marks its whole prepared span crowded (T11).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from safecut.contracts import Rle, SamObject, Track
from safecut.meta.sam import Detection
from safecut.track.axes import crowded_span

#: The most proxy frames an object may go missing and still be the same track (WP1 step 4).
GAP_MERGE_FRAMES = 2
#: SAM returns at most this many objects per frame for one request (PRE-A §1.6).
SAM_OBJECT_CAP = 16

Box = tuple[int, int, int, int]
MaskFn = Callable[[Detection], Rle | None]


@dataclass(frozen=True)
class ObjectLabel:
    """What a SAM object is: its concept (the track-ID prefix), the phrase that found it, and the child flag."""

    concept: str
    prompt: str
    child_phrase: bool = False


@dataclass(frozen=True)
class Frame:
    """The prepared clip's geometry and the proxy → prepared frame table."""

    width: int
    height: int
    frames: int
    from_proxy: Sequence[int]


def split_on_gaps(frames: Sequence[int], gap: int = GAP_MERGE_FRAMES) -> list[list[int]]:
    """Sorted proxy frames → runs whose consecutive frames miss at most ``gap`` frames between them."""
    pieces: list[list[int]] = []
    for j in sorted(set(frames)):
        if pieces and j - pieces[-1][-1] - 1 <= gap:
            pieces[-1].append(j)
        else:
            pieces.append([j])
    return pieces


def clamp_box(box: tuple[float, float, float, float], width: int, height: int) -> Box | None:
    """Round outward to whole pixels and clip to the frame; ``None`` if nothing of it is left."""
    x1 = max(0, math.floor(box[0]))
    y1 = max(0, math.floor(box[1]))
    x2 = min(width, math.ceil(box[2]))
    y2 = min(height, math.ceil(box[3]))
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def interpolate(a: Box, b: Box, t: float) -> tuple[float, float, float, float]:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
    )


def densify(anchors: Mapping[int, Box], width: int, height: int) -> dict[int, Box]:
    """A box on every prepared frame from the first anchor to the last: anchors as given, frames between two
    anchors interpolated linearly and rounded outward."""
    frames = sorted(anchors)
    boxes: dict[int, Box] = {}
    for fa, fb in pairwise(frames):
        a, b = anchors[fa], anchors[fb]
        for f in range(fa + 1, fb):
            box = clamp_box(interpolate(a, b, (f - fa) / (fb - fa)), width, height)
            if box is not None:
                boxes[f] = box
    for f in frames:
        boxes[f] = anchors[f]
    return dict(sorted(boxes.items()))


def next_ids(existing: Iterable[str]) -> dict[str, int]:
    """The next free number per concept, after every track ID already in the job."""
    taken: dict[str, int] = defaultdict(int)
    for track_id in existing:
        concept, _, number = track_id.rpartition(":")
        taken[concept] = max(taken[concept], int(number))
    return {concept: n + 1 for concept, n in taken.items()}


def link_request(
    detections: Sequence[Detection],
    *,
    request: int,
    labels: Callable[[str], ObjectLabel],
    geometry: Frame,
    source: str,
    numbering: dict[str, int],
    masks: MaskFn | None = None,
    gap: int = GAP_MERGE_FRAMES,
) -> list[Track]:
    """Every track one SAM request yields, numbered from ``numbering`` (updated in place).

    ``labels(object_id)`` names each SAM object (one phrase for a phrase request; per object for a batched object
    prompt). Tracks are numbered in order of their first frame, then SAM object id, so numbering is stable.
    """
    by_object: dict[str, dict[int, Detection]] = defaultdict(dict)
    for d in detections:
        if not 0 <= d.frame < len(geometry.from_proxy):
            continue  # a frame past the proxy can't be placed on the prepared clip
        by_object[d.object_id][d.frame] = d
    pieces: list[tuple[int, int, str, list[Detection]]] = []
    for object_id, frames in by_object.items():
        for run in split_on_gaps(list(frames), gap):
            pieces.append((geometry.from_proxy[run[0]], int(object_id), object_id, [frames[j] for j in run]))
    pieces.sort(key=lambda p: (p[0], p[1], p[3][0].frame))
    previous: dict[str, str] = {}
    tracks: list[Track] = []
    for _, _, object_id, run in pieces:
        label = labels(object_id)
        anchors: dict[int, Box] = {}
        rles: dict[int, Rle] = {}
        conf: dict[int, float] = {}
        for d in run:
            box = clamp_box(d.box, geometry.width, geometry.height)
            if box is None:
                continue
            f = geometry.from_proxy[d.frame]
            anchors[f] = box
            if d.confidence is not None:
                conf[f] = d.confidence
            if masks is not None and d.mask is not None:
                rle = masks(d)
                if rle is not None:
                    rles[f] = rle
        if not anchors:
            continue
        number = numbering.get(label.concept, 1)
        numbering[label.concept] = number + 1
        track_id = f"{label.concept}:{number}"
        tracks.append(
            Track(
                track_id=track_id,
                concept=label.concept,
                first=min(anchors),
                last=max(anchors),
                boxes=densify(anchors, geometry.width, geometry.height),
                masks=rles,
                reentry_of=previous.get(object_id),
                source=source,
                prompt=label.prompt,
                origin="sam",
                sam_object=SamObject(request=request, object_id=object_id),
                child_phrase=label.child_phrase,
                conf=conf,
            )
        )
        previous[object_id] = track_id
    return tracks


def crowded(detections: Sequence[Detection], geometry: Frame, cap: int = SAM_OBJECT_CAP) -> set[int]:
    """Prepared frames around every proxy frame where this request returned ``cap`` objects or more (T11)."""
    per_frame: dict[int, set[str]] = defaultdict(set)
    for d in detections:
        per_frame[d.frame].add(d.object_id)
    out: set[int] = set()
    for j, objects in per_frame.items():
        if len(objects) >= cap and 0 <= j < len(geometry.from_proxy):
            out.update(crowded_span(j, geometry.from_proxy, geometry.frames))
    return out
