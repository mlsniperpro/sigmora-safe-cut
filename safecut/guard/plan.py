"""The leak guard: decisions + tracks → ``plan.json`` (DESIGN §2.6, WP3 step 5, ARCHITECTURE §3.7).

Every hidden or ``needs_you`` item is planned on every frame of each of its tracks, widened in time by the
back-fill before the first detection (half a second, ``ceil(0.5 x fps)`` frames, the first box held still) and 8
frames after the last, and padded in space (``regions``). A person or child is covered face/head only (DESIGN
§2.7): its face tracks, and its body tracks as a head estimate where no face track is planned; only the creator's
Remove person (``person_solid``) covers the whole body. No cover ever hides a kept participant's face: each entry
of another item lists the kept faces it must leave clear (``keep_clear``), except a child's and an audit patch's.
Crowded frames (a concept at SAM's 16-object cap) get a crowd fill over every tracked object there. A pixelated
item keeps one grid for its whole life, anchored at its first face box with cells big enough that the face spans at
most 6 blocks, so the mosaic never shifts between frames. An item a model read through (a flagged leak's
``through_item``) renders solid from then on, and every audit patch is rebuilt from its decision item, so no re-plan
ever loses one.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, MutableMapping

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
    face_frames,
    head_box,
    identity_only,
    nearest_box,
)
from safecut.decide.geometry import BoxT, area, box_at, clamp, grow, intersection, union
from safecut.guard.regions import Region, TrackRegions, ratio_for

#: DESIGN §2.6: faces 15 % + 8 px, everything else 8 % + 8 px.
PADDING = Padding(face=0.15, default=0.08, px=8)
#: DESIGN §2.6: extend 8 frames after the last detection.
EXTEND = 8
#: DESIGN §2.6: hold the last box through gaps up to 2 s.
GAP_HOLD_S = 2.0
#: DESIGN §2.6: the back-fill before a track's first box, in seconds (a late detection, held still).
BACKFILL_S = 0.5
#: DESIGN §2.7: a face spans at most 6 mosaic blocks.
MAX_BLOCKS = 6

Grid = tuple[int, int, int]


def backfill_frames(job: Job) -> int:
    """``ceil(0.5 x job.fps)``: half a second before a track's first box (DESIGN §2.6, ARCHITECTURE §3.7)."""
    return math.ceil(BACKFILL_S * job.fps)


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


#: A body under a face, in face sizes: this many face widths out on each side, this many face heights down.
BODY_SIDE, BODY_DOWN = 1.0, 7.0


def body_below(face: BoxT, width: int, height: int) -> BoxT:
    """A whole-person box from a (padded) face box: shoulders a face width out each side, down seven face heights
    (clamped to the frame), for a whole-person hide where SAM tracked no body."""
    x1, y1, x2, y2 = face
    w, h = x2 - x1, y2 - y1
    box = clamp((x1 - BODY_SIDE * w, y1, x2 + BODY_SIDE * w, y2 + BODY_DOWN * h), width, height)
    return box if box is not None else face


def _crowd_fills(tracks: Tracks, job: Job) -> list[CrowdFill]:
    """One fill per run of consecutive crowded frames over the whole crowded region (DESIGN §2.6): every track present
    there, kept ones too (SAM's cap dropped objects among them, which nothing else localises), padded; the whole
    frame when no track is present."""
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
            ratio = ratio_for(t.concept, PADDING.face, PADDING.default)
            for frame in run:
                box = box_at(t, frame)
                if box is not None:
                    boxes.append(grow(box, ratio, PADDING.px, job.width, job.height))
        fills.append(CrowdFill(frames=run, box=union(boxes) if boxes else (0, 0, job.width, job.height)))
    return fills


def hold_until(track: Track, by_id: dict[str, Track], job: Job) -> int:
    """The last frame the guard covers a track on: ``last + extend``, and, when SAM picked the object up again as a
    new track (a re-entry), on through the gap up to 2 s (DESIGN §2.6's gap hold, which the split would lose)."""
    end = track.last + EXTEND
    hold = math.ceil(GAP_HOLD_S * job.fps)
    for other in by_id.values():
        if other.reentry_of == track.track_id:
            end = max(end, min(other.first - 1, track.last + hold))
    return end


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


#: Regions of one track over a frame range, keyed by (track_id, first frame, last frame): they depend only on the track
#: and the job, never on the decisions, so a re-plan after a review edit can reuse them.
RegionCache = MutableMapping[tuple[str, int, int], list[Region]]


