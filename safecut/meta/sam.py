"""SAM 3.1 request bodies, cost metering and a call wrapper. Parsing is Meta's ``meta-sam-parser`` (WP1).

One noun phrase (or one batch of object prompts) per request; the proxy clip's file ID comes from
``files.json`` by name, never ``prepared.mp4`` (PRE-A §10.6).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx

from safecut import config
from safecut.config import Settings
from safecut.contracts import ResponseEntry, ResponsesIndex, dump, load, now_utc
from safecut.meta import cost
from safecut.meta.client import CallSpec, MetaClient, StreamResult, Units
from safecut.meta.errors import MetaError
from safecut.meta.retry import RetryPolicy

log = logging.getLogger(__name__)


def video_body(settings: Settings, *, file_id: str, text: str, object_prompt: bool = False) -> dict[str, Any]:
    """A SAM video request: ``text`` is a noun phrase, or ``build_object_prompt`` output when ``object_prompt``."""
    if not file_id.startswith(("file-", "file_")):
        raise ValueError(f"not a Files API id: {file_id!r}")
    if not text.strip():
        raise ValueError("SAM needs a noun phrase or object prompts")
    metadata: dict[str, str] = {"include_confidence": "true", "mask_encoding": "one_bit"}
    if object_prompt:
        metadata["propagation_direction"] = "both"
    body: dict[str, Any] = {
        "model": settings.sam_model,
        "metadata": metadata,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}, {"type": "input_video", "file_id": file_id}],
            }
        ],
    }
    if settings.sam_send_store:
        body["store"] = False
    return body


def image_body(settings: Settings, *, image_data_url: str, text: str) -> dict[str, Any]:
    if not image_data_url.startswith(("data:image/", "https://")):
        raise ValueError("SAM image input must be a data: URL or an https URL")
    body: dict[str, Any] = {
        "model": settings.sam_model,
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": image_data_url}],
            }
        ],
    }
    if settings.sam_send_store:
        body["store"] = False
    return body


def video_meter(response: Mapping[str, Any]) -> tuple[Units, float | None]:
    """Frames billed from ``usage.video_frames_processed`` (documented); missing or zero → unknown."""
    usage = response.get("usage")
    frames = cast(Mapping[str, Any], usage).get("video_frames_processed") if isinstance(usage, Mapping) else None
    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        return {}, None
    return {"frames": frames}, cost.sam_video_usd(frames)


def image_meter(_response: Mapping[str, Any]) -> tuple[Units, float | None]:
    return {"images": 1}, cost.sam_image_usd(1)


class ResponseLog:
    """``responses.json`` for one job: SAM responses Meta keeps because ``store: false`` couldn't be sent.

    Each ID is noted when its call completes, before parsing; :meth:`delete_pending` runs after parsing and
    again on cancel, a failed stage and the segment's end (PRE-A §10.4 "SAM responses").
    """

    NAME = "responses.json"

    def __init__(self, job_dir: str | Path) -> None:
        self.path = Path(job_dir) / self.NAME
        self._lock = asyncio.Lock()

    def index(self) -> ResponsesIndex:
        return load(self.path, ResponsesIndex) if self.path.exists() else ResponsesIndex([])

    async def note(self, response_id: str) -> None:
        async with self._lock:
            entries = list(self.index().root)
            if all(e.response_id != response_id for e in entries):
                entries.append(ResponseEntry(response_id=response_id))
                dump(ResponsesIndex(entries), self.path)

    async def delete_pending(self, client: MetaClient) -> int:
        """Request deletion of every noted response not yet requested. Returns the receipt's count.

        A 404 counts as done (an earlier DELETE landed). Any other failure is logged and stays pending for
        the sweeper; it never blocks the rest.
        """
        for response_id in self.index().pending:
            try:
                await client.request("DELETE", f"responses/{response_id}", _delete_spec(), meter=_no_cost)
            except MetaError as exc:
                if exc.status != 404:
                    log.warning("SAM response delete failed", extra={"response_id": response_id, "error": str(exc)})
                    continue
            await self._mark(response_id)
        return self.index().requested

    async def _mark(self, response_id: str) -> None:
        async with self._lock:
            entries = [
                e.model_copy(update={"requested_at": now_utc()}) if e.response_id == response_id else e
                for e in self.index().root
            ]
            dump(ResponsesIndex(entries), self.path)


def _no_cost(_: Any) -> tuple[Units, float]:
    return {}, 0.0


def _delete_spec() -> CallSpec:
    return CallSpec(
        stage="sam:delete_response",
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy.for_files(),
        timeout=httpx.Timeout(config.FILES_DELETE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        total_timeout_s=config.FILES_DELETE_TIMEOUT_S,
        # Cleanup must work exactly when Meta has been failing: never refused by the breaker.
        breaker=False,
    )


async def segment_video(
    client: MetaClient,
    body: Mapping[str, Any],
    *,
    sam_frames: int,
    stage: str = "track",
    responses: ResponseLog | None = None,
) -> StreamResult:
    """Run one SAM video request; feed ``result.events`` to ``meta_sam_parser.parse_responses_stream``.

    When SAM isn't sent ``store: false`` and ``SAFECUT_SAM_DELETE_RESPONSES`` is on, pass the job's
    ``responses`` log: the response ID is noted before this returns, and the caller runs
    ``responses.delete_pending`` after parsing.
    """
    spec = CallSpec(
        stage=stage,
        model=cast(str, body["model"]),
        estimate_usd=cost.sam_video_estimate(sam_frames),
        estimate_units={"frames": float(max(config.SAM_MIN_FRAMES_BILLED, sam_frames))},
        policy=RetryPolicy.for_sam(),
        timeout=httpx.Timeout(config.SAM_IDLE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        lane="sam",
        total_timeout_s=config.SAM_TOTAL_TIMEOUT_S,
        store_param=client.settings.sam_send_store,
    )
    _need_log(client, responses)
    result = await client.stream(spec, body, meter=video_meter)
    await _note(client, result, responses)
    return result


def _need_log(client: MetaClient, responses: ResponseLog | None) -> None:
    """Refuse before spending: a SAM response that must be deleted needs somewhere to be recorded."""
    if client.settings.delete_sam_responses and responses is None:
        raise ValueError("SAFECUT_SAM_DELETE_RESPONSES is on: pass the job's ResponseLog so the response is deleted")


async def _note(client: MetaClient, result: StreamResult, responses: ResponseLog | None) -> None:
    if not client.settings.delete_sam_responses or responses is None:
        return
    response_id = result.response.get("id")
    if isinstance(response_id, str) and response_id:
        await responses.note(response_id)
    else:
        log.warning("SAM response without an id: it can't be deleted", extra={"request_id": result.request_id})


async def segment_image(
    client: MetaClient, body: Mapping[str, Any], *, stage: str = "probe", responses: ResponseLog | None = None
) -> StreamResult:
    spec = CallSpec(
        stage=stage,
        model=cast(str, body["model"]),
        estimate_usd=cost.sam_image_usd(1),
        estimate_units={"images": 1},
        policy=RetryPolicy.for_sam(),
        timeout=httpx.Timeout(config.SAM_IDLE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        lane="sam",
        total_timeout_s=config.SAM_TOTAL_TIMEOUT_S,
        store_param=client.settings.sam_send_store,
    )
    _need_log(client, responses)
    result = await client.stream(spec, body, meter=image_meter)
    await _note(client, result, responses)
    return result
