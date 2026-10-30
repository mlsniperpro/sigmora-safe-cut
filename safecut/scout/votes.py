"""Role-pass self-consistency and escalation rulings (``role-pass.md`` rules 1–7, windows; ``escalation.md``).

Pure functions over parsed votes, so every rule is property-tested (TEST-VECTORS A1–A16, B1–B3, E1–E9). The
invariant they keep: a track is ``participant`` only on 3/3 valid ``participant`` votes citing ≥ 2 keyframes where
it is present, in every window it appears in; and escalation can never make anything a participant.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["participant", "bystander", "child", "unsure"]
Suggestion = Literal["participant", "bystander", "child"]
VOTES = 3
DISAGREED = "Judges disagreed: "


@dataclass(frozen=True)
class TrackVote:
    role: Role
    evidence: str
    frames: tuple[int, ...]
    matches_participant: int | None = None


@dataclass(frozen=True)
class ObjectVote:
    sensitive: bool
    content: str
    frames: tuple[int, ...]


@dataclass(frozen=True)
class Vote:
    """One role-pass call's answer for one window; ``failed`` when the call failed after retries."""

    failed: bool = False
    tracks: Mapping[str, TrackVote] = field(default_factory=dict[str, TrackVote])
    objects: Mapping[str, ObjectVote] = field(default_factory=dict[str, ObjectVote])


@dataclass(frozen=True)
class TrackResult:
    """One track's combined judgement (a window's, or every window's)."""

    role: Role
    votes: tuple[Role, Role, Role]
    evidence: str
    frames: tuple[int, ...]
    #: Which of the three votes were failure placeholders (a failed call), not judgements.
    failed: tuple[bool, bool, bool]
    matches_participant: int | None

    @property
    def failed_votes(self) -> int:
        return sum(self.failed)


@dataclass(frozen=True)
class ObjectResult:
    sensitive: bool
    content: str
    frames: tuple[int, ...]


def merge_track_votes(a: TrackVote, b: TrackVote) -> TrackVote:
    """One answer naming a label twice, merged fail closed: a child entry wins; two different roles are ``unsure``."""
    frames = tuple(sorted({*a.frames, *b.frames}))
    if "child" in (a.role, b.role):
        child = a if a.role == "child" else b
        return TrackVote("child", child.evidence, frames, None)
    if a.role != b.role:
        return TrackVote("unsure", a.evidence or b.evidence, frames, None)
    return TrackVote(
        a.role, a.evidence, frames, a.matches_participant if a.matches_participant == b.matches_participant else None
    )


def _valid(frames: Sequence[int], present: frozenset[int]) -> bool:
    """Every cited frame was sent with the track on it, and at least one was cited (rule 5)."""
    return bool(frames) and all(f in present for f in frames)


def judge_window(track_id: str, votes: Sequence[Vote], present: frozenset[int]) -> TrackResult:
    """Rules 2–7 for one track in one window. ``present``: the keyframes sent in this window showing the track."""
    if len(votes) != VOTES:
        raise ValueError(f"the role pass makes exactly {VOTES} votes")
    roles: list[Role] = []
    cited: list[tuple[int, ...]] = []
    evidence: list[str] = []
    indices: list[int | None] = []
    for vote in votes:
        answer = None if vote.failed else vote.tracks.get(track_id)
        if answer is not None and answer.role == "child" and not _valid(answer.frames, present):
            # A child flag is never discarded (fail closed: it locks the track hidden), only its bad citations are.
            answer = TrackVote(role="child", evidence=answer.evidence, frames=())
        if answer is None or (answer.role != "child" and not _valid(answer.frames, present)):
            roles.append("unsure")  # missing, failed or discarded (an unseen frame cited) counts as unsure
            cited.append(())
            evidence.append("")
            indices.append(None)
            continue
        roles.append(answer.role)
        cited.append(tuple(sorted(set(answer.frames))))
        evidence.append(answer.evidence)
        indices.append(answer.matches_participant)
    final: Role
    if "child" in roles:
        final = "child"
    elif all(r == "participant" for r in roles) and len({f for fs in cited for f in fs}) >= 2:
        final = "participant"
    elif all(r == "bystander" for r in roles):
        final = "bystander"
    else:
        final = "unsure"
    if final == "unsure":
        frames = sorted({f for fs in cited for f in fs})
        first = next((e for e in evidence if e.strip()), "")
        text = DISAGREED + first if first else "No usable judgement: hidden until you decide."
    else:
        frames = sorted({f for r, fs in zip(roles, cited, strict=True) if r == final for f in fs})
        text = next(e for r, e in zip(roles, evidence, strict=True) if r == final)
    same = indices[0] if final == "participant" and len(set(indices)) == 1 else None
    return TrackResult(
        role=final,
        votes=(roles[0], roles[1], roles[2]),
        evidence=text,
        frames=tuple(frames),
        failed=(votes[0].failed, votes[1].failed, votes[2].failed),
        matches_participant=same,
    )


