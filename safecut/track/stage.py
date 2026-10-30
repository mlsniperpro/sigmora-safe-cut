"""``track``: ``prepared.mp4`` → ``sam_proxy.mp4`` → one SAM 3.1 sweep per concept → ``tracks.json`` (WP1).

Live: the proxy is uploaded once (Files API), every concept is swept in parallel (the client's SAM lane bounds
how many run at once), each response is recorded under ``raw/sam/`` and parsed, and the uploads are deleted
when the stage ends. Replay (``--replay`` / ``SAFECUT_REPLAY=1``) reads those recordings instead and calls nothing.
A concept whose sweep fails fails the stage: a missing sweep would leave its objects unhidden (fail closed).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from safecut import config
from safecut.config import Settings
from safecut.contracts import Job, SamRequest, Track, Tracks, dump, load
from safecut.meta import replay, sam
from safecut.meta.client import MetaClient
from safecut.meta.errors import MetaError
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.track import media
from safecut.track.axes import from_proxy_table, sam_fps_eff
from safecut.track.link import Frame, ObjectLabel, crowded, link_request, next_ids
from safecut.track.masks import mask_table

log = logging.getLogger(__name__)

#: The base sweep (WP1 step 3): every concept that can identify a person.
CONCEPTS: tuple[str, ...] = ("face", "person", "license plate", "screen", "phone", "document", "name badge")
JOB = "job.json"
PROXY = "sam_proxy.mp4"
TRACKS = "tracks.json"
RAW_STAGE = "sam"


class TrackError(RuntimeError):
    """The track stage can't produce a trustworthy ``tracks.json`` (a failed sweep, a bad proxy)."""


class RecordedFailure(MetaError):
    """Replay of a SAM request that failed when it was recorded (the miss loop's static-box path)."""


@dataclass(frozen=True)
class Proxy:
    path: Path
    fps: int
    frames: int
    width: int
    height: int
    #: The upload this proxy was made from: a recorded answer is reused only for the same clip.
    source_sha256: str = ""


@dataclass
class SamCall:
    """One SAM request: what was asked, and what came back (live or replayed)."""

    kind: Literal["phrase", "object_prompt"]
    concept: str | None
    text: str
    labels: dict[str, ObjectLabel] = field(default_factory=dict[str, ObjectLabel])
    file_id: str = ""
    events: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    usd: float = 0.0
    #: The recording's name for an object-prompt batch (``objects-loop1``); phrases are named by their text.
    name: str = ""
    #: A miss-loop phrase in the child set (``kids``): its tracks are ``child_phrase`` (WP3 rule 0).
    child_phrase: bool = False
    #: The objects an object-prompt request names (what ``text`` encodes), for a responder; never recorded.
    prompts: list[sam.ObjectPrompt] = field(default_factory=list[sam.ObjectPrompt])

    def info(self, frames: int) -> dict[str, Any]:
        return {"kind": self.kind, "concept": self.concept, "text": self.text, "sam_frames": frames,
                "prompts": self.prompts, "labels": self.labels}  # fmt: skip

    @property
    def key(self) -> str:
        if self.kind == "object_prompt":
            if not self.name:
                raise ValueError("an object-prompt request needs a recording name")
            return self.name
        return f"phrase-{replay.slug(self.text)}"

    def label(self, object_id: str) -> ObjectLabel:
        if self.kind == "phrase":
            return ObjectLabel(concept=self.concept or self.text, prompt=self.text, child_phrase=self.child_phrase)
        if object_id not in self.labels:
            raise TrackError(f"SAM answered object {object_id}, which the object-prompt request never named")
        return self.labels[object_id]


