"""The miss loop's SAM side (``miss-loop.md`` step 5, failure handling; PRE-A §1.3, §12).

Per loop: one batched object-prompt request (every planned item its own object id, on its own proxy frame,
propagated both ways) plus at most three phrase sweeps. Results bind by object id. An item SAM returns nothing for
(a failed request, a budget stop, an empty result, past the item cap) gets a static hidden box. Never dropped.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from safecut import config
from safecut.contracts import Job, Track, Tracks
from safecut.meta import cost, replay, sam
from safecut.meta.client import CallSpec
from safecut.meta.errors import MetaError
from safecut.meta.retry import RetryPolicy
from safecut.scout import calls
from safecut.scout.miss import Miss, static_track
from safecut.track import media
from safecut.track import stage as track_stage
from safecut.track.axes import from_proxy_table, to_proxy
from safecut.track.link import ObjectLabel, next_ids

log = logging.getLogger(__name__)

#: Red-team input per sampled frame (a ~1280 px image, PRE-A §3.1) plus the answer, priced as Spark 1.3.
REDTEAM_TOKENS_PER_FRAME = 1_500
REDTEAM_OUTPUT_TOKENS = 4_000
REDTEAM_PASSES = 3
AUDIT_RESERVE_FACTOR = 1.2


#: Red-team frames per pass beyond pass 1's sample (redteam.md: follow-up passes re-check far fewer frames).
LATER_PASS_FRAMES = (10, 5)


def audit_reserve(job: Job, model: str, tracks: int) -> float:
    """What the audit may still need (PRE-A §9.1 A8): 1.2 × red-team passes 1–3 at redteam.md's sampling (1 fps,
    4 frames around each track's covered span, the middle frame, then 10 and 5 frames). The miss loop never spends
    it: an audit that can't run blocks publishing."""
    first = -(-job.frames // job.fps) + 4 * tracks + 2
    total = 0.0
    for frames in (first, *LATER_PASS_FRAMES):
        total += cost.responses_usd(model, input_tokens=frames * REDTEAM_TOKENS_PER_FRAME, cached_tokens=0,
                                    output_tokens=REDTEAM_OUTPUT_TOKENS)  # fmt: skip
    return AUDIT_RESERVE_FACTOR * total


def covers(track: Track, miss: Miss, *, reach: int) -> bool:
    """Whether ``track`` has a box holding the miss's point within ``reach`` frames of the miss's frame."""
    x, y = miss.point
    return any(
        (box := track.boxes.get(f)) is not None and box[0] <= x < box[2] and box[1] <= y < box[3]
        for f in range(miss.frame - reach, miss.frame + reach + 1)
    )


@dataclass
class LoopResult:
    tracks: Tracks
    new: list[Track]
    #: The phrases SAM actually swept (answered), for "already searched" in later prompts.
    swept: list[str]


def _object_call(job: Job, proxy: track_stage.Proxy, items: Sequence[Miss], loop: int) -> track_stage.SamCall:
    table = from_proxy_table(job.frames, job.fps, proxy.fps, proxy.frames)
    prompts = [
        sam.ObjectPrompt(object_id=k, frame=to_proxy(m.frame, table), point=m.point, box=m.box)
        for k, m in enumerate(items, start=1)
    ]
    labels = {
        str(k): ObjectLabel(concept=m.concept.concept, prompt=m.phrase, child_phrase=m.concept.child_phrase)
        for k, m in enumerate(items, start=1)
    }
    text = sam.object_prompt_text((job.width, job.height), prompts)
    name = f"objects-loop{loop}"
    return track_stage.SamCall(kind="object_prompt", concept=None, text=text, labels=labels, name=name, prompts=prompts)


async def _send(
    ctx: calls.Context, proxy: track_stage.Proxy, calls_: list[track_stage.SamCall]
) -> list[sam.Segmentation | None]:
    """Each request's segmentation, or ``None`` when it failed (live or as recorded)."""
    if ctx.responder is not None:
        for c in calls_:
            raw = ctx.responder(track_stage.RAW_STAGE, c.key, c.info(proxy.frames))
            replay.save(ctx.job_dir, track_stage.RAW_STAGE, c.key, raw)
    if ctx.replay or ctx.responder is not None:
        out: list[sam.Segmentation | None] = []
        for c in calls_:
            try:
                events = track_stage.replayed(ctx.job_dir, c, proxy).events
                out.append(await sam.parse_video_events(events, size=(proxy.width, proxy.height)))
            except (track_stage.RecordedFailure, MetaError):
                out.append(None)
        return out
    if ctx.client is None or ctx.store is None:
        raise ValueError("a live miss loop needs the job's client and file store")
    client, store = ctx.client, ctx.store
    responses = sam.ResponseLog(ctx.job_dir) if ctx.settings.delete_sam_responses else None
    upload_lock = asyncio.Lock()
    uploaded: list[str] = []

    async def file_id() -> str:
        async with upload_lock:
            if not uploaded:
                uploaded.append(await store.upload(proxy.path, track_stage.PROXY))
            return uploaded[0]

    async def one(c: track_stage.SamCall) -> sam.Segmentation | None:
        reused = track_stage.checkpoint(ctx.job_dir, c, proxy, model=ctx.settings.sam_model)
        if reused is not None:  # this job's own earlier answer (a resumed stage): never re-billed
            try:
                return await sam.parse_video_events(reused.events, size=(proxy.width, proxy.height))
            except (MetaError, ValueError):
                log.warning("recorded miss-loop answer unusable; asking again", extra={"key": c.key})

        async def send(fid: str) -> sam.StreamResult:
            c.file_id = fid
            body = sam.video_body(ctx.settings, file_id=fid, text=c.text, object_prompt=c.kind == "object_prompt")
            return await sam.segment_video(
                client, body, sam_frames=proxy.frames, stage="miss_loop", responses=responses
            )

        try:
            result = await store.call_with_reupload(proxy.path, track_stage.PROXY, await file_id(), send)
            c.events, c.usd = result.events, result.usd
            replay.save(ctx.job_dir, track_stage.RAW_STAGE, c.key,
                        track_stage.recording(c, model=ctx.settings.sam_model, frames=proxy.frames,
                                              source_sha256=proxy.source_sha256))  # fmt: skip
            return await sam.parse_video_events(result.events, size=(proxy.width, proxy.height))
        except MetaError as exc:  # BudgetExceeded included: the item falls back to a static box
            log.warning("miss-loop SAM request failed", extra={"key": c.key, "error": type(exc).__name__})
            request = {"kind": c.kind, "text": c.text}
            failure = {"failed": type(exc).__name__}
            failed = replay.RawCall(
                synthetic=False, stage="track", model=ctx.settings.sam_model, request=request, response=failure
            )
            replay.save(ctx.job_dir, track_stage.RAW_STAGE, c.key, failed)
            return None

    try:
        # A TaskGroup: an unexpected error in one request cancels the others before their responses are deleted.
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(c)) for c in calls_]
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from None
    finally:
        if responses is not None:
            await responses.delete_pending(client)
    return [t.result() for t in tasks]


