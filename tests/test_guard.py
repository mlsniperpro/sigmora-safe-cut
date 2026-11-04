"""WP3 step 5: the leak guard (DESIGN §2.6) — table tests and the E4 properties (≥ 2000 examples each)."""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from safecut import contracts
from safecut.contracts import Audit, DecisionItem, Decisions, Plan, PlanEntry, Track, Tracks
from safecut.decide import geometry as g
from safecut.decide.policy import Inputs, decide
from safecut.decide.review import ReviewEdit, apply_review
from safecut.guard import run as guard_run
from safecut.guard.plan import EXTEND, PADDING, backfill_frames, body_below, plan, read_through
from safecut.guard.regions import held_box, mask_ok
from safecut.render.draw import hidden_mask
from tests.safety_factories import FPS, FRAMES, H, W, job, roles, row, track, track_sets, tracks
from tests.test_policy import E4

JOB = job()
EDIT: TypeAdapter[ReviewEdit] = TypeAdapter(ReviewEdit)


def hide_all(ts: Tracks) -> Decisions:
    return decide(Inputs(job=JOB, tracks=ts))


def entries(p: Plan, frame: int, item_id: str) -> list[PlanEntry]:
    return [e for e in p.frames.get(frame, []) if e.item_id == item_id]


def covered(p: Plan, frame: int, item_id: str, box: tuple[int, int, int, int]) -> bool:
    """Every pixel of ``box`` is under one of the item's entries (box or mask) or a crowd fill."""
    want = np.zeros((H, W), dtype=np.bool_)
    want[box[1] : box[3], box[0] : box[2]] = True
    have = np.zeros((H, W), dtype=np.bool_)
    for e in entries(p, frame, item_id):
        if e.mask is not None:
            have |= g.decode(e.mask)
        else:
            have[e.box[1] : e.box[3], e.box[0] : e.box[2]] = True
    for fill in p.crowd_fills:
        if frame in fill.frames:
            have[fill.box[1] : fill.box[3], fill.box[0] : fill.box[2]] = True
    return bool((have | ~want).all())


def identity_box(
    t: Track, box: tuple[int, int, int, int], item: DecisionItem, *, ts: Tracks, p: Plan, frame: int
) -> tuple[int, int, int, int] | None:
    """What of ``box`` must be hidden (DESIGN §2.7): an identity-only item's body track is hidden as its head estimate,
    and only where none of the item's face tracks is planned (there the face cover hides the identity); else ``box``."""
    if t.concept != "person" or not contracts.identity_only(item.kind, item.style):
        return box
    by_id = {x.track_id: x for x in ts.tracks}
    faced = contracts.face_frames((by_id[x] for x in item.track_ids), backfill=p.temporal.backfill,
                                  extend=p.temporal.extend, frames=FRAMES)  # fmt: skip
    return None if frame in faced else contracts.head_box(box)


