"""WP3 policy: one table test per rule (DESIGN §2.5, API-NOTES §12, TEST-VECTORS P/A/E/B) and the E4 properties."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from safecut import contracts
from safecut.contracts import Decisions, Participant, StageStatus, Turn
from safecut.decide import run as decide_run
from safecut.decide.policy import (
    HOLD_ORDER,
    REASON_MAX,
    Inputs,
    decide,
    kind_of,
    normal_words,
    short_reason,
    speech_evidence,
)
from tests.safety_factories import (
    H,
    job,
    role_rows,
    roles,
    row,
    scene,
    track,
    track_sets,
    tracks,
    transcript,
)

#: E4: every safety property runs at least 2000 examples (more under the soak profile).
E4 = settings(max_examples=max(2000, settings().max_examples), deadline=None)

PARTICIPANT = ("participant", "participant", "participant")


def only(decisions: Decisions, track_id: str) -> dict[str, Any]:
    items = [i for i in decisions.items if track_id in i.track_ids]
    assert len(items) == 1
    return items[0].model_dump()


def run(*ts: Any, rs: Any = (), objects: Any = None, **kw: Any) -> Decisions:
    """Decide with a working scene and transcript unless the test overrides them."""
    inputs = Inputs(
        job=kw.pop("job", job()),
        tracks=tracks(*ts),
        roles=kw.pop("roles", roles(*rs, objects=objects)),
        scene=kw.pop("scene", scene()),
        transcript=kw.pop("transcript", transcript()),
    )
    assert not kw
    return decide(inputs)


def matched(track_id: str = "face:1", **extra: Any) -> Any:
    return row(track_id, *PARTICIPANT, matches_participant=0, **extra)


# ---------------------------------------------------------------------------------------------- rule tables


def test_participant_with_speech_is_kept_by_the_model() -> None:  # A1 + P6
    got = only(run(track("face:1", 0, 20), rs=[matched()]), "face:1")
    assert (got["decision"], got["decided_by"], got["style"], got["hold"]) == ("keep", "model", None, None)
    assert got["reason"].startswith("participant: ")
    assert got["evidence_frames"] == [5, 15]


def test_default_is_hide_for_every_concept_without_a_judgement() -> None:
    ts = [track(f"{c}:1", 0, 10) for c in ("license plate", "screen", "document", "menu")]
    got = run(*ts)
    assert all(i.decision == "hide" and i.style == "solid" for i in got.items)
    assert {i.kind for i in got.items} == {"plate", "screen", "document", "other"}


def test_a_person_the_role_pass_never_judged_needs_you_with_no_roles() -> None:
    got = only(run(track("face:1", 0, 20)), "face:1")
    assert (got["decision"], got["hold"]) == ("needs_you", "no_roles")


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_a_failed_role_pass_holds_everyone(status: StageStatus) -> None:
    r = row("face:1", "unsure", "unsure", "unsure", escalated=False, failed_votes=3)
    got = only(run(track("face:1", 0, 20), roles=roles(r, status=status)), "face:1")
    assert (got["decision"], got["hold"]) == ("needs_you", "no_roles")


def test_three_failed_votes_hold_no_roles() -> None:
    r = row("face:1", "unsure", "unsure", "unsure", failed_votes=3, escalated=False)
    assert only(run(track("face:1", 0, 20), rs=[r]), "face:1")["hold"] == "no_roles"


def test_bystander_is_hidden_by_the_model_with_its_evidence() -> None:  # A5
    r = row("face:1", "bystander", "bystander", "bystander", evidence="walks behind the guest")
    got = only(run(track("face:1", 0, 20), rs=[r]), "face:1")
    assert (got["decision"], got["decided_by"], got["reason"]) == ("hide", "model", "bystander: walks behind the guest")


def test_empty_evidence_still_gives_a_readable_reason() -> None:
    r = row("face:1", "bystander", "bystander", "bystander", evidence="  ")
    assert only(run(track("face:1", 0, 20), rs=[r]), "face:1")["reason"] == "bystander: no evidence given"


@pytest.mark.parametrize(
    ("votes", "escalated", "suggested", "hold", "reason"),
    [
        (("participant", "participant", "bystander"), True, "participant", None, "a closer look suggests participant"),
        (("participant", "participant", "bystander"), True, None, None, "checks didn't all agree"),
        (("participant", "participant", "unsure"), False, None, "no_roles", "checks didn't all agree"),  # E3
    ],
)
def test_disputed_tracks_need_the_creator(
    votes: tuple[str, ...], escalated: bool, suggested: Any, hold: Any, reason: str
) -> None:  # A3, E3-E7
    r = row("face:1", *votes, escalated=escalated, suggested_role=suggested)
    got = only(run(track("face:1", 0, 20), rs=[r]), "face:1")
    assert (got["decision"], got["decided_by"], got["hold"]) == ("needs_you", "policy", hold)
    assert reason in got["reason"]


def test_one_keyframe_is_not_enough() -> None:  # A2 (a row that says participant on one frame)
    r = row("face:1", *PARTICIPANT, frames=(5,), role="participant", matches_participant=0)
    got = only(run(track("face:1", 0, 20), rs=[r]), "face:1")
    assert got["decision"] == "needs_you"
    assert "2 keyframes" in got["reason"]


def test_a_failed_vote_blocks_a_keep_even_with_a_participant_role() -> None:
    r = row("face:1", *PARTICIPANT, failed_votes=1, matches_participant=0)
    assert only(run(track("face:1", 0, 20), rs=[r]), "face:1")["decision"] == "needs_you"


@pytest.mark.parametrize("votes", [("participant", "participant", "child"), ("child", "bystander", "unsure")])
def test_any_child_vote_locks_a_hidden_child(votes: tuple[str, ...]) -> None:  # A4, E1
    got = only(run(track("face:1", 0, 20), rs=[row("face:1", *votes)]), "face:1")
    assert (got["kind"], got["decision"], got["locked"], got["decided_by"]) == ("child", "hide", True, "model")


def test_an_escalation_child_ruling_locks() -> None:  # E2
    r = row("face:1", "participant", "participant", "unsure", role="child", escalated=True)
    assert only(run(track("face:1", 0, 20), rs=[r]), "face:1")["locked"] is True


def test_rule_0_child_phrase_locks_whatever_the_votes_say() -> None:
    got = only(run(track("face:1", 0, 20, child_phrase=True), rs=[matched()]), "face:1")
    assert (got["kind"], got["decision"], got["locked"], got["decided_by"]) == ("child", "hide", True, "policy")


def test_rule_0_applies_to_object_phrases_too() -> None:  # API-NOTES §12 over-locking note: "kids menu"
    got = only(run(track("kid menu:1", 0, 5, child_phrase=True)), "kid menu:1")
    assert (got["kind"], got["locked"], got["style"]) == ("child", True, "solid")


def test_an_object_with_a_child_vote_is_a_child() -> None:
    r = row("screen:1", "child", "unsure", "unsure")
    assert only(run(track("screen:1", 0, 5), rs=[r]), "screen:1")["kind"] == "child"


def test_a_reentry_is_hidden_until_the_creator_merges_it() -> None:
    a = track("face:1", 0, 10)
    b = track("face:2", 20, 30, reentry_of="face:1")
    got = run(a, b, rs=[matched("face:1", frames=(2, 8)), matched("face:2", frames=(22, 28))])
    assert only(got, "face:1")["decision"] == "keep"
    second = only(got, "face:2")
    assert second["decision"] == "needs_you"
    assert "merge" in second["reason"]


def test_a_static_person_box_is_never_auto_kept() -> None:
    got = only(run(track("person:1", 3, 3, origin="static"), rs=[matched("person:1")]), "person:1")
    assert (got["decision"], got["origin"], got["hold"]) == ("needs_you", "static", None)


def test_a_static_object_box_needs_the_creator() -> None:
    got = only(run(track("envelope:1", 9, 9, origin="static")), "envelope:1")
    assert (got["decision"], got["origin"], got["kind"]) == ("needs_you", "static", "other")


def test_plates_are_always_hidden() -> None:
    objects = [{"track_id": "license plate:1", "sensitive": False, "content": "blank", "frames": [1]}]
    got = only(run(track("license plate:1", 0, 5), objects=objects), "license plate:1")
    assert (got["decision"], got["decided_by"], got["style"]) == ("hide", "policy", "solid")


@pytest.mark.parametrize(
    ("sensitive", "decision", "by"),
    [(True, "hide", "model"), (False, "needs_you", "policy")],
)
def test_screens_are_hidden_unless_non_personal_then_the_creator_decides(
    sensitive: bool, decision: str, by: str
) -> None:  # B1, B2; DESIGN §2.5: never auto-kept
    objects = [{"track_id": "screen:1", "sensitive": sensitive, "content": "a menu", "frames": [3]}]
    got = only(run(track("screen:1", 0, 5), objects=objects), "screen:1")
    assert (got["decision"], got["decided_by"], got["evidence_frames"]) == (decision, by, [3])


def test_empty_object_content_falls_back_to_the_concept() -> None:
    objects = [{"track_id": "screen:1", "sensitive": True, "content": " ", "frames": [3]}]
    assert only(run(track("screen:1", 0, 5), objects=objects), "screen:1")["reason"] == "sensitive screen: screen"


# ---------------------------------------------------------------------------------------------- holds (P vectors)


@pytest.mark.parametrize(
    ("kw", "hold"),
    [
        ({"scene": scene(status="failed")}, "no_scene"),  # P1
        ({"scene": None}, "no_scene"),  # a missing scene.json counts as failed
        ({"scene": scene(children=1)}, "unmatched_child"),  # P2
        ({"transcript": transcript(status="failed")}, "no_speech"),  # P9
        ({"transcript": transcript(status="skipped")}, "no_speech"),  # P9b
        ({"transcript": transcript(degraded=True)}, "no_speech"),
        ({"transcript": None}, "no_speech"),  # audio, but no transcript file
    ],
)
def test_holds(kw: dict[str, Any], hold: str) -> None:
    got = only(run(track("face:1", 0, 20), rs=[matched()], **kw), "face:1")
    assert (got["decision"], got["hold"]) == ("needs_you", hold)


def test_hold_precedence_writes_the_first_in_order() -> None:
    got = only(
        run(
            track("face:1", 0, 20), rs=[matched()], scene=scene(status="failed"), transcript=transcript(status="failed")
        ),
        "face:1",
    )
    assert got["hold"] == "no_scene"
    assert HOLD_ORDER == ("no_scene", "no_speech", "no_roles", "unmatched_child", "no_speech_link")


@pytest.mark.parametrize(
    ("kw", "hold"),
    [
        ({"scene": scene(status="failed")}, "no_scene"),
        ({"transcript": transcript(status="failed")}, "no_speech"),
        ({}, "no_roles"),
    ],
)
def test_a_role_failure_still_writes_the_first_hold_in_order(kw: dict[str, Any], hold: str) -> None:
    failed = row("face:1", "unsure", "unsure", "unsure", failed_votes=3, escalated=False)
    unescalated = row("face:2", "participant", "participant", "unsure", escalated=False)
    got = run(track("face:1", 0, 20), track("face:2", 0, 20, (200, 10, 240, 50)), rs=[failed, unescalated], **kw)
    assert (only(got, "face:1")["hold"], only(got, "face:2")["hold"]) == (hold, hold)
    assert only(got, "face:1")["reason"] == "the role check couldn't judge this person"


def test_every_id_of_a_child_is_locked_across_reentries() -> None:
    a = track("face:1", 0, 10)
    b = track("face:2", 20, 30, reentry_of="face:1")
    c = track("face:3", 40, 50, reentry_of="face:2")
    # The child vote lands on the middle ID only; the earlier and later IDs are the same child.
    rs = [matched("face:1", frames=(2, 8)), row("face:2", "child", "participant", "participant", frames=(22, 28)),
          matched("face:3", frames=(42, 48))]  # fmt: skip
    got = run(a, b, c, rs=rs)
    for track_id in ("face:1", "face:2", "face:3"):
        item = only(got, track_id)
        assert (item["decision"], item["kind"], item["locked"]) == ("hide", "child", True), track_id


def test_a_matched_scene_child_lets_participants_be_kept() -> None:  # P3
    kid = track("face:4", 0, 20, (200, 10, 240, 50))
    got = run(
        track("face:1", 0, 20), kid, rs=[matched(), row("face:4", "child", "child", "child")], scene=scene(children=1)
    )
    assert only(got, "face:1")["decision"] == "keep"


def test_children_are_counted_as_items_not_tracks() -> None:  # P5: face:4 + person:3 is one child item
    kid_face = track("face:4", 0, 20, (210, 20, 230, 40))
    kid_body = track("person:3", 0, 20, (200, 10, 250, 90))
    rs = [matched(), row("face:4", "child", "child", "child"), row("person:3", "child", "child", "child")]
    got = run(track("face:1", 0, 20), kid_face, kid_body, rs=rs, scene=scene(children=2))
    assert only(got, "face:1")["hold"] == "unmatched_child"
    assert only(got, "face:4")["item_id"] == only(got, "person:3")["item_id"]


@pytest.mark.parametrize("votes", [("bystander",) * 3, ("child",) * 3])  # P10, P12
def test_a_child_phrase_poster_never_matches_a_scene_child(votes: tuple[str, ...]) -> None:
    poster = track("person:9", 0, 20, (200, 10, 250, 90), child_phrase=True)
    got = run(track("face:1", 0, 20), poster, rs=[matched(), row("person:9", *votes)], scene=scene(children=1))
    assert only(got, "face:1")["hold"] == "unmatched_child"
    assert only(got, "person:9")["locked"] is True


def test_a_child_made_only_of_reentries_does_not_count() -> None:
    a = track("face:4", 0, 5, (200, 10, 240, 50))
    b = track("face:5", 10, 20, (200, 10, 240, 50), reentry_of="face:4")
    rs = [matched(), row("face:5", "child", "child", "child")]
    got = run(track("face:1", 0, 20), a, b, rs=rs, scene=scene(children=1))
    assert only(got, "face:1")["hold"] == "unmatched_child"


def amina_and_kev(quote: str | None, turn: int | None, text: str = "And this is my mate, Kev.") -> Any:
    host = Participant(description="host", evidence="x", speaker="S1", introduced_in_turn=None, introduction_quote=None)
    kev = Participant(description="Kev", evidence="x", speaker=None, introduced_in_turn=turn, introduction_quote=quote)
    turns = [Turn(speaker="S1", start=0, end=1, text="Hi, I'm Amina"), Turn(speaker="S1", start=1, end=2, text="so"),
             Turn(speaker="S1", start=2, end=3, text=text)]  # fmt: skip
    return scene(participants=[host, kev]), transcript(turns=turns)


@pytest.mark.parametrize(
    ("quote", "turn", "kept"),
    [
        ("my mate Kev", 2, True),  # P7: introduced, silent
        ("my friend Kev", 2, False),  # P11b: the quote isn't in the turn
        ("Kev", 2, False),  # P11c: one word is no evidence
        ("...", 2, False),  # P11c
        ("my mate Kev", 7, False),  # a turn that doesn't exist
        (None, None, False),  # P11: speaker null alone is nothing
    ],
)
def test_introduction_evidence(quote: str | None, turn: int | None, kept: bool) -> None:
    sc, tr = amina_and_kev(quote, turn)
    got = only(
        run(track("face:2", 0, 20), rs=[row("face:2", *PARTICIPANT, matches_participant=1)], scene=sc, transcript=tr),
        "face:2",
    )
    assert got["decision"] == ("keep" if kept else "needs_you")
    assert got["hold"] == (None if kept else "no_speech_link")


def test_votes_naming_different_participants_have_no_link() -> None:  # P8
    got = only(run(track("face:1", 0, 20), rs=[row("face:1", *PARTICIPANT)]), "face:1")
    assert got["hold"] == "no_speech_link"


def test_an_empty_but_working_transcript_still_needs_evidence() -> None:  # P9c
    got = only(run(track("face:1", 0, 20), rs=[row("face:1", *PARTICIPANT)], transcript=transcript(turns=[])), "face:1")
    assert got["hold"] == "no_speech_link"


def test_a_clip_without_audio_needs_no_speech() -> None:
    got = run(track("face:1", 0, 20), rs=[row("face:1", *PARTICIPANT)], job=job(audio=False), transcript=None)
    assert only(got, "face:1")["decision"] == "keep"


def test_a_participant_index_out_of_range_is_no_evidence() -> None:
    sc, tr = amina_and_kev(None, None)
    assert not speech_evidence(5, sc, tr)
    assert not speech_evidence(None, sc, tr)
    assert normal_words("  Hi,   I'm  AMINA! ") == "hi im amina"


# ---------------------------------------------------------------------------------------------- grouping, styles


def test_face_and_person_of_one_participant_are_one_kept_item() -> None:
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 100))
    got = run(face, body, rs=[matched("face:1"), matched("person:1")])
    assert len(got.items) == 1
    assert got.items[0].decision == "keep"
    assert got.items[0].track_ids == ["face:1", "person:1"]


def test_a_face_and_body_that_disagree_ask_the_creator() -> None:
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 100))
    got = run(face, body, rs=[matched("face:1"), row("person:1", "bystander", "bystander", "bystander")])
    item = got.items[0].model_dump()
    assert (item["decision"], item["reason"], item["hold"]) == ("needs_you", "the face and body checks disagree", None)


def test_a_mixed_item_takes_the_first_hold_in_order() -> None:
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 100))
    r_body = row("person:1", "participant", "unsure", "unsure", escalated=False)
    got = run(face, body, rs=[matched("face:1"), r_body], scene=scene(children=1))
    assert got.items[0].hold == "no_roles"


def test_hidden_bodies_combine_their_deciders() -> None:
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 100))
    bystander = row("face:1", "bystander", "bystander", "bystander")
    got = run(face, body, rs=[bystander, row("person:1", "bystander", "bystander", "bystander")])
    assert (got.items[0].decision, got.items[0].decided_by) == ("hide", "model")
    by_policy = run(face, track("person:1", 0, 20, (10, 5, 60, 100)), rs=[bystander], objects=None)
    assert by_policy.items[0].decision == "needs_you"  # the body was never judged


@pytest.mark.parametrize(
    ("ts", "style"),
    [
        ([track("face:1", 0, 5, (20, 10, 40, 30))], "pixelate"),
        ([track("person:1", 0, 5, (10, 5, 60, 40))], "solid"),
        ([track("face:1", 0, 5, (20, 10, 40, 30)), track("person:1", 0, 5, (10, 5, 60, 40))], "pixelate"),
        ([track("person:1", 0, 5, (10, 5, 60, 5 + H // 4 + 1))], "person_solid"),  # DESIGN §2.7b: prominent
        (
            [track("face:1", 0, 5, (20, 10, 40, 30)), track("person:1", 0, 5, (10, 5, 60, 5 + H // 4 + 1))],
            "person_solid",
        ),
    ],
)
def test_styles(ts: list[Any], style: str) -> None:
    got = run(*ts, rs=[row(t.track_id, "bystander", "bystander", "bystander") for t in ts])
    assert [i.style for i in got.items] == [style]


def test_a_child_with_a_body_gets_a_whole_person_mask() -> None:
    face = track("face:1", 0, 20, (20, 10, 40, 30))
    body = track("person:1", 0, 20, (10, 5, 60, 100))
    got = run(face, body, rs=[row("face:1", "child", "child", "child")])
    assert (got.items[0].kind, got.items[0].style) == ("child", "person_solid")


@pytest.mark.parametrize(
    ("concept", "kind"),
    [("face", "person"), ("person", "person"), ("license plate", "plate"), ("phone", "screen"),
     ("name badge", "document"), ("menu", "other"), ("envelope", "other"), ("monitor", "other")],
)  # fmt: skip
def test_kinds(concept: str, kind: str) -> None:
    assert kind_of(concept) == kind


def test_item_ids_follow_first_frame() -> None:
    got = run(track("screen:1", 30, 40), track("face:1", 0, 5, (200, 10, 240, 50)))
    assert [(i.item_id, i.track_ids) for i in got.items] == [("i_1", ["face:1"]), ("i_2", ["screen:1"])]


def test_the_example_job_decides_validly(tmp_path: Path) -> None:
    src = Path("fixtures/contracts/j_example")
    dst = tmp_path / "j_example"
    dst.mkdir()
    for name in ("job.json", "tracks.json", "roles.json", "scene.json", "transcript.json"):
        shutil.copy(src / name, dst / name)
    decide_run(dst)
    contracts.validate_job_dir(dst)
    got = contracts.load(dst / "decisions.json", Decisions)
    assert [(i.item_id, i.decision) for i in got.items] == [
        ("i_1", "keep"),
        ("i_2", "hide"),
        ("i_3", "needs_you"),
        ("i_4", "needs_you"),
    ]


# ---------------------------------------------------------------------------------------------- E4 properties


@st.composite
def policy_inputs(draw: st.DrawFn) -> Inputs:
    ts = draw(track_sets())
    status: StageStatus = draw(st.sampled_from(["ok", "ok", "ok", "failed"]))
    rows = draw(role_rows(ts, status))
    objects = [
        {"track_id": t.track_id, "sensitive": draw(st.booleans()), "content": "x", "frames": [t.first]}
        for t in ts
        if t.concept not in ("face", "person") and draw(st.booleans())
    ]
    audio = draw(st.booleans())
    sc = draw(st.sampled_from([None, scene(), scene(status="failed"), scene(children=1)]))
    if sc is not None and draw(st.booleans()):
        sc = scene(participants=[*sc.participants, *amina_and_kev("my mate Kev", 2)[0].participants[1:]])
    tr = draw(st.sampled_from([None, transcript(), transcript(degraded=True), transcript(turns=[])])) if audio else None
    if audio and draw(st.booleans()):
        tr = amina_and_kev("my mate Kev", 2)[1]
    return Inputs(job=job(audio=audio), tracks=tracks(*ts), roles=roles(*rows, status=status, objects=objects),
                  scene=sc, transcript=tr)  # fmt: skip


@pytest.mark.entry("E4:non_participant_never_kept")
@E4
@given(policy_inputs())
def test_property_nothing_but_a_unanimous_participant_is_kept(inputs: Inputs) -> None:
    got = decide(inputs)
    rows = {r.track_id: r for r in inputs.roles.tracks} if inputs.roles else {}
    by_id = {t.track_id: t for t in inputs.tracks.tracks}
    for item in got.items:
        if item.decision != "keep":
            continue
        for tid in item.track_ids:
            r, t = rows[tid], by_id[tid]
            assert r.role == "participant"
            assert r.votes == ["participant"] * 3
            assert not r.failed_votes
            assert len(set(r.frames)) >= 2
            assert t.concept in ("face", "person")
            assert t.reentry_of is None
            assert t.origin == "sam"
            assert not t.child_phrase


@E4
@given(policy_inputs())
def test_property_every_decision_passes_the_contract(inputs: Inputs) -> None:
    got = decide(inputs)
    assert sorted(t for i in got.items for t in i.track_ids) == sorted(t.track_id for t in inputs.tracks.tracks)
    contracts._check_decisions(got, inputs.job, inputs.tracks, inputs.roles)
    contracts._check_auto_keeps(
        got, inputs.job, scene=inputs.scene, roles=inputs.roles, transcript=inputs.transcript, tracks=inputs.tracks
    )
    for item in got.items:
        assert item.reason
        assert (item.hold is None) or item.decision == "needs_you"


@pytest.mark.entry("E4:child_never_kept")
@E4
@given(policy_inputs())
def test_property_children_are_never_kept(inputs: Inputs) -> None:
    got = decide(inputs)
    rows = {r.track_id: r for r in inputs.roles.tracks} if inputs.roles else {}
    phrase = {t.track_id for t in inputs.tracks.tracks if t.child_phrase}
    for item in got.items:
        child = any(t in phrase or (t in rows and ("child" in rows[t].votes or rows[t].role == "child"))
                    for t in item.track_ids)  # fmt: skip
        if child:
            assert (item.kind, item.decision, item.locked) == ("child", "hide", True)


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=40))
def test_property_normal_words_matches_the_contract(text: str) -> None:
    assert normal_words(text) == contracts._normal_words(text)


def test_cited_frames_must_be_on_the_track() -> None:
    """Audit finding: two cited frames outside the track's own span are no evidence for it."""
    got = only(run(track("face:1", 40, 55), rs=[matched(frames=(2, 3))]), "face:1")
    assert got["decision"] == "needs_you"


