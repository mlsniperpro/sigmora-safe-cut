"""The leak guard: decisions + tracks → ``plan.json`` (DESIGN §2.6, WP3 step 5, ARCHITECTURE §3.7).

Every hidden or ``needs_you`` item is planned on every frame of each of its tracks, widened in time by the
back-fill before the first detection (SAM confirms an object about 15 of its frames late: ``ceil(15 x fps /
sam_fps)`` prepared frames) and 8 frames after the last, and padded in space (``regions``). Crowded frames (a
concept at SAM's 16-object cap) get a crowd fill over every tracked object there. A pixelated item keeps one grid
for its whole life, anchored at its first face box with cells big enough that the face spans at most 6 blocks, so
the mosaic never shifts between frames. An item a model read through (a flagged leak's ``through_item``) renders
solid from then on, and every audit patch is rebuilt from its decision item, so no re-plan ever loses one.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from safecut.contracts import (
    CrowdFill,
    DecisionItem,
    Decisions,
    Job,
    Leak,
    Padding,
    Plan,
    PlanEntry,
    Style,
    Temporal,
    Track,
    Tracks,
)
from safecut.decide.geometry import BoxT, box_at, grow, union
from safecut.guard.regions import TrackRegions, ratio_for

#: DESIGN §2.6: faces 15 % + 8 px, everything else 8 % + 8 px.
PADDING = Padding(face=0.15, default=0.08, px=8)
#: DESIGN §2.6: extend 8 frames after the last detection.
EXTEND = 8
#: DESIGN §2.6: hold the last box through gaps up to 2 s.
GAP_HOLD_S = 2.0
#: SAM's hotstart: it confirms a new object about 15 of its own frames late (PRE-A §5b, T10).
HOTSTART_SAM_FRAMES = 15
#: DESIGN §2.7: a face spans at most 6 mosaic blocks.
MAX_BLOCKS = 6

Grid = tuple[int, int, int]


def backfill_frames(job: Job, tracks: Tracks) -> int:
    """``ceil(15 x job.fps / sam_fps)`` with ``sam_fps`` the effective proxy rate (ARCHITECTURE §3.7)."""
    return math.ceil(HOTSTART_SAM_FRAMES * job.fps / min(tracks.sam_fps, job.fps))


def locked_grid(item: DecisionItem, by_id: dict[str, Track], job: Job) -> Grid | None:
    """``[x0, y0, cell]`` for a pixelated item: origin at its earliest face's first padded box, cell from its widest
    face box (≤ 6 blocks across), fixed for the item's whole life (DESIGN §2.7)."""
    faces = [by_id[t] for t in item.track_ids if t in by_id and by_id[t].concept == "face"]
    if not faces:
        return None
    first = min(faces, key=lambda t: (t.first, t.track_id))
    x0, y0, _, _ = grow(first.boxes[first.first], PADDING.face, PADDING.px, job.width, job.height)
    widest = max(b[2] - b[0] for t in faces for b in t.boxes.values())
    return (x0, y0, max(2, math.ceil(widest / MAX_BLOCKS)))


def read_through(leaks: Iterable[Leak]) -> set[str]:
    """Items a model read through (redteam.md L7): a flagged leak that the audit didn't leave unresolved."""
    return {leak.through_item for leak in leaks if leak.through_item is not None and not leak.unresolved}


def _crowd_fills(tracks: Tracks, hidden: set[str], job: Job) -> list[CrowdFill]:
    """One fill per run of consecutive crowded frames, over every hidden track present there (padded)."""
    runs: list[list[int]] = []
    for frame in tracks.crowded_frames:
        if runs and frame == runs[-1][-1] + 1:
            runs[-1].append(frame)
        else:
            runs.append([frame])
    fills: list[CrowdFill] = []
    for run in runs:
        boxes: list[BoxT] = []
        for t in tracks.tracks:
            if t.track_id not in hidden:
                continue
            ratio = ratio_for(t.concept, PADDING.face, PADDING.default)
            for frame in run:
                box = box_at(t, frame)
                if box is not None:
                    boxes.append(grow(box, ratio, PADDING.px, job.width, job.height))
        fills.append(CrowdFill(frames=run, box=union(boxes) if boxes else (0, 0, job.width, job.height)))
    return fills


def _patch_entries(item: DecisionItem, job: Job) -> Iterable[tuple[int, PlanEntry]]:
    """An audit patch: its raw box padded by its kind's spatial padding over its own span, no temporal padding
    (API-NOTES §12)."""
    if item.box is None or item.first is None or item.last is None:
        return
    ratio = PADDING.face if item.kind == "person" else PADDING.default
    box = grow(item.box, ratio, PADDING.px, job.width, job.height)
    entry = PlanEntry(item_id=item.item_id, shape="box", box=box, mask=None, style="solid", grid=None,
                      source="audit_patch")  # fmt: skip
    for frame in range(item.first, min(job.frames, item.last + 1)):
        yield frame, entry


def plan(job: Job, tracks: Tracks, decisions: Decisions, *, solid: Iterable[str] = ()) -> Plan:
    """The plan for every hidden item; the items in ``solid`` (read through, :func:`read_through`) render solid."""
    backfill = backfill_frames(job, tracks)
    # Within SAM's own sampling step a missing box is interpolation, not a gap the object vanished in.
    interp_gap = math.ceil(job.fps / min(tracks.sam_fps, job.fps))
    solid = set(solid)
    by_id = {t.track_id: t for t in tracks.tracks}
    frames: dict[int, list[PlanEntry]] = {}
    hidden: set[str] = set()
    for item in decisions.items:
        if item.decision == "keep" or item.style is None:
            continue
        if item.origin == "audit_patch":
            for frame, entry in _patch_entries(item, job):
                frames.setdefault(frame, []).append(entry)
            continue
        style: Style = "solid" if item.item_id in solid else item.style
        grid = locked_grid(item, by_id, job) if style == "pixelate" else None
        if style == "pixelate" and grid is None:
            # contracts._check_decisions refuses this: a mosaic is sized from a face track.
            raise ValueError(f"{item.item_id} is pixelated but has no face track to size its grid")
        for track_id in item.track_ids:
            track = by_id[track_id]
            hidden.add(track_id)
            regions = TrackRegions(
                track,
                ratio=ratio_for(track.concept, PADDING.face, PADDING.default),
                px=PADDING.px,
                width=job.width,
                height=job.height,
                interp_gap=interp_gap,
            )
            for frame in range(max(0, track.first - backfill), min(job.frames, track.last + EXTEND + 1)):
                region = regions.at(frame)
                entry = PlanEntry(
                    item_id=item.item_id,
                    shape="mask" if region.mask is not None else "box",
                    box=region.box,
                    mask=region.mask,
                    style=style,
                    grid=grid,
                )
                frames.setdefault(frame, []).append(entry)
    return Plan(
        padding=PADDING,
        temporal=Temporal(extend=EXTEND, backfill=backfill, gap_hold_s=GAP_HOLD_S),
        frames=dict(sorted(frames.items())),
        crowd_fills=_crowd_fills(tracks, hidden, job),
    )