def combine_windows(results: Sequence[TrackResult]) -> TrackResult:
    """A track seen in several windows (A14–A16): child anywhere wins; participant or bystander only if it is that
    in every window; anything else is unsure."""
    if not results:
        raise ValueError("a track appears in at least one window")
    if len(results) == 1:
        return results[0]
    roles = [r.role for r in results]
    final: Role
    if "child" in roles:
        final = "child"
    elif all(r == "participant" for r in roles):
        final = "participant"
    elif all(r == "bystander" for r in roles):
        final = "bystander"
    else:
        final = "unsure"
    votes: list[Role] = []
    for k in range(VOTES):
        by_window: list[Role] = [r.votes[k] for r in results]
        if "child" in by_window:
            votes.append("child")
        elif all(v == "participant" for v in by_window):
            votes.append("participant")
        else:
            other: Role = next(v for v in by_window if v != "participant")
            votes.append(other)
    indices = {r.matches_participant for r in results}
    same = next(iter(indices)) if final == "participant" and len(indices) == 1 else None
    return TrackResult(
        role=final,
        votes=(votes[0], votes[1], votes[2]),
        evidence=results[0].evidence,
        frames=tuple(sorted({f for r in results for f in r.frames})),
        failed=(
            any(r.failed[0] for r in results),
            any(r.failed[1] for r in results),
            any(r.failed[2] for r in results),
        ),
        matches_participant=same,
    )


def judge_object(track_id: str, votes: Sequence[Vote], present: frozenset[int]) -> ObjectResult:
    """Rule 4: ``sensitive`` is false only on 3/3 explicit, valid ``false`` votes (B1–B3); else true."""
    answers = [None if v.failed else v.objects.get(track_id) for v in votes]
    valid = [a for a in answers if a is not None and _valid(a.frames, present)]
    clear = len(valid) == VOTES and all(not a.sensitive for a in valid)
    content = next((a.content for a in valid if a.content.strip() and a.sensitive != clear), "")
    content = content or next((a.content for a in valid if a.content.strip()), "")
    return ObjectResult(
        sensitive=not clear,
        content=content or "content not described: hidden until you decide",
        frames=tuple(sorted({f for a in valid for f in a.frames})),
    )


def combine_object_windows(results: Sequence[ObjectResult]) -> ObjectResult:
    """``sensitive`` is false only if false in every window; content from the first window; frames the union."""
    if not results:
        raise ValueError("an object appears in at least one window")
    return ObjectResult(
        sensitive=any(r.sensitive for r in results),
        content=results[0].content,
        frames=tuple(sorted({f for r in results for f in r.frames})),
    )


def disputed(result: TrackResult) -> bool:
    """Escalated once: a disagreement with at least one real judgement (not a child, not all votes failed)."""
    return result.role == "unsure" and result.failed_votes < VOTES


# ---------------------------------------------------------------------------
# Escalation (escalation.md "Applying the ruling"; vectors E1–E9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ruling:
    role: Role
    evidence: str
    frames: tuple[int, ...]


@dataclass(frozen=True)
class Escalation:
    """What escalation adds to one disputed track."""

    role: Role
    escalated: bool
    suggested_role: Suggestion | None
    evidence: str | None
    frames: tuple[int, ...] | None


NO_ESCALATION = Escalation(role="unsure", escalated=False, suggested_role=None, evidence=None, frames=None)


def check_ruling(ruling: Ruling | None, present: frozenset[int]) -> Ruling | None:
    """A ruling counts only if it cites frames shown with the track on them; a ``participant`` ruling needs two
    (the escalation prompt's own bar), else it is read as ``unsure``. ``None``: failed, skipped or invalid."""
    if ruling is not None and ruling.role == "child" and not _valid(ruling.frames, present):
        return Ruling(role="child", evidence=ruling.evidence, frames=())  # a child ruling locks, citations or not
    if ruling is None or not _valid(ruling.frames, present):
        return None
    if ruling.role == "participant" and len(set(ruling.frames)) < 2:
        return Ruling(role="unsure", evidence=ruling.evidence, frames=ruling.frames)
    return ruling


def apply_rulings(rulings: Sequence[Ruling | None]) -> Escalation:
    """Combine one disputed track's windows (``None`` = that window failed, was skipped or cited badly).

    Any ``child`` ruling → child (locked). Else any failed window → no suggestion and ``escalated: false`` (rule 3).
    Else all windows agree → that suggestion (an ``unsure`` agreement suggests nothing but is still escalated);
    windows that disagree suggest nothing (E9). The track's role is never anything but ``unsure`` or ``child``.
    """
    if not rulings:
        raise ValueError("a disputed track is escalated in at least one window")
    for ruling in rulings:
        if ruling is not None and ruling.role == "child":
            return Escalation(role="child", escalated=True, suggested_role=None, evidence=ruling.evidence,
                              frames=ruling.frames)  # fmt: skip
    if any(r is None for r in rulings):
        return NO_ESCALATION
    valid = [r for r in rulings if r is not None]
    agreed = {r.role for r in valid}
    if len(agreed) != 1 or valid[0].role == "unsure":
        return Escalation(role="unsure", escalated=True, suggested_role=None, evidence=None, frames=None)
    role = valid[0].role
    suggestion: Suggestion = "participant" if role == "participant" else "bystander"
    return Escalation(
        role="unsure",
        escalated=True,
        suggested_role=suggestion,
        evidence=valid[0].evidence,
        frames=tuple(sorted({f for r in valid for f in r.frames})),
    )