def make_proxy(job_dir: Path, job: Job, settings: Settings) -> Proxy:
    """``sam_proxy.mp4`` from ``prepared.mp4`` at ``min(SAFECUT_SAM_FPS, job.fps)``, same size, no audio."""
    fps = sam_fps_eff(job.fps, settings.sam_fps)
    out = job_dir / PROXY
    partial = job_dir / f".{PROXY}.partial.mp4"
    try:
        media.run(["-y", "-i", str(job_dir / job.prepared), "-vf", f"fps={fps}", "-an", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-g", str(2 * fps),
                   "-movflags", "+faststart", "-map_metadata", "-1", str(partial)])  # fmt: skip
        size = media.facts(partial).size
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if size != (job.width, job.height):
        partial.unlink(missing_ok=True)
        raise TrackError(f"proxy is {size}, not the prepared {job.width}x{job.height}")
    partial.replace(out)
    return Proxy(path=out, fps=fps, frames=media.frame_count(out), width=size[0], height=size[1],
                 source_sha256=job.source_sha256)  # fmt: skip


def recording(
    call: SamCall, *, model: str, frames: int, synthetic: bool = False, source_sha256: str = ""
) -> replay.RawCall:
    request: dict[str, Any] = {"kind": call.kind, "concept": call.concept, "text": call.text,
                               "file_id": call.file_id, "sam_frames": frames}  # fmt: skip
    if source_sha256:
        request["source_sha256"] = source_sha256
    if call.labels:
        request["labels"] = {k: vars(v) for k, v in call.labels.items()}
    return replay.RawCall(synthetic=synthetic, stage="track", model=model, request=request, events=call.events,
                          usd=call.usd)  # fmt: skip


def replayed(job_dir: Path, call: SamCall, proxy: Proxy) -> SamCall:
    raw = replay.load_call(job_dir, RAW_STAGE, call.key)
    failure = raw.failure()
    if failure is not None:
        raise RecordedFailure(f"recorded SAM failure: {failure[0]}")
    if raw.request.get("text") != call.text or raw.events is None:
        raise replay.ReplayMissing(f"replay: {call.key} was recorded for a different request")
    if raw.request.get("sam_frames") != proxy.frames:
        # Recorded against another proxy: its frame numbers would land on the wrong prepared frames.
        recorded = raw.request.get("sam_frames")
        raise replay.ReplayMissing(f"replay: {call.key} was recorded for a {recorded}-frame proxy, not {proxy.frames}")
    recorded_source = raw.request.get("source_sha256")
    if recorded_source is not None and proxy.source_sha256 and recorded_source != proxy.source_sha256:
        raise replay.ReplayMissing(f"replay: {call.key} was recorded for another clip")
    call.events = raw.events
    call.file_id = str(raw.request.get("file_id") or "")
    return call


async def sweep(
    client: MetaClient,
    *,
    store: FileStore,
    job_dir: Path,
    proxy: Proxy,
    calls: Sequence[SamCall],
    responses: sam.ResponseLog | None,
) -> list[sam.Segmentation]:
    """Run ``calls`` live against the uploaded proxy, in parallel; record each before parsing it.

    A request this job already answered live for the same proxy is reused from its recording, never re-billed
    (PRE-A §10.4 checkpoints). If any request fails, the others are cancelled before the caller deletes the
    uploads (``TaskGroup``): a re-run re-pays the failed request and any that were still streaming then (finished
    ones were recorded), never one that had already been answered."""
    upload_lock = asyncio.Lock()
    uploaded: list[str] = []

    async def file_id() -> str:
        async with upload_lock:
            if not uploaded:
                uploaded.append(await store.upload(proxy.path, PROXY))
            return uploaded[0]

    async def one(call: SamCall) -> sam.Segmentation:
        reused = checkpoint(job_dir, call, proxy, model=client.settings.sam_model)
        if reused is not None:
            try:
                seg = await sam.parse_video_events(reused.events, size=(proxy.width, proxy.height))
            except MetaError as exc:
                seg = None  # a recorded answer that never parsed is no checkpoint: ask again (it is overwritten)
                log.warning("recorded SAM answer unusable; asking again", extra={"key": call.key, "error": str(exc)})
            if seg is not None and all(d.frame < proxy.frames for d in seg.detections):
                return seg

        async def send(fid: str) -> sam.StreamResult:
            call.file_id = fid
            body = sam.video_body(client.settings, file_id=fid, text=call.text,
                                  object_prompt=call.kind == "object_prompt")  # fmt: skip
            return await sam.segment_video(client, body, sam_frames=proxy.frames, responses=responses)

        result = await store.call_with_reupload(proxy.path, PROXY, await file_id(), send)
        call.events, call.usd = result.events, result.usd
        replay.save(job_dir, RAW_STAGE, call.key, recording(call, model=client.settings.sam_model, frames=proxy.frames,
                                                            source_sha256=proxy.source_sha256))  # fmt: skip
        return await sam.parse_video_events(result.events, size=(proxy.width, proxy.height))

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(c)) for c in calls]
    except ExceptionGroup as failed:
        # One typed error for the caller: a Meta failure first, else whatever else broke (a disk error saving).
        metas = [e for e in failed.exceptions if isinstance(e, MetaError)]
        raise (metas or list(failed.exceptions))[0] from None
    finally:
        if responses is not None:
            await responses.delete_pending(client)
    return [t.result() for t in tasks]


