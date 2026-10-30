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

from safecut.contracts import Job, Track, Tracks
from safecut.meta import cost, replay, sam
from safecut.meta.client import CallSpec
from safecut.meta.errors import BudgetExceeded, MetaError
from safecut.meta.retry import RetryPolicy
from safecut.scout import calls
from safecut.scout.miss import Miss, static_track
from safecut.track import stage as track_stage
from safecut.track.axes import from_proxy_table, to_proxy
from safecut.track.link import ObjectLabel, next_ids

log = logging.getLogger(__name__)

#: Red-team input per sampled frame (a ~1280 px image, PRE-A §3.1) plus the answer, priced as Spark 1.3.
REDTEAM_TOKENS_PER_FRAME = 1_500
REDTEAM_OUTPUT_TOKENS = 4_000
REDTEAM_PASSES = 3
AUDIT_RESERVE_FACTOR = 1.2


def audit_reserve(job: Job, model: str) -> float:
    """What the audit may still need (PRE-A §9.1 A8): 1.2 × red-team passes 1–3 at 1 fps. The miss loop never
    spends it: an audit that can't run blocks publishing."""
    frames = -(-job.frames // job.fps)
    per_pass = cost.responses_usd(model, input_tokens=frames * REDTEAM_TOKENS_PER_FRAME, cached_tokens=0,
                                  output_tokens=REDTEAM_OUTPUT_TOKENS)  # fmt: skip
    return AUDIT_RESERVE_FACTOR * REDTEAM_PASSES * per_pass


@dataclass
class LoopResult:
    tracks: Tracks
    new: list[Track]


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
                out.append(await sam.parse_video_events(track_stage.replayed(ctx.job_dir, c).events))
            except (track_stage.RecordedFailure, MetaError):
                out.append(None)
        return out
    if ctx.client is None or ctx.store is None:
        raise ValueError("a live miss loop needs the job's client and file store")
    client, store = ctx.client, ctx.store
    responses = sam.ResponseLog(ctx.job_dir) if ctx.settings.delete_sam_responses else None
    file_id = await store.upload(proxy.path, track_stage.PROXY)

    async def one(c: track_stage.SamCall) -> sam.Segmentation | None:
        async def send(fid: str) -> sam.StreamResult:
            c.file_id = fid
            body = sam.video_body(ctx.settings, file_id=fid, text=c.text, object_prompt=c.kind == "object_prompt")
            return await sam.segment_video(
                client, body, sam_frames=proxy.frames, stage="miss_loop", responses=responses
            )

        try:
            result = await store.call_with_reupload(proxy.path, track_stage.PROXY, file_id, send)
            c.events, c.usd = result.events, result.usd
            replay.save(ctx.job_dir, track_stage.RAW_STAGE, c.key,
                        track_stage.recording(c, model=ctx.settings.sam_model, frames=proxy.frames))  # fmt: skip
            return await sam.parse_video_events(result.events)
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
        return list(await asyncio.gather(*(one(c) for c in calls_)))
    finally:
        if responses is not None:
            await responses.delete_pending(client)


async def affordable(ctx: calls.Context, proxy: track_stage.Proxy, requests: int) -> bool:
    """Step 6: the loop's SAM requests plus the audit reserve must fit the remaining budget, checked before any
    request is sent (replay never spends)."""
    if ctx.replay or ctx.responder is not None or ctx.client is None or requests == 0:
        return True
    spec = CallSpec(stage="miss_loop", model=ctx.settings.sam_model, estimate_usd=0.0, estimate_units={},
                    policy=RetryPolicy.for_sam(), timeout=sam.delete_spec().timeout)  # fmt: skip
    need = requests * cost.sam_video_estimate(proxy.frames) + audit_reserve(ctx.job, ctx.settings.role_model)
    try:
        await ctx.client.preflight(spec, need)
    except BudgetExceeded:
        return False
    return True


async def run_loop(
    ctx: calls.Context, tracks: Tracks, *, prompts_: list[Miss], sweeps: list[Miss], static: list[Miss], loop: int
) -> LoopResult:
    """One loop: SAM for the planned items, static boxes for everything SAM didn't return. Updates each miss's
    ``track_ids`` and returns the job's tracks with the new ones appended."""
    job = ctx.job
    proxy = track_stage.existing_proxy(ctx.job_dir, job, ctx.settings)
    calls_: list[track_stage.SamCall] = []
    if prompts_:
        calls_.append(_object_call(job, proxy, prompts_, loop))
    for m in sweeps:
        calls_.append(track_stage.SamCall(kind="phrase", concept=m.concept.concept, text=m.phrase,
                                          child_phrase=m.concept.child_phrase))  # fmt: skip
    if not await affordable(ctx, proxy, len(calls_)):
        for m in [*prompts_]:
            m.notes.append("budget")
        static = [*static, *prompts_]
        calls_, prompts_ = [], []
    results = await _send(ctx, proxy, calls_) if calls_ else []
    done = [(c, r) for c, r in zip(calls_, results, strict=True) if r is not None]
    updated = track_stage.build(job, proxy, [c for c, _ in done], [r for _, r in done], model=ctx.settings.sam_model,
                                existing=tracks)  # fmt: skip
    new = updated.tracks[len(tracks.tracks) :]
    index_of = {id(c): i for i, (c, _) in enumerate(done)}
    first_request = len(tracks.requests)
    for m_index, m in enumerate(prompts_, start=1):
        call = calls_[0] if calls_ and calls_[0].kind == "object_prompt" else None
        request = first_request + index_of[id(call)] if call is not None and id(call) in index_of else None
        m.track_ids = [t.track_id for t in new if t.sam_object and t.sam_object.request == request
                       and t.sam_object.object_id == str(m_index)]  # fmt: skip
    for m in sweeps:
        call = next((c for c in calls_ if c.kind == "phrase" and c.text == m.phrase), None)
        if call is not None and id(call) in index_of:
            request = first_request + index_of[id(call)]
            m.track_ids += [t.track_id for t in new if t.sam_object and t.sam_object.request == request]
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
    return LoopResult(tracks=Tracks.model_validate(final.model_dump()), new=[*new, *statics])
