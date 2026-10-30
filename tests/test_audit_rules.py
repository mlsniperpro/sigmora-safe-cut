"""WP4 audit rules, pure: leak decisions (TEST-VECTORS L1-L14), grid mapping (G7-G14), sampling, patches, spots."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from safecut.audit import leaks as rules
from safecut.contracts import DecisionItem, Decisions, Leak, Plan
from safecut.decide import geometry as g
from safecut.decide.geometry import iou as iou_of
from safecut.scout.grid import BAR_H as ROLE_PASS_BAR
from tests.safety_factories import track, tracks

W, H = 1280, 720


def item(item_id: str, track_ids: list[str], decision: str = "keep", kind: str = "person") -> DecisionItem:
    style = None if decision == "keep" else "solid"
    return DecisionItem.model_validate({"item_id": item_id, "track_ids": track_ids, "kind": kind,
                                        "decision": decision, "reason": "r", "evidence_frames": [], "style": style,
                                        "decided_by": "policy" if decision != "keep" else "creator",
                                        "locked": False})  # fmt: skip


def frame50(*specs: tuple[str, tuple[int, int, int, int]]) -> dict[str, Any]:
    return {tid: track(tid, 50, 50, box) for tid, box in specs}


A = frame50(("face:1", (100, 100, 200, 200)))
KEPT_A = Decisions(items=[item("i_7", ["face:1"])])


@pytest.mark.parametrize(
    ("kind", "box", "leak"),
    [
        ("face", (110, 110, 190, 190), False),  # L1: IoU 0.64, same kind
        ("face", (180, 100, 280, 200), True),  # L2: IoU 0.11
        ("text", (110, 110, 190, 190), True),  # L3: kind doesn't match a face track
        ("face", (600, 300, 650, 360), True),  # L4: confidence never filters (no item there)
        ("misaligned_redaction", (110, 110, 190, 190), True),  # never excluded
        ("other", (110, 110, 190, 190), True),
    ],
)
def test_leak_decision_vectors(kind: Any, box: tuple[int, int, int, int], leak: bool) -> None:
    got = rules.excluded_by(kind, box, 50, KEPT_A, A)
    assert (got is None) == leak
    if not leak:
        assert got == "i_7"


def test_l11_a_text_finding_on_a_kept_non_personal_object_is_excused() -> None:
    menu = frame50(("menu:1", (100, 100, 200, 200)))
    decisions = Decisions(items=[item("i_8", ["menu:1"], kind="other")])
    assert rules.excluded_by("text", (110, 110, 190, 190), 50, decisions, menu) == "i_8"


def test_l12_a_kept_person_box_never_excuses_a_face() -> None:
    body = frame50(("person:1", (80, 60, 260, 560)))
    decisions = Decisions(items=[item("i_9", ["person:1"])])
    assert rules.excluded_by("face", (120, 110, 160, 150), 50, decisions, body) is None


def test_l13_a_plate_matches_only_a_plate_track() -> None:
    screen = frame50(("screen:2", (290, 390, 390, 440)))
    plate = frame50(("license plate:1", (290, 390, 390, 440)))
    finding = (300, 400, 380, 430)
    assert rules.excluded_by("plate", finding, 50, Decisions(items=[item("i_5", ["screen:2"], kind="screen")]),
                             screen) is None  # fmt: skip
    assert rules.excluded_by("plate", finding, 50, Decisions(items=[item("i_6", ["license plate:1"], kind="plate")]),
                             plate) == "i_6"  # fmt: skip


def test_hidden_items_and_other_frames_never_excuse() -> None:
    hidden = Decisions(items=[item("i_7", ["face:1"], decision="hide")])
    assert rules.excluded_by("face", (110, 110, 190, 190), 50, hidden, A) is None
    assert rules.excluded_by("face", (110, 110, 190, 190), 51, KEPT_A, A) is None
    assert rules.excluded_by("face", (110, 110, 190, 190), 50, KEPT_A, {}) is None


def plan_with(frame: int, *entries: tuple[str, tuple[int, int, int, int]]) -> Plan:
    return Plan.model_validate({
        "padding": {"face": 0.15, "default": 0.08, "px": 8}, "temporal": {"extend": 8, "backfill": 57, "gap_hold_s": 2},
        "frames": {str(frame): [{"item_id": i, "shape": "box", "box": b, "mask": None, "style": "solid", "grid": None}
                                for i, b in entries]},
    })  # fmt: skip


def test_l14_the_read_through_item_covers_the_largest_share() -> None:
    decisions = Decisions(items=[item("i_1", ["face:1"], "hide"), item("i_2", ["face:2"], "hide")])
    plan = plan_with(50, ("i_1", (150, 80, 400, 300)), ("i_2", (0, 120, 120, 300)))
    assert rules.through_item((100, 100, 200, 140), 50, decisions, plan) == "i_1"
    assert rules.through_item((500, 500, 600, 600), 50, decisions, plan) is None
    assert rules.through_item((100, 100, 200, 140), 51, decisions, plan) is None


def test_an_audit_patch_is_never_read_through() -> None:
    patch = DecisionItem.model_validate({
        "item_id": "p_1", "track_ids": [], "kind": "other", "decision": "hide", "reason": "r",
        "evidence_frames": [50], "style": "solid", "decided_by": "policy", "locked": True, "origin": "audit_patch",
        "audit_label": "A1", "box": [100, 100, 200, 200], "first": 40, "last": 60,
    })  # fmt: skip
    assert (
        rules.through_item((100, 100, 200, 140), 50, Decisions(items=[patch]), plan_with(50, ("p_1", (0, 0, 9, 9))))
        is None
    )


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ([100, 100, 300, 400], (128, 36, 384, 264)),  # G7
        ([100, 0, 300, 40], "in_bar"),  # G8 / G8b: the caller decides
        ([500, 500, 501, 501], (624, 324, 656, 356)),  # G10: degenerate → 32 px
        ([-5, 60, 1001, 1001], (0, 6, 1280, 720)),  # G11
        ([300, 100, 100, 400], (128, 36, 384, 264)),  # G12: reversed corners
        ([100, 40, 300, 60], (128, 0, 384, 6)),  # G13: straddles the bar
        ([0, 60, 10, 61], (0, 0, 22, 22)),  # G14
        ([1, 2, 3], None),  # malformed → whole-frame leak by the caller
    ],
)
def test_grid_vectors(raw: list[int], want: Any) -> None:
    assert rules.grid_box(raw, width=W, height=H, bar=40) == want


def test_bar_height_and_frame_label() -> None:
    # API-NOTES §5: bar_h = 40 sent pixels for every clip, the same bar as the role pass (redteam.md Inputs).
    assert rules.bar_height(720) == rules.bar_height(180) == rules.bar_height(1920) == ROLE_PASS_BAR == 40
    assert rules.is_frame_label("F 000090")
    assert not rules.is_frame_label("AMINA")
    assert not rules.is_frame_label(None)
    assert not rules.is_frame_label("F")


@settings(max_examples=500, deadline=None)
@given(st.lists(st.integers(-50, 1050), min_size=4, max_size=4), st.sampled_from([(1280, 720), (320, 180), (640, 360)]))
def test_property_grid_boxes_are_in_frame_and_non_empty(raw: list[int], size: tuple[int, int]) -> None:
    w, h = size
    got = rules.grid_box(raw, width=w, height=h, bar=rules.bar_height(h))
    if got != "in_bar":
        assert got is not None
        assert 0 <= got[0] < got[2] <= w
        assert 0 <= got[1] < got[3] <= h


def test_sampling_takes_1_fps_track_edges_gaps_and_flagged_frames() -> None:
    t = track("face:1", 70, 200, anchors=[70, 71, 190, 200])
    plan = plan_with(0)
    got = rules.sample_frames(300, 30, tracks(t), plan, extra=[77, 999])
    assert {0, 30, 60, 90, 270} <= set(got)
    assert {0, 12, 209, 216, 130, 77} <= set(got)  # 70-57-8 clamps to 0; 70-57-1; 200+8+1; 200+8+8; gap middle
    assert 999 not in got
    assert got == sorted(set(got))


def leak(frame: int, box: tuple[int, int, int, int], kind: Any = "face") -> Leak:
    return Leak(frame=frame, box=box, kind=kind, detector="egoblur", patched_item=None)


def test_leaks_that_touch_within_a_step_share_a_patch() -> None:
    run = [leak(10, (10, 10, 30, 30)), leak(11, (12, 10, 32, 30)), leak(40, (14, 10, 34, 30)),
           leak(11, (200, 10, 230, 40), "plate")]  # fmt: skip
    groups = rules.group_leaks(run, step=30)
    assert [(g.first, g.last, g.box) for g in groups] == [(10, 40, (10, 10, 34, 30)), (11, 11, (200, 10, 230, 40))]
    patch = rules.make_patch(groups[0], 3, 5, frames=60, sample_step=30, extend=8)
    assert patch.model_dump(include={"item_id", "audit_label", "first", "last", "evidence_frames", "kind"}) == {
        "item_id": "p_3", "audit_label": "A5", "first": 0, "last": 59, "evidence_frames": [10], "kind": "person"
    }  # fmt: skip
    assert rules.patch_kind(["plate", "text"]) == "plate"
    assert rules.patch_kind(["text"]) == "other"


def test_next_numbers_and_spots() -> None:
    assert rules.next_numbers(Decisions(items=[])) == (1, 1)
    spots = rules.make_spots([leak(10, (10, 10, 30, 30)), leak(10, (20, 10, 40, 30)), leak(90, (10, 10, 30, 30))], 30)
    assert [(s.spot_id, s.first, s.last, s.boxes) for s in spots] == [
        ("s1", 10, 10, {10: (10, 10, 40, 30)}),
        ("s2", 90, 90, {90: (10, 10, 30, 30)}),
    ]


def test_leaks_merge_only_at_iou_0_3_or_more() -> None:
    """API-NOTES §12: consecutive leaks of one object merge at IoU ≥ 0.3; boxes that merely touch stay apart."""
    near = [leak(10, (10, 10, 30, 30)), leak(12, (25, 10, 45, 30))]  # IoU 5/35 ≈ 0.14
    assert len(rules.group_leaks(near, step=30)) == 2
    same = [leak(10, (10, 10, 30, 30)), leak(12, (14, 10, 34, 30))]  # IoU 16/24 ≈ 0.67
    assert len(rules.group_leaks(same, step=30)) == 1


def test_exclusion_uses_the_kept_tracks_visible_mask_where_it_has_one() -> None:
    """redteam.md: a finding is excused by the *visible* region of a kept item: its SAM mask on that frame."""
    yy, xx = np.mgrid[0:180, 0:320]
    thin = (np.abs(xx - 150) <= 8) & (yy >= 20) & (yy < 160)  # a thin pole-like body inside a wide box
    body = {"person:1": track("person:1", 50, 50, (100, 20, 200, 160), masks={50: g.encode(thin)})}
    kept = Decisions(items=[item("i_7", ["person:1"])])
    beside = (100, 20, 140, 160)  # inside the kept box (box IoU 0.4) but off its visible body
    assert iou_of((100, 20, 200, 160), beside) > rules.EXCLUDE_IOU
    assert rules.excluded_by("person", beside, 50, kept, body) is None
    assert rules.excluded_by("person", (140, 20, 160, 160), 50, kept, body) == "i_7"  # on the body itself
    boxed = {"person:1": track("person:1", 50, 50, (100, 20, 200, 160))}  # no mask: its box
    assert rules.excluded_by("person", beside, 50, kept, boxed) == "i_7"
