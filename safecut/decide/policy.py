"""The policy: deny by default, a reason to allow (DESIGN §2.5, WP3 step 3, API-NOTES §12).

Pure functions over the job's contract files. Every track of every concept starts hidden. The one path to
``keep`` is a person track that the role pass called a participant 3/3 on at least two keyframes, that isn't a
child, a re-entry or a static box, with a scene pass that ran, a usable transcript (when the clip has audio),
every scene child matched, and speech or an introduction as evidence. Anything that could have been kept but
misses one of those becomes ``needs_you`` with the first ``hold`` that explains why.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from safecut.contracts import (
    DecisionItem,
    Decisions,
    Hold,
    Job,
    RoleObject,
    Roles,
    RoleTrack,
    Scene,
    Style,
    Track,
    Tracks,
    Transcript,
)
from safecut.decide.group import group_tracks, inside_share

Decision = Literal["hide", "keep", "needs_you"]
DecidedBy = Literal["policy", "model"]
Kind = Literal["person", "child", "plate", "screen", "document", "other"]

PERSON_CONCEPTS = frozenset({"face", "person"})
#: API-NOTES §12 (PR #2 UI-SPEC §0): exactly these concepts; anything else is ``other``.
SCREEN_CONCEPTS = frozenset({"screen", "phone"})
DOCUMENT_CONCEPTS = frozenset({"document", "name badge"})
#: DESIGN §2.7b: a bystander whose box is taller than this share of the frame gets a whole-person mask.
PROMINENT_HEIGHT = 0.25
#: API-NOTES §12: when several holds apply, the first in this order is written.
HOLD_ORDER: tuple[Hold, ...] = ("no_scene", "no_speech", "no_roles", "unmatched_child", "no_speech_link")
#: A face and a body grouping couldn't pair are still linked for the child lock when the face is inside the body on at
#: least this share of their shared frames (fail closed: lower than grouping's 80 %).
CHILD_LINK = 0.5
#: UI-SPEC §8 request 4: a reason is at most this long, lowercase-first, with no trailing full stop.
REASON_MAX = 90


@dataclass(frozen=True)
class Inputs:
    """What the policy reads. ``roles``, ``scene`` and ``transcript`` are None when their file is missing."""

    job: Job
    tracks: Tracks
    roles: Roles | None = None
    scene: Scene | None = None
    transcript: Transcript | None = None


@dataclass(frozen=True)
class Verdict:
    """One track's outcome before its item combines them."""

    decision: Decision
    decided_by: DecidedBy
    reason: str
    hold: Hold | None = None
    child: bool = False


def kind_of(concept: str) -> Kind:
    if concept in PERSON_CONCEPTS:
        return "person"
    if concept == "license plate":
        return "plate"
    if concept in SCREEN_CONCEPTS:
        return "screen"
    if concept in DOCUMENT_CONCEPTS:
        return "document"
    return "other"


def is_child_vote(row: RoleTrack) -> bool:
    """escalation.md rules 1-2: any child vote, or a child ruling, makes the track a child."""
    return row.role == "child" or "child" in row.votes


def normal_words(text: str) -> str:
    """API-NOTES §12: lowercased, punctuation removed (so "I'm" is one word), spaces collapsed."""
    return " ".join("".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).split())


def speech_evidence(index: int | None, scene: Scene, transcript: Transcript) -> bool:
    """API-NOTES §12: participant ``index`` has a turn by its speaker, or its introduction quote (≥ 2 words,
    normalised) is in the introducing turn's normalised text."""
    if index is None or not 0 <= index < len(scene.participants):
        return False
    who = scene.participants[index]
    if who.speaker is not None and any(turn.speaker == who.speaker for turn in transcript.turns):
        return True
    turn, quote = who.introduced_in_turn, normal_words(who.introduction_quote or "")
    return (
        turn is not None
        and turn < len(transcript.turns)
        and len(quote.split()) >= 2
        and quote in normal_words(transcript.turns[turn].text)
    )


@dataclass(frozen=True)
class _Gates:
    """The job-wide conditions every auto-keep needs (API-NOTES §12), worked out once."""

    no_scene: bool
    no_speech: bool
    usable_transcript: bool
    unmatched_child: bool


def _usable(job: Job, transcript: Transcript | None) -> bool:
    return job.audio and transcript is not None and transcript.status == "ok" and not transcript.degraded