async def _fits(ctx: calls.Context, usd: float, ctx_tracks: Tracks) -> bool:
    """``usd`` plus the audit reserve fit the remaining budget (replay never spends)."""
    if ctx.replay or ctx.responder is not None or ctx.client is None:
        return True
    spec = CallSpec(stage="miss_loop", model=ctx.settings.sam_model, estimate_usd=0.0, estimate_units={},
                    policy=RetryPolicy.for_sam(), timeout=sam.delete_spec().timeout)  # fmt: skip
    reserve = audit_reserve(ctx.job, ctx.settings.redteam_model, len(ctx_tracks.tracks))
    try:
        await ctx.client.preflight(spec, usd + reserve)
    except MetaError as exc:  # over budget, or the ledger can't answer (API-NOTES §10.5): never spend blind
        log.warning("miss loop: budget check refused", extra={"error": type(exc).__name__})
        return False
    return True


async def affordable(ctx: calls.Context, proxy: track_stage.Proxy, requests: int, ctx_tracks: Tracks) -> bool:
    """Step 6: the loop's SAM requests plus the audit reserve must fit the remaining budget, checked before any
    request is sent."""
    return requests == 0 or await _fits(ctx, requests * cost.sam_video_estimate(proxy.frames), ctx_tracks)


#: The text of a role-pass call (instructions, context, labels) in bytes, for its pre-call estimate.
ROLE_TEXT_BYTES = 24_000


async def calls_affordable(
    ctx: calls.Context,
    windows: Sequence[Sequence[int]],
    ctx_tracks: Tracks,
    *,
    model: str,
    effort: str,
    per_window: int,
) -> bool:
    """``per_window`` image calls per window, at their worst case, plus the audit reserve fit the remaining budget
    (step 6: nothing after the first role pass may spend the money the audit needs)."""
    worst = [
        cost.responses_estimate(
            model,
            counted=None,
            max_output_tokens=config.max_output_tokens(model, effort),
            fallback=cost.fallback_input_tokens(text_bytes=ROLE_TEXT_BYTES, images=len(w), video_seconds=0),
        )
        for w in windows
    ]
    return await _fits(ctx, per_window * sum(worst), ctx_tracks)


async def repass_affordable(ctx: calls.Context, windows: Sequence[Sequence[int]], ctx_tracks: Tracks) -> bool:
    """Step 6 for the loop-1 role re-pass: its three votes per window plus the audit reserve must fit the remaining
    budget; otherwise the re-pass is skipped and loop 1's tracks stay hidden."""
    return await calls_affordable(ctx, windows, ctx_tracks, model=ctx.settings.role_model,
                                  effort=ctx.settings.role_effort, per_window=3)  # fmt: skip