def _regions(
    track: Track, start: int, end: int, *, job: Job, interp_gap: int, cache: RegionCache | None
) -> list[Region]:
    """The track's region on each frame ``start … end - 1`` (from the cache when it has them)."""
    key = (track.track_id, start, end)
    found = cache.get(key) if cache is not None else None
    if found is None:
        regions = TrackRegions(track, ratio=ratio_for(track.concept, PADDING.face, PADDING.default), px=PADDING.px,
                               width=job.width, height=job.height, interp_gap=interp_gap)  # fmt: skip
        found = [regions.at(frame) for frame in range(start, end)]
        if cache is not None:
            cache[key] = found
    return found


def _with_body(
    face: Track, start: int, regions: list[Region], *, bodies: dict[int, list[BoxT]], job: Job, interp_gap: int
) -> list[Region]:
    """A whole-person item's face regions, with an estimated body under the face on every frame where none of the
    item's body regions holds this face (a face-only item, a face seen longer than its body track, or a merged
    face elsewhere in the frame). The body grows from the padded face *box* (a mask outline can sit inside it)."""
    boxed = TrackRegions(face.model_copy(update={"masks": {}}), ratio=PADDING.face, px=PADDING.px, width=job.width,
                         height=job.height, interp_gap=interp_gap)  # fmt: skip
    out: list[Region] = []
    for frame, held in enumerate(regions, start=start):
        padded = boxed.at(frame).box
        if any(intersection(padded, b) >= 0.5 * area(padded) for b in bodies.get(frame, [])):
            out.append(held)
        else:
            out.append(Region(body_below(union([held.box, padded]), job.width, job.height)))
    return out


def _heads(
    track: Track, start: int, end: int, *, faced: frozenset[int], job: Job, interp_gap: int
) -> Iterable[tuple[int, Region]]:
    """An identity-only item's body track as a head estimate (DESIGN §2.7) on each frame ``start … end - 1`` no face
    track of the item is planned on: the top of the body box (where the guard holds it, and where SAM last saw it),
    padded like a face. Never the whole body."""
    raw = TrackRegions(track.model_copy(update={"masks": {}}), ratio=0.0, px=0, width=job.width, height=job.height,
                       interp_gap=interp_gap)  # fmt: skip
    for frame in range(start, end):
        if frame in faced:
            continue
        heads = [head_box(raw.at(frame).box)]
        seen = nearest_box(track, frame)
        if seen is not None:
            heads.append(head_box(seen))
        yield frame, Region(grow(union(heads), PADDING.face, PADDING.px, job.width, job.height))


def kept_faces(job: Job, tracks: Tracks, decisions: Decisions, *, interp_gap: int) -> dict[int, list[BoxT]]:
    """Every kept participant's padded face box, by frame (DESIGN §2.6): from each face track of a kept person, on
    the frames SAM saw it (``first … last``, gaps held), padded like any face cover."""
    by_id = {t.track_id: t for t in tracks.tracks}
    out: dict[int, list[BoxT]] = {}
    for item in decisions.items:
        if item.decision != "keep" or item.kind != "person":
            continue
        for track in (by_id[t] for t in item.track_ids if t in by_id and by_id[t].concept == "face"):
            regions = TrackRegions(track.model_copy(update={"masks": {}}), ratio=PADDING.face, px=PADDING.px,
                                   width=job.width, height=job.height, interp_gap=interp_gap)  # fmt: skip
            for frame in range(track.first, min(job.frames, track.last + 1)):
                out.setdefault(frame, []).append(regions.at(frame).box)
    return out


def _clip_kept(
    frames: dict[int, list[PlanEntry]], kept: dict[int, list[BoxT]], decisions: Decisions, by_id: dict[str, Track]
) -> None:
    """Leave every kept participant's face clear of every other item's cover (``keep_clear``), except a child's (a
    child always wins), an audit patch (a leak the audit found stays covered), and where the item's own face is
    inside that kept face on the frame: a hidden face is never uncovered to keep another face clear (the audit would
    only patch it back over both), so only its padding, a body or an object's cover gives way."""
    unclipped = {i.item_id for i in decisions.items if i.kind == "child" or i.origin == "audit_patch"}
    hidden_faces = {
        i.item_id: [by_id[t] for t in i.track_ids if t in by_id and by_id[t].concept == "face"]
        for i in decisions.items
        if i.decision != "keep"
    }
    for frame, entries in frames.items():
        faces = kept.get(frame)
        if not faces:
            continue
        for n, entry in enumerate(entries):
            if entry.item_id in unclipped or entry.source == "audit_patch":
                continue
            own = [b for t in hidden_faces.get(entry.item_id, []) if (b := nearest_box(t, frame)) is not None]
            clear = [
                f for f in faces if intersection(f, entry.box) > 0 and not any(intersection(f, b) > 0 for b in own)
            ]
            if clear:
                entries[n] = entry.model_copy(update={"keep_clear": clear})


