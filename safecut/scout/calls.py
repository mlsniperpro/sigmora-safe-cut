"""One Muse Spark / Wonder JSON call, live or replayed, as a fail-closed outcome (``docs/prompts`` rules 2–3).

Live: the body is built with ``store: false`` and strict structured output, sent through WP0's client (pre-call
reservation, retries, one re-ask on invalid JSON), and recorded under ``raw/<stage>/`` before it is used. A failure
is recorded too, so a replay reproduces it. Replay reads the recording and validates the answer with the same
pydantic model a live call uses. A failed call is ``failed`` and a budget stop is ``skipped``: never a judgement.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ValidationError

from safecut.config import Settings
from safecut.contracts import Job
from safecut.meta import replay, responses
from safecut.meta.client import MetaClient, StreamResult
from safecut.meta.errors import BudgetExceeded, MetaError
from safecut.meta.files import FileStore
from safecut.scout.prompts import VERSION

log = logging.getLogger(__name__)

PREPARED_NAME = "prepared.mp4"
Status = Literal["ok", "failed", "skipped"]
Message = dict[str, Any]


@dataclass
class Context:
    """What a scout stage needs: the job, its settings, and (live only) a client and the job's uploads."""

    job_dir: Path
    job: Job
    settings: Settings
    replay: bool
    client: MetaClient | None = None
    store: FileStore | None = None
    #: Answers calls in place of Meta (the synthetic demo job); its answers are recorded like live ones.
    responder: replay.Responder | None = None

    @property
    def seconds(self) -> float:
        return self.job.frames / self.job.fps


@dataclass(frozen=True)
class Outcome[M: BaseModel]:
    status: Status
    value: M | None = None
    reason: str = ""
    usd: float = 0.0
    #: The completed response (live or replayed), for usage checks such as the speech fallback's dropped audio.
    response: Mapping[str, Any] | None = None


def text_part(text: str) -> dict[str, Any]:
    return {"type": "input_text", "text": text}


def image_part(path: Path) -> dict[str, Any]:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "input_image", "image_url": f"data:image/jpeg;base64,{data}"}


def video_part(file_id: str) -> dict[str, Any]:
    return {"type": "input_video", "file_id": file_id}


def system(text: str) -> Message:
    return {"role": "system", "content": [text_part(text)]}


def user(*parts: dict[str, Any]) -> Message:
    return {"role": "user", "content": list(parts)}


