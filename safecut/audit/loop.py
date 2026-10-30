"""The audit loop (WP4 step 2, DESIGN §2.8, ``docs/prompts/redteam.md``): find leaks, patch them, prove it.

Pass 1 runs the face/plate detector on **every** output frame and the red-team on the sampled frames (1 per
second, the edges of every track's covered span, long gaps, every frame the detector flagged). Each leak becomes
an audit patch (or, read through a mosaic, a solid re-render of that item); the guard re-plans, the renderer
re-renders, and the next pass re-checks only the patched frames. After pass 3 whatever is left is ``unresolved``
and publishing stays off. Nothing fails open: a frame the detector never scanned, or the red-team never answered,
counts in ``unresolved`` (``audit_failed``), and a cap that stopped a call blocks as ``over_budget``.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from safecut.audit import leaks as rules
from safecut.audit.detectors import Detection, Detector
from safecut.audit.opinion import Ask, Opinion, consult
from safecut.audit.redteam import MAX_FRAMES_PER_CALL, Answer, BudgetCause, RedTeam
from safecut.contracts import (
    Audit,
    BlockedReason,
    DecisionItem,
    Decisions,
    EgoBlurSummary,
    Job,
    Leak,
    OpenWeightSummary,
    Plan,
    RedteamHit,
    RedteamNone,
    Roles,
    Scene,
    Tracks,
    dump,
    load,
)
from safecut.guard.plan import plan as make_plan
from safecut.guard.plan import read_through
from safecut.render import REDACTED, render
from safecut.render.draw import Frame
from safecut.render.video import read_frames

log = logging.getLogger(__name__)

#: WP4 / redteam.md: at most 3 passes.
MAX_PASSES = 3


@dataclass
class State:
    job: Job
    tracks: Tracks
    decisions: Decisions
    plan: Plan
    leaks: list[Leak] = field(default_factory=list[Leak])
    redteam: list[RedteamNone | RedteamHit] = field(default_factory=list[RedteamNone | RedteamHit])
    unanswered: set[int] = field(default_factory=set[int])
    budget_cause: BudgetCause | None = None
    scanned: set[int] = field(default_factory=set[int])
    faces: int = 0
    plates: int = 0
    seconds: dict[str, float] = field(default_factory=dict[str, float])
    #: The model that answered the red-team (None: nothing answered, or the synthetic oracle).
    redteam_model: str | None = None
    #: The open-weight second opinion, when it ran in this audit.
    opinion: Opinion | None = None


def approved(decisions: Decisions, roles: Roles | None, scene: Scene | None) -> list[str]:
    """redteam.md: the kept-clear items in words, so the red-team doesn't report them."""
    rows = {r.track_id: r for r in roles.tracks} if roles is not None else {}
    out: list[str] = []
    for item in decisions.items:
        if item.decision != "keep":
            continue
        if item.kind == "person":
            words = f"the person kept clear as {item.item_id}"
            for track_id in item.track_ids:
                index = rows[track_id].matches_participant if track_id in rows else None
                if scene is not None and index is not None and index < len(scene.participants):
                    words = scene.participants[index].description
                    break
            out.append(f"{words} (approved participant)")
        else:
            out.append(f"the {item.kind} kept clear as {item.item_id} (approved as harmless)")
    return out


def frames_of(job_dir: Path, job: Job, wanted: set[int]) -> Iterator[tuple[int, Frame]]:
    """The redacted frames in ``wanted``, in order (the whole clip is decoded; detection is the cost)."""
    for index, frame in enumerate(read_frames(job_dir / REDACTED, job)):
        if index in wanted:
            yield index, frame


