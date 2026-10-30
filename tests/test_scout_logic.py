"""Pure scout logic: grid mapping (G1–G14), vote aggregation (A1–A16, B1–B3), escalation (E1–E9) and the miss
loop (M1–M13), each with hypothesis properties."""

from __future__ import annotations

from typing import cast, get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from safecut.contracts import Track
from safecut.scout import grid, miss, votes
from safecut.scout.votes import ObjectVote, Ruling, TrackVote, Vote

W, H = 1280, 720

# ---------------------------------------------------------------------------- grid


@pytest.mark.parametrize(
    ("xy", "want"),
    [
        ((500, 500), (640, 340)),
        ((0, 0), None),
        ((1001, 1000), (1279, 719)),
        ((0, 52), (0, 0)),
        ((0, 51), None),
        ((250, 750), (320, 530)),
    ],
)
def test_g1_g6_points(xy: tuple[int, int], want: tuple[int, int] | None) -> None:
    assert grid.point(*xy, W, H) == want


@pytest.mark.parametrize(
    ("box", "kw", "want"),
    [
        ((100, 100, 300, 400), {"kind": "redteam"}, (128, 36, 384, 264)),  # G7
        ((100, 0, 300, 40), {"kind": "redteam", "finding": "text", "text": "F 000090"}, None),  # G8
        ((100, 0, 300, 40), {"kind": "redteam", "finding": "face"}, (0, 0, W, H)),  # G8b
        ((100, 0, 300, 40), {"kind": "redteam", "finding": "text", "text": "AMINA"}, (0, 0, W, H)),  # G8b
        ((100, 0, 300, 40), {"kind": "miss"}, None),  # G9
        ((500, 500, 501, 501), {"kind": "redteam"}, (624, 324, 656, 356)),  # G10
        ((-5, 60, 1001, 1001), {"kind": "redteam"}, (0, 6, 1280, 720)),  # G11
        ((300, 100, 100, 400), {"kind": "redteam"}, (128, 36, 384, 264)),  # G12
        ((100, 40, 300, 60), {"kind": "redteam"}, (128, 0, 384, 6)),  # G13
        ((0, 60, 10, 61), {"kind": "redteam"}, (0, 0, 22, 22)),  # G14
        ((500, 500, 501, 501), {"kind": "miss"}, None),  # a degenerate miss box is discarded
    ],
)
def test_g7_g14_boxes(box: tuple[int, int, int, int], kw: dict[str, str], want: object) -> None:
    kind = cast(grid.BoxKind, kw["kind"])
    assert grid.box(box, W, H, kind=kind, finding=kw.get("finding", ""), text=kw.get("text", "")) == want


@given(x=st.integers(-50, 1050), y=st.integers(-50, 1050), w=st.integers(16, 1920), h=st.integers(16, 1920))
def test_point_in_bounds_and_monotone(x: int, y: int, w: int, h: int) -> None:
    p = grid.point(x, y, w, h)
    if p is not None:
        assert 0 <= p[0] < w
        assert 0 <= p[1] < h
        q = grid.point(x + 1, y + 1, w, h)
        assert q is not None
        assert q[0] >= p[0]
        assert q[1] >= p[1]


@given(px=st.integers(0, 1279), py=st.integers(0, 719))
def test_round_trip_within_one_pixel(px: int, py: int) -> None:
    back = grid.point(grid.to_grid(px, W), grid.to_grid(py + grid.BAR_H, H + grid.BAR_H), W, H)
    assert back is not None
    assert abs(back[0] - px) <= 1
    assert abs(back[1] - py) <= 1


@given(b=st.tuples(*[st.integers(-20, 1020)] * 4), kind=st.sampled_from(["miss", "redteam"]))
def test_boxes_are_half_open_in_frame(b: tuple[int, int, int, int], kind: str) -> None:
    out = grid.box(b, W, H, kind=cast(grid.BoxKind, kind))
    if out is not None:
        assert 0 <= out[0] < out[2] <= W
        assert 0 <= out[1] < out[3] <= H


# ---------------------------------------------------------------------------- votes

PRESENT = frozenset({90, 120, 150})


def v(role: str = "participant", frames: tuple[int, ...] = (90, 120), idx: int | None = None, ev: str = "") -> Vote:
    track = TrackVote(role=cast(votes.Role, role), evidence=ev or role, frames=frames, matches_participant=idx)
    return Vote(tracks={"face:7": track})


FAILED = Vote(failed=True)
EMPTY = Vote()