def _gates(inputs: Inputs, groups: Sequence[Sequence[Track]], rows: dict[str, RoleTrack]) -> _Gates:
    scene, job = inputs.scene, inputs.job
    usable = _usable(job, inputs.transcript)
    # API-NOTES §12: a child item has a non-child_phrase track voted child or ruled child by escalation, and isn't
    # made only of re-entries; a child_phrase track never counts, even one voted child (P10, P12).
    voted = {
        tid for tid, row in rows.items()
        if "child" in row.votes or (row.escalated and row.role == "child")
    }  # fmt: skip
    # Counted as distinct children: items linked as one child (the same links the child lock follows, so a child split
    # across a duplicate body or an unpaired face and body counts once and can't satisfy the scene count twice).
    tracks = inputs.tracks.tracks
    root = _components(tracks, child_links(tracks, groups))
    child_items = len({
        root[group[0].track_id]
        for group in groups
        if any(t.track_id in voted and not t.child_phrase for t in group)
        and not all(t.reentry_of is not None for t in group)
    })  # fmt: skip
    return _Gates(
        no_scene=scene is None or scene.status != "ok",
        no_speech=job.audio and not usable,
        usable_transcript=usable,
        unmatched_child=scene is not None and len(scene.children) > child_items,
    )


def short_reason(reason: str) -> str:
    """UI-SPEC §8 request 4: at most :data:`REASON_MAX` characters, lowercase-first, no trailing full stop."""
    text = " ".join(reason.split()).rstrip(" .")
    if len(text) > REASON_MAX:
        text = text[: REASON_MAX - 1].rstrip() + "…"
    return text[:1].lower() + text[1:] if text else "hidden by default"


def _evidence(row: RoleTrack) -> str:
    return row.evidence.strip() or "no evidence given"


def judge_person(track: Track, row: RoleTrack | None, inputs: Inputs, gates: _Gates) -> Verdict:
    """One face or person track (DESIGN §2.5 and API-NOTES §12; the first rule that applies wins)."""
    if track.child_phrase:  # WP3 rule 0
        return Verdict("hide", "policy", "child: named as a child by the miss loop, so always hidden", child=True)
    if row is not None and is_child_vote(row):
        return Verdict("hide", "model", f"child: {_evidence(row)}", child=True)
    if track.origin == "static":
        return Verdict("needs_you", "policy", "spotted by Muse Spark; SAM couldn't follow it, so a fixed box hides it")
    roles = inputs.roles
    if roles is None or roles.status != "ok" or row is None or row.failed_votes == 3:
        return Verdict("needs_you", "policy", "the role check couldn't judge this person",
                       hold=_first_hold(gates, "no_roles"))  # fmt: skip
    if row.role == "bystander":
        return Verdict("hide", "model", f"bystander: {_evidence(row)}")
    if row.role == "unsure":
        suggestion = f"; a closer look suggests {row.suggested_role}" if row.suggested_role else ""
        hold = None if row.escalated else _first_hold(gates, "no_roles")
        return Verdict("needs_you", "policy", f"checks didn't all agree{suggestion}", hold=hold)
    seen = {f for f in row.frames if track.first <= f <= track.last}  # cited frames the track is actually on
    if row.votes != ["participant"] * 3 or row.failed_votes or len(seen) < 2:
        return Verdict("needs_you", "policy", "participant, but not on 3/3 votes over 2 keyframes")
    if track.reentry_of is not None:
        return Verdict("needs_you", "policy", "came back into view as a new ID: hidden until you merge it")

    hold = _participant_hold(row, inputs, gates)
    if hold is not None:
        return Verdict("needs_you", "policy", _HOLD_REASONS[hold], hold=hold)
    return Verdict("keep", "model", f"participant: {_evidence(row)}")


_HOLD_REASONS: dict[Hold, str] = {
    "no_scene": "participant, but the scene check didn't run, so you decide",
    "no_speech": "participant, but the speech check didn't work, so you decide",
    "no_roles": "the role check couldn't judge this person",
    "unmatched_child": "participant, but a child in the scene wasn't found, so nobody is kept automatically",
    "no_speech_link": "participant, but nothing they said or were introduced by links them to the talk",
}


def _first_hold(gates: _Gates, hold: Hold) -> Hold:
    """API-NOTES §12: when several holds apply, the first in :data:`HOLD_ORDER` is written."""
    if gates.no_scene:
        return "no_scene"
    if gates.no_speech:
        return "no_speech"
    return hold