def scan(state: State, job_dir: Path, detector: Detector, wanted: set[int], *, count: bool = False) -> list[Leak]:
    """The detector on every frame in ``wanted``; a crash stops the scan and leaves the rest unscanned. With ``count``
    (pass 1, every frame) its detections are tallied for ``egoblur.faces``/``plates``."""
    by_track = {t.track_id: t for t in state.tracks.tracks}
    found: list[Leak] = []
    done: set[int] = set()
    started = time.perf_counter()
    try:
        for index, frame in frames_of(job_dir, state.job, wanted):
            detections: list[Detection] = detector.detect(frame)
            state.scanned.add(index)
            done.add(index)
            for d in detections:
                if count and d.kind == "face":
                    state.faces += 1
                elif count:
                    state.plates += 1
                if rules.excluded_by(d.kind, d.box, index, state.decisions, by_track) is None:
                    found.append(Leak(frame=index, box=d.box, kind=d.kind, detector="egoblur", patched_item=None))
    except Exception:
        log.exception("audit: the detector stopped after %d of %d frames", len(done), len(wanted))
    if not count:
        # A re-check (pass 2-3) that didn't cover its frames leaves those fixes unverified: unresolved, never clean.
        # (Pass 1's unscanned frames count through frames_scanned.)
        state.unanswered.update(wanted - done)
    state.seconds["detector"] = state.seconds.get("detector", 0.0) + time.perf_counter() - started
    return found


async def red_team(
    state: State, job_dir: Path, redteam: RedTeam, frames: set[int], approved_items: list[str]
) -> list[Leak]:
    """Ask the red-team about ``frames``; record one entry per finding (or ``none``) and return the leaks."""
    if not frames:
        return []
    job = state.job
    bar = rules.bar_height(job.height)
    by_track = {t.track_id: t for t in state.tracks.tracks}
    started = time.perf_counter()
    answer = Answer()
    batch: list[tuple[int, Frame]] = []
    pending = iter(frames_of(job_dir, job, frames))
    while True:  # one call's worth of frames in memory at a time
        batch = list(itertools.islice(pending, MAX_FRAMES_PER_CALL))
        if not batch:
            break
        got = await redteam.ask(batch, approved_items, bar=bar)
        answer.findings.update(got.findings)
        sent = {f for f, _ in batch}
        # A frame the answer neither covers nor admits missing is unanswered all the same (fail closed).
        answer.missing += sorted((sent - set(got.findings)) | (set(got.missing) & sent))
        answer.model = answer.model or got.model
        answer.budget_cause = answer.budget_cause or got.budget_cause
    state.seconds["redteam"] = state.seconds.get("redteam", 0.0) + time.perf_counter() - started
    state.unanswered.update(answer.missing)
    state.redteam_model = state.redteam_model or answer.model
    state.budget_cause = state.budget_cause or answer.budget_cause
    found: list[Leak] = []
    for frame in sorted(answer.findings):
        hits = 0
        for finding in answer.findings[frame]:
            mapped = rules.grid_box(finding.box, width=job.width, height=job.height, bar=bar)
            if mapped == "in_bar" and finding.kind == "text" and rules.is_frame_label(finding.text):
                continue  # the model read our own frame label (API-NOTES §5, G8)
            box = (0, 0, job.width, job.height) if mapped in (None, "in_bar") else mapped
            exclude = rules.excluded_by(finding.kind, box, frame, state.decisions, by_track)
            state.redteam.append(
                RedteamHit(
                    frame=frame,
                    finding="hit",
                    kind=finding.kind,
                    text=finding.text,
                    detail=finding.detail,
                    box=box,
                    confidence=finding.confidence,
                    excluded_by=exclude,
                )
            )
            hits += 1
            if exclude is not None:
                continue
            through = (
                rules.through_item(box, frame, state.decisions, state.plan)
                if finding.kind in ("text", "screen", "plate")
                else None
            )
            found.append(
                Leak(
                    frame=frame,
                    box=box,
                    kind=finding.kind,
                    detector="redteam",
                    patched_item=None,
                    flag="redaction_too_weak" if through else None,
                    through_item=through,
                )
            )
        if not hits:
            state.redteam.append(RedteamNone(frame=frame, finding="none"))
    return found