@pytest.mark.parametrize(
    ("ballots", "role", "failed"),
    [
        ((v(), v(), v()), "participant", 0),  # A1
        ((v(frames=(90,)), v(frames=(90,)), v(frames=(90,))), "unsure", 0),  # A2
        ((v(), v(), v("bystander")), "unsure", 0),  # A3
        ((v(), v(), v("child")), "child", 0),  # A4
        ((v("bystander", (90,)),) * 3, "bystander", 0),  # A5
        ((v(), EMPTY, v()), "unsure", 0),  # A6
        ((v(), v(frames=(95,)), v()), "unsure", 0),  # A7
        ((v(), v(), FAILED), "unsure", 1),  # A8
        ((v("unsure"),) * 3, "unsure", 0),  # A9
    ],
)
def test_a1_a9(ballots: tuple[Vote, Vote, Vote], role: str, failed: int) -> None:
    result = votes.judge_window("face:7", ballots, PRESENT)
    assert result.role == role
    assert result.failed_votes == failed
    assert votes.disputed(result) == (role == "unsure")


def test_a10_unknown_track_is_ignored() -> None:
    hallucinated = Vote(tracks={"face:99": TrackVote("participant", "x", (90, 120))})
    assert votes.judge_window("face:7", (hallucinated,) * 3, PRESENT).role == "unsure"


def test_a11_a12_a13_collapse() -> None:
    a11 = votes.judge_window("face:7", (v(idx=0), v(frames=(120, 150), idx=0), v(frames=(90,), idx=0)), PRESENT)
    assert a11.frames == (90, 120, 150)
    assert a11.evidence == "participant"
    assert a11.matches_participant == 0
    a12 = votes.judge_window("face:7", (v(idx=0), v(idx=1), v(idx=0)), PRESENT)
    assert a12.role == "participant"
    assert a12.matches_participant is None
    a13 = votes.judge_window(
        "face:7",
        (v(frames=(90,), ev="speaks to host"), v("bystander", (120,), ev="background"), v(frames=(150,))),
        PRESENT,
    )
    assert a13.role == "unsure"
    assert a13.frames == (90, 120, 150)
    assert a13.evidence == "Judges disagreed: speaks to host"


def _window(*ballots: Vote, present: frozenset[int]) -> votes.TrackResult:
    return votes.judge_window("face:7", ballots, present)


def test_a14_a15_a16_windows() -> None:
    w1 = frozenset({90, 120})
    w2 = frozenset({1500, 1530})
    p1 = v(frames=(90, 120), idx=0)
    p2 = v(frames=(1500, 1530), idx=0)
    a14 = votes.combine_windows([_window(p1, p1, p1, present=w1), _window(p2, p2, v("bystander", (1500,)), present=w2)])
    assert a14.role == "unsure"
    assert a14.votes == ("participant", "participant", "bystander")
    a15 = votes.combine_windows([_window(p1, p1, p1, present=w1), _window(p2, p2, p2, present=w2)])
    assert a15.role == "participant"
    assert a15.frames == (90, 120, 1500, 1530)
    assert a15.matches_participant == 0
    b1, b2 = v("bystander", (90,)), v("bystander", (1500,))
    a16 = votes.combine_windows([_window(b1, b1, b1, present=w1), _window(b2, b2, b2, present=w2)])
    assert a16.role == "bystander"


def o(sensitive: bool) -> Vote:
    return Vote(objects={"screen:2": ObjectVote(sensitive=sensitive, content="a menu" if not sensitive else "inbox",
                                                frames=(90,))})  # fmt: skip


@pytest.mark.parametrize(
    ("ballots", "sensitive"),
    [((o(False),) * 3, False), ((o(True), o(False), o(False)), True), ((o(False), o(False), FAILED), True)],
)
def test_b1_b3_objects(ballots: tuple[Vote, Vote, Vote], sensitive: bool) -> None:
    assert votes.judge_object("screen:2", ballots, PRESENT).sensitive is sensitive


def test_objects_across_windows_fail_closed() -> None:
    clear = votes.judge_object("screen:2", (o(False),) * 3, PRESENT)
    unclear = votes.judge_object("screen:2", (o(False), o(False), EMPTY), PRESENT)
    assert votes.combine_object_windows([clear, clear]).sensitive is False
    assert votes.combine_object_windows([clear, unclear]).sensitive is True