def checkpoint(job_dir: Path, call: SamCall, proxy: Proxy, *, model: str) -> SamCall | None:
    """This call's earlier live answer for the same proxy and model, if one was recorded and succeeded (never a
    synthetic one)."""
    if not replay.exists(job_dir, RAW_STAGE, call.key):
        return None
    raw = replay.load_call(job_dir, RAW_STAGE, call.key)
    if raw.synthetic or raw.failure() is not None or raw.events is None:
        return None
    same = (raw.request.get("text"), raw.request.get("sam_frames"), raw.model, raw.request.get("source_sha256"))
    if not proxy.source_sha256 or same != (call.text, proxy.frames, model, proxy.source_sha256):
        return None
    call.events = raw.events
    call.file_id = str(raw.request.get("file_id") or "")
    call.usd = raw.usd or 0.0  # what the request cost (spent by the earlier run, in cost.jsonl, not again)
    log.info("SAM request reused from this job's recording", extra={"key": call.key})
    return call


def build(
    job: Job,
    proxy: Proxy,
    calls: Sequence[SamCall],
    parsed: Sequence[sam.Segmentation],
    *,
    model: str,
    existing: Tracks | None = None,
    with_masks: bool = True,
) -> Tracks:
    """Link every call's detections into tracks, appended after ``existing`` (the miss loop adds to a job)."""
    table = from_proxy_table(job.frames, job.fps, proxy.fps, proxy.frames)
    geometry = Frame(width=job.width, height=job.height, frames=job.frames, from_proxy=table)
    tracks: list[Track] = list(existing.tracks) if existing else []
    requests: list[SamRequest] = list(existing.requests) if existing else []
    concepts: list[str] = list(existing.concepts) if existing else []
    crowd: set[int] = set(existing.crowded_frames) if existing else set()
    numbering = next_ids(t.track_id for t in tracks)

    for call, seg in zip(calls, parsed, strict=True):
        past = [d.frame for d in seg.detections if d.frame >= proxy.frames]
        if past:
            # Fail closed: a detection we can't place on the prepared clip would leave someone untracked.
            raise TrackError(f"SAM answered frame {past[0]}, past the proxy's {proxy.frames} frames ({call.key})")
        index = len(requests)
        table_of_masks = mask_table(seg.detections, job.height, job.width) if with_masks else {}
        requests.append(
            SamRequest(
                kind=call.kind,
                concept=call.concept,
                file_id=call.file_id,
                fps=proxy.fps,
                frames_billed=seg.frames_billed if seg.frames_billed is not None else proxy.frames,
                matches=len({d.object_id for d in seg.detections}),
                usd=call.usd,
            )
        )
        if call.kind == "phrase" and call.text not in concepts:
            concepts.append(call.text)
        tracks += link_request(
            seg.detections,
            request=index,
            labels=call.label,
            geometry=geometry,
            source=model,
            numbering=numbering,
            masks=lambda d, t=table_of_masks: t.get((d.frame, d.object_id)),
        )
        crowd |= crowded(seg.detections, geometry)
    return Tracks(concepts=concepts, sam_fps=proxy.fps, sam_frames=proxy.frames, tracks=tracks,
                  crowded_frames=sorted(crowd), requests=requests)  # fmt: skip


