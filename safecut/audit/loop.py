"""The audit loop (WP4 step 2, DESIGN §2.8, ``docs/prompts/redteam.md``): find leaks, patch them, prove it.

Pass 1 runs the face/plate detector on **every** output frame and the red-team on the sampled frames (1 per
second, the edges of every track's covered span, long gaps, every frame the detector flagged). Each leak
becomes an audit patch (and, read through a mosaic, its item is re-rendered solid too); the guard re-plans, the
renderer re-renders, and the next pass scans the whole new render and red-teams the fixes. After pass 3 whatever
is left is ``unresolved`` and publishing stays off. Nothing fails open: a frame the detector never scanned, or the
red-team never answered, counts in ``unresolved`` (``audit_failed``), and a cap that stopped a call blocks as
``over_budget``.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import TypeAdapter

from safecut.audit import gpu
from safecut.audit import leaks as rules
from safecut.audit.detectors import Detection, Detector, device_of
from safecut.audit.opinion import Ask, Opinion, attempted, consult, data_url, mark_attempted, recorded, save
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
from safecut.decide.geometry import area
from safecut.guard import camera_for, region_cache
from safecut.guard.plan import plan as make_plan
from safecut.guard.plan import read_through
from safecut.receipt import retire
from safecut.render import REDACTED, file_sha256, render, rendered_from_plan, write_atomic
from safecut.render.draw import Frame, hidden_mask
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
    detector_calls: int = 0
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


def detected(detector: Detector, job_dir: Path, job: Job, wanted: set[int]) -> Iterator[tuple[int, list[Detection]]]:
    """Each wanted frame's detections, in order: one GPU call for the whole scan, or the local detector per frame."""
    batch = gpu.batches(detector, job_dir, wanted)
    if batch is not None:
        yield from batch
        return
    for index, frame in frames_of(job_dir, job, wanted):
        yield index, detector.detect(frame)


def scan(state: State, job_dir: Path, detector: Detector, wanted: set[int], *, count: bool = False) -> list[Leak]:
    """The detector on every frame in ``wanted``; a crash stops the scan and leaves the rest unscanned. A frame's
    detections are tallied for ``egoblur.faces``/``plates`` the first time it is scanned. With ``count`` (pass 1) the
    frames it didn't reach count through ``frames_scanned``; on a re-check they are unanswered."""
    by_track = {t.track_id: t for t in state.tracks.tracks}
    found: list[Leak] = []
    done: set[int] = set()
    started = time.perf_counter()
    try:
        for index, detections in detected(detector, job_dir, state.job, wanted):
            state.detector_calls += 1
            first = index not in state.scanned  # tallied once per frame: pass 1, or the pass that first scanned it
            for d in detections:
                if first and d.kind == "face":
                    state.faces += 1
                elif first:
                    state.plates += 1
                if rules.excluded_by(d.kind, d.box, index, state.decisions, by_track, fps=state.job.fps) is None:
                    found.append(Leak(frame=index, box=d.box, kind=d.kind, detector="egoblur", patched_item=None))
            # Scanned only once its detections are all judged: a crash part-way leaves the frame unscanned.
            state.scanned.add(index)
            done.add(index)
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
            # A whole-frame box stands for a finding we couldn't place (fail closed): nothing kept excuses it.
            placed = mapped not in (None, "in_bar")
            exclude = (
                rules.excluded_by(finding.kind, box, frame, state.decisions, by_track, fps=job.fps) if placed else None
            )
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


def patch(state: State, found: list[Leak]) -> list[Leak]:
    """Turn this pass's leaks into fixes: every leak shares an audit patch over its box (static, padded, held over
    ``f ± (half + extend)``), and an item a model read text through is re-rendered solid as well (the guard reads
    the flags). Returns the leaks with their ``patched_item``."""
    job, plan = state.job, state.plan
    number, label = rules.next_numbers(state.decisions)
    new_items: list[DecisionItem] = []
    patched: list[Leak] = []
    del plan
    for group in rules.group_leaks(found, 0):  # one patch per leak frame, at that frame's box: patches follow
        flagged = any(leak.through_item is not None for leak in group.leaks)  # a read-through: its item goes solid
        if not flagged and area(group.box) > rules.PATCH_MAX_SHARE * job.width * job.height:
            # Too big to be a face: never painted (it would hide the scene, a kept face too); the creator sees it.
            patched += [leak.model_copy(update={"unresolved": True}) for leak in group.leaks]
            continue
        item = rules.make_patch(group, number, label, frames=job.frames, hold=rules.patch_hold(job.fps))
        new_items.append(item)
        number, label = number + 1, label + 1
        patched += [leak.model_copy(update={"patched_item": item.item_id}) for leak in group.leaks]
    state.decisions = Decisions(items=[*state.decisions.items, *new_items])
    return patched


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
            # null only when the detector never ran on record (PRE-A §12): carried detector leaks keep a count.
            faces=state.faces if state.scanned else _carried_faces(state.leaks),
            plates=(state.plates if detector.detects_plates else None),
            device=device_of(detector),
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


