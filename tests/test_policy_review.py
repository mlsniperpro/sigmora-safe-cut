"""WP3 step 4: creator overrides (``apply_review``) and the decide stage's replay of ``review.json``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter

from safecut import contracts
from safecut.contracts import Audit, DecisionItem, Decisions
from safecut.decide import run as decide_run
from safecut.decide.policy import Inputs, decide
from safecut.decide.review import PATCH_REASON, ReviewEdit, ReviewError, apply_review, effective
from tests.safety_factories import job, roles, row, scene, track, tracks, transcript
from tests.test_policy import E4, policy_inputs

EDIT: TypeAdapter[ReviewEdit] = TypeAdapter(ReviewEdit)


def edits(*raw: dict[str, Any]) -> list[ReviewEdit]:
    return [EDIT.validate_python(e) for e in raw]


def base_tracks() -> Any:
    return tracks(
        track("face:1", 0, 20, (10, 10, 30, 30)),
        track("face:2", 0, 20, (100, 10, 120, 30)),
        track("face:3", 0, 20, (200, 10, 220, 30)),
        track("face:4", 25, 35, (10, 10, 30, 30), reentry_of="face:1"),
    )


def base() -> Decisions:
    """i_1 kept participant (face:1), i_2 bystander (face:2), i_3 locked child (face:3), i_4 re-entry (face:4)."""
    ts = [
        track("face:1", 0, 20, (10, 10, 30, 30)),
        track("face:2", 0, 20, (100, 10, 120, 30)),
        track("face:3", 0, 20, (200, 10, 220, 30)),
        track("face:4", 25, 35, (10, 10, 30, 30), reentry_of="face:1"),
    ]
    p = ("participant",) * 3
    rs = [
        row("face:1", *p, matches_participant=0),
        row("face:2", *("bystander",) * 3),
        row("face:3", "child", "participant", "participant"),
        row("face:4", *p, matches_participant=0, frames=(26, 30)),
    ]
    got = decide(Inputs(job=job(), tracks=tracks(*ts), roles=roles(*rs), scene=scene(), transcript=transcript()))
    assert [i.decision for i in got.items] == ["keep", "hide", "hide", "needs_you"]
    return got


def by_id(d: Decisions) -> dict[str, DecisionItem]:
    return {i.item_id: i for i in d.items}


def test_keep_and_hide_are_the_creators() -> None:
    got = by_id(apply_review(base(), edits({"type": "keep", "edit_id": "a", "item_id": "i_2"})).decisions)
    assert (got["i_2"].decision, got["i_2"].decided_by, got["i_2"].style) == ("keep", "creator", None)
    hide = edits({"type": "hide", "edit_id": "b", "item_id": "i_1"})
    got = by_id(apply_review(base(), hide, tracks=base_tracks(), job=job()).decisions)  # exactly the policy's style
    assert (got["i_1"].decision, got["i_1"].decided_by, got["i_1"].style) == ("hide", "creator", "pixelate")
    got = by_id(apply_review(base(), hide).decisions)  # without the tracks: its face track id says mosaic
    assert got["i_1"].style == "pixelate"


def test_a_locked_child_can_not_be_kept_or_merged() -> None:
    with pytest.raises(ReviewError) as err:
        apply_review(base(), edits({"type": "keep", "edit_id": "a", "item_id": "i_3"}))
    assert (err.value.code, err.value.edit_id) == ("locked", "a")
    with pytest.raises(ReviewError, match="locked"):
        apply_review(base(), edits({"type": "merge", "edit_id": "m", "item_id": "i_3", "into": "i_1"}))


def test_merge_a_reentry_into_a_kept_participant() -> None:
    got = apply_review(base(), edits({"type": "merge", "edit_id": "m", "item_id": "i_4", "into": "i_1"})).decisions
    items = by_id(got)
    assert "i_4" not in items
    assert (items["i_1"].track_ids, items["i_1"].decided_by) == (["face:1", "face:4"], "creator")


@pytest.mark.parametrize(
    "edit",
    [
        {"type": "merge", "edit_id": "m", "item_id": "i_4", "into": "i_2"},  # into a hidden item
        {"type": "merge", "edit_id": "m", "item_id": "i_4", "into": "i_4"},  # into itself
        {"type": "merge", "edit_id": "m", "item_id": "i_9", "into": "i_1"},  # unknown
        {"type": "keep", "edit_id": "k", "item_id": "i_9"},
    ],
)
def test_invalid_edits_are_refused(edit: dict[str, Any]) -> None:
    with pytest.raises(ReviewError):
        apply_review(base(), edits(edit))


def test_remove_person_is_a_whole_person_solid_hide_recorded_on_the_item() -> None:
    got = by_id(apply_review(base(), edits({"type": "remove_person", "edit_id": "r", "item_id": "i_1"})).decisions)
    item = got["i_1"]
    assert (item.decision, item.style, item.removed_by_creator, item.decided_by) == (
        "hide", "person_solid", True, "creator"
    )  # fmt: skip
    assert item.model_dump()["removed_by_creator"] is True
    assert "removed_by_creator" not in got["i_2"].model_dump()  # absent while false: old receipt hashes hold
    kept = by_id(apply_review(base(), edits({"type": "remove_person", "edit_id": "r", "item_id": "i_1"},
                                            {"type": "keep", "edit_id": "k", "item_id": "i_1"})).decisions)  # fmt: skip
    assert kept["i_1"].removed_by_creator is False


def test_remove_person_refuses_objects() -> None:
    d = decide(Inputs(job=job(), tracks=tracks(track("screen:1", 0, 5))))
    with pytest.raises(ReviewError, match="not a person"):
        apply_review(d, edits({"type": "remove_person", "edit_id": "r", "item_id": "i_1"}))


def test_a_removed_flag_on_anything_but_a_creator_hide_is_refused() -> None:
    item = base().items[0].model_dump()
    with pytest.raises(ValueError, match="removed person"):
        DecisionItem.model_validate({**item, "removed_by_creator": True})


def test_undo_drops_an_edit_and_an_undo_of_an_undo_restores_it() -> None:
    log = edits(
        {"type": "keep", "edit_id": "a", "item_id": "i_2"},
        {"type": "undo", "edit_id": "u", "reverts": "a"},
    )
    assert by_id(apply_review(base(), log).decisions)["i_2"].decision == "hide"
    log += edits({"type": "undo", "edit_id": "uu", "reverts": "u"})
    assert by_id(apply_review(base(), log).decisions)["i_2"].decision == "keep"
    assert [e.edit_id for e in effective(log + log)] == ["a"]  # a re-sent edit applies once


def test_an_edit_an_undo_left_inapplicable_is_skipped_not_fatal() -> None:
    log = edits(
        {"type": "keep", "edit_id": "k", "item_id": "i_4"},
        {"type": "merge", "edit_id": "m", "item_id": "i_2", "into": "i_4"},
        {"type": "undo", "edit_id": "u", "reverts": "k"},
        {"type": "hide", "edit_id": "h", "item_id": "i_1"},
    )
    result = apply_review(base(), log)
    assert result.skipped == ["m"]
    assert by_id(result.decisions)["i_1"].decision == "hide"


def audit_with_spot() -> Audit:
    return Audit.model_validate(
        {
            "frames_scanned": 60, "egoblur": {"model": "yunet-face", "faces": 1, "plates": None},
            "leaks": [{"frame": 12, "box": [40, 40, 60, 60], "kind": "face", "detector": "egoblur",
                       "patched_item": None, "unresolved": True}],
            "redteam": [{"frame": f, "finding": "none"} for f in (0, 30)],
            "unresolved": 1, "passes": 3, "sample_step": 30, "blocked_reason": "unresolved_leaks",
            "spots": [{"spot_id": "s1", "first": 12, "last": 14,
                       "boxes": {"12": [40, 40, 60, 60], "14": [44, 40, 64, 60]}}],
        }
    )  # fmt: skip


def test_cover_spot_adds_a_locked_audit_patch_and_marks_the_spot() -> None:
    result = apply_review(
        base(), edits({"type": "cover_spot", "edit_id": "c", "spot_id": "s1"}), audit=audit_with_spot(), frames=60
    )
    patch = by_id(result.decisions)["p_1"]
    assert patch.model_dump(include={"kind", "box", "first", "last", "evidence_frames", "audit_label", "locked"}) == {
        "kind": "person", "box": (40, 40, 64, 60), "first": 0, "last": 37, "evidence_frames": [12],
        "audit_label": "A1", "locked": True,
    }  # fmt: skip
    assert patch.reason == PATCH_REASON
    assert result.audit is not None
    assert result.audit.spots[0].covered_by == "p_1"
    # Covering a covered spot again (the log replayed over its own result) adds nothing.
    again = apply_review(result.decisions, edits({"type": "cover_spot", "edit_id": "c2", "spot_id": "s1"}),
                         audit=result.audit, frames=60)  # fmt: skip
    assert again.decisions == result.decisions
    assert again.audit == result.audit
    with pytest.raises(ReviewError, match="no spot s9"):
        apply_review(base(), edits({"type": "cover_spot", "edit_id": "c", "spot_id": "s9"}),
                     audit=audit_with_spot(), frames=60)  # fmt: skip
    with pytest.raises(ReviewError, match="needs the audit"):
        apply_review(base(), edits({"type": "cover_spot", "edit_id": "c", "spot_id": "s1"}))


def test_decide_stage_keeps_patches_and_replays_the_review(tmp_path: Path) -> None:
    src, dst = Path("fixtures/contracts/j_example"), tmp_path / "j_example"
    dst.mkdir()
    for name in ("job.json", "tracks.json", "roles.json", "scene.json", "transcript.json", "decisions.json"):
        shutil.copy(src / name, dst / name)
    review = [
        {"type": "keep", "edit_id": "a", "item_id": "i_3"},
        {"type": "cover_spot", "edit_id": "c", "spot_id": "s1"},
    ]
    (dst / "review.json").write_text(json.dumps(review))
    decide_run(dst)
    got = by_id(contracts.load(dst / "decisions.json", Decisions))
    assert got["i_3"].decided_by == "creator"
    assert got["p_1"].origin == "audit_patch"  # kept from the earlier decisions.json
    contracts.validate_job_dir(dst)


@pytest.mark.entry("E4:child_never_kept")
@E4
@given(policy_inputs(), st.lists(st.tuples(st.sampled_from(["keep", "hide", "merge", "remove_person", "undo"]),
                                           st.integers(0, 7), st.integers(0, 7)), max_size=8))  # fmt: skip
def test_property_children_are_never_kept_even_after_creator_edits(
    inputs: Inputs, raw: list[tuple[str, int, int]]
) -> None:
    decided = decide(inputs)
    ids = [i.item_id for i in decided.items]
    log: list[ReviewEdit] = []
    for n, (kind, a, b) in enumerate(raw):
        src, dst = ids[a % len(ids)], ids[b % len(ids)]
        spec: dict[str, Any] = {"type": kind, "edit_id": f"e{n}", "item_id": src}
        if kind == "merge":
            spec["into"] = dst
        if kind == "undo":
            spec = {"type": "undo", "edit_id": f"e{n}", "reverts": f"e{b % max(1, n)}"}
        candidate = [*log, EDIT.validate_python(spec)]
        try:
            apply_review(decided, candidate)
        except ReviewError:
            continue  # the API refuses it; the log stays as it was
        log = candidate
    final = apply_review(decided, log).decisions
    children = {t for i in decided.items if i.kind == "child" for t in i.track_ids}
    for item in final.items:
        if set(item.track_ids) & children:
            assert item.decision == "hide"
            assert item.locked
    contracts._check_decisions(final, inputs.job, inputs.tracks, None)


def test_merging_into_a_kept_static_item_makes_it_a_sam_item() -> None:
    """Audit finding: a static origin with a SAM track in it fails the contract."""
    ts = tracks(track("face:1", 3, 3, origin="static"), track("face:2", 0, 10, (100, 10, 120, 30)))
    d = decide(Inputs(job=job(), tracks=ts))
    static = next(i for i in d.items if i.origin == "static")
    other = next(i for i in d.items if i.origin == "sam")
    log = edits({"type": "keep", "edit_id": "k", "item_id": static.item_id},
                {"type": "merge", "edit_id": "m", "item_id": other.item_id, "into": static.item_id})  # fmt: skip
    merged = apply_review(d, log).decisions
    assert [i.origin for i in merged.items] == ["sam"]
    contracts._check_decisions(merged, job(), ts, None)


def test_a_locked_item_can_not_be_hidden_by_the_creator_either() -> None:
    # A creator "hide" would take the decision over (decided_by creator) from the policy that locked it.
    with pytest.raises(ReviewError) as err:
        apply_review(base(), edits({"type": "hide", "edit_id": "h", "item_id": "i_3"}))
    assert err.value.code == "locked"


def test_undoing_a_cover_spot_removes_its_patch_and_reopens_the_spot() -> None:
    cover = {"type": "cover_spot", "edit_id": "c", "spot_id": "s1"}
    covered = apply_review(base(), edits(cover), audit=audit_with_spot(), frames=60)
    assert covered.audit is not None
    # The server folds the whole log over its last result: the cover replays as a no-op, the undo reverts it.
    undone = apply_review(covered.decisions, edits(cover, {"type": "undo", "edit_id": "u", "reverts": "c"}),
                          audit=covered.audit, frames=60)  # fmt: skip
    assert "p_1" not in by_id(undone.decisions)
    assert undone.audit is not None
    assert undone.audit.spots[0].covered_by is None
    # From the policy's decisions the undone cover never applies.
    fresh = apply_review(base(), edits(cover, {"type": "undo", "edit_id": "u", "reverts": "c"}),
                         audit=audit_with_spot(), frames=60)  # fmt: skip
    assert "p_1" not in by_id(fresh.decisions)
    assert fresh.audit is not None
    assert fresh.audit.spots[0].covered_by is None


def test_an_undo_of_an_unknown_or_later_edit_reverts_nothing() -> None:
    with pytest.raises(ReviewError) as err:
        apply_review(base(), edits({"type": "undo", "edit_id": "u", "reverts": "nope"}))
    assert (err.value.code, err.value.edit_id) == ("unknown_edit", "u")
    # Not strict (a stage replaying the log): skipped silently.
    assert apply_review(base(), edits({"type": "undo", "edit_id": "u", "reverts": "nope"}), strict=False).skipped == []
    # An undo naming an edit sent after it reverts nothing.
    log = edits({"type": "undo", "edit_id": "u", "reverts": "a"}, {"type": "keep", "edit_id": "a", "item_id": "i_2"})
    assert [e.edit_id for e in effective(log)] == ["a"]
    assert by_id(apply_review(base(), log).decisions)["i_2"].decision == "keep"


def test_a_stale_last_edit_never_aborts_the_decide_stage(tmp_path: Path) -> None:
    src, dst = Path("fixtures/contracts/j_example"), tmp_path / "j_example"
    dst.mkdir()
    for name in ("job.json", "tracks.json", "roles.json", "scene.json", "transcript.json", "decisions.json"):
        shutil.copy(src / name, dst / name)
    (dst / "review.json").write_text(json.dumps([{"type": "keep", "edit_id": "a", "item_id": "i_99"}]))
    decide_run(dst)
    contracts.validate_job_dir(dst)


def test_a_kept_prominent_person_hidden_again_is_covered_face_only() -> None:
    """DESIGN §2.7 (owner, 11-04): however prominent, a re-hidden person gets the face mosaic, the policy's style;
    only Remove person covers the whole person."""
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 170))
    ts = tracks(face, body)
    p = ("participant",) * 3
    rs = roles(row("face:1", *p, matches_participant=0), row("person:1", *p, matches_participant=0))
    inputs = Inputs(job=job(), tracks=ts, roles=rs, scene=scene(), transcript=transcript())
    decided = decide(inputs)
    assert decided.items[0].decision == "keep"
    hide = edits({"type": "hide", "edit_id": "h", "item_id": "i_1"})
    exact = apply_review(decided, hide, tracks=ts, job=job()).decisions.items[0]
    assert exact.style == "pixelate"
    assert apply_review(decided, hide).decisions.items[0].style == "pixelate"  # no tracks: from the face track id
    remove = edits({"type": "remove_person", "edit_id": "r", "item_id": "i_1"})
    assert apply_review(decided, remove).decisions.items[0].style == "person_solid"
    small = tracks(face, track("person:1", 0, 20, (10, 5, 60, 40)))
    decided_small = decide(Inputs(job=job(), tracks=small, roles=inputs.roles, scene=scene(), transcript=transcript()))
    assert apply_review(decided_small, hide, tracks=small, job=job()).decisions.items[0].style == "pixelate"


def test_a_creator_hide_clears_the_hold() -> None:
    got = by_id(apply_review(base(), edits({"type": "hide", "edit_id": "h", "item_id": "i_4"})).decisions)
    assert (got["i_4"].decision, got["i_4"].hold, got["i_4"].decided_by) == ("hide", None, "creator")


def test_a_spot_covered_again_after_an_undo_keeps_its_patch_number() -> None:
    """API-NOTES §12: an A-number never changes once given, even as the server replays the whole log."""
    log = edits(
        {"type": "cover_spot", "edit_id": "c1", "spot_id": "s1"},
        {"type": "undo", "edit_id": "u1", "reverts": "c1"},
        {"type": "cover_spot", "edit_id": "c2", "spot_id": "s1"},
    )
    raw = audit_with_spot().model_dump(mode="json")
    raw["leaks"].append({"frame": 40, "box": [100, 40, 120, 60], "kind": "face", "detector": "egoblur",
                         "patched_item": None, "unresolved": True})  # fmt: skip
    raw["spots"].append({"spot_id": "s2", "first": 40, "last": 40, "boxes": {"40": [100, 40, 120, 60]}})
    raw["unresolved"] = 2
    two = Audit.model_validate(raw)
    log += edits({"type": "cover_spot", "edit_id": "c3", "spot_id": "s2"})  # takes the next number
    first = apply_review(base(), log, audit=two, frames=60)
    assert first.audit is not None
    covered_by = first.audit.spots[0].covered_by
    label = by_id(first.decisions)[str(covered_by)].audit_label
    more = [*log, *edits({"type": "keep", "edit_id": "k1", "item_id": "i_2"})]
    # The API folds the whole log over the decisions and audit the last edit saved.
    again = apply_review(first.decisions, more, audit=first.audit, frames=60)
    assert again.audit is not None
    assert again.audit.spots[0].covered_by == covered_by
    assert by_id(again.decisions)[str(covered_by)].audit_label == label
