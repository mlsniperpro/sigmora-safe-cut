"""The leak guard: decisions + tracks → ``plan.json`` (DESIGN §2.6, WP3 step 5, ARCHITECTURE §3.7).

Every hidden or ``needs_you`` item is planned on every frame of each of its tracks, widened in time by the
back-fill before the first detection (0.3 s, ``ceil(0.3 x fps)`` frames, the first box held still) and 8
frames after the last, and padded in space (``regions``). A person or child is covered face/head only (DESIGN
§2.7): its face tracks, and its body tracks as a head estimate where no face track is planned; only the creator's
Remove person (``person_solid``) covers the whole body. No cover ever hides a kept participant's face: each entry
of another item lists the kept faces it must leave clear (``keep_clear``), except a child's and an audit patch's.
Crowded frames (a concept at SAM's 16-object cap) get a crowd fill over every tracked object there. A pixelated
item keeps one grid for its whole life, anchored at its first face box with cells big enough that the face spans at
most 4 blocks (DESIGN's limit is 6), so the mosaic never shifts between frames. An item a model read through (a
flagged leak's ``through_item``) renders solid from then on, and every audit patch is rebuilt from its decision item,
so no re-plan ever loses one.

Held boxes move with the camera (``safecut.guard.motion``, ``plan(..., camera=...)``, stored in ``plan.json``): the
back-fill, extend, a re-entry or gap hold and an audit patch follow the scene's pan instead of staying still where the
person no longer is, and draw nothing on a frame where that carries them out of the frame.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable, MutableMapping

from safecut.contracts import (
    Camera,
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
    camera_delta,
    clip_box,
    face_frames,
    head_box,
    identity_only,
    is_held,
    live_frames,
    nearest_box,
    patch_source,
    sam_interp_gap,
    translate,
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
BACKFILL_S = 0.3
#: DESIGN §2.7: a face spans at most 6 mosaic blocks; we use 4 (coarser is always allowed, finer never): with 6, the
#: demo's bystander still left a trace the entry gate's pixel check (E3) could read on a few edge frames.
MAX_BLOCKS = 4

Grid = tuple[int, int, int]


def backfill_frames(job: Job) -> int:
    """``ceil(0.3 x job.fps)``: 0.3 s before a track's first box (DESIGN §2.6, ARCHITECTURE §3.7)."""
    return math.ceil(BACKFILL_S * job.fps)


def locked_grid(item: DecisionItem, by_id: dict[str, Track], job: Job) -> Grid | None:
    """``[x0, y0, cell]`` for a pixelated item: origin at its earliest face's first padded box, cell from its widest
    face box (≤ 4 blocks across), fixed for the item's whole life (DESIGN §2.7)."""
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


def _patch_entries(item: DecisionItem, job: Job, camera: Camera | None = None) -> Iterable[tuple[int, PlanEntry]]:
    """An audit patch: its raw box padded by its kind's spatial padding over its own span, no temporal padding
    (API-NOTES §12). With a camera the box moves with the scene from its evidence frame (``patch_source``), and a
    frame where that carries it out of the frame draws nothing."""
    if item.box is None or item.first is None or item.last is None:
        return
    ratio = PADDING.face if item.kind == "person" else PADDING.default
    hold = backfill_frames(job)
    still = grow(item.box, ratio, PADDING.px, job.width, job.height)
    entry = PlanEntry(item_id=item.item_id, shape="box", box=still, mask=None, style="solid", grid=None,
                      source="audit_patch")  # fmt: skip
    for frame in range(item.first, min(job.frames, item.last + 1)):
        if camera is None:
            yield frame, entry
            continue
        moved = patch_source(item, frame, camera, hold, job.frames)
        if moved is None or clip_box(moved, job.width, job.height) is None:
            continue
        box = grow(moved, ratio, PADDING.px, job.width, job.height)
        yield frame, entry if box == still else entry.model_copy(update={"box": box})


#: Regions of one track over a frame range, keyed by (track_id, first frame, last frame, camera): they depend only on
#: the track, the job and the camera, never on the decisions, so a re-plan after a review edit can reuse them. The
#: camera part is None without one, else a hash of its offsets (a new camera never finds the old regions).
RegionCache = MutableMapping[tuple[str, int, int, int | None], list[Region | None]]


def _regions(
    track: Track,
    start: int,
    end: int,
    *,
    job: Job,
    interp_gap: int,
    cache: RegionCache | None,
    camera: Camera | None = None,
) -> list[Region | None]:
    """The track's region on each frame ``start … end - 1`` (from the cache when it has them); None on a frame where
    the camera carried a held box out of the frame."""
    key = (track.track_id, start, end, None if camera is None else hash(tuple(camera)))
    found = cache.get(key) if cache is not None else None
    if found is None:
        regions = TrackRegions(track, ratio=ratio_for(track.concept, PADDING.face, PADDING.default), px=PADDING.px,
                               width=job.width, height=job.height, interp_gap=interp_gap, camera=camera)  # fmt: skip
        found = [regions.region(frame) for frame in range(start, end)]
        if cache is not None:
            cache[key] = found
    return found