def _descriptor(body: Mapping[str, Any], schema_name: str, effort: str) -> dict[str, Any]:
    """What was asked, without the images or video: enough to audit a recording, never the footage."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    images = sum(
        1
        for m in cast(list[Mapping[str, Any]], body.get("input", []))
        for p in cast(list[Any], m.get("content") or [])
        if isinstance(p, Mapping) and cast(Mapping[str, Any], p).get("type") == "input_image"
    )
    return {"schema": schema_name, "prompt_version": VERSION, "effort": effort, "images": images,
            "body_sha256": hashlib.sha256(canonical).hexdigest()}  # fmt: skip


def completed_response(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    for event in reversed(events):
        if event.get("type") == "response.completed" and isinstance(event.get("response"), Mapping):
            return cast(Mapping[str, Any], event["response"])
    raise replay.ReplayMissing("recording has no response.completed event")


def _replayed[M: BaseModel](ctx: Context, stage: str, key: str, out: type[M]) -> Outcome[M]:
    raw = replay.load_call(ctx.job_dir, stage, key)
    recorded = raw.request.get("prompt_version")
    if recorded is not None and recorded != VERSION:
        log.warning("replaying an answer recorded with other prompts", extra={"key": f"{stage}/{key}",
                                                                               "recorded": recorded})  # fmt: skip
    failure = raw.failure()
    if failure is not None:
        status: Status = "skipped" if failure[0] == "budget" else "failed"
        return Outcome(status=status, reason=failure[1])
    if raw.events is None:
        raise replay.ReplayMissing(f"replay: {stage}/{key} has neither events nor a recorded failure")
    response = completed_response(raw.events)
    try:
        value = out.model_validate_json(responses.output_text(response))
    except (ValidationError, MetaError) as exc:
        return Outcome(status="failed", reason=f"recorded answer is unusable: {type(exc).__name__}")
    return Outcome(status="ok", value=value, response=response)


def _checkpoint[M: BaseModel](
    ctx: Context, stage: str, key: str, *, model: str, request: Mapping[str, Any], out: type[M]
) -> Outcome[M] | None:
    """This job's earlier live answer to exactly this request (same model, same body hash), never re-billed (PRE-A
    §10.4 checkpoints): a resumed ``roles`` re-asks nothing it already paid for, so it writes the same files."""
    if not replay.exists(ctx.job_dir, stage, key):
        return None
    try:
        raw = replay.load_call(ctx.job_dir, stage, key)
    except ValueError:  # a corrupt or old-format recording is no checkpoint: ask again (it is overwritten)
        return None
    if raw.synthetic or raw.failure() is not None or raw.events is None or raw.model != model:
        return None
    if raw.request.get("body_sha256") != request["body_sha256"]:
        return None
    outcome = _replayed(ctx, stage, key, out)
    if outcome.status != "ok":
        return None  # an answer that doesn't validate is asked again
    log.info("call reused from this job's recording", extra={"key": f"{stage}/{key}"})
    return outcome


async def call_json[M: BaseModel](
    ctx: Context,
    *,
    stage: str,
    key: str,
    model: str,
    effort: str,
    messages: Callable[[str | None], list[Message]],
    schema: Mapping[str, Any],
    schema_name: str,
    out: type[M],
    video: bool = False,
    info: Mapping[str, Any] | None = None,
) -> Outcome[M]:
    """Run (or replay) one JSON call. ``messages(file_id)`` builds the input; ``file_id`` is the uploaded
    ``prepared.mp4`` when ``video`` (re-uploaded once if Meta lost it), else ``None``. ``info`` tells a responder
    what was asked (frames, labels); it is never sent."""
    if ctx.replay:
        return _replayed(ctx, stage, key, out)
    if ctx.responder is not None:
        replay.save(ctx.job_dir, stage, key, ctx.responder(stage, key, info or {}))
        return _replayed(ctx, stage, key, out)
    if ctx.client is None or ctx.store is None:
        raise ValueError("a live scout call needs the job's client and file store")
    client, store = ctx.client, ctx.store
    holder: dict[str, Any] = {}
    if not video:  # the whole request is known up front (images inline): a resumed stage reuses its own answer
        body = responses.build_body(model, messages(None), effort=effort, schema=schema, schema_name=schema_name)
        reused = _checkpoint(ctx, stage, key, model=model, request=_descriptor(body, schema_name, effort), out=out)
        if reused is not None:
            return reused

    async def send(file_id: str | None) -> tuple[M, StreamResult]:
        body = responses.build_body(model, messages(file_id), effort=effort, schema=schema, schema_name=schema_name)
        holder["request"] = _descriptor(body, schema_name, effort)
        return await responses.create_json(client, out, body, stage=stage, effort=effort,
                                           video_seconds=ctx.seconds if video else 0.0)  # fmt: skip

    def record(**fields: Any) -> None:
        call = replay.RawCall(synthetic=False, stage=stage, model=model, request=holder.get("request", {}), **fields)
        replay.save(ctx.job_dir, stage, key, call)

    try:
        if video:
            prepared = ctx.job_dir / ctx.job.prepared
            file_id = await store.upload(prepared, PREPARED_NAME)
            go: Callable[[str], Awaitable[tuple[M, StreamResult]]] = send
            value, result = await store.call_with_reupload(prepared, PREPARED_NAME, file_id, go)
        else:
            value, result = await send(None)
    except BudgetExceeded as exc:
        log.warning("budget stop", extra={"stage": stage, "key": key, "cap": exc.cap})
        record(response={"failed": "budget", "reason": str(exc)})
        return Outcome(status="skipped", reason=f"budget: {exc.cap}")
    except MetaError as exc:
        log.warning("call failed", extra={"stage": stage, "key": key, "error": type(exc).__name__})
        record(response={"failed": type(exc).__name__, "reason": str(exc)[:300]})
        return Outcome(status="failed", reason=type(exc).__name__)
    record(events=result.events, usd=result.usd)
    return Outcome(status="ok", value=value, usd=result.usd, response=result.response)