#: Failures outside a Meta call (a proxy that can't be rebuilt or doesn't match, a disk error, a recording that
#: doesn't validate): the loop's misses fall back to static boxes instead of crashing ``roles``.
LOCAL_FAILURES = (track_stage.TrackError, media.MediaError, OSError, ValueError)


async def _sam_for(
    ctx: calls.Context, tracks: Tracks, *, prompts_: list[Miss], sweeps: list[Miss], static: list[Miss], loop: int
) -> tuple[Tracks, list[Track], list[str]]:
    """The loop's SAM requests: the batched object prompt and the phrase sweeps. Sets each answered miss's
    ``track_ids`` (only tracks that hold its point near its frame); returns the tracks with SAM's new ones, those
    new tracks and the phrases actually swept. A miss left without ``track_ids`` gets a static box from the caller."""
    job = ctx.job
    try:
        proxy = track_stage.proxy_for(ctx.job_dir, job, ctx.settings, tracks)
        calls_: list[track_stage.SamCall] = []
        if prompts_:
            calls_.append(_object_call(job, proxy, prompts_, loop))
        for m in sweeps:
            calls_.append(track_stage.SamCall(kind="phrase", concept=m.concept.concept, text=m.phrase,
                                              child_phrase=m.concept.child_phrase))  # fmt: skip
        if not await affordable(ctx, proxy, len(calls_), tracks):
            for m in prompts_:
                m.notes.append("budget")
            return tracks, [], []
        results = await _send(ctx, proxy, calls_)
        done = [(c, r) for c, r in zip(calls_, results, strict=True) if r is not None]
        if not done:
            return tracks, [], []
        updated = track_stage.build(job, proxy, [c for c, _ in done], [r for _, r in done],
                                    model=ctx.settings.sam_model, existing=tracks)  # fmt: skip
    except LOCAL_FAILURES as err:
        # An answer that can't be placed on the clip (a frame past the proxy, an unnamed object), or no proxy to
        # ask with, is no answer: every miss of this loop falls back to a static box (M11: never dropped).
        log.warning("miss loop: SAM can't be used", extra={"loop": loop, "error": f"{type(err).__name__}: {err}"})
        for m in prompts_:
            m.notes.append("sam_unusable")
        return tracks, [], []
    new = updated.tracks[len(tracks.tracks) :]
    request_of = {id(c): len(tracks.requests) + i for i, (c, _) in enumerate(done)}
    prompt_request = request_of.get(id(calls_[0])) if prompts_ else None
    for m_index, m in enumerate(prompts_, start=1):
        # Like a sweep's, a prompt's track covers the miss only if it holds the point near the reported frame: SAM
        # can answer an object prompt somewhere else entirely (the track stays; the miss gets a static box too).
        m.track_ids = [t.track_id for t in new if t.sam_object and t.sam_object.request == prompt_request
                       and t.sam_object.object_id == str(m_index) and covers(t, m, reach=job.fps)]  # fmt: skip
    swept: list[str] = []
    for m in sweeps:
        call = next((c for c in calls_ if c.kind == "phrase" and c.text == m.phrase), None)
        if call is not None and id(call) in request_of:
            swept.append(m.phrase)
            found = [t for t in new if t.sam_object and t.sam_object.request == request_of[id(call)]]
            # A sweep's track covers this miss only if it holds the reported point near the reported frame; one
            # found elsewhere leaves the miss to its point prompt or a static box (M11: never dropped).
            m.track_ids += [t.track_id for t in found if covers(t, m, reach=job.fps)]
    return updated, new, swept


async def run_loop(
    ctx: calls.Context, tracks: Tracks, *, prompts_: list[Miss], sweeps: list[Miss], static: list[Miss], loop: int
) -> LoopResult:
    """One loop: SAM for the planned items, static boxes for everything SAM didn't return. Updates each miss's
    ``track_ids`` and returns the job's tracks with the new ones appended."""
    job = ctx.job
    if ctx.settings.miss_sam == "stub" and (prompts_ or sweeps):
        for m in prompts_:
            m.notes.append("miss_sam_stub")
        static, prompts_, sweeps = [*static, *prompts_], [], []
    updated, new, swept = tracks, [], []
    if prompts_ or sweeps:
        updated, new, swept = await _sam_for(ctx, tracks, prompts_=prompts_, sweeps=sweeps, static=static, loop=loop)
    numbering = next_ids(t.track_id for t in updated.tracks)
    statics: list[Track] = []
    for m in [*prompts_, *static]:
        if m.track_ids:
            continue
        number = numbering.get(m.concept.concept, 1)
        numbering[m.concept.concept] = number + 1
        track = static_track(m, f"{m.concept.concept}:{number}", fps=job.fps, frames=job.frames, width=job.width,
                             height=job.height)  # fmt: skip
        m.track_ids = [track.track_id]
        m.notes.append("static")
        statics.append(track)
    final = updated.model_copy(update={"tracks": [*updated.tracks, *statics]})
    return LoopResult(tracks=Tracks.model_validate(final.model_dump()), new=[*new, *statics], swept=swept)