def phrase_calls(concepts: Sequence[str]) -> list[SamCall]:
    seen: list[str] = []
    for c in concepts:
        text = " ".join(c.lower().split())
        if text and text not in seen:
            seen.append(text)
    return [SamCall(kind="phrase", concept=c, text=c) for c in seen]


async def run_calls(
    job_dir: Path,
    job: Job,
    proxy: Proxy,
    calls: list[SamCall],
    *,
    settings: Settings,
    replay_mode: bool,
    client: MetaClient | None = None,
    responder: replay.Responder | None = None,
) -> list[sam.Segmentation]:
    """Replay or send ``calls``; live calls delete the job's uploads when they're done (AGENTS rule 6)."""
    if responder is not None:
        for c in calls:
            replay.save(job_dir, RAW_STAGE, c.key, responder(RAW_STAGE, c.key, c.info(proxy.frames)))
    if replay_mode or responder is not None:
        size = (proxy.width, proxy.height)
        return [await sam.parse_video_events(replayed(job_dir, c, proxy).events, size=size) for c in calls]
    if client is None:
        async with job_client(job_dir, settings) as own:
            return await run_calls(job_dir, job, proxy, calls, settings=settings, replay_mode=False, client=own)
    store = FileStore(client, job_dir)
    responses = sam.ResponseLog(job_dir) if settings.delete_sam_responses else None
    try:
        return await sweep(client, store=store, job_dir=job_dir, proxy=proxy, calls=calls, responses=responses)
    finally:
        await store.delete_all()


def proxy_for(job_dir: Path, job: Job, settings: Settings, tracks: Tracks) -> Proxy:
    """The proxy the job's tracks were made from (the miss loop's object prompts need its frame table): rebuilt
    from ``prepared.mp4`` and checked against ``tracks.json``, never trusted from a leftover file."""
    proxy = make_proxy(job_dir, job, settings)
    if (proxy.fps, proxy.frames) != (tracks.sam_fps, tracks.sam_frames):
        raise TrackError(f"proxy is {proxy.frames} frames at {proxy.fps} fps; tracks.json was made from "
                         f"{tracks.sam_frames} at {tracks.sam_fps}")  # fmt: skip
    return proxy


async def run_async(
    job_dir: Path,
    *,
    replay_mode: bool = False,
    concepts: Sequence[str] = CONCEPTS,
    settings: Settings | None = None,
    client: MetaClient | None = None,
    responder: replay.Responder | None = None,
) -> Path:
    settings = settings or config.load_settings()
    replay_mode = replay_mode or settings.replay
    job = load(job_dir / JOB, Job)
    proxy = make_proxy(job_dir, job, settings)
    calls = phrase_calls(concepts)
    parsed = await run_calls(
        job_dir, job, proxy, calls, settings=settings, replay_mode=replay_mode, client=client, responder=responder
    )
    tracks = build(job, proxy, calls, parsed, model=settings.sam_model)
    log.info("tracked", extra={"job_id": job.job_id, "tracks": len(tracks.tracks), "replay": replay_mode})
    return dump(tracks, job_dir / TRACKS)


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The stage entry point: writes and returns ``tracks.json``."""
    return asyncio.run(run_async(job_dir, replay_mode=replay))
