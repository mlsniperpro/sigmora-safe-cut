"""SAM 3.1 request bodies, cost metering and a call wrapper. Parsing is Meta's ``meta-sam-parser`` (WP1).

One noun phrase (or one batch of object prompts) per request; the proxy clip's file ID comes from
``files.json`` by name, never ``prepared.mp4`` (PRE-A §10.6).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import httpx

from safecut import config
from safecut.config import Settings
from safecut.contracts import RESPONSE_ID_PATTERN, ResponseEntry, ResponsesIndex, dump, load, now_utc
from safecut.meta import cost
from safecut.meta.client import CallSpec, MetaClient, StreamResult, Units
from safecut.meta.errors import MetaConfigError, MetaError
from safecut.meta.retry import RetryPolicy

log = logging.getLogger(__name__)
_RESPONSE_ID = re.compile(RESPONSE_ID_PATTERN)


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

    Each ID is noted the moment the stream names it (``response.created``, before parsing, on every attempt,
    including ones that then fail, are retried or are cancelled); :meth:`delete_pending` runs after parsing
    and again on cancel, a failed stage and the segment's end (PRE-A §10.4 "SAM responses").

    Every read-modify-write here is synchronous (no ``await`` inside), so tasks on one event loop can't
    interleave their updates. :meth:`note` never raises (it runs inside a paid stream): an ID it can't
    write is kept in memory for :meth:`delete_pending`. An ID that isn't a plain token can't be put in a
    DELETE path safely: it is kept in :attr:`refused` and logged as an error, so WP4's receipt notes says how
    many responses could not be deleted.
    """

    NAME = "responses.json"

    def __init__(self, job_dir: str | Path) -> None:
        self.path = Path(job_dir) / self.NAME
        self._unsaved: list[str] = []
        self._requested_unrecorded: set[str] = set()  # deletion requested; responses.json couldn't record it
        self._streaming: set[str] = set()  # IDs whose stream is still open: never deleted mid-stream
        self.refused: list[str] = []

    def index(self) -> ResponsesIndex:
        return load(self.path, ResponsesIndex) if self.path.exists() else ResponsesIndex([])

    def check(self) -> None:
        """Raise now (before any spend) if ``responses.json`` can't be read."""
        self.index()

    def note(self, response_id: str) -> None:
        if not _RESPONSE_ID.fullmatch(response_id):
            log.error("SAM response id refused: not a plain token; it can't be deleted", extra={"id": response_id[:64]})
            if response_id not in self.refused:
                self.refused.append(response_id)
            return
        try:
            entries = list(self.index().root)
            if all(e.response_id != response_id for e in entries):
                entries.append(ResponseEntry(response_id=response_id))
                dump(ResponsesIndex(entries), self.path)
        except (OSError, ValueError):
            log.exception("responses.json write failed; the id is kept in memory", extra={"response_id": response_id})
            if response_id not in self._unsaved:
                self._unsaved.append(response_id)

    def begin(self, response_id: str) -> None:
        """A stream named its response: note it, and keep it out of :meth:`delete_pending` until it ends."""
        self.note(response_id)
        self._streaming.add(response_id)

    def ended(self, response_ids: list[str]) -> None:
        """Those streams are over (completed, failed or cancelled): their responses may now be deleted."""
        self._streaming.difference_update(response_ids)

    def requested(self) -> int:
        """The receipt's ``responses_delete_requested``: only the requests recorded in responses.json (PRE-A
        §10.4; the receipt check compares the two). Requests it couldn't record are :meth:`unrecorded`."""
        try:
            return self.index().requested
        except (OSError, ValueError):
            log.exception("responses.json unreadable; no request can be counted")
            return 0

    def unrecorded(self) -> int:
        """Deletes Meta accepted whose record failed: for the receipt's note, never its count."""
        return len(self._requested_unrecorded)

    async def delete_pending(self, client: MetaClient) -> int:
        """Request deletion of every noted response not yet requested. Returns every request made, recorded or
        not (:meth:`requested` plus :meth:`unrecorded`); the receipt counts only :meth:`requested`.

        A 404 with an error body counts as done (an earlier DELETE landed); an empty-body 404 means a wrong
        path (``MetaConfigError``) and is a failure. Any failure is logged and stays pending for the sweeper;
        it never blocks the rest, and an unreadable responses.json never blocks the in-memory IDs.
        """
        self._flush_unsaved()
        try:
            recorded = self.index().pending
        except (OSError, ValueError):
            log.exception("responses.json unreadable; deleting the in-memory ids only")
            recorded = []
        for response_id in [*recorded, *self._unsaved]:
            if response_id in self._requested_unrecorded:
                continue  # already requested; only the record of it failed
            if response_id in self._streaming:
                continue  # another SAM stream of this job is still reading it; its own caller deletes it
            try:
                result = await client.request("DELETE", f"responses/{response_id}", delete_spec(), meter=_no_cost)
                answer: Any = result.body
                if isinstance(answer, dict) and cast(dict[str, Any], answer).get("deleted") is False:
                    # PRE-A §10.4 leaves the body unspecified, but an explicit refusal is never a request done.
                    log.warning("SAM response delete refused", extra={"response_id": response_id})
                    continue
            except MetaError as exc:
                if exc.status != 404 or isinstance(exc, MetaConfigError):
                    log.warning("SAM response delete failed", extra={"response_id": response_id, "error": str(exc)})
                    continue
            if response_id in self._unsaved:
                self._unsaved.remove(response_id)
                self._requested_unrecorded.add(response_id)
            else:
                self._mark(response_id)
        return self.requested() + self.unrecorded()

    def _flush_unsaved(self) -> None:
        for response_id in list(self._unsaved):
            self._unsaved.remove(response_id)
            self.note(response_id)  # back into the list if the write still fails

    def _mark(self, response_id: str) -> None:
        try:
            entries = [
                e.model_copy(update={"requested_at": now_utc()}) if e.response_id == response_id else e
                for e in self.index().root
            ]
            dump(ResponsesIndex(entries), self.path)
        except (OSError, ValueError):
            log.exception("responses.json write failed after a delete", extra={"response_id": response_id})
            self._requested_unrecorded.add(response_id)


def _no_cost(_: Any) -> tuple[Units, float]:
    return {}, 0.0


def delete_spec() -> CallSpec:
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
    return await _stream(client, spec, body, video_meter, responses)


async def _stream(
    client: MetaClient,
    spec: CallSpec,
    body: Mapping[str, Any],
    meter: Callable[[Mapping[str, Any]], tuple[Units, float | None]],
    responses: ResponseLog | None,
) -> StreamResult:
    """Stream one SAM call; when its responses must be deleted, log each ID as the stream names it and mark
    the stream ended (so ``delete_pending`` may delete it) however the call ends."""
    if not client.settings.delete_sam_responses:
        return await client.stream(spec, body, meter=meter)
    if responses is None:
        raise ValueError("SAFECUT_SAM_DELETE_RESPONSES is on: pass the job's ResponseLog so the response is deleted")
    responses.check()  # refuse before spending if responses.json can't be read
    seen: list[str] = []

    def begin(response_id: str) -> None:
        seen.append(response_id)
        responses.begin(response_id)

    try:
        return await client.stream(spec, body, meter=meter, on_response_id=begin)
    finally:
        responses.ended(seen)


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
    return await _stream(client, spec, body, image_meter, responses)