def _participant_hold(row: RoleTrack, inputs: Inputs, gates: _Gates) -> Hold | None:
    if gates.no_scene or gates.no_speech:
        return _first_hold(gates, "no_scene")
    if gates.unmatched_child:
        return "unmatched_child"
    scene, transcript = inputs.scene, inputs.transcript
    linked = (
        not gates.usable_transcript
        or scene is None
        or transcript is None
        or speech_evidence(row.matches_participant, scene, transcript)
    )
    return None if linked else "no_speech_link"


def judge_object(track: Track, row: RoleTrack | None, obj: RoleObject | None) -> Verdict:
    """A plate, screen, document or other object: never kept without the creator (WP3 step 3)."""
    if track.child_phrase:  # WP3 rule 0 (over-locking is accepted: API-NOTES §12 note)
        return Verdict("hide", "policy", "child: named as a child by the miss loop, so always hidden", child=True)
    if row is not None and is_child_vote(row):
        return Verdict("hide", "model", f"child: {_evidence(row)}", child=True)
    if track.concept == "license plate":
        return Verdict("hide", "policy", "licence plate: always hidden")
    if track.origin == "static":
        return Verdict("needs_you", "policy", "spotted by Muse Spark; SAM couldn't follow it, so a fixed box hides it")
    if obj is None:
        return Verdict("hide", "policy", f"{track.concept}: hidden by default")
    content = obj.content.strip() or track.concept
    if obj.sensitive:
        return Verdict("hide", "model", f"sensitive {track.concept}: {content}")
    return Verdict("needs_you", "policy", f"looks non-personal ({content}); keep it clear if you agree")


def _combine(verdicts: Sequence[Verdict]) -> Verdict:
    """An item's outcome: a child anywhere locks it; all keep keeps; any doubt or a keep/hide mix asks the creator;
    otherwise hidden."""
    children = [v for v in verdicts if v.child]
    if children:
        by = "policy" if any(v.decided_by == "policy" for v in children) else "model"
        return Verdict("hide", by, children[0].reason, child=True)
    decisions = {v.decision for v in verdicts}
    if decisions == {"keep"}:
        return verdicts[0]
    if decisions == {"hide"}:
        by = "model" if all(v.decided_by == "model" for v in verdicts) else "policy"
        return Verdict("hide", by, verdicts[0].reason)
    asking = [v for v in verdicts if v.decision == "needs_you"]
    holds = {v.hold for v in asking}
    hold: Hold | None = next((h for h in HOLD_ORDER if h in holds), None)
    reason = asking[0].reason if asking else "the face and body checks disagree"
    return Verdict("needs_you", "policy", reason, hold=hold)


def child_links(tracks: Sequence[Track], groups: Sequence[Sequence[Track]]) -> dict[str, set[str]]:
    """Which tracks are one person for the child lock: tracks sharing a review item; tracks linked by ``reentry_of``
    (either way); and a face inside a body on half their shared frames or more when either of the two is unpaired
    (grouping, which needs 80 %, didn't make them one item: a tie, a face partly outside its body, or the face paired
    with someone holding the child). Two paired items never link this way (an adult carrying their child)."""
    by_id = {t.track_id: t for t in tracks}
    group_of = {t.track_id: tuple(x.track_id for x in g) for g in groups for t in g}
    alone = {g[0].track_id for g in groups if len(g) == 1}
    links: dict[str, set[str]] = {t.track_id: set(group_of[t.track_id]) - {t.track_id} for t in tracks}
    for t in tracks:
        if t.reentry_of is not None and t.reentry_of in by_id:
            links[t.track_id].add(t.reentry_of)
            links[t.reentry_of].add(t.track_id)
    faces = [t for t in tracks if t.concept == "face" and t.origin == "sam"]
    bodies = [t for t in tracks if t.concept == "person" and t.origin == "sam"]
    for f in faces:
        for b in bodies:
            if (f.track_id in alone or b.track_id in alone) and inside_share(f, b) >= CHILD_LINK:
                links[f.track_id].add(b.track_id)
                links[b.track_id].add(f.track_id)
    return links


def _components(tracks: Sequence[Track], links: Mapping[str, set[str]]) -> dict[str, str]:
    root = {t.track_id: t.track_id for t in tracks}

    def find(track_id: str) -> str:
        while root[track_id] != track_id:
            root[track_id] = root[root[track_id]]
            track_id = root[track_id]
        return track_id

    for tid, others in links.items():
        for other in others:
            root[find(tid)] = find(other)
    return {t.track_id: find(t.track_id) for t in tracks}