def disk(cx: int, cy: int, r: int) -> contracts.Rle:
    yy, xx = np.mgrid[0:H, 0:W]
    return g.encode((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)


# ---------------------------------------------------------------------------------------------- table tests


def test_backfill_is_half_a_second() -> None:
    assert backfill_frames(job(fps=30)) == 15  # DESIGN §2.6: ceil(0.5 x fps)
    assert backfill_frames(job(fps=24)) == 12
    assert backfill_frames(job(fps=25)) == 13


def test_a_hidden_face_is_padded_15_percent_plus_8_px_on_each_side() -> None:
    ts = tracks(track("face:1", 20, 30, (100, 50, 140, 90)))
    p = plan(JOB, ts, hide_all(ts))
    (e,) = entries(p, 25, "i_1")
    assert e.box == (86, 36, 154, 104)  # 40 px: 6 + 8 each side
    assert p.padding == PADDING
    assert (p.temporal.extend, p.temporal.backfill) == (8, 15)


def test_objects_are_padded_8_percent() -> None:
    ts = tracks(track("screen:1", 20, 30, (100, 50, 150, 100)))
    (e,) = entries(plan(JOB, ts, hide_all(ts)), 25, "i_1")
    assert e.box == (88, 38, 162, 112)


def test_kept_items_are_not_planned() -> None:
    ts = tracks(track("face:1", 0, 10))
    d = decide(Inputs(job=job(audio=False), tracks=ts, roles=roles(row("face:1", *["participant"] * 3)),
                      scene=None))  # fmt: skip
    assert d.items[0].decision == "needs_you"  # no scene: held
    keep = Decisions(items=[d.items[0].model_copy(update={"decision": "keep", "style": None, "hold": None,
                                                          "decided_by": "creator"})])  # fmt: skip
    assert plan(JOB, ts, keep).frames == {}


def test_backfill_and_extend_hold_the_edge_box_still() -> None:
    """DESIGN §2.6: no sweep along the motion: a cover never runs ahead of its object into where it isn't yet."""
    t = track("face:1", 40, 50, (100, 60, 120, 80), step=(2, 0))  # moving right 2 px a frame
    ts = tracks(t)
    p = plan(JOB, ts, hide_all(ts))
    assert min(p.frames) == 40 - 15
    assert max(p.frames) == 50 + EXTEND
    for frame in range(25, 40):
        assert covered(p, frame, "i_1", (100, 60, 120, 80)), frame  # the first box, held still
        (e,) = entries(p, frame, "i_1")
        assert e.box[0] >= 100 - 2 - 3 - 8 - 1  # grown at most 10 % (2 px) each side, then padded (3 + 8 px)
    for frame in range(51, 59):
        assert covered(p, frame, "i_1", (120, 60, 140, 80)), frame  # the last box, held still
        (e,) = entries(p, frame, "i_1")
        assert e.box[2] <= 140 + 5 + 4 + 8 + 1  # grown at most 25 % (5 px) each side, then padded


def test_held_box_grows_2_percent_a_frame_and_is_capped() -> None:
    assert held_box((100, 100, 200, 200), 10, 0.25, 1280, 720) == (80, 80, 220, 220)
    assert held_box((100, 100, 200, 200), 500, 0.25, 1280, 720) == (75, 75, 225, 225)  # 25 % after the last box
    assert held_box((100, 100, 200, 200), 500, 0.10, 1280, 720) == (90, 90, 210, 210)  # 10 % before the first


def test_a_gap_holds_the_interpolated_box_never_the_whole_path() -> None:
    """SAM lost the object for 41 frames while it moved 84 px: each gap frame covers the interpolated box (grown from
    the nearer anchor), not a cover stretched from where it was lost to where it came back."""
    t = track("face:1", 0, 50, (40, 40, 60, 60), step=(2, 0), anchors=[0, 1, 2, 3, 45, 46, 47, 48, 49, 50])
    ts = tracks(t)
    p = plan(JOB, ts, hide_all(ts))
    for frame in range(4, 45):
        interp = g.box_at(t, frame)
        assert interp is not None
        assert covered(p, frame, "i_1", interp), frame
        (e,) = entries(p, frame, "i_1")
        assert e.box[2] - e.box[0] <= 20 * 1.5 + 2 * (5 + 8), (frame, e.box)  # grown 25 %, then face-padded


def test_crowded_frames_get_a_fill_over_every_hidden_object() -> None:
    ts = tracks(track("face:1", 0, 20, (10, 10, 30, 30)), track("face:2", 0, 20, (200, 100, 230, 130)),
                crowded=[5, 6, 7, 12])  # fmt: skip
    p = plan(JOB, ts, hide_all(ts))
    assert [f.frames for f in p.crowd_fills] == [[5, 6, 7], [12]]
    assert all(g.contains(f.box, (10, 10, 30, 30)) and g.contains(f.box, (200, 100, 230, 130)) for f in p.crowd_fills)


def test_a_crowd_with_nothing_hidden_fills_the_frame() -> None:
    ts = tracks(track("face:1", 0, 4), crowded=[30])
    assert plan(JOB, ts, hide_all(ts)).crowd_fills[0].box == (0, 0, W, H)


def test_the_pixelate_grid_is_locked_to_the_first_face_and_sized_for_6_blocks() -> None:
    ts = tracks(track("face:1", 0, 30, (100, 60, 136, 96), step=(1, 1)))
    p = plan(JOB, ts, hide_all(ts))
    grids = {e.grid for es in p.frames.values() for e in es}
    assert grids == {(86, 46, 6)}  # 36 px wide: 6 px cells, origin at the first padded box


def test_a_face_that_grows_gets_cells_from_its_widest_box() -> None:
    t = Track.model_validate(
        {**track("face:1", 0, 1).model_dump(), "boxes": {0: (10, 10, 22, 22), 1: (10, 10, 52, 52)}}
    )  # 42 px at its widest: under a quarter of the frame, so a mosaic (a taller face is a close-up, covered whole)
    ts = tracks(t)
    (e,) = entries(plan(JOB, ts, hide_all(ts)), 1, "i_1")
    assert e.grid is not None
    assert e.grid[2] == 7  # ceil(42 / 6)


def test_an_item_read_through_renders_solid_from_then_on() -> None:
    ts = tracks(track("face:1", 0, 30, (100, 60, 136, 96)))
    d = hide_all(ts)
    audit = Audit.model_validate({
        "frames_scanned": FRAMES, "egoblur": {"model": "yunet-face", "faces": 0, "plates": None},
        "leaks": [{"frame": 10, "box": [100, 60, 120, 80], "kind": "text", "detector": "redteam",
                   "patched_item": "i_1", "flag": "redaction_too_weak", "through_item": "i_1"}],
        "redteam": [{"frame": 10, "finding": "hit", "kind": "text", "text": "A", "detail": "x",
                     "box": [100, 60, 120, 80], "confidence": "high"}],
        "unresolved": 0, "passes": 1, "sample_step": FPS, "blocked_reason": None,
    })  # fmt: skip
    assert read_through(audit.leaks) == {"i_1"}
    assert read_through([]) == set()
    p = plan(JOB, ts, d, solid=read_through(audit.leaks))
    assert {e.style for es in p.frames.values() for e in es} == {"solid"}
    assert {e.grid for es in p.frames.values() for e in es} == {None}


def test_audit_patches_are_rebuilt_over_their_own_span_without_temporal_padding() -> None:
    patch = DecisionItem.model_validate({
        "item_id": "p_1", "track_ids": [], "kind": "person", "decision": "hide", "reason": "Added by the audit",
        "evidence_frames": [20], "style": "solid", "decided_by": "policy", "locked": True, "origin": "audit_patch",
        "audit_label": "A1", "box": [100, 60, 120, 80], "first": 5, "last": 35,
    })  # fmt: skip
    p = plan(JOB, tracks(track("face:1", 0, 1)), Decisions(items=[patch]))
    assert sorted(p.frames) == list(range(5, 36))
    (e,) = p.frames[20]
    assert (e.box, e.source, e.style) == ((89, 49, 131, 91), "audit_patch", "solid")


def test_a_pixelated_item_without_a_face_is_refused() -> None:
    ts = tracks(track("person:1", 0, 5))
    bad = hide_all(ts).items[0].model_copy(update={"style": "pixelate"})
    with pytest.raises(ValueError, match="no face track"):
        plan(JOB, ts, Decisions(items=[bad]))


def test_mask_entries_follow_sams_outline_padded_outward() -> None:
    t = track("face:1", 10, 14, (70, 60, 131, 121), masks={10: disk(100, 90, 30), 14: disk(100, 90, 30)})
    ts = tracks(t)
    (item,) = hide_all(ts).items  # a close-up (a third of the frame): whole person; here its face's own outline
    p = plan(JOB, ts, Decisions(items=[item.model_copy(update={"style": "solid"})]))
    for frame in (10, 12, 14):  # its own mask, then both neighbours' shifted to the box between them
        (e,) = entries(p, frame, "i_1")
        assert e.shape == "mask"
        assert e.mask is not None
        mask = g.decode(e.mask)
        assert mask[90, 100]
        assert not mask[0, 0]  # mask-shaped, not the box
        assert (mask | ~g.decode(disk(100, 90, 30))).all()  # holds SAM's own outline
    (e,) = entries(p, 5, "i_1")
    assert e.shape == "box"  # back-fill holds a box


def test_a_sliver_mask_falls_back_to_the_box() -> None:
    sliver = np.zeros((H, W), dtype=np.bool_)
    sliver[90, 70:131] = True
    t = track("face:1", 10, 10, (70, 60, 131, 121), masks={10: g.encode(sliver)})
    ts = tracks(t)
    (e,) = entries(plan(JOB, ts, hide_all(ts)), 10, "i_1")
    assert e.shape == "box"
    assert not mask_ok(sliver, (70, 60, 131, 121))


def test_guard_stage_on_the_example_job(tmp_path: Path) -> None:
    src, dst = Path("fixtures/contracts/j_example"), tmp_path / "j_example"
    dst.mkdir()
    for name in ("job.json", "tracks.json", "roles.json", "scene.json", "transcript.json", "decisions.json"):
        shutil.copy(src / name, dst / name)
    guard_run(dst)
    contracts.validate_job_dir(dst)


# ---------------------------------------------------------------------------------------------- E4 properties


@st.composite
def guarded(draw: st.DrawFn) -> tuple[Tracks, Decisions, Plan]:
    ts = draw(track_sets())
    with_masks: list[Track] = []
    for t in ts:
        if t.origin == "sam" and draw(st.booleans()):
            keys = sorted(t.boxes)
            chosen = draw(st.lists(st.sampled_from(keys), min_size=1, max_size=3, unique=True))
            masks: dict[int, Any] = {}
            for f in chosen:
                b = t.boxes[f]
                cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
                r = max(1, min(b[2] - b[0], b[3] - b[1]) // 2)
                masks[f] = disk(cx, cy, r) if draw(st.integers(0, 4)) else g.encode(np.zeros((H, W), dtype=np.bool_))
            with_masks.append(Track.model_validate({**t.model_dump(), "masks": masks}))
        else:
            with_masks.append(t)
    crowded = sorted(set(draw(st.lists(st.integers(0, FRAMES - 1), max_size=4))))
    tset = tracks(*with_masks, sam_fps=draw(st.sampled_from([1, 8, 30])), crowded=crowded)
    d = hide_all(tset)
    return tset, d, plan(JOB, tset, d)


@pytest.mark.entry("E4:hidden_frames_covered")
@E4
@given(guarded())
def test_property_every_visible_frame_of_a_hidden_track_is_covered_by_its_padded_box(
    case: tuple[Tracks, Decisions, Plan],
) -> None:
    ts, d, p = case
    owner = {t: i.item_id for i in d.items for t in i.track_ids}
    items = {i.item_id: i for i in d.items}
    for t in ts.tracks:
        item = items[owner[t.track_id]]
        heads = t.concept == "person" and contracts.identity_only(item.kind, item.style)
        ratio = PADDING.face if t.concept == "face" or heads else PADDING.default
        for frame, raw in t.boxes.items():
            box = identity_box(t, raw, item, ts=ts, p=p, frame=frame)
            if box is None:
                continue  # its face cover hides the identity on this frame
            # The contract's reading of the padding (half the ratio each side + px) must be fully under the plan.
            dx, dy = int(ratio / 2 * (box[2] - box[0])) + PADDING.px, int(ratio / 2 * (box[3] - box[1])) + PADDING.px
            padded = (max(0, box[0] - dx), max(0, box[1] - dy), min(W, box[2] + dx), min(H, box[3] + dy))
            es = entries(p, frame, owner[t.track_id])
            if any(e.mask is not None for e in es) and not heads:
                # Mask-shaped: SAM's own outline of the object (padded outward) is under what the plan hides on that
                # frame: every entry of the item (a body's box as much as a face's mask) and any crowd fill.
                if frame in t.masks:
                    fills = [f for f in p.crowd_fills if frame in f.frames]
                    have = hidden_mask(es, fills, H, W)
                    assert (have | ~g.decode(t.masks[frame])).all(), (t.track_id, frame)
            else:
                assert covered(p, frame, owner[t.track_id], padded), (t.track_id, frame)
    contracts._check_plan(p, JOB, d)
    contracts._check_plan_covers(p, d, ts, JOB)
    contracts._check_plan_styles(p, d, None)
    contracts._check_plan_geometry(p, d, ts, JOB)


@pytest.mark.entry("E4:backfill_gap_hold")
@E4
@given(guarded())
def test_property_backfill_and_gap_hold_hold(case: tuple[Tracks, Decisions, Plan]) -> None:
    ts, d, p = case
    owner = {t: i.item_id for i in d.items for t in i.track_ids}
    items = {i.item_id: i for i in d.items}
    hold = int(2.0 * FPS)
    for t in ts.tracks:
        item = owner[t.track_id]

        def want(box: tuple[int, int, int, int], frame: int) -> tuple[int, int, int, int] | None:
            return identity_box(t, box, items[item], ts=ts, p=p, frame=frame)  # noqa: B023 -- used within this iteration

        first_box, last_box = t.boxes[t.first], t.boxes[t.last]
        for frame in range(max(0, t.first - p.temporal.backfill), t.first):
            if (b := want(first_box, frame)) is not None:
                assert covered(p, frame, item, b), ("backfill", t.track_id, frame)
        for frame in range(t.last + 1, min(FRAMES, t.last + p.temporal.extend + 1)):
            if (b := want(last_box, frame)) is not None:
                assert covered(p, frame, item, b), ("extend", t.track_id, frame)
        keys = sorted(t.boxes)
        for before, after in itertools.pairwise(keys):
            if after - before - 1 > hold:
                continue
            for frame in range(before + 1, after):
                interp = g.box_at(t, frame)
                assert interp is not None
                b = want(interp, frame)
                if b is not None and all(e.mask is None for e in entries(p, frame, item)):
                    assert covered(p, frame, item, b), ("gap", t.track_id, frame)


@pytest.mark.entry("E4:locked_grid_fixed")
@E4
@given(guarded())
def test_property_locked_grids_never_move(case: tuple[Tracks, Decisions, Plan]) -> None:
    _, d, p = case
    for item in d.items:
        grids = {e.grid for es in p.frames.values() for e in es if e.item_id == item.item_id}
        if item.style == "pixelate":
            assert len(grids) == 1
            assert None not in grids
        else:
            assert grids <= {None}


def test_a_sliver_mask_in_a_small_box_falls_back_to_the_box() -> None:
    """Audit finding: dilation grew one stray pixel in a 30 px face box into a disk that 'spanned' it."""
    sliver = np.zeros((H, W), dtype=np.bool_)
    sliver[105, 115] = True
    ts = tracks(track("face:1", 10, 10, (100, 90, 130, 120), masks={10: g.encode(sliver)}))
    (e,) = entries(plan(JOB, ts, hide_all(ts)), 10, "i_1")
    assert e.shape == "box"
    assert covered(plan(JOB, ts, hide_all(ts)), 10, "i_1", (100, 90, 130, 120))


def test_a_reentry_gap_is_held_up_to_2_s() -> None:
    """DESIGN §2.6's gap hold survives SAM splitting a lost object into a re-entry (a new track)."""
    first = track("face:1", 0, 5, (40, 40, 60, 60))
    again = track("face:2", 50, 59, (40, 40, 60, 60), reentry_of="face:1")
    ts = tracks(first, again, sam_fps=30)
    p = plan(JOB, ts, hide_all(ts))
    assert p.temporal.backfill == 15
    for frame in range(6, 50):  # extend, then the hold, then the re-entry's back-fill: never bare
        assert covered(p, frame, "i_1", (40, 40, 60, 60)) or covered(p, frame, "i_2", (40, 40, 60, 60)), frame


@settings(max_examples=300, deadline=None)
@given(st.integers(0, 60), st.integers(0, 60), st.integers(1, 40), st.integers(1, 40))
def test_property_dilation_contains_the_exact_elliptical_one(cx: int, cy: int, rx: int, ry: int) -> None:
    mask = np.zeros((90, 120), dtype=np.bool_)
    mask[cy : cy + 9, cx : cx + 13] = True
    mask[cy + 20 : cy + 22, cx + 30 : cx + 31] = True
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rx + 1, 2 * ry + 1))
    exact = cv2.dilate(mask.astype(np.uint8), kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    got = g.dilate(mask, rx, ry)
    assert (got | ~exact).all()


def test_a_crowd_fill_covers_every_tracked_object_kept_ones_too() -> None:
    """DESIGN §2.6 "fill the whole crowded region": SAM's cap dropped objects somewhere among the ones it kept, so the
    fill spans every track on the crowded frames, a kept participant's too, never just the hidden ones."""
    host = track("face:1", 0, 20, (10, 10, 30, 30))
    other = track("face:2", 0, 20, (200, 100, 230, 130))
    ts = tracks(host, other, crowded=[10, 11])
    decided = hide_all(ts)
    kept = Decisions(items=[decided.items[0].model_copy(update={"decision": "keep", "style": None}), decided.items[1]])
    (fill,) = plan(JOB, ts, kept).crowd_fills
    assert g.contains(fill.box, (10, 10, 30, 30))
    assert g.contains(fill.box, (200, 100, 230, 130))


def test_removing_a_face_only_person_covers_a_body_under_the_face() -> None:
    ts = tracks(track("face:1", 0, 20, (100, 20, 120, 40)))
    removed = apply_review(hide_all(ts), [EDIT.validate_python({"type": "remove_person", "edit_id": "r",
                                                                 "item_id": "i_1"})]).decisions  # fmt: skip
    p = plan(JOB, ts, removed)
    (e,) = entries(p, 10, "i_1")
    assert e.style == "person_solid"
    assert g.contains(e.box, (70, 20, 150, H))  # a face width out each side, down to the frame's bottom here
    assert body_below((100, 20, 120, 40), W, H) == (80, 20, 140, 180)


def test_cached_regions_plan_exactly_as_fresh_ones() -> None:
    t1 = track("face:1", 10, 14, (70, 60, 131, 121), masks={10: disk(100, 90, 30), 14: disk(100, 90, 30)})
    t2 = track("face:2", 0, 40, (200, 100, 230, 130), step=(1, 0), anchors=[0, 1, 2, 30, 31, 40])
    ts = tracks(t1, t2)
    decided = hide_all(ts)
    cache: dict[Any, Any] = {}
    first = plan(JOB, ts, decided, cache=cache)
    assert cache
    edited = Decisions(items=[decided.items[0].model_copy(update={"style": "solid"}), decided.items[1]])
    assert plan(JOB, ts, edited, cache=cache) == plan(JOB, ts, edited)
    assert plan(JOB, ts, decided, cache=cache) == first


def test_the_guard_stage_reuses_regions_until_the_tracks_change(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(Path("fixtures/contracts/j_example"), job_dir)
    first = guard_run(job_dir).read_text()
    assert guard_run(job_dir).read_text() == first
    contracts.validate_job_dir(job_dir)
    (job_dir / "tracks.json").write_text((job_dir / "tracks.json").read_text() + "\n")  # a new tracks.json
    assert guard_run(job_dir).read_text() == first


def test_a_prominent_bystander_is_hidden_by_the_face_and_only_remove_person_covers_the_body() -> None:
    """DESIGN §2.7: identity only. A prominent bystander's face is mosaicked and their body stays in the shot; the
    creator's Remove person covers the whole person, with an estimated body where the body track (10-30) is shorter
    than the face's (0-50)."""
    face = track("face:1", 0, 50, (130, 25, 160, 55))
    body = track("person:1", 10, 30, (100, 20, 200, 170))
    ts = tracks(face, body)
    by = ("bystander",) * 3
    decided = decide(Inputs(job=JOB, tracks=ts, roles=roles(row("face:1", *by), row("person:1", *by))))
    (item,) = decided.items
    assert (item.style, item.track_ids) == ("pixelate", ["face:1", "person:1"])
    p = plan(JOB, ts, decided)
    for frame in (0, 5, 20, 45, 50):
        assert covered(p, frame, "i_1", (130, 25, 160, 55)), frame
        assert not hidden_mask(entries(p, frame, "i_1"), [], H, W)[80:].any(), frame  # the body stays in the shot
    removed = apply_review(decided, [EDIT.validate_python({"type": "remove_person", "edit_id": "r",
                                                            "item_id": "i_1"})]).decisions  # fmt: skip
    p = plan(JOB, ts, removed)
    for frame in (0, 5, 20, 45, 50):
        assert covered(p, frame, "i_1", (120, 55, 170, H)), frame  # below the face, to the frame's bottom


def test_a_read_through_whole_person_stays_whole_when_it_goes_solid() -> None:
    """redteam.md re-renders a read-through item solid; that never shrinks a whole-person cover to the face."""
    ts = tracks(track("face:1", 0, 20, (150, 20, 170, 40)))
    removed = apply_review(hide_all(ts), [EDIT.validate_python({"type": "remove_person", "edit_id": "r",
                                                                 "item_id": "i_1"})]).decisions  # fmt: skip
    p = plan(JOB, ts, removed, solid={"i_1"})
    (e,) = entries(p, 10, "i_1")
    assert e.style == "solid"
    assert covered(p, 10, "i_1", (140, 40, 180, H))


def test_a_merged_face_away_from_the_items_body_still_gets_a_body() -> None:
    """A whole-person item's body region covers its own frames; a merged face elsewhere in the frame (a re-entry's
    back-fill while the old body is held) gets its own estimated body, not the far-away one's."""
    body = track("person:1", 0, 20, (10, 5, 60, 170))
    face = track("face:2", 40, 100, (250, 20, 270, 40), reentry_of="person:1")
    ts = tracks(body, face)
    decided = hide_all(ts)
    merged = Decisions(items=[DecisionItem.model_validate({**decided.items[0].model_dump(), "track_ids": [
        "person:1", "face:2"], "style": "person_solid", "decision": "hide", "decided_by": "creator",
        "removed_by_creator": True})])  # fmt: skip
    p = plan(JOB, ts, merged)
    for frame in (25, 30):  # face:2's back-fill, person:1's extend/hold region elsewhere
        assert covered(p, frame, "i_1", (245, 40, 275, H)), frame


def test_back_fill_of_a_fast_moving_face_stays_at_its_first_box() -> None:
    """DESIGN §2.6 (owner, 11-04): a cover never runs ahead of its object. A small face crossing the frame fast gets
    half a second of back-fill at its first box, held still, and nothing before that or along its path."""
    t = track("face:1", 20, 28, (200, 80, 220, 100), step=(10, 0), anchors=[20, 24, 28])
    ts = tracks(t)
    p = plan(job(fps=30), ts, hide_all(ts))
    assert min(p.frames) == 20 - 15
    for frame in range(5, 20):
        assert covered(p, frame, "i_1", (200, 80, 220, 100)), frame
        (e,) = entries(p, frame, "i_1")
        assert e.box[0] >= 200 - 2 - 3 - 8 - 1, (frame, e.box)
