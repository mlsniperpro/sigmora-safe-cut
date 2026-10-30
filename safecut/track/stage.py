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
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.track import media
from safecut.track.axes import from_proxy_table, sam_fps_eff
from safecut.track.link import Frame, ObjectLabel, crowded, link_request, next_ids
from safecut.track.masks import frame_rle

log = logging.getLogger(__name__)

#: The base sweep (WP1 step 3): every concept that can identify a person.
CONCEPTS: tuple[str, ...] = ("face", "person", "license plate", "screen", "phone", "document", "name badge")
JOB = "job.json"
PROXY = "sam_proxy.mp4"
TRACKS = "tracks.json"
RAW_STAGE = "sam"


class TrackError(RuntimeError):
    """The track stage can't produce a trustworthy ``tracks.json`` (a failed sweep, a bad proxy)."""


@dataclass(frozen=True)
class Proxy:
    path: Path
    fps: int
    frames: int


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

    @property
    def key(self) -> str:
        return f"phrase-{replay.slug(self.text)}" if self.kind == "phrase" else f"objects-{replay.slug(self.text)[:40]}"

    def label(self, object_id: str) -> ObjectLabel:
        if self.kind == "phrase":
            return ObjectLabel(concept=self.concept or self.text, prompt=self.text)
        if object_id not in self.labels:
            raise TrackError(f"SAM answered object {object_id}, which the object-prompt request never named")
        return self.labels[object_id]


def make_proxy(job_dir: Path, job: Job, settings: Settings) -> Proxy:
    """``sam_proxy.mp4`` from ``prepared.mp4`` at ``min(SAFECUT_SAM_FPS, job.fps)``, same size, no audio."""
    fps = sam_fps_eff(job.fps, settings.sam_fps)
    out = job_dir / PROXY
    partial = job_dir / f".{PROXY}.partial.mp4"
    media.run(["-y", "-i", str(job_dir / job.prepared), "-vf", f"fps={fps}", "-an", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-g", str(2 * fps),
               "-movflags", "+faststart", "-map_metadata", "-1", str(partial)])  # fmt: skip
    size = media.facts(partial).size
    if size != (job.width, job.height):
        partial.unlink(missing_ok=True)
        raise TrackError(f"proxy is {size}, not the prepared {job.width}x{job.height}")
    partial.replace(out)
    return Proxy(path=out, fps=fps, frames=media.frame_count(out))


def recording(call: SamCall, *, model: str, frames: int, synthetic: bool = False) -> replay.RawCall:
    request: dict[str, Any] = {"kind": call.kind, "concept": call.concept, "text": call.text,
                               "file_id": call.file_id, "sam_frames": frames}  # fmt: skip
    if call.labels:
        request["labels"] = {k: vars(v) for k, v in call.labels.items()}
    return replay.RawCall(synthetic=synthetic, stage="track", model=model, request=request, events=call.events,
                          usd=call.usd)  # fmt: skip


def replayed(job_dir: Path, call: SamCall) -> SamCall:
    raw = replay.load_call(job_dir, RAW_STAGE, call.key)
    if raw.request.get("text") != call.text or raw.events is None:
        raise replay.ReplayMissing(f"replay: {call.key} was recorded for a different request")
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
    """Run ``calls`` live against the uploaded proxy, in parallel; record each before parsing it."""
    file_id = await store.upload(proxy.path, PROXY)

    async def one(call: SamCall) -> sam.Segmentation:
        async def send(fid: str) -> sam.StreamResult:
            call.file_id = fid
            body = sam.video_body(client.settings, file_id=fid, text=call.text,
                                  object_prompt=call.kind == "object_prompt")  # fmt: skip
            return await sam.segment_video(client, body, sam_frames=proxy.frames, responses=responses)

        result = await store.call_with_reupload(proxy.path, PROXY, file_id, send)
        call.events, call.usd = result.events, result.usd
        replay.save(job_dir, RAW_STAGE, call.key, recording(call, model=client.settings.sam_model, frames=proxy.frames))
        return await sam.parse_video_events(result.events)

    try:
        return list(await asyncio.gather(*(one(c) for c in calls)))
    finally:
        if responses is not None:
            await responses.delete_pending(client)


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

    def masks(d: sam.Detection) -> Any:
        return frame_rle(d.mask, d.box, job.height, job.width) if d.mask is not None else None

    for call, seg in zip(calls, parsed, strict=True):
        index = len(requests)
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
        if call.kind == "phrase" and call.concept not in concepts:
            concepts.append(call.text)
        tracks += link_request(seg.detections, request=index, labels=call.label, geometry=geometry, source=model,
                               numbering=numbering, masks=masks if with_masks else None)  # fmt: skip
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
) -> list[sam.Segmentation]:
    """Replay or send ``calls``; live calls delete the job's uploads when they're done (AGENTS rule 6)."""
    if replay_mode:
        return [await sam.parse_video_events(replayed(job_dir, c).events) for c in calls]
    if client is None:
        async with job_client(job_dir, settings) as own:
            return await run_calls(job_dir, job, proxy, calls, settings=settings, replay_mode=False, client=own)
    store = FileStore(client, job_dir)
    responses = sam.ResponseLog(job_dir) if settings.delete_sam_responses else None
    try:
        return await sweep(client, store=store, job_dir=job_dir, proxy=proxy, calls=calls, responses=responses)
    finally:
        await store.delete_all()


def existing_proxy(job_dir: Path, job: Job, settings: Settings) -> Proxy:
    path = job_dir / PROXY
    if not path.exists():
        return make_proxy(job_dir, job, settings)
    return Proxy(path=path, fps=sam_fps_eff(job.fps, settings.sam_fps), frames=media.frame_count(path))


async def run_async(
    job_dir: Path,
    *,
    replay_mode: bool = False,
    concepts: Sequence[str] = CONCEPTS,
    settings: Settings | None = None,
    client: MetaClient | None = None,
) -> Path:
    settings = settings or config.load_settings()
    replay_mode = replay_mode or settings.replay
    job = load(job_dir / JOB, Job)
    proxy = make_proxy(job_dir, job, settings)
    calls = phrase_calls(concepts)
    parsed = await run_calls(job_dir, job, proxy, calls, settings=settings, replay_mode=replay_mode, client=client)
    tracks = build(job, proxy, calls, parsed, model=settings.sam_model)
    log.info("tracked", extra={"job_id": job.job_id, "tracks": len(tracks.tracks), "replay": replay_mode})
    return dump(tracks, job_dir / TRACKS)


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The stage entry point: writes and returns ``tracks.json``."""
    return asyncio.run(run_async(job_dir, replay_mode=replay))