def _carried_faces(leaks: list[Leak]) -> int | None:
    faces = [leak for leak in leaks if leak.detector == "egoblur"]
    return sum(leak.kind == "face" for leak in faces) if faces else None


#: Leaks an audit has found so far, written before it changes decisions, plan or video, and removed when its
#: audit.json is written: a crash part-way never loses what it found or which fixes it still had to re-check.
PENDING = Path("raw/audit/pending.json")
_LEAKS: TypeAdapter[list[Leak]] = TypeAdapter(list[Leak])


def save_pending(job_dir: Path, leaks: list[Leak]) -> None:
    path = job_dir / PENDING
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_LEAKS.dump_json(leaks))
    tmp.replace(path)


def earlier_leaks(job_dir: Path, previous: Audit | None) -> list[Leak]:
    """Every leak an earlier run of this job recorded: its audit.json and, after a crash, its pending record."""
    leaks = list(previous.leaks) if previous is not None else []
    path = job_dir / PENDING
    if path.exists():
        try:
            pending = _LEAKS.validate_json(path.read_bytes())
        except ValueError:
            log.warning("audit: an unreadable pending record (a crash mid-write); its fixes are re-checked anyway")
            pending = []
        seen = {(leak.frame, leak.box, leak.kind, leak.detector) for leak in leaks}
        leaks += [leak for leak in pending if (leak.frame, leak.box, leak.kind, leak.detector) not in seen]
    return leaks


def reopened(leaks: list[Leak], plan: Plan, decisions: Decisions, *, height: int, width: int) -> list[Leak]:
    """Leaks an earlier run left unresolved (or whose patch never landed) that nothing solid in the current plan
    covers: found again before this
    run's first pass, so a re-run never forgets them (redteam.md "Never default to clean"). A mosaic never counts
    as cover: a model that read through one can read through it again (it is the leak's own ``through_item``)."""
    hidden = {i.item_id for i in decisions.items if i.decision != "keep"}
    out: list[Leak] = []
    for leak in leaks:
        # Unresolved, or patched by an item that never landed (a crash between the pending record and the patch).
        if not leak.unresolved and (leak.patched_item is None or leak.patched_item in hidden):
            continue
        # The pixels the renderer fills solid on that frame (a mask entry hides its mask, not its box).
        solid = [e for e in plan.frames.get(leak.frame, []) if e.style != "pixelate"]
        fills = [f for f in plan.crowd_fills if leak.frame in f.frames]
        filled = hidden_mask(solid, fills, height, width)
        x1, y1, x2, y2 = leak.box
        if not bool(filled[y1:y2, x1:x2].all()):
            out.append(leak.model_copy(update={"unresolved": False, "patched_item": None}))
    return out


def rejudged(leaks: list[Leak], decisions: Decisions, plan: Plan) -> tuple[list[Leak], bool]:
    """Earlier runs' text, screen and plate leaks judged against today's decisions and plan (the creator may have
    hidden what they lie on since): one that now reads through a hidden item is flagged ``redaction_too_weak``, and
    that item renders solid (redteam.md). Returns the leaks and whether any was newly flagged."""
    out: list[Leak] = []
    newly = False
    for leak in leaks:
        if leak.flag is None and leak.kind in ("text", "screen", "plate") and leak.detector != "egoblur":
            through = rules.through_item(leak.box, leak.frame, decisions, plan)
            if through is not None:
                leak = leak.model_copy(update={"flag": "redaction_too_weak", "through_item": through})  # noqa: PLW2901 -- the judged copy replaces it
                newly = True
        out.append(leak)
    return out, newly