def patch(state: State, found: list[Leak]) -> tuple[list[Leak], set[int]]:
    """Turn this pass's leaks into fixes: every leak shares an audit patch over its box (static, padded, held over
    ``f ± (half + extend)``), and an item a model read text through is re-rendered solid as well. Returns the leaks
    with their ``patched_item`` and the frames the fixes changed (the next pass re-checks those)."""
    job, plan = state.job, state.plan
    redrawn = {leak.through_item for leak in found if leak.through_item is not None}
    changed = {f for f, es in plan.frames.items() if any(e.item_id in redrawn for e in es)}
    number, label = rules.next_numbers(state.decisions)
    new_items: list[DecisionItem] = []
    patched: list[Leak] = []
    for group in rules.group_leaks(found, job.fps):
        item = rules.make_patch(group, number, label, frames=job.frames, sample_step=job.fps,
                                extend=plan.temporal.extend)  # fmt: skip
        new_items.append(item)
        number, label = number + 1, label + 1
        patched += [leak.model_copy(update={"patched_item": item.item_id}) for leak in group.leaks]
        if item.first is not None and item.last is not None:
            changed.update(range(item.first, item.last + 1))
    state.decisions = Decisions(items=[*state.decisions.items, *new_items])
    return patched, changed


def summary(state: State, passes: int, detector: Detector, previous: Audit | None) -> Audit:
    job = state.job
    open_leaks = [leak for leak in state.leaks if leak.unresolved]
    unscanned = job.frames - len(state.scanned)
    unresolved = len(open_leaks) + unscanned + len(state.unanswered)
    reason: BlockedReason | None = None
    if state.budget_cause is not None:
        reason = "over_budget"
    elif unscanned or state.unanswered:
        reason = "audit_failed"
    elif open_leaks:
        reason = "unresolved_leaks"
    keep_opinion = state.opinion is None and previous is not None and job.open_weight_attempted
    if state.opinion is not None:
        ow, ow_entries = state.opinion.summary, state.opinion.entries
    elif keep_opinion and previous is not None:  # redteam.md "Re-runs": copied into every rewritten audit
        ow, ow_entries = previous.open_weight, previous.redteam_open
    else:
        ow, ow_entries = OpenWeightSummary(), []
    return Audit(
        frames_scanned=len(state.scanned),
        egoblur=EgoBlurSummary(
            model=detector.model,
            faces=state.faces if state.scanned else None,  # null: the detector never ran (PRE-A §12)
            plates=(state.plates if detector.detects_plates else None),
        ),
        leaks=state.leaks,
        redteam=state.redteam,
        unresolved=unresolved,
        passes=passes,
        sample_step=job.fps,
        spots=rules.make_spots(open_leaks, job.fps),
        blocked_reason=reason,
        audit_budget_cause=state.budget_cause if reason == "over_budget" else None,
        open_weight=ow,
        redteam_open=ow_entries,
    )


def carried(previous: Audit | None, decisions: Decisions, detector: Detector) -> list[Leak]:
    """An earlier run's fixed leaks stay on record while their fix does: the receipt keeps counting them, and an
    item read through stays solid. A leak whose patch or read-through item is no longer hidden is dropped, as is a
    plate the current detector couldn't have reported."""
    if previous is None:
        return []
    hidden = {i.item_id for i in decisions.items if i.decision in ("hide", "needs_you")}
    return [
        leak for leak in previous.leaks
        if not leak.unresolved and leak.patched_item in hidden
        and (leak.through_item is None or leak.through_item in hidden)
        and not (leak.detector == "egoblur" and leak.kind == "plate" and not detector.detects_plates)
    ]  # fmt: skip


async def settle(
    state: State,
    job_dir: Path,
    *,
    detector: Detector,
    redteam: RedTeam,
    found: list[Leak],
    words: list[str],
    passes: int,
    max_passes: int,
) -> int:
    """``found`` are the leaks pass ``passes`` turned up. Patch them, re-plan, re-render and re-check the changed
    frames as the next pass, until a pass finds nothing; leaks found by the last allowed pass stay unresolved.
    Returns the passes run. (The second opinion's leaks come in the same way: its re-check is the next pass.)"""
    job, tracks = state.job, state.tracks
    while found:
        if passes >= max_passes:
            state.leaks += [leak.model_copy(update={"unresolved": True}) for leak in found]
            break
        fixed, changed = patch(state, found)
        state.leaks += fixed
        state.plan = make_plan(job, tracks, state.decisions, solid=read_through(state.leaks))
        dump(state.decisions, job_dir / "decisions.json")
        dump(state.plan, job_dir / "plan.json")
        render(job_dir)
        passes += 1
        found = scan(state, job_dir, detector, changed)
        rechecks = {group.first for group in rules.group_leaks(fixed, job.fps)} | {
            leak.frame for leak in fixed if leak.detector != "egoblur"
        }
        found += await red_team(state, job_dir, redteam, rechecks, words)
    return passes