ROLES = list(get_args(votes.Role))
ballot = st.one_of(
    st.just(FAILED),
    st.just(EMPTY),
    st.builds(
        lambda role, frames, idx: v(role, tuple(frames), idx),
        st.sampled_from(ROLES),
        st.lists(st.sampled_from([90, 95, 120, 150]), max_size=3),
        st.sampled_from([None, 0, 1]),
    ),
)


@given(ballots=st.tuples(ballot, ballot, ballot))
def test_property_participant_needs_three_valid_votes(ballots: tuple[Vote, Vote, Vote]) -> None:
    result = votes.judge_window("face:7", ballots, PRESENT)
    cast_child = any(not b.failed and "face:7" in b.tracks and b.tracks["face:7"].role == "child" for b in ballots)
    if result.role == "participant":
        assert not cast_child
        assert all(not b.failed and b.tracks["face:7"].role == "participant" for b in ballots)
        assert len(set(result.frames)) >= 2
        assert set(result.frames) <= PRESENT
    assert (result.role == "child") == cast_child  # any child vote locks it, even citing nothing valid
    if result.matches_participant is not None:
        assert result.role == "participant"
    assert len(result.votes) == 3


@given(windows=st.lists(st.tuples(ballot, ballot, ballot), min_size=1, max_size=3))
def test_property_windows_never_promote(windows: list[tuple[Vote, Vote, Vote]]) -> None:
    per = [votes.judge_window("face:7", w, PRESENT) for w in windows]
    combined = votes.combine_windows(per)
    if combined.role == "participant":
        assert all(r.role == "participant" for r in per)
    if any(r.role == "child" for r in per):
        assert combined.role == "child"
    assert combined.failed_votes >= max(r.failed_votes for r in per)


# ---------------------------------------------------------------------------- escalation


def r(role: str, frames: tuple[int, ...] = (90, 120)) -> Ruling:
    return Ruling(role=cast(votes.Role, role), evidence=f"{role} ruling", frames=frames)


def test_e2_to_e9() -> None:
    present = frozenset({90, 120, 210, 240})
    check = votes.check_ruling
    e2 = votes.apply_rulings([check(r("child"), present)])
    assert (e2.role, e2.escalated) == ("child", True)
    assert votes.apply_rulings([None]) == votes.NO_ESCALATION  # E3: failed
    e4 = votes.apply_rulings([check(r("participant", (210, 240)), present)])
    assert (e4.role, e4.suggested_role, e4.frames, e4.escalated) == ("unsure", "participant", (210, 240), True)
    e5 = votes.apply_rulings([check(r("bystander"), present)])
    assert e5.suggested_role == "bystander"
    assert votes.apply_rulings([check(r("participant", (205,)), present)]) == votes.NO_ESCALATION  # E6
    e7 = votes.apply_rulings([check(r("unsure", (210,)), present)])
    assert (e7.suggested_role, e7.evidence, e7.frames, e7.escalated) == (None, None, None, True)
    e8 = votes.apply_rulings([check(r("participant"), present), check(r("child"), present)])
    assert e8.role == "child"
    e9 = votes.apply_rulings([check(r("participant"), present), check(r("bystander"), present)])
    assert (e9.suggested_role, e9.escalated) == (None, True)
    one_frame = votes.apply_rulings([check(r("participant", (210,)), present)])
    assert one_frame.suggested_role is None  # a participant ruling needs two cited frames


ruling = st.one_of(
    st.none(),
    st.builds(r, st.sampled_from(ROLES), st.lists(st.sampled_from([90, 95, 120]), max_size=3).map(tuple)),
)


@given(rulings=st.lists(ruling, min_size=1, max_size=3))
def test_property_escalation_never_keeps(rulings: list[Ruling | None]) -> None:
    present = frozenset({90, 120})
    out = votes.apply_rulings([votes.check_ruling(x, present) for x in rulings])
    assert out.role in ("unsure", "child")
    if not out.escalated:
        assert out == votes.NO_ESCALATION


# ---------------------------------------------------------------------------- miss loop

SWEPT = ["face", "person", "license plate", "screen", "phone", "document", "name badge"]
SENT = frozenset({420, 600})


def raw(phrase: str, *, recurs: bool = True, frame: int = 420, point: tuple[int, int] = (500, 500),
        box: tuple[int, int, int, int] | None = None) -> miss.RawMiss:  # fmt: skip
    return miss.RawMiss(what="x", sam_phrase=phrase, frame=frame, point=point, box=box, recurs=recurs)