def test_reasons_are_short_lowercase_first_without_a_full_stop() -> None:
    """UI-SPEC §8 request 4: ≤ 90 characters, lowercase-first, no trailing full stop (the UI capitalises)."""
    long = "The man in the red jacket walks behind the host at the counter and never speaks or looks at the camera. "
    r = row("face:1", "bystander", "bystander", "bystander", evidence=long * 2)
    reason = only(run(track("face:1", 0, 20), rs=[r]), "face:1")["reason"]
    assert len(reason) <= REASON_MAX
    assert reason.startswith("bystander: The man")
    assert reason.endswith("…")
    assert short_reason("Hidden.") == "hidden"
    assert short_reason("  ") == "hidden by default"


def test_a_child_carried_by_an_adult_pairs_with_their_own_body() -> None:
    """The child's face lies inside the adult's body box and their own: the body it fills most is theirs, so the
    child's whole item is locked, the adult's face and body stay one item, and one child counts once."""
    adult_face = track("face:1", 0, 20, (60, 10, 80, 30))
    adult = track("person:1", 0, 20, (40, 5, 160, 175))
    child_face = track("face:2", 0, 20, (110, 60, 122, 72))
    child = track("person:2", 0, 20, (100, 55, 135, 120))
    rs = [matched("face:1"), matched("person:1"), row("face:2", "child", "participant", "participant"),
          matched("person:2")]  # fmt: skip
    got = run(adult_face, adult, child_face, child, rs=rs, scene=scene(children=1))
    kid = only(got, "face:2")
    assert (kid["track_ids"], kid["kind"], kid["locked"], kid["decision"]) == (
        ["face:2", "person:2"], "child", True, "hide"
    )  # fmt: skip
    assert only(got, "face:1")["track_ids"] == ["face:1", "person:1"]
    assert only(got, "face:1")["decision"] == "keep"


def test_a_child_face_no_body_can_claim_locks_every_body_holding_it() -> None:
    """Two identical bodies hold the child's face equally (an exact tie pairs nothing): neither body can be kept."""
    child_face = track("face:2", 0, 20, (110, 60, 122, 72))
    a = track("person:1", 0, 20, (100, 55, 135, 120))
    b = track("person:2", 0, 20, (100, 55, 135, 120))
    rs = [row("face:2", "child", "child", "child"), matched("person:1"), matched("person:2")]
    got = run(child_face, a, b, rs=rs, scene=scene(children=1))
    assert only(got, "face:2")["track_ids"] == ["face:2"]
    for body in ("person:1", "person:2"):
        item = only(got, body)
        assert (item["decision"], item["kind"], item["locked"]) == ("hide", "child", True), body
