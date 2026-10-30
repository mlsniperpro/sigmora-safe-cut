"""``roles``: Set-of-Mark keyframes → three independent role votes per window → ``roles.json`` (``role-pass.md``,
``escalation.md``, ``miss-loop.md``).

1. Every 1 fps keyframe is drawn with its labels and sent in windows of ≤ 50 (5 s overlap), three votes each
   sharing one cached prefix; only the final instruction block differs between votes.
2. Votes are aggregated by :mod:`safecut.scout.votes`: participant only on 3/3 valid votes over ≥ 2 keyframes.
3. Miss loop 1 sends what the votes say SAM missed to SAM (object prompts, recurring phrases), then a role re-pass
   judges loop 1's new tracks on the keyframes around them; miss loop 2 sends the re-pass's misses, and its tracks
   stay hidden for the creator. Every reported miss ends up covered (a SAM track or a static box).
4. Disputed tracks get one escalation call per window at max effort: a suggestion for the creator, never a keep.

The stage always writes ``roles.json`` (``failed``/``skipped`` with every track ``unsure`` when no vote could run).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecut import config
from safecut.config import Settings
from safecut.contracts import (
    Job,
    Missed,
    Point,
    RoleObject,
    Roles,
    RoleTrack,
    Scene,
    Track,
    Tracks,
    Transcript,
    dump,
    load,
)
from safecut.meta import replay
from safecut.meta.client import MetaClient
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.scout import calls, miss, missloop, prompts, som, votes
from safecut.scout.schemas import ESCALATION, ROLE_PASS, EscalationOut, RolePassOut
from safecut.track.axes import time_to_frame

log = logging.getLogger(__name__)

JOB, TRACKS, SCENE, TRANSCRIPT, ROLES = "job.json", "tracks.json", "scene.json", "transcript.json", "roles.json"
VOTE_STAGE = "roles"
ESCALATE_STAGE = "escalate"
WINDOW = 50
OVERLAP_S = 5
#: Votes 2 and 3 start once vote 1 has been answered, or this long after it was sent (the prefix is cached).
STAGGER_S = 20.0
#: Speech-fallback turn times are untrusted: each turn's frame range is widened by this (speech-fallback.md).
FALLBACK_TOLERANCE_S = 1.5
#: Loop 1's re-pass looks at keyframes this close to the new tracks (miss-loop.md inputs).
REPASS_REACH_S = 2
PEOPLE = frozenset({"face", "person"})


def windows(frames: Sequence[int], fps: int, size: int = WINDOW, overlap_s: int = OVERLAP_S) -> list[list[int]]:
    """Consecutive keyframe windows of at most ``size``, each overlapping the next by ``overlap_s`` seconds."""
    if not frames:
        return []
    out: list[list[int]] = []
    start = 0
    while True:
        out.append(list(frames[start : start + size]))
        if start + size >= len(frames):
            return out
        cut = frames[start + size - 1] - overlap_s * fps
        start = next(i for i in range(start + 1, len(frames)) if frames[i] > cut)


def participant_count(scene: Scene | None) -> int:
    """How many participants a vote may index (none when the scene pass didn't succeed)."""
    return len(scene.participants) if scene is not None and scene.status == "ok" else 0


def is_person(track: Track) -> bool:
    return track.concept in PEOPLE


# ---------------------------------------------------------------------------- prompt context


def transcript_by_frames(job: Job, transcript: Transcript | None) -> str:
    if not job.audio:
        return "none (the clip has no audio)"
    if transcript is None or transcript.status != "ok" or transcript.degraded:
        return "speech unavailable"
    if not transcript.turns:
        return "none (no speech was recognised)"
    widen = FALLBACK_TOLERANCE_S if transcript.source_kind == "fallback" else 0.0
    lines: list[str] = []
    for t in transcript.turns:
        a = time_to_frame(t.start - widen, job.fps, job.frames)
        b = time_to_frame(t.end + widen, job.fps, job.frames)
        lines.append(f'[{t.speaker} frames {a}–{b}] "{prompts.inline(t.text, prompts.TURN_CHARS)}"')
    return "\n".join(lines)


def context_text(job: Job, scene: Scene | None, transcript: Transcript | None, swept: Sequence[str]) -> str:
    ok = scene is not None and scene.status == "ok"
    summary = prompts.inline(scene.summary, 600) if ok and scene is not None else "No scene context is available."
    participants = "none"
    children = "none"
    if ok and scene is not None:
        if scene.participants:
            participants = "; ".join(
                f"[{i}] {prompts.inline(p.description)} ({prompts.inline(p.evidence)})"
                for i, p in enumerate(scene.participants)
            )
        if scene.children:
            children = "; ".join(prompts.inline(c.description) for c in scene.children)
    return prompts.render("role.context", scene_summary=summary, participants_list=participants,
                          children_list=children, transcript_by_frames=transcript_by_frames(job, transcript),
                          swept=", ".join(swept))  # fmt: skip


def labels_text(per_frame: Sequence[tuple[int, Sequence[str]]]) -> str:
    return "{" + ", ".join(f"F{f}: [{', '.join(labels)}]" for f, labels in per_frame) + "}"


def vote_text(k: int, per_frame: Sequence[tuple[int, Sequence[str]]]) -> str:
    labels = labels_text(per_frame)
    if k == 3:
        order = list(dict.fromkeys(label for _, ls in per_frame for label in ls))
        return prompts.render("role.vote3", labels_per_frame=labels, labels_reversed=", ".join(reversed(order)))
    return prompts.render(f"role.vote{k}", labels_per_frame=labels)


# ---------------------------------------------------------------------------- one role pass


@dataclass
class Window:
    index: int
    frames: list[int]
    #: The labels judged in this window, per keyframe (only frames where one of them is present).
    per_frame: list[tuple[int, list[str]]]
    #: Frames where SAM hit its object cap: shown, but never evidence (role-pass.md failure handling).
    crowded: frozenset[int] = frozenset()

    @property
    def sent(self) -> frozenset[int]:
        return frozenset(self.frames)

    def shown(self, track_id: str) -> bool:
        """Whether this window showed the track at all (crowded frames included)."""
        return any(track_id in labels for _, labels in self.per_frame)

    def present(self, track_id: str) -> frozenset[int]:
        """The keyframes that can count as this track's evidence: sent, showing it, and not crowded."""
        return frozenset(f for f, labels in self.per_frame if track_id in labels and f not in self.crowded)


@dataclass
class PassResult:
    """A role pass's ballots per window, and what its votes said SAM missed."""

    windows: list[Window]
    ballots: list[list[votes.Vote]]
    misses: list[miss.RawMiss] = field(default_factory=list[miss.RawMiss])
    window_of_miss: list[int] = field(default_factory=list[int])
    calls: int = 0
    failed_calls: int = 0
    budget_stops: int = 0
    hallucinated: int = 0


def to_vote(
    answer: RolePassOut, judged: set[str], participants: int, people: frozenset[str] = frozenset()
) -> tuple[votes.Vote, int]:
    """A parsed answer as a :class:`votes.Vote`; labels it wasn't asked about are dropped and counted (rule 6),
    except a child answer on any person label of the job (``people``): any child vote wins, asked or not.

    A label answered twice is merged fail closed: a child answer wins, two different roles become ``unsure``, and
    an object is sensitive if either entry says so. A participant index outside the scene's list is dropped."""
    tracks: dict[str, votes.TrackVote] = {}
    objects: dict[str, votes.ObjectVote] = {}
    dropped = 0
    for t in answer.tracks:
        if t.track_id not in judged and not (t.role == "child" and t.track_id in people):
            dropped += 1
            continue
        index = (
            t.matches_participant
            if t.matches_participant is not None and 0 <= t.matches_participant < participants
            else None
        )
        vote = votes.TrackVote(t.role, t.evidence, tuple(t.frames), index)
        if t.track_id in tracks:
            vote = votes.merge_track_votes(tracks[t.track_id], vote)
        tracks[t.track_id] = vote
    for o in answer.objects:
        if o.track_id not in judged:
            dropped += 1
            continue
        found = votes.ObjectVote(o.sensitive, o.content, tuple(o.frames))
        if o.track_id in objects:
            before = objects[o.track_id]
            found = votes.ObjectVote(before.sensitive or found.sensitive, before.content or found.content,
                                     tuple(sorted({*before.frames, *found.frames})))  # fmt: skip
        objects[o.track_id] = found
    return votes.Vote(tracks=tracks, objects=objects), dropped


async def three_votes(
    make: Callable[[int], Coroutine[Any, Any, calls.Outcome[RolePassOut]]], *, stagger: bool
) -> list[calls.Outcome[RolePassOut]]:
    """Vote 1 first; votes 2 and 3 together once vote 1 has answered or ``STAGGER_S`` passed, so they read the
    prefix vote 1 cached (``role-pass.md`` rule 1)."""
    try:
        # A TaskGroup: if any vote raises, the others are cancelled (never a paid call left running unwatched).
        async with asyncio.TaskGroup() as group:
            first = group.create_task(make(1))
            if stagger:
                await asyncio.wait({first}, timeout=STAGGER_S)
            rest = [group.create_task(make(2)), group.create_task(make(3))]
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from None
    return [first.result(), *(r.result() for r in rest)]


async def role_pass(
    ctx: calls.Context,
    *,
    tracks: Tracks,
    judged: Sequence[Track],
    frames: Sequence[int],
    context: str,
    tag: str,
    participants: int,
    every_window: bool = True,
) -> PassResult:
    """Three votes per window over ``frames`` (keyframes), judging ``judged``. The first pass asks every window,
    even one with no labels, because the miss loop rides in it; a re-pass only asks windows with new labels."""
    keyframes = som.write(ctx.job_dir, ctx.job, tracks, frames)
    judged_ids = {t.track_id for t in judged}
    people = frozenset(t.track_id for t in tracks.tracks if is_person(t))
    result = PassResult(windows=[], ballots=[])
    for w, chunk in enumerate(windows([k.frame for k in keyframes], ctx.job.fps)):
        per_frame = [
            (k.frame, [label for label in k.labels if label in judged_ids]) for k in keyframes if k.frame in chunk
        ]
        crowded = frozenset(chunk) & frozenset(tracks.crowded_frames)
        labelled = [(f, ls) for f, ls in per_frame if ls]
        result.windows.append(Window(index=w, frames=chunk, per_frame=labelled, crowded=crowded))
    system = calls.system(prompts.text("role.system"))

    async def run_window(window: Window) -> list[calls.Outcome[RolePassOut]]:
        images = [calls.image_part(ctx.job_dir / som.SOM_DIR / f"{f:06d}.jpg") for f in window.frames]
        prefix = [calls.text_part(context), *images]

        def make(k: int) -> Coroutine[Any, Any, calls.Outcome[RolePassOut]]:
            final = calls.text_part(vote_text(k, window.per_frame))
            info = {"vote": k, "frames": window.frames, "labels_per_frame": window.per_frame}
            return calls.call_json(ctx, stage=VOTE_STAGE, key=f"{tag}-w{window.index}-v{k}", info=info,
                                   model=ctx.settings.role_model, effort=ctx.settings.role_effort,
                                   messages=lambda _fid: [system, calls.user(*prefix, final)], schema=ROLE_PASS,
                                   schema_name="role_pass", out=RolePassOut)  # fmt: skip

        return await three_votes(make, stagger=not ctx.replay)

    asked = [w for w in result.windows if w.per_frame or every_window]
    outcomes = await asyncio.gather(*(run_window(w) for w in asked))
    by_window = dict(zip((w.index for w in asked), outcomes, strict=True))
    for window in result.windows:
        ballots: list[votes.Vote] = []
        for outcome in by_window.get(window.index, []):
            result.calls += 1
            if outcome.status != "ok" or outcome.value is None:
                result.failed_calls += 1
                result.budget_stops += outcome.status == "skipped"
                ballots.append(votes.Vote(failed=True))
                continue
            vote, dropped = to_vote(outcome.value, judged_ids, participants, people)
            result.hallucinated += dropped
            ballots.append(vote)
            for m in outcome.value.missed:
                point = (m.point.x, m.point.y)
                raw = miss.RawMiss(m.what, m.sam_phrase, m.frame, point, m.box, m.recurs)
                result.misses.append(raw)
                result.window_of_miss.append(window.index)
        result.ballots.append(ballots)
    if result.hallucinated:
        log.info("role pass named labels it wasn't asked about", extra={"tag": tag, "count": result.hallucinated})
    return result


@dataclass
class Judged:
    person: dict[str, votes.TrackResult] = field(default_factory=dict[str, votes.TrackResult])
    objects: dict[str, votes.ObjectResult] = field(default_factory=dict[str, votes.ObjectResult])


def child_voted(ballots: Sequence[votes.Vote], track_id: str) -> bool:
    return any((vote := b.tracks.get(track_id)) is not None and vote.role == "child" for b in ballots if not b.failed)


def aggregate(result: PassResult, judged: Sequence[Track]) -> Judged:
    out = Judged()
    for track in judged:
        per_window: list[votes.TrackResult] = []
        per_object: list[votes.ObjectResult] = []
        for window, ballots in zip(result.windows, result.ballots, strict=True):
            # A window that showed the track only on crowded frames is still judged, with no valid evidence: a
            # child vote there still locks it, anything else there can't count toward a keep. So is a window with a
            # child vote for a track it didn't show (any child vote wins, fail closed).
            relevant = window.shown(track.track_id) or (is_person(track) and child_voted(ballots, track.track_id))
            if not relevant or len(ballots) != votes.VOTES:
                continue
            present = window.present(track.track_id)
            if is_person(track):
                per_window.append(votes.judge_window(track.track_id, ballots, present))
            else:
                per_object.append(votes.judge_object(track.track_id, ballots, present))
        if per_window:
            out.person[track.track_id] = votes.combine_windows(per_window)
        if per_object:
            out.objects[track.track_id] = votes.combine_object_windows(per_object)
    return out


# ---------------------------------------------------------------------------- miss loop


def validated_misses(result: PassResult, job: Job, tracks: Tracks) -> list[miss.Miss]:
    valid: list[miss.Miss] = []
    for raw, w in zip(result.misses, result.window_of_miss, strict=True):
        item = miss.validate(raw, sent=result.windows[w].sent, width=job.width, height=job.height)
        if item is not None:
            valid.append(item)
    fresh = miss.untracked(miss.dedupe(valid, job.width, job.height), tracks.tracks)
    if len(fresh) < len(valid):
        log.info("misses dropped as duplicates or already tracked", extra={"count": len(valid) - len(fresh)})
    return fresh


def to_missed(m: miss.Miss) -> Missed:
    return Missed(what=m.what, sam_phrase=m.phrase, frame=m.frame, point=Point(x=m.point[0], y=m.point[1]),
                  box=m.box, recurs=m.recurs, track_ids=list(m.track_ids))  # fmt: skip


# ---------------------------------------------------------------------------- escalation


def dispute_text(track_id: str, ballots: Sequence[Sequence[votes.Vote]]) -> str:
    said: list[str] = []
    for k in range(votes.VOTES):
        answer = next((b[k].tracks[track_id] for b in ballots if len(b) == votes.VOTES and not b[k].failed
                       and track_id in b[k].tracks), None)  # fmt: skip
        said.append("no answer" if answer is None else f'{answer.role}: "{prompts.inline(answer.evidence, 200)}"')
    return f"{track_id}: [{', '.join(said)}]"


async def escalate(
    ctx: calls.Context,
    *,
    tracks: Tracks,
    disputed: Sequence[str],
    ballots_of: dict[str, list[list[votes.Vote]]],
    context_summary: str,
    transcript_frames: str,
) -> dict[str, votes.Escalation]:
    """One call per ≤ 50-keyframe window holding disputed tracks; rulings validated and combined per track."""
    if not disputed:
        return {}
    by_id = {t.track_id: t for t in tracks.tracks}
    pool = set(som.keyframe_numbers(ctx.job)) | set(som.extra_keyframes(ctx.job, [by_id[d] for d in disputed]))
    frames = [f for f in sorted(pool) if any(f in by_id[d].boxes for d in disputed)]
    chunks = windows(frames, ctx.job.fps)
    settings = ctx.settings
    if not await missloop.calls_affordable(ctx, chunks, tracks, model=settings.escalate_model,
                                           effort=settings.escalate_effort, per_window=1):  # fmt: skip
        log.warning("escalation skipped: no budget beside the audit reserve", extra={"disputed": len(disputed)})
        return {}  # advisory only: the disputed tracks stay unsure, with no suggestion
    crowded = frozenset(tracks.crowded_frames)
    som.write(ctx.job_dir, ctx.job, tracks, frames)
    context = prompts.render("escalate.context", scene_summary=context_summary, transcript_by_frames=transcript_frames)
    system = calls.system(prompts.text("escalate.system"))
    # Per window index, combined in time order (escalation.md: the evidence is the first window's), not in the order
    # the concurrent calls happen to finish.
    rulings: dict[str, dict[int, votes.Ruling | None]] = {d: {} for d in disputed}
    children: dict[str, votes.Ruling] = {}

    async def one(index: int, chunk: list[int]) -> None:
        shown = {d: [f for f in chunk if f in by_id[d].boxes] for d in disputed}
        # Crowded frames are shown but never evidence (as in the role pass): a ruling citing only them is invalid,
        # except a child ruling, which locks whatever it cites.
        present = {d: frozenset(f for f in shown[d] if f not in crowded) for d in disputed}
        here = [d for d in disputed if shown[d]]
        if not here:
            return
        per_frame = [(f, [d for d in here if f in by_id[d].boxes]) for f in chunk]
        ask = prompts.render("escalate.user", labels_per_frame=labels_text([(f, ls) for f, ls in per_frame if ls]),
                             disputes="\n".join(dispute_text(d, ballots_of[d]) for d in here))  # fmt: skip
        images = [calls.image_part(ctx.job_dir / som.SOM_DIR / f"{f:06d}.jpg") for f in chunk]
        outcome = await calls.call_json(
            ctx, stage=ESCALATE_STAGE, key=f"w{index}", model=ctx.settings.escalate_model,
            effort=ctx.settings.escalate_effort,
            messages=lambda _fid: [system, calls.user(calls.text_part(context), *images, calls.text_part(ask))],
            schema=ESCALATION, schema_name="escalation", out=EscalationOut,
            info={"frames": chunk, "disputed": here},
        )  # fmt: skip
        answers: dict[str, votes.Ruling] = {}
        for got in outcome.value.rulings if outcome.value is not None else []:
            ruling = votes.Ruling(got.role, got.evidence, tuple(got.frames))
            seen = answers.get(got.track_id)
            answers[got.track_id] = ruling if seen is None else votes.merge_rulings(seen, ruling)
            log.info("escalation", extra={"track": got.track_id, "why_others_wrong": got.why_others_wrong[:200]})
        for d in here:
            rulings[d][index] = votes.check_ruling(answers.get(d), present[d])
        for track_id, ruling in answers.items():
            # Every tag is drawn on the images: a child ruling on a label it wasn't asked about still locks it.
            if track_id not in here and ruling.role == "child" and track_id in by_id and is_person(by_id[track_id]):
                children.setdefault(track_id, ruling)

    await asyncio.gather(*(one(i, chunk) for i, chunk in enumerate(chunks)))
    out = {d: votes.apply_rulings([r[i] for i in sorted(r)]) for d, r in rulings.items() if r}
    for track_id, ruling in children.items():
        if out.get(track_id, votes.NO_ESCALATION).role != "child":
            out[track_id] = votes.Escalation(role="child", escalated=True, suggested_role=None,
                                             evidence=ruling.evidence, frames=())  # fmt: skip
    return out


# ---------------------------------------------------------------------------- the stage


def load_optional[M: Scene | Transcript](path: Path, model: type[M]) -> M | None:
    """The earlier stage's file, or ``None`` when it is missing or unreadable: the role pass then runs without that
    context (no scene participants or speech to support a keep, so it leans to unsure, the safe side)."""
    if not path.exists():
        return None
    try:
        return load(path, model)
    except ValueError as exc:  # ContractError: a corrupt file is no context, never a crash before roles.json
        log.warning("context file unreadable; judged without it", extra={"file": path.name, "error": str(exc)[:200]})
        return None


def role_track(track_id: str, result: votes.TrackResult, escalation: votes.Escalation | None) -> RoleTrack:
    role = result.role
    if escalation is not None and escalation.role == "child":
        role = "child"
    return RoleTrack(
        track_id=track_id,
        role=role,
        votes=list(result.votes),
        escalated=escalation.escalated if escalation is not None else False,
        evidence=result.evidence,
        frames=list(result.frames),
        failed_votes=result.failed_votes,
        matches_participant=result.matches_participant,
        suggested_role=escalation.suggested_role if escalation is not None else None,
        escalation_evidence=escalation.evidence if escalation is not None and escalation.escalated else None,
        escalation_frames=list(escalation.frames) if escalation is not None and escalation.frames is not None else None,
    )


UNSEEN = votes.TrackResult(
    role="unsure",
    votes=("unsure", "unsure", "unsure"),
    evidence="Not on any keyframe the judges saw.",
    frames=(),
    failed=(False, False, False),
    matches_participant=None,
)


@dataclass
class State:
    """What the role passes and miss loops have found so far."""

    tracks: Tracks
    judged: list[Track]
    swept: list[str]
    results: Judged
    ballots_of: dict[str, list[list[votes.Vote]]]
    misses: list[miss.Miss] = field(default_factory=list[miss.Miss])


async def miss_loops(ctx: calls.Context, state: State, first: PassResult, scene: Scene | None,
                     transcript: Transcript | None) -> None:  # fmt: skip
    """Loop 1 on the first pass's misses, a role re-pass on its new tracks, loop 2 on the re-pass's misses."""
    job = ctx.job
    loop_misses = validated_misses(first, job, state.tracks)
    for loop in range(1, miss.MAX_LOOPS + 1):
        if not loop_misses:
            return
        planned = miss.plan(loop_misses, swept=state.swept)
        outcome = await missloop.run_loop(
            ctx, state.tracks, prompts_=planned.prompts, sweeps=planned.sweeps, static=planned.static, loop=loop
        )
        state.misses += loop_misses
        state.swept += outcome.swept  # only what SAM really searched counts as "already searched"
        state.tracks = outcome.tracks
        dump(state.tracks, ctx.job_dir / TRACKS)
        stamp_output(ctx.job_dir)  # even if this run dies later, a re-run still knows its own appends
        new_judged = [t for t in outcome.new if som.judged(t)]
        if loop == miss.MAX_LOOPS or not new_judged:
            return  # loop 2's tracks get no role pass: they stay hidden for the creator
        reach = REPASS_REACH_S * job.fps
        keyframes = sorted(set(som.keyframe_numbers(job)) | set(som.extra_keyframes(job, new_judged)))
        near = [f for f in keyframes if any(t.first - reach <= f <= t.last + reach for t in new_judged)]
        if not await missloop.repass_affordable(ctx, windows(near, job.fps), state.tracks):
            log.warning("miss loop: no budget for the role re-pass beside the audit reserve; loop 1's tracks stay "
                        "hidden", extra={"tracks": len(new_judged)})  # fmt: skip
            return
        added = ", ".join(t.track_id for t in new_judged)
        context = context_text(job, scene, transcript, state.swept) + f"\nThese were added last round: {added}."
        again = await role_pass(
            ctx, tracks=state.tracks, judged=new_judged, frames=near, context=context, tag=f"pass{loop + 1}",
            participants=participant_count(scene), every_window=False,
        )  # fmt: skip
        later = aggregate(again, new_judged)
        flagged = [t for t in state.judged if is_person(t) and any(child_voted(b, t.track_id) for b in again.ballots)]
        earlier = aggregate(again, flagged)
        for track_id, child in earlier.person.items():
            prior = state.results.person.get(track_id)
            state.results.person[track_id] = votes.combine_windows([prior, child]) if prior else child
        state.results.person.update(later.person)
        state.results.objects.update(later.objects)
        state.ballots_of.update({t.track_id: again.ballots for t in new_judged})
        loop_misses = validated_misses(again, job, state.tracks)


def assemble(state: State, status: calls.Status, escalations: dict[str, votes.Escalation], model: str,
             keyframes: Sequence[int]) -> Roles:  # fmt: skip
    seen = {t.track_id for t in state.judged} | state.results.person.keys() | state.results.objects.keys()
    role_tracks: list[RoleTrack] = []
    objects: list[RoleObject] = []
    for track in (t for t in state.tracks.tracks if som.judged(t) and t.track_id in seen):
        if is_person(track):
            result = state.results.person.get(track.track_id, UNSEEN)
            if status != "ok":
                result = votes.TrackResult(
                    role="unsure", votes=result.votes, evidence="The role checks could not run.", frames=(),
                    failed=result.failed, matches_participant=None,
                )  # fmt: skip
            role_tracks.append(role_track(track.track_id, result, escalations.get(track.track_id)))
        elif track.track_id in state.results.objects:
            o = state.results.objects[track.track_id]
            objects.append(
                RoleObject(track_id=track.track_id, sensitive=o.sensitive, content=o.content, frames=list(o.frames))
            )
    return Roles(
        status=status,
        model=model if status == "ok" else None,
        tracks=role_tracks,
        objects=objects,
        missed=[to_missed(m) for m in state.misses if m.track_ids],
        keyframes=[f"{som.SOM_DIR}/{f:06d}.jpg" for f in keyframes],
    )


#: What ``roles`` was given (``tracks.json`` as the track stage wrote it) and the digest of the ``tracks.json`` it
#: left (with the miss loop's tracks appended). Job-local bookkeeping, never a recording.
INPUT_COPY = ".roles-input-tracks.json"
OUTPUT_STAMP = ".roles-output-tracks.sha256"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def track_stage_tracks(job_dir: Path) -> Tracks:
    """``tracks.json`` as the ``track`` stage wrote it. When it is still exactly what an earlier run of this stage
    left, that run's input is restored (tracks, requests, concepts and crowded frames), so a re-run of ``roles`` on
    its own output asks the same calls and reuses their recordings (never re-billed); otherwise it is the input."""
    path, copy, stamp = job_dir / TRACKS, job_dir / INPUT_COPY, job_dir / OUTPUT_STAMP
    if copy.is_file() and stamp.is_file() and stamp.read_text().strip() == _digest(path):
        log.info("roles: this stage's earlier output; starting from its input again")
        shutil.copyfile(copy, path)
    else:
        shutil.copyfile(path, copy)
        stamp.unlink(missing_ok=True)
    return load(path, Tracks)


def stamp_output(job_dir: Path) -> None:
    (job_dir / OUTPUT_STAMP).write_text(_digest(job_dir / TRACKS) + "\n")


async def roles(ctx: calls.Context) -> Roles:
    job = ctx.job
    tracks = track_stage_tracks(ctx.job_dir)
    scene = load_optional(ctx.job_dir / SCENE, Scene)
    transcript = load_optional(ctx.job_dir / TRANSCRIPT, Transcript)
    judged = [t for t in tracks.tracks if som.judged(t)]
    keyframes = sorted(set(som.keyframe_numbers(job)) | set(som.extra_keyframes(job, judged)))
    swept = list(tracks.concepts)
    context = context_text(job, scene, transcript, swept)
    first = await role_pass(ctx, tracks=tracks, judged=judged, frames=keyframes, context=context, tag="pass1",
                            participants=participant_count(scene))  # fmt: skip
    state = State(tracks=tracks, judged=judged, swept=swept, results=aggregate(first, judged),
                  ballots_of={t.track_id: first.ballots for t in judged})  # fmt: skip
    status: calls.Status = "ok"
    if first.calls and first.failed_calls == first.calls:
        status = "skipped" if first.budget_stops == first.calls else "failed"
    if status == "ok":
        await miss_loops(ctx, state, first, scene, transcript)
    ok = scene is not None and scene.status == "ok"
    summary = prompts.inline(scene.summary, 600) if ok and scene is not None else "No scene context is available."
    by_id = {t.track_id: t for t in state.tracks.tracks}
    # A child_phrase track is locked a child by WP3 rule 0 whatever any vote says: never in the disputed set.
    disputed = [
        tid for tid, r in state.results.person.items() if votes.disputed(r) and not by_id[tid].child_phrase
    ] if status == "ok" else []  # fmt: skip
    escalations = await escalate(
        ctx, tracks=state.tracks, disputed=disputed, ballots_of=state.ballots_of, context_summary=summary,
        transcript_frames=transcript_by_frames(job, transcript),
    )  # fmt: skip
    result = assemble(state, status, escalations, ctx.settings.role_model, keyframes)
    stamp_output(ctx.job_dir)
    return result


async def run_async(
    job_dir: Path,
    *,
    replay_mode: bool = False,
    settings: Settings | None = None,
    client: MetaClient | None = None,
    responder: replay.Responder | None = None,
) -> Path:
    settings = settings or config.load_settings()
    job = load(job_dir / JOB, Job)
    ctx = calls.Context(job_dir=job_dir, job=job, settings=settings, replay=replay_mode or settings.replay,
                        responder=responder)  # fmt: skip
    if ctx.replay or ctx.responder is not None:
        return dump(await roles(ctx), job_dir / ROLES)
    if client is None:
        async with job_client(job_dir, settings) as own:
            return await run_async(job_dir, replay_mode=False, settings=settings, client=own)
    ctx.client, ctx.store = client, FileStore(client, job_dir)
    try:
        return dump(await roles(ctx), job_dir / ROLES)
    finally:
        await ctx.store.delete_all()


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The ``roles`` stage entry point: writes ``roles.json`` (and appends miss-loop tracks to ``tracks.json``)."""
    return asyncio.run(run_async(job_dir, replay_mode=replay))