async def audit_job(
    job_dir: Path,
    *,
    detector: Detector,
    redteam: RedTeam,
    max_passes: int = MAX_PASSES,
    opinion: Ask | None = None,
    opinion_grid_ok: bool = False,
) -> tuple[Audit, dict[str, float]]:
    """Run the audit on ``job_dir`` (rendering first if needed); write ``audit.json`` and, when it patched,
    ``decisions.json``, ``plan.json`` and the re-rendered video. Returns the audit and its timings."""
    job = load(job_dir / "job.json", Job)
    tracks = load(job_dir / "tracks.json", Tracks)
    decisions = load(job_dir / "decisions.json", Decisions)
    roles = load(job_dir / "roles.json", Roles) if (job_dir / "roles.json").exists() else None
    scene = load(job_dir / "scene.json", Scene) if (job_dir / "scene.json").exists() else None
    previous = load(job_dir / "audit.json", Audit) if (job_dir / "audit.json").exists() else None
    state = State(job=job, tracks=tracks, decisions=decisions, plan=load(job_dir / "plan.json", Plan))
    state.leaks = carried(previous, decisions, detector)
    if not (job_dir / REDACTED).exists():
        render(job_dir)
    words = approved(decisions, roles, scene)
    everything = set(range(job.frames))
    found = scan(state, job_dir, detector, everything, count=True)
    flagged = {group.first for group in rules.group_leaks(found, job.fps)}  # one look per detector run, not per frame
    sampled = rules.sample_frames(job.frames, job.fps, tracks, state.plan, extra=flagged)
    found += await red_team(state, job_dir, redteam, set(sampled), words)
    passes = await settle(state, job_dir, detector=detector, redteam=redteam, found=found, words=words, passes=1,
                          max_passes=max_passes)  # fmt: skip
    if opinion is not None and not job.open_weight_attempted:
        # At most once in the job's life, marked before the first call (redteam.md "Second opinion").
        state.job = job = job.model_copy(update={"open_weight_attempted": True})
        dump(job, job_dir / "job.json")
        by_track = {t.track_id: t for t in tracks.tracks}
        state.opinion = await consult(opinion, list(frames_of(job_dir, job, set(sampled))), job=job,
                                      words="; ".join(words) or "none", decisions=state.decisions, by_track=by_track,
                                      grid_ok=opinion_grid_ok)  # fmt: skip
        passes = await settle(state, job_dir, detector=detector, redteam=redteam, found=state.opinion.leaks,
                              words=words, passes=passes, max_passes=max_passes)  # fmt: skip
    audit = summary(state, passes, detector, previous)
    dump(audit, job_dir / "audit.json")
    write_run(job_dir, audit, state, detector)
    return audit, state.seconds


#: Where the audit records what ran and how long it took (job-dir only; the receipt reads the red-team model).
RUN = Path("raw/audit/run.json")


def write_run(job_dir: Path, audit: Audit, state: State, detector: Detector) -> None:
    """WP4's CPU timing (seconds per detector frame) and which models answered."""
    path = job_dir / RUN
    path.parent.mkdir(parents=True, exist_ok=True)
    per_frame = state.seconds.get("detector", 0.0) / max(1, audit.frames_scanned)
    record = {"detector": detector.model, "redteam_model": state.redteam_model, "seconds": state.seconds,
              "detector_s_per_frame": per_frame, "frames_scanned": audit.frames_scanned}  # fmt: skip
    path.write_text(json.dumps(record, indent=1))
