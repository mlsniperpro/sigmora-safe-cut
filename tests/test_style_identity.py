"""Lane STYLE (2026-11-04): hide identity, not the shot (DESIGN §2.6, §2.7).

* a hidden person or child is covered face/head only (the locked-grid mosaic, or solid over a head estimate with no
  face to size it); ``person_solid`` is only the creator's Remove person;
* a held cover never moves ahead of its object: half a second of back-fill, the first box held still and grown at
  most 10 %; after the last box and through gaps, held still and grown at most 25 %;
* no cover hides a kept participant's face (``keep_clear``), except a child's and an audit patch;
* the face mosaic at its real cell size is not a face to the live audit detector (YuNet);
* the live street-interview job that showed covers "everywhere" now covers only where its objects are.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from safecut import contracts as c
from safecut.audit.detectors import YuNet
from safecut.contracts import DecisionItem, Decisions, Job, Plan, PlanEntry, Track, Tracks
from safecut.decide import geometry as g
from safecut.decide.policy import style_for
from safecut.decide.review import ReviewEdit, apply_review
from safecut.guard.plan import MAX_BLOCKS, PADDING, backfill_frames, plan
from safecut.guard.regions import MAX_GROWTH, MAX_GROWTH_BEFORE, TrackRegions, held_box
from safecut.render.draw import apply, hidden_mask
from tests.safety_factories import H, W, job, track, tracks
from tests.safety_jobs import draw_face

EDIT: TypeAdapter[ReviewEdit] = TypeAdapter(ReviewEdit)
FIXTURE = Path(__file__).parent / "fixtures" / "live_street_2026_11_04.json"


def item(item_id: str, track_ids: list[str], kind: str = "person", **over: Any) -> DecisionItem:
    data: dict[str, Any] = {
        "item_id": item_id,
        "track_ids": track_ids,
        "kind": kind,
        "decision": "hide",
        "reason": "test",
        "evidence_frames": [],
        "style": "solid",
        "decided_by": "policy",
        "locked": kind == "child",
    }
    return DecisionItem.model_validate(data | over)


def check(p: Plan, decisions: Decisions, ts: Tracks, j: Job) -> None:
    """The contract checker's plan rules (what ``validate_job_dir`` runs on a job's plan)."""
    c._check_plan_covers(p, decisions, ts, j)  # pyright: ignore[reportPrivateUsage] -- the unit under test
    c._check_plan_styles(p, decisions, None)  # pyright: ignore[reportPrivateUsage]
    c._check_plan_geometry(p, decisions, ts, j)  # pyright: ignore[reportPrivateUsage]


def drawn(p: Plan, frame: int, item_id: str | None = None) -> np.ndarray:
    entries = [e for e in p.frames.get(frame, []) if item_id is None or e.item_id == item_id]
    return hidden_mask(entries, [f for f in p.crowd_fills if frame in f.frames], H, W)


# ------------------------------------------------------------------------------------------------ styles (§2.7)


@pytest.mark.parametrize("kind", ["person", "child"])
def test_people_and_children_are_covered_face_only(kind: str) -> None:
    face, body = track("face:1", 0, 9, (100, 20, 140, 70)), track("person:1", 0, 9, (80, 10, 170, 179))
    assert style_for(kind, [face, body]) == "pixelate"  # type: ignore[arg-type] -- a policy kind
    assert style_for(kind, [body]) == "solid"  # type: ignore[arg-type]
    assert style_for("plate", [track("license plate:1", 0, 9)]) == "solid"


def test_a_re_hidden_person_never_gets_the_whole_person() -> None:
    ts = tracks(track("face:1", 0, 9, (100, 20, 140, 70)), track("person:1", 0, 9, (80, 10, 170, 179)))
    kept = item("i_1", ["face:1", "person:1"], decision="keep", style=None, decided_by="creator")
    hide = [EDIT.validate_python({"type": "hide", "edit_id": "e1", "item_id": "i_1"})]
    assert apply_review(Decisions(items=[kept]), hide, tracks=ts, job=job()).decisions.items[0].style == "pixelate"
    alone = apply_review(Decisions(items=[kept]), hide).decisions  # from the track ids alone
    assert alone.items[0].style == "pixelate"


def test_a_hidden_person_draws_their_face_not_their_body() -> None:
    j = job()
    face = track("face:1", 10, 49, (120, 20, 160, 70))
    body = track("person:1", 0, 59, (100, 10, 190, 179))
    ts = tracks(face, body)
    d = Decisions(items=[item("i_1", ["face:1", "person:1"], style="pixelate")])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    backfill, padded_face = backfill_frames(j), g.grow((120, 20, 160, 70), PADDING.face, PADDING.px, W, H)
    for f in range(face.first, face.last + 1):
        mask = drawn(p, f)
        assert mask[padded_face[1] : padded_face[3], padded_face[0] : padded_face[2]].all()  # the face is hidden
        assert not mask[110:].any()  # nothing below the head: the body stays in the shot
    # Before the face is seen (and its back-fill), the body draws only a head estimate: its top, mosaicked.
    head = c.head_box((100, 10, 190, 179))
    assert head == (100, 10, 190, 48)
    for f in range(face.first - backfill):
        mask = drawn(p, f)
        assert mask[head[1] : head[3], head[0] : head[2]].all()
        assert not mask[80:].any()
        assert {e.style for e in p.frames[f]} == {"pixelate"}


def test_a_hidden_person_without_a_face_gets_a_solid_head_estimate() -> None:
    j, body = job(), track("person:1", 0, 59, (100, 10, 190, 179))
    ts = tracks(body)
    d = Decisions(items=[item("i_1", ["person:1"], style="solid")])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    for f in range(60):
        assert {e.style for e in p.frames[f]} == {"solid"}
        assert not drawn(p, f)[80:].any()


def test_only_remove_person_covers_the_whole_body() -> None:
    j = job()
    ts = tracks(track("face:1", 0, 59, (120, 20, 160, 70)), track("person:1", 0, 59, (100, 10, 190, 179)))
    removed = item("i_1", ["face:1", "person:1"], style="person_solid", decided_by="creator", removed_by_creator=True)
    d = Decisions(items=[removed])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    assert drawn(p, 30)[100:179, 100:190].all()


def test_the_checker_refuses_a_body_left_bare_where_no_face_is_planned() -> None:
    j, body = job(), track("person:1", 0, 59, (100, 10, 190, 179))
    ts = tracks(body)
    d = Decisions(items=[item("i_1", ["person:1"], style="solid")])
    p = plan(j, ts, d)
    p.frames[30] = [PlanEntry(item_id="i_1", shape="box", box=(100, 100, 190, 179), mask=None, style="solid",
                              grid=None)]  # fmt: skip
    with pytest.raises(c.ContractError, match="i_1 doesn't cover person:1"):
        check(p, d, ts, j)


# ----------------------------------------------------------------------------------------- held covers (§2.6)


def test_a_track_first_seen_at_frame_100_has_no_cover_before_its_half_second() -> None:
    j = job(200)
    plate = track("license plate:1", 100, 150, (100, 100, 140, 120), step=(1, 0))
    ts = tracks(plate)
    d = Decisions(items=[item("i_1", ["license plate:1"], kind="plate")])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    lead = math.ceil(0.5 * j.fps)
    assert p.temporal.backfill == lead == 15
    assert min(f for f, es in p.frames.items() if es) == 100 - lead
    # Held still (no sweep along the motion), grown at most 10 % each side before the first box.
    edge = g.grow(g.grow((100, 100, 140, 120), 0, 0, W, H), 0, 0, W, H)
    widest = g.grow((96, 98, 144, 122), PADDING.default, PADDING.px, W, H)
    for f in range(100 - lead, 100):
        (entry,) = p.frames[f]
        assert g.contains(widest, entry.box), (f, entry.box)
        assert g.contains(entry.box, g.grow(edge, PADDING.default, PADDING.px, W, H))


@settings(max_examples=300, deadline=None)
@given(
    x=st.integers(0, 250),
    y=st.integers(0, 140),
    w=st.integers(4, 60),
    h=st.integers(4, 30),
    distance=st.integers(0, 120),
    after=st.booleans(),
)
def test_a_held_box_stays_within_four_times_its_edge_box(  # noqa: PLR0917 -- hypothesis draws each one
    x: int, y: int, w: int, h: int, distance: int, after: bool
) -> None:
    edge = (x, y, min(W, x + w), min(H, y + h))
    held = held_box(edge, distance, MAX_GROWTH if after else MAX_GROWTH_BEFORE, W, H)
    assert g.contains(held, edge)
    padded = g.grow(edge, PADDING.default, PADDING.px, W, H)
    assert g.area(g.grow(held, PADDING.default, PADDING.px, W, H)) <= 4 * g.area(padded)


def test_a_long_gap_holds_the_object_where_it_is_not_across_the_frame() -> None:
    gappy = track("license plate:1", 0, 100, (10, 10, 30, 20), anchors=[0, 100])
    gappy = gappy.model_copy(update={"boxes": {0: (10, 10, 30, 20), 100: (280, 150, 300, 160)}})
    regions = TrackRegions(gappy, ratio=0, px=0, width=W, height=H, interp_gap=4)
    for f in range(1, 100):
        box = regions.at(f).box
        assert g.area(box) <= 4 * 20 * 10, (f, box)


# ------------------------------------------------------------------------------------- kept faces stay clear


def test_a_bystander_cover_leaves_the_kept_presenters_face_untouched() -> None:
    j = job()
    presenter = track("face:1", 0, 59, (130, 30, 170, 80))
    bystander = track("person:2", 0, 59, (60, 0, 200, 179))  # behind the presenter, padded body over their face
    kid = track("face:3", 0, 59, (150, 60, 175, 90))
    ts = tracks(presenter, bystander, kid)
    kept = item("i_1", ["face:1"], decision="keep", style=None, decided_by="model", reason="participant")
    hidden = item("i_2", ["person:2"], style="person_solid", decided_by="creator", removed_by_creator=True)
    child = item("i_3", ["face:3"], kind="child", style="pixelate")
    d = Decisions(items=[kept, hidden, child])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    face = g.grow((130, 30, 170, 80), PADDING.face, PADDING.px, W, H)
    frame = np.full((H, W, 3), 128, dtype=np.uint8)
    frame[face[1] : face[3], face[0] : face[2]] = (10, 200, 30)
    for f in (0, 30, 59):
        bystander_mask = drawn(p, f, "i_2")
        assert bystander_mask.any()
        assert not bystander_mask[face[1] : face[3], face[0] : face[2]].any()
        out = apply(frame, p.frames[f], [])
        child_cover = drawn(p, f, "i_3")  # a child always wins: its cover is never clipped
        bare = np.zeros((H, W), dtype=np.bool_)
        bare[face[1] : face[3], face[0] : face[2]] = True
        bare &= ~child_cover
        assert (out[bare] == frame[bare]).all()
        assert child_cover[60:90, 150:175].all()
    assert all(not e.keep_clear for es in p.frames.values() for e in es if e.item_id == "i_3")


def test_the_checker_refuses_a_clear_box_that_is_no_kept_face() -> None:
    j = job()
    ts = tracks(track("face:1", 0, 59, (130, 30, 170, 80)), track("license plate:2", 0, 59, (20, 120, 80, 150)))
    d = Decisions(items=[item("i_2", ["license plate:2"], kind="plate")])
    p = plan(j, ts, d)
    p.frames[5] = [e.model_copy(update={"keep_clear": [(20, 120, 80, 150)]}) for e in p.frames[5]]
    with pytest.raises(c.ContractError, match="not a kept face"):
        check(p, d, ts, j)


# ------------------------------------------------------------------------------------- the audit can't see it


def test_the_face_mosaic_at_its_real_cell_size_is_not_a_face_to_yunet() -> None:
    """The live audit (``SAFECUT_AUDIT_GPU=0``) runs YuNet on every rendered frame; a face under the mosaic must not
    read as a face (were it to, the cells would have to get coarser, never finer)."""
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[:] = (90, 110, 80)
    draw_face(frame, 320, 180, 160, (150, 180, 220))
    yunet = YuNet()
    found = [d.box for d in yunet.detect(frame)]
    assert found, "precondition: YuNet sees the drawn face"
    face = max(found, key=g.area)
    j = job(1, width=640, height=360)
    ts = tracks(track("face:1", 0, 0, face))
    d = Decisions(items=[item("i_1", ["face:1"], style="pixelate")])
    p = plan(j, ts, d)
    (entry,) = p.frames[0]
    assert entry.grid is not None
    assert entry.grid[2] * MAX_BLOCKS >= face[2] - face[0]
    out = apply(frame, p.frames[0], [])
    assert not [b for b in (d.box for d in yunet.detect(out)) if g.intersection(b, face) > 0]


# ---------------------------------------------------------------------------- the live street job (regression)


def street() -> tuple[Job, Tracks, Decisions]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = data["job"]
    j = Job(job_id=data["job_id"], source="street-interview.mp4", source_sha256="0" * 64, prepared="prepared.mp4",
            fps=raw["fps"], width=raw["width"], height=raw["height"], frames=raw["frames"], times=raw["times"],
            audio=raw["audio"], created_at=raw["created_at"])  # fmt: skip
    ts: list[Track] = [
        Track(
            track_id=t["track_id"],
            concept=t["concept"],
            first=t["first"],
            last=t["last"],
            boxes={int(k): tuple(v) for k, v in t["boxes"].items()},
            reentry_of=t.get("reentry_of"),
            source="sam-3.1",
            prompt=t["concept"],
            child_phrase=t.get("child_phrase", False),
        )
        for t in data["tracks"]
    ]
    # The live plan's back-fill was the old ceil(15 x fps / sam_fps): it gives the clip's SAM rate.
    sam_fps = math.ceil(15 * j.fps / data["temporal"]["backfill"])
    ts_all = Tracks(concepts=sorted({t.concept for t in ts}), sam_fps=sam_fps, sam_frames=j.frames, tracks=ts)
    return j, ts_all, Decisions.model_validate({"items": data["items"]})


def test_the_street_job_covers_only_where_its_objects_are() -> None:
    j, ts, d = street()
    # The live policy gave held participants person_solid; under the new rule a policy never does (re-decided here
    # the way policy.style_for would: by the item's kind and tracks).
    by_id = {t.track_id: t for t in ts.tracks}
    restyled: list[DecisionItem] = []
    for i in d.items:
        if i.style is not None and not i.removed_by_creator:
            i = i.model_copy(update={"style": style_for(i.kind, [by_id[t] for t in i.track_ids])})  # type: ignore[arg-type]  # noqa: PLW2901
        restyled.append(i)
    d = Decisions(items=restyled)
    p = plan(j, ts, d)
    check(p, d, ts, j)
    hidden = {t for i in d.items if i.decision != "keep" for t in i.track_ids}
    for frame in range(j.frames):
        entries = p.frames.get(frame, [])
        mask = hidden_mask(entries, [], j.height, j.width)
        live = np.zeros_like(mask)
        for t in (by_id[t] for t in hidden):
            box = t.boxes.get(frame)
            if box is not None:
                x1, y1, x2, y2 = g.grow(box, PADDING.face, PADDING.px, j.width, j.height)
                live[y1:y2, x1:x2] = True
        # No frame is covered beyond a quarter of the frame except where live tracks themselves are.
        assert float((mask & ~live).mean()) <= 0.25, frame
        for e in entries:  # every held entry stays within 4x its object's padded box
            assert g.area(e.box) <= 0.25 * j.width * j.height or live[e.box[1] : e.box[3], e.box[0] : e.box[2]].any()
    assert float(hidden_mask(p.frames.get(210, []), [], j.height, j.width).mean()) < 0.25  # was ~95 % live


def test_a_hidden_face_is_never_uncovered_to_keep_a_kept_face_clear() -> None:
    """A bystander's face slides into the presenter's padded face: its padding gives way, its face never does (the
    audit would only patch it back over both)."""
    j = job()
    presenter = track("face:1", 0, 59, (130, 30, 170, 80))
    bystander = track("face:2", 0, 59, (172, 40, 202, 75))  # right beside the presenter's face, inside its padding
    ts = tracks(presenter, bystander)
    kept = item("i_1", ["face:1"], decision="keep", style=None, decided_by="model", reason="participant")
    hidden = item("i_2", ["face:2"], style="pixelate")
    d = Decisions(items=[kept, hidden])
    p = plan(j, ts, d)
    check(p, d, ts, j)
    for f in (0, 30, 59):
        assert drawn(p, f, "i_2")[40:75, 172:202].all()  # the bystander's face is fully covered
        assert not any(e.keep_clear for e in p.frames[f] if e.item_id == "i_2")