def _with_body(
    face: Track,
    start: int,
    regions: list[Region | None],
    *,
    bodies: dict[int, list[BoxT]],
    job: Job,
    interp_gap: int,
    camera: Camera | None = None,
) -> list[Region | None]:
    """A whole-person item's face regions, with an estimated body under the face on every frame where none of the
    item's body regions holds this face (a face-only item, a face seen longer than its body track, or a merged
    face elsewhere in the frame). The body grows from the padded face *box* (a mask outline can sit inside it).
    Where the camera carried the held face out of the frame, nothing is drawn."""
    boxed = TrackRegions(face.model_copy(update={"masks": {}}), ratio=PADDING.face, px=PADDING.px, width=job.width,
                         height=job.height, interp_gap=interp_gap, camera=camera)  # fmt: skip
    out: list[Region | None] = []
    for frame, held in enumerate(regions, start=start):
        face_box = boxed.region(frame)
        if held is None or face_box is None:
            out.append(None)
            continue
        padded = face_box.box
        if any(intersection(padded, b) >= 0.5 * area(padded) for b in bodies.get(frame, [])):
            out.append(held)
        else:
            out.append(Region(body_below(union([held.box, padded]), job.width, job.height)))
    return out


def _heads(
    track: Track,
    start: int,
    end: int,
    *,
    faced: frozenset[int],
    job: Job,
    interp_gap: int,
    camera: Camera | None = None,
) -> Iterable[tuple[int, Region]]:
    """An identity-only item's body track as a head estimate (DESIGN §2.7) on each frame ``start … end - 1`` no face
    track of the item is planned on: the top of the body box (where the guard holds it, and where SAM last saw it),
    padded like a face. Never the whole body. With a camera a held box moves with the scene, and a frame where it
    is carried out of the frame draws nothing."""
    raw = TrackRegions(track.model_copy(update={"masks": {}}), ratio=0.0, px=0, width=job.width, height=job.height,
                       interp_gap=interp_gap, camera=camera)  # fmt: skip
    keys = sorted(track.boxes)
    for frame in range(start, end):
        if frame in faced:
            continue
        held = raw.region(frame)
        heads = [] if held is None else [head_box(held.box, job.width)]
        moving = camera is not None and is_held(track, frame, interp_gap)
        near = nearest_box(track, frame)  # where SAM saw it: the keyframe nearest (the edge box when held)
        if near is not None:
            if moving and camera is not None:
                moved = clip_box(translate(near, *camera_delta(camera, frame, _nearest_key(keys, frame))),
                                 job.width, job.height)  # fmt: skip
                near = moved
            if near is not None:
                heads.append(head_box(near, job.width))
        between = box_at(track, frame)  # between anchors: the interpolated box (not through a held gap's pan)
        if between is not None and not moving:
            heads.append(head_box(between, job.width))
        if heads:
            yield frame, Region(grow(union(heads), PADDING.face, PADDING.px, job.width, job.height))


def _nearest_key(keys: list[int], frame: int) -> int:
    """The keyframe :func:`nearest_box` reads on ``frame`` (the earlier on a tie)."""
    i = bisect.bisect_left(keys, frame)
    return min(keys[max(0, i - 1) : i + 1], key=lambda k: (abs(k - frame), k))


def kept_faces(
    job: Job, tracks: Tracks, decisions: Decisions, *, interp_gap: int, padded: bool = True
) -> dict[int, list[BoxT]]:
    """Every kept participant's padded face box, by frame (DESIGN §2.6): from each face track of a kept person, on
    the frames SAM saw it (``first … last``, gaps held), padded like any face cover."""
    by_id = {t.track_id: t for t in tracks.tracks}
    out: dict[int, list[BoxT]] = {}
    for item in decisions.items:
        if item.decision != "keep" or item.kind != "person":
            continue
        for track in (by_id[t] for t in item.track_ids if t in by_id and by_id[t].concept == "face"):
            regions = TrackRegions(track.model_copy(update={"masks": {}}), ratio=PADDING.face if padded else 0.0,
                                   px=PADDING.px if padded else 0, width=job.width, height=job.height,
                                   interp_gap=interp_gap)  # fmt: skip
            for frame in range(track.first, min(job.frames, track.last + 1)):
                out.setdefault(frame, []).append(regions.at(frame).box)
    return out


def _clip_kept(
    frames: dict[int, list[PlanEntry]],
    kept: dict[int, list[BoxT]],
    faces_only: dict[int, list[BoxT]],
    decisions: Decisions,
    by_id: dict[str, Track],
) -> None:
    """Leave every kept participant's face clear of every other item's cover (``keep_clear``), audit patches
    included, except a child's: a child always wins; otherwise a kept face always wins (owner, 11-04: a hidden track
    that switched onto a kept face, or a patch over it, must never paint it). What is cleared is the kept face's own
    box (``faces_only``, unpadded): whatever is inside it is the kept face, in front (a hidden track that switched
    onto it included); a leak right beside it stays covered."""
    del by_id
    unclipped = {i.item_id for i in decisions.items if i.kind == "child"}
    for frame, entries in frames.items():
        if not kept.get(frame):
            continue
        for n, entry in enumerate(entries):
            if entry.item_id in unclipped:
                continue
            clear = [f for f in faces_only.get(frame, []) if intersection(f, entry.box) > 0]
            if clear:
                entries[n] = entry.model_copy(update={"keep_clear": clear})