def planned(*items: miss.RawMiss) -> miss.LoopPlan:
    valid = [m for m in (miss.validate(i, sent=SENT, width=W, height=H) for i in items) if m is not None]
    return miss.plan(miss.dedupe(valid, W, H), swept=SWEPT)


@pytest.mark.parametrize(
    ("phrase", "recurs", "sweep", "note"),
    [
        ("Envelope.", True, True, None),  # M1
        ("envelope", False, False, None),  # M2
        ("House Number", True, True, None),  # M3
        ("addressed envelope on table", True, False, "phrase_too_long"),  # M4
        ("face", True, False, None),  # M5
        ("thing", True, False, None),  # M6
    ],
)
def test_m1_m6(phrase: str, recurs: bool, sweep: bool, note: str | None) -> None:
    p = planned(raw(phrase, recurs=recurs))
    assert len(p.prompts) == 1  # the point prompt always runs
    assert p.prompts[0].sweep is sweep
    assert (note in p.prompts[0].notes) if note else not p.prompts[0].notes


def test_m7_unsent_frame_dropped() -> None:
    assert miss.validate(raw("envelope", frame=421), sent=SENT, width=W, height=H) is None


def test_m8_item_cap() -> None:
    p = planned(*(raw(f"thing{k}", point=(100 * k + 50, 500)) for k in range(9)))
    assert len(p.prompts) == 8
    assert len(p.static) == 1
    assert p.static[0].notes == ["item_cap"]
    track = miss.static_track(p.static[0], "thing8:1", fps=30, frames=900, width=W, height=H)
    assert (track.first, track.last) == (390, 450)
    assert track.origin == "static"
    side = round(0.06 * 720)
    box = track.boxes[420]
    assert (box[2] - box[0], box[3] - box[1]) == (side, side)


def test_m9_point_in_bar() -> None:
    assert miss.validate(raw("envelope", point=(0, 0)), sent=SENT, width=W, height=H) is None
    with_box = miss.validate(raw("envelope", point=(0, 0), box=(100, 100, 300, 400)), sent=SENT, width=W, height=H)
    assert with_box is not None
    assert with_box.point == (255, 149)


def test_m10_dedupe_and_phrase_budget() -> None:
    # 30 px apart on the same frame: one item (5% of the 1,469 px diagonal is 73 px).
    p = planned(raw("envelope", point=(500, 500)), raw("envelope", point=(523, 500)))
    assert len(p.prompts) == 1
    q = planned(*(raw(name, point=(80 * k + 50, 500)) for k, name in enumerate(["a", "b", "c", "d"])))
    assert [m.sweep for m in q.prompts] == [True, True, True, False]
    assert q.prompts[3].notes == ["phrase_budget"]


@pytest.mark.parametrize(
    ("phrase", "concept", "child"),
    [
        ("Kids", "person", True),  # M12
        ("little girl", "person", True),
        ("school kids", "person", True),
        ("babies", "person", True),
        ("schoolchildren", "person", True),
        ("kids menu", "person", True),  # fail closed: any child token locks
        ("passers-by", "person", False),
        ("old men", "person", False),
        ("faces", "face", False),
        ("driver license", "driver license", False),  # head noun license: an object
        ("face mask", "face mask", False),
        ("reflection of a sign", "reflection of a sign", False),
    ],
)
def test_m12_m13_concepts(phrase: str, concept: str, child: bool) -> None:
    got = miss.concept_for(miss.normalise(phrase))
    assert (got.concept, got.child_phrase) == (concept, child)


@given(phrase=st.text(min_size=1, max_size=30))
def test_property_normalise_is_idempotent_and_concepts_are_ids(phrase: str) -> None:
    norm = miss.normalise(phrase)
    assert miss.normalise(norm) == norm
    if norm:
        concept = miss.concept_for(norm)
        assert ":" not in concept.concept
        assert concept.concept.strip() == concept.concept


def test_a_miss_already_tracked_is_dropped_but_another_concepts_box_does_not_count() -> None:
    def tracked(concept: str) -> Track:
        return Track(track_id=f"{concept}:1", concept=concept, first=420, last=420, boxes={420: (600, 300, 700, 400)},
                     source="sam-3.1", prompt=concept)  # fmt: skip

    item = miss.validate(raw("envelope", point=(500, 500)), sent=SENT, width=W, height=H)
    assert item is not None
    assert item.point == (640, 340)
    assert miss.untracked([item], [tracked("envelope")]) == []
    assert miss.untracked([item], [tracked("screen")]) == [item]