def _child_closure(
    tracks: Sequence[Track], groups: Sequence[Sequence[Track]], judged: Mapping[str, Verdict]
) -> dict[str, Verdict]:
    """No ID of a child can be kept: every track :func:`child_links` connects to a child, however many links away,
    is locked hidden as a child too."""
    root = _components(tracks, child_links(tracks, groups))
    child_roots = {root[tid] for tid, v in judged.items() if v.child}
    reason = "child: linked to a child (same item, a re-entry, or face and body), so always hidden"
    return {
        t.track_id: Verdict("hide", "policy", reason, child=True)
        for t in tracks
        if not judged[t.track_id].child and root[t.track_id] in child_roots
    }


def style_for(kind: Kind, group: Sequence[Track], job: Job) -> Style:
    """DESIGN §2.7/§2.7b: objects solid; a child or a prominent person gets a whole-person solid mask; other
    people a locked-grid mosaic sized from the face (or solid with no face to size it)."""
    has_person = any(t.concept == "person" for t in group)
    has_face = any(t.concept == "face" for t in group)
    if kind == "child":
        # The whole child: a body mask, or (face only) the face and a body under it (the guard estimates one).
        return "person_solid" if has_person or has_face else "solid"
    if kind != "person":
        return "solid"
    prominent = any(
        t.concept == "person" and max(b[3] - b[1] for b in t.boxes.values()) > PROMINENT_HEIGHT * job.height
        for t in group
    )
    # A face taller than that share is a close-up: whole person, with a body under the face wherever no body track
    # holds it (SAM missed the body, or lost it early; the guard estimates one per frame).
    close_up = any(
        t.concept == "face" and max(b[3] - b[1] for b in t.boxes.values()) > PROMINENT_HEIGHT * job.height
        for t in group
    )
    if (prominent and has_person) or close_up:
        return "person_solid"
    return "pixelate" if has_face else "solid"


def _rows(tracks: Sequence[RoleTrack]) -> dict[str, RoleTrack]:
    """One row per track. Should a track appear twice, the row that keeps more hidden wins (fail closed): a child
    vote first, then anything but a participant ruling."""
    rows: dict[str, RoleTrack] = {}
    for row in tracks:
        held = rows.get(row.track_id)
        if held is None or _hides_more(row, held):
            rows[row.track_id] = row
    return rows


def _hides_more(row: RoleTrack, than: RoleTrack) -> bool:
    if is_child_vote(row) != is_child_vote(than):
        return is_child_vote(row)
    return than.role == "participant" and row.role != "participant"


def decide(inputs: Inputs) -> Decisions:
    """``decisions.json`` for every track: one item per group, ``i_1`` … in order of first frame."""
    rows = _rows(inputs.roles.tracks) if inputs.roles is not None else {}
    objects: dict[str, RoleObject] = {}
    for obj in inputs.roles.objects if inputs.roles is not None else []:
        if obj.track_id not in objects or obj.sensitive:  # a duplicate ruling fails closed: sensitive wins
            objects[obj.track_id] = obj
    groups = group_tracks(inputs.tracks.tracks)
    gates = _gates(inputs, groups, rows)
    judged = {
        t.track_id: judge_person(t, rows.get(t.track_id), inputs, gates)
        if t.concept in PERSON_CONCEPTS
        else judge_object(t, rows.get(t.track_id), objects.get(t.track_id))
        for t in inputs.tracks.tracks
    }
    judged.update(_child_closure(inputs.tracks.tracks, groups, judged))
    items: list[DecisionItem] = []
    for number, group in enumerate(groups, start=1):
        person = all(t.concept in PERSON_CONCEPTS for t in group)
        verdict = _combine([judged[t.track_id] for t in group])
        kind: Kind = "child" if verdict.child else ("person" if person else kind_of(group[0].concept))
        frames: set[int] = set()
        for t in group:
            if t.track_id in rows:
                frames.update(rows[t.track_id].frames)
            if t.track_id in objects:
                frames.update(objects[t.track_id].frames)
        items.append(
            DecisionItem(
                item_id=f"i_{number}",
                track_ids=[t.track_id for t in group],
                kind=kind,
                decision=verdict.decision,
                reason=short_reason(verdict.reason),
                evidence_frames=sorted(frames),
                style=None if verdict.decision == "keep" else style_for(kind, group, inputs.job),
                decided_by=verdict.decided_by,
                locked=verdict.child,
                hold=verdict.hold if verdict.decision == "needs_you" else None,
                origin="static" if all(t.origin == "static" for t in group) else "sam",
            )
        )
    return Decisions(items=items)