def _item_regions(
    item: DecisionItem,
    by_id: dict[str, Track],
    job: Job,
    *,
    backfill: int,
    interp_gap: int,
    cache: RegionCache | None,
    camera: Camera | None = None,
) -> Iterable[tuple[int, Region]]:
    """Every (frame, region) one hidden item draws, over each of its tracks' padded frame range (none on a frame
    where the camera carried a held box out of the frame)."""
    # A whole-person item covers an estimated body under its face on every frame no body track of the item covers
    # (a face-only item, or a face seen longer than its body track): DESIGN §2.7b's whole person, never a face.
    # Body regions of the item, by frame: a face is covered whole on a frame where one of them holds it.
    bodies: dict[int, list[BoxT]] = {}
    if item.style == "person_solid":  # the item's own style: a read-through re-render solid never shrinks it
        for t in (by_id[t] for t in item.track_ids if by_id[t].concept == "person"):
            b_start, b_end = max(0, t.first - backfill), min(job.frames, hold_until(t, by_id, job) + 1)
            b_regions = _regions(t, b_start, b_end, job=job, interp_gap=interp_gap, cache=cache, camera=camera)
            # Only where the body is drawn: its held box gives way to another live track of the item (below).
            others = live_frames(by_id[x] for x in item.track_ids if x != t.track_id)
            for frame, region in enumerate(b_regions, start=b_start):
                if region is not None and (t.first <= frame <= t.last or frame not in others):
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
        placed: Iterable[tuple[int, Region | None]]
        if identity and track.concept == "person":
            placed = _heads(track, start, end, faced=faced, job=job, interp_gap=interp_gap, camera=camera)
        else:
            regions = _regions(track, start, end, job=job, interp_gap=interp_gap, cache=cache, camera=camera)
            if item.style == "person_solid" and track.concept == "face":
                regions = _with_body(track, start, regions, bodies=bodies, job=job, interp_gap=interp_gap,
                                     camera=camera)  # fmt: skip
            placed = zip(range(start, end), regions, strict=True)
        # A held box (back-fill, extend, re-entry hold) is held where the object was last seen (moved with the camera,
        # when there is one) while the object moves: where another track of the item is tracked, that track's live box
        # is drawn instead (DESIGN §2.6).
        others = live_frames(by_id[t] for t in item.track_ids if t != track_id)
        for f, r in placed:
            if r is not None and (track.first <= f <= track.last or f not in others):
                yield f, r


def plan(
    job: Job,
    tracks: Tracks,
    decisions: Decisions,
    *,
    solid: Iterable[str] = (),
    cache: RegionCache | None = None,
    camera: Camera | None = None,
) -> Plan:
    """The plan for every hidden item; the items in ``solid`` (read through, :func:`read_through`) render solid.
    ``cache`` must belong to exactly these ``job`` and ``tracks`` (``safecut.guard.run`` scopes it). ``camera`` is the
    scene's cumulative translation on every frame (``safecut.guard.motion``): held boxes move with it, and the plan
    records it; without one they are held still, as before."""
    if camera is not None and len(camera) != job.frames:
        raise ValueError(f"camera has {len(camera)} offsets, the job {job.frames} frames")
    backfill = backfill_frames(job)
    interp_gap = sam_interp_gap(job.fps, tracks.sam_fps)  # within SAM's own sampling step a gap is interpolation
    solid = set(solid)
    by_id = {t.track_id: t for t in tracks.tracks}
    frames: dict[int, list[PlanEntry]] = {}
    for item in decisions.items:
        if item.decision == "keep" or item.style is None:
            continue
        if item.origin == "audit_patch":
            for frame, entry in _patch_entries(item, job, camera):
                frames.setdefault(frame, []).append(entry)
            continue
        style: Style = "solid" if item.item_id in solid else item.style
        grid = locked_grid(item, by_id, job) if style == "pixelate" else None
        if style == "pixelate" and grid is None:
            # contracts._check_decisions refuses this: a mosaic is sized from a face track.
            raise ValueError(f"{item.item_id} is pixelated but has no face track to size its grid")
        for frame, region in _item_regions(
            item, by_id, job, backfill=backfill, interp_gap=interp_gap, cache=cache, camera=camera
        ):
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
    kept = kept_faces(job, tracks, decisions, interp_gap=interp_gap)
    own_boxes = kept_faces(job, tracks, decisions, interp_gap=interp_gap, padded=False)
    _clip_kept(frames, kept, own_boxes, decisions, by_id)
    return Plan(
        padding=PADDING,
        temporal=Temporal(extend=EXTEND, backfill=backfill, gap_hold_s=GAP_HOLD_S),
        frames=dict(sorted(frames.items())),
        crowd_fills=_crowd_fills(tracks, job),
        camera=None if camera is None else [(int(x), int(y)) for x, y in camera],
    )