def planned_in_full(decisions: Decisions, plan: Plan) -> bool:
    """Every hidden item of ``decisions`` has entries in ``plan``, and the plan names no item ``decisions`` lacks."""
    hidden = {i.item_id for i in decisions.items if i.decision != "keep"}
    planned = {e.item_id for entries in plan.frames.values() for e in entries}
    return planned <= {i.item_id for i in decisions.items} and hidden <= planned


def carried(previous: Audit | list[Leak] | None, decisions: Decisions, detector: Detector) -> list[Leak]:
    """An earlier run's fixed leaks stay on record while their fix does: the receipt keeps counting them, and an
    item read through stays solid. A leak whose patch or read-through item is no longer hidden is dropped, as is a
    plate the current detector couldn't have reported."""
    if previous is None:
        return []
    hidden = {i.item_id for i in decisions.items if i.decision in ("hide", "needs_you")}
    return [
        leak for leak in (previous.leaks if isinstance(previous, Audit) else previous)
        if not leak.unresolved and leak.patched_item in hidden
        and (leak.through_item is None or leak.through_item in hidden)
        and not (leak.detector == "egoblur" and leak.kind == "plate" and not detector.detects_plates)
    ]  # fmt: skip


def plan_camera(state: State, job_dir: Path) -> list[tuple[int, int]] | None:
    """The camera every re-plan keeps: the one the current ``plan.json`` records (the guard measured it), else the
    clip's own (measured once per process; None when there is no clip or it never moved)."""
    return state.plan.camera if state.plan.camera is not None else camera_for(job_dir, state.job)


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
    """``found`` are the leaks pass ``passes`` turned up. Patch them, re-plan, re-render, and as the next pass scan
    the whole new render and red-team the fixes, until a pass finds nothing; leaks found by the last allowed pass
    stay unresolved. Returns the passes run. (The second opinion's leaks come in the same way: its re-check is the
    next pass.)"""
    job, tracks = state.job, state.tracks
    while found:
        if passes >= max_passes:
            state.leaks += [leak.model_copy(update={"unresolved": True}) for leak in found]
            break
        fixed = patch(state, found)
        state.leaks += fixed
        state.plan = make_plan(job, tracks, state.decisions, solid=read_through(state.leaks),
                               cache=region_cache(job_dir), camera=plan_camera(state, job_dir))  # fmt: skip
        save_pending(job_dir, state.leaks)  # before the patches land: a crash from here on keeps them on record
        # The plan first: a crash before the decisions land leaves a plan that hides more, never one that hides less
        # than decisions.json says (and the next audit re-plans; see ``planned_in_full``).
        dump(state.plan, job_dir / "plan.json")
        dump(state.decisions, job_dir / "decisions.json")
        render(job_dir)
        passes += 1
        # Every frame of the new render, not just the patched ones: a re-encode shifts pixels on frames it didn't
        # redraw (x264 rate control), and the detector's guarantee is about the video as published.
        found = scan(state, job_dir, detector, set(range(job.frames)))
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
    opinion_model: str = "",
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
    earlier = earlier_leaks(job_dir, previous)
    state.leaks = carried(earlier, decisions, detector)
    # Everything earlier runs recorded goes on the pending record before audit.json is replaced by the placeholder,
    # so a crash from here on still knows what was left unresolved.
    save_pending(job_dir, state.leaks + [leak for leak in earlier if leak.unresolved])
    # Never default to clean (redteam.md): before this audit changes anything (patches, plan, video), the job's
    # receipt is retired and audit.json says nothing was checked yet, so a crash part-way leaves a blocked audit,
    # never the previous clean verdict beside a changed video.
    retire(job_dir)
    dump(summary(state, 0, detector, previous), job_dir / "audit.json")
    state.leaks, newly = rejudged(state.leaks, state.decisions, state.plan)
    if newly or not planned_in_full(state.decisions, state.plan):  # read through now, or a crash between the files
        state.plan = make_plan(job, tracks, state.decisions, solid=read_through(state.leaks),
                               cache=region_cache(job_dir), camera=plan_camera(state, job_dir))  # fmt: skip
        dump(state.plan, job_dir / "plan.json")
    reopen = reopened(earlier, state.plan, state.decisions, height=job.height, width=job.width)
    save_pending(job_dir, state.leaks + [leak.model_copy(update={"unresolved": True}) for leak in reopen])
    if not rendered_from_plan(job_dir):  # no video, or one drawn from another plan (a crash, an edit): draw it now
        render(job_dir)
    words = approved(decisions, roles, scene)
    everything = set(range(job.frames))
    found = scan(state, job_dir, detector, everything, count=True)
    seen = {(leak.frame, leak.box, leak.kind, leak.detector) for leak in found}
    found += [leak for leak in reopen if (leak.frame, leak.box, leak.kind, leak.detector) not in seen]
    flagged = {leak.frame for leak in found}  # redteam.md Inputs: "and every frame EgoBlur flagged"
    # The fixes earlier runs made for the red team are re-read on every run (the model saw what the detector can't).
    refix = {leak.frame for leak in state.leaks if leak.detector != "egoblur"}
    refix |= {leak.frame for leak in earlier if leak.unresolved}  # and what they left unresolved is asked again
    sampled = rules.sample_frames(job.frames, job.fps, tracks, state.plan, extra=flagged | refix)
    found += await red_team(state, job_dir, redteam, set(sampled), words)
    passes = await settle(state, job_dir, detector=detector, redteam=redteam, found=found, words=words, passes=1,
                          max_passes=max_passes)  # fmt: skip
    if attempted(job_dir, job) and not job.open_weight_attempted:  # job.json was rebuilt: the flag never clears
        state.job = job = job.model_copy(update={"open_weight_attempted": True})
        dump(job, job_dir / "job.json")
    if opinion is not None and not job.open_weight_attempted:
        # At most once in the job's life, marked before the first call (redteam.md "Second opinion").
        mark_attempted(job_dir, job, opinion_model)
        state.job = job = job.model_copy(update={"open_weight_attempted": True})
        dump(job, job_dir / "job.json")
        bar = rules.bar_height(job.height)
        urls = [(f, data_url(img, f, bar)) for f, img in frames_of(job_dir, job, set(sampled))]  # streamed: JPEGs only
        state.opinion = await consult(opinion, urls, model=opinion_model, words="; ".join(words) or "none", job=job,
                                      decisions=state.decisions, plan=state.plan,
                                      by_track={t.track_id: t for t in tracks.tracks},
                                      grid_ok=opinion_grid_ok)  # fmt: skip
        save(job_dir, job, state.opinion)
        passes = await settle(state, job_dir, detector=detector, redteam=redteam, found=state.opinion.leaks,
                              words=words, passes=passes, max_passes=max_passes)  # fmt: skip
    elif job.open_weight_attempted:
        state.opinion = recorded(
            job_dir, job
        )  # redteam.md "Re-runs": what it said is copied into every rewritten audit
    audit = summary(state, passes, detector, previous)
    dump(audit, job_dir / "audit.json")
    (job_dir / PENDING).unlink(missing_ok=True)
    write_run(job_dir, audit, state, detector)
    return audit, state.seconds


#: Where the audit records what ran and how long it took (job-dir only; the receipt reads the red-team model).
RUN = Path("raw/audit/run.json")


def write_run(job_dir: Path, audit: Audit, state: State, detector: Detector) -> None:
    """WP4's CPU timing (seconds per detector frame) and which models answered."""
    path = job_dir / RUN
    path.parent.mkdir(parents=True, exist_ok=True)
    per_frame = state.seconds.get("detector", 0.0) / max(1, state.detector_calls)
    # The video this audit checked: a receipt only seals an audit that describes the video in the job now.
    # A GPU detector's time is in its calls (pass 1 before the audit started): its own wall seconds, not this loop's.
    gpu = {"gpu_calls": getattr(detector, "calls", 0), "gpu_wall_s": round(getattr(detector, "wall_s", 0.0), 3)}
    record = {"detector": detector.model, "device": device_of(detector), **gpu, "redteam_model": state.redteam_model,
              "seconds": state.seconds,
              "detector_s_per_frame": per_frame, "frames_scanned": audit.frames_scanned,
              "video_sha256": file_sha256(job_dir / REDACTED)}  # fmt: skip
    write_atomic(path, json.dumps(record, indent=1))