def _item_regions(
    item: DecisionItem, by_id: dict[str, Track], job: Job, *, backfill: int, interp_gap: int, cache: RegionCache | None
) -> Iterable[tuple[int, Region]]:
    """Every (frame, region) one hidden item draws, over each of its tracks' padded frame range."""
    # A whole-person item covers an estimated body under its face on every frame no body track of the item covers
    # (a face-only item, or a face seen longer than its body track): DESIGN §2.7b's whole person, never a face.
    # Body regions of the item, by frame: a face is covered whole on a frame where one of them holds it.
    bodies: dict[int, list[BoxT]] = {}
    if item.style == "person_solid":  # the item's own style: a read-through re-render solid never shrinks it
        for t in (by_id[t] for t in item.track_ids if by_id[t].concept == "person"):
            b_start, b_end = max(0, t.first - backfill), min(job.frames, hold_until(t, by_id, job) + 1)
            b_regions = _regions(t, b_start, b_end, job=job, interp_gap=interp_gap, cache=cache)
            for frame, region in enumerate(b_regions, start=b_start):
                bodies.setdefault(frame, []).append(region.box)
    # DESIGN §2.7: a hidden person or child is covered face/head only. Its body tracks draw nothing where a face
    # track of the item is planned, and a head estimate elsewhere (face missed, turned away, between detections).
    identity = identity_only(item.kind, item.style)
    faced = (
        face_frames((by_id[t] for t in item.track_ids), backfill=backfill, extend=EXTEND, frames=job.frames)
        if identity
        else frozenset[int]()
    )
    for track_id in item.track_ids:
        track = by_id[track_id]
        start, end = max(0, track.first - backfill), min(job.frames, hold_until(track, by_id, job) + 1)
        placed: Iterable[tuple[int, Region]]
        if identity and track.concept == "person":
            placed = _heads(track, start, end, faced=faced, job=job, interp_gap=interp_gap)
        else:
            regions = _regions(track, start, end, job=job, interp_gap=interp_gap, cache=cache)
            if item.style == "person_solid" and track.concept == "face":
                regions = _with_body(track, start, regions, bodies=bodies, job=job, interp_gap=interp_gap)
            placed = zip(range(start, end), regions, strict=True)
        yield from placed


def plan(
    job: Job,
    tracks: Tracks,
    decisions: Decisions,
    *,
    solid: Iterable[str] = (),
    cache: RegionCache | None = None,
) -> Plan:
    """The plan for every hidden item; the items in ``solid`` (read through, :func:`read_through`) render solid.
    ``cache`` must belong to exactly these ``job`` and ``tracks`` (``safecut.guard.run`` scopes it)."""
    backfill = backfill_frames(job)
    # Within SAM's own sampling step a missing box is interpolation, not a gap the object vanished in.
    interp_gap = math.ceil(job.fps / min(tracks.sam_fps, job.fps))
    solid = set(solid)
    by_id = {t.track_id: t for t in tracks.tracks}
    frames: dict[int, list[PlanEntry]] = {}
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
        for frame, region in _item_regions(item, by_id, job, backfill=backfill, interp_gap=interp_gap, cache=cache):
            # Built unvalidated (thousands per clip): every field comes from validated inputs or the round-trip
            # tested encoder, and every reader of plan.json validates it on load.
            entry = PlanEntry.model_construct(
                item_id=item.item_id,
                shape="mask" if region.mask is not None else "box",
                box=region.box,
                mask=region.mask,
                style=style,
                grid=grid,
            )
            frames.setdefault(frame, []).append(entry)
    _clip_kept(frames, kept_faces(job, tracks, decisions, interp_gap=interp_gap), decisions, by_id)
    return Plan(
        padding=PADDING,
        temporal=Temporal(extend=EXTEND, backfill=backfill, gap_hold_s=GAP_HOLD_S),
        frames=dict(sorted(frames.items())),
        crowd_fills=_crowd_fills(tracks, job),
    )
