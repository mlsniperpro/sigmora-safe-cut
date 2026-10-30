"""SAM 3.1 request bodies, cost metering, a call wrapper and the stream parser (WP0 base, WP1 parser).

One noun phrase (or one batch of object prompts) per request; the proxy clip's file ID comes from
``files.json`` by name, never ``prepared.mp4`` (PRE-A §10.6). Parsing wraps Meta's ``meta-sam-parser`` and fails
closed: an incomplete stream or a dropped line is ``MetaIncomplete``, never a partial result (PRE-A §10.6).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
from meta_sam_parser import (
    CompletedOutcome,
    ParserFinish,
    PromptBox,
    PromptObject,
    PromptPoint,
    ResponsesStreamError,
    ResponsesStreamRefusalError,
    ResponseStreamOutcome,
    SegmentationBoxRecord,
    SegmentationMask,
    SegmentationMaskRecord,
    SegmentationTextRecord,
    build_object_prompt,
    parse_responses_stream,
    video_segmentation_format,
)
from meta_sam_parser import FramePrompt as SamFramePrompt

from safecut import config
from safecut.config import Settings
from safecut.contracts import RESPONSE_ID_PATTERN, ResponseEntry, ResponsesIndex, dump, load, now_utc
from safecut.meta import cost, parallel
from safecut.meta.client import CallSpec, MetaClient, StreamResult, Units
from safecut.meta.errors import MetaConfigError, MetaError, MetaIncomplete, MetaRefusal
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


# ---------------------------------------------------------------------------
# Object prompts (PRE-A §1.3) and the stream parser (§1.4, §10.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObjectPrompt:
    """One object of a batched object-prompt request: a positive point, optionally a half-open box, on a proxy
    frame. ``object_id`` is the id the request gives it; SAM reports the object under the same id."""

    object_id: int
    frame: int
    point: tuple[int, int]
    box: tuple[int, int, int, int] | None = None


def object_prompt_text(size: tuple[int, int], prompts: Sequence[ObjectPrompt]) -> str:
    """``build_object_prompt`` text for a batch (half-open boxes in, inclusive out; vectors O1–O3)."""
    if not prompts:
        raise ValueError("an object-prompt request needs at least one object")
    if len({p.object_id for p in prompts}) != len(prompts):
        raise ValueError("object ids in one request must be unique")
    objects = [
        PromptObject(
            id=p.object_id,
            prompts=(
                SamFramePrompt(
                    frame=p.frame,
                    box=PromptBox(*p.box) if p.box is not None else None,
                    points=(PromptPoint(p.point[0], p.point[1]),),
                ),
            ),
        )
        for p in prompts
    ]
    return build_object_prompt(size=size, objects=objects)


@dataclass(frozen=True)
class Detection:
    """One SAM record: an object on one frame of the request's own video (the proxy)."""

    frame: int
    object_id: str
    #: Half-open ``[x1, y1, x2, y2)`` in the proxy's pixels.
    box: tuple[int, int, int, int]
    #: The box-sized mask as SAM sent it (decode with ``meta_sam_parser.decode_mask_to_raster``).
    mask: SegmentationMask | None
    confidence: float | None


@dataclass(frozen=True)
class Segmentation:
    detections: tuple[Detection, ...]
    #: ``usage.video_frames_processed`` (the frames billed), or None when SAM didn't report it.
    frames_billed: int | None


async def _aiter(events: Sequence[Mapping[str, Any]]) -> AsyncIterator[Mapping[str, Any]]:
    for event in events:
        yield event


class _LaneCollector:
    """A parser for Meta's stream adapter that keeps the lane's text: the adapter still checks the stream (one
    lane, refusals, the terminal event); the text is then parsed with Meta's segmentation parser by lines."""

    def __init__(self) -> None:
        self.parts: list[str] = []

    def push(self, chunk: str, *, emit: bool = True) -> tuple[()]:
        del emit
        self.parts.append(chunk)
        return ()

    def finish(self, outcome: ResponseStreamOutcome) -> ParserFinish[object, tuple[str, ResponseStreamOutcome]]:
        return ParserFinish(events=(), result=("".join(self.parts), outcome))


class _LaneText:
    def create_parser(self) -> _LaneCollector:
        return _LaneCollector()


#: A parsed record, picklable across the pool: ("box", frame, id, left, top, right, bottom, confidence),
#: ("mask", frame, id, revision, encoding, payload, width, height), ("text", order) for a stray line, or
#: ("space", w, h) for each box token's media size.
_Record = tuple[Any, ...]
_Diagnostic = tuple[str, str, int]
#: Below this many mask pixels a stream is parsed in-process (a pool costs more than it saves).
PARALLEL_MIN_PIXELS = 1_500_000
_MASK_SIZE = re.compile(r"data=([0-9]+),([0-9]+),")
#: A box token's fields: its ``w``/``h`` name the pixel space every coordinate is in (the parser drops them).
_BOX_TOKEN = re.compile(r"<\|box;([^|]*)\|>")
#: A line with frame-record syntax (a ``<Nf>`` header or ``<|token|>``s) that the parser couldn't read as one.
_RECORD_SYNTAX = re.compile(r"<\s*[0-9]+\s*f|<\|")


def parse_lines(chunk: tuple[str, int]) -> tuple[list[_Record], list[_Diagnostic]]:
    """Meta's video segmentation parser over whole lines (``chunk`` = text, first line number)."""
    text, first = chunk
    parser = video_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    records: list[_Record] = []
    for r in result.records:
        if isinstance(r, SegmentationBoxRecord) and r.frame is not None:
            records.append(("box", r.frame.frame_index, r.object_id, r.left, r.top, r.right, r.bottom, r.confidence))
        elif isinstance(r, SegmentationTextRecord) and _RECORD_SYNTAX.search(r.text):
            records.append(("text", r.order))
        elif isinstance(r, SegmentationTextRecord) and r.text.strip():
            log.warning("SAM stream carried a prose line; ignored", extra={"chars": len(r.text)})
        elif isinstance(r, SegmentationMaskRecord) and r.frame is not None:
            m = r.mask
            mask = ("mask", r.frame.frame_index, r.object_id, r.revision, m.encoding, m.payload, m.width, m.height)
            records.append(mask)
    for fields in _BOX_TOKEN.findall(text):
        keys = dict(part.split("=", 1) for part in fields.split(";") if "=" in part)
        records.append(("space", keys.get("w"), keys.get("h")))
    diagnostics = [(d.severity, d.code, d.line + first - 1) for d in result.diagnostics]
    return records, diagnostics


def _chunks(text: str, parts: int) -> list[tuple[str, int]]:
    """Whole lines, split into about ``parts`` pieces of similar mask area."""
    lines = text.split("\n")
    weights = [sum(int(h) * int(w) for h, w in _MASK_SIZE.findall(line)) + 1 for line in lines]
    target = sum(weights) / max(parts, 1)
    out: list[tuple[str, int]] = []
    start, acc = 0, 0
    for i, weight in enumerate(weights):
        acc += weight
        if acc >= target and i + 1 < len(lines):
            out.append(("\n".join(lines[start : i + 1]) + "\n", start + 1))
            start, acc = i + 1, 0
    out.append(("\n".join(lines[start:]), start + 1))
    return [c for c in out if c[0]]


def _collect(
    records: Sequence[_Record],
) -> tuple[dict[tuple[int, str], tuple[int, SegmentationMask]], dict[tuple[int, str], _Record], set[tuple[int, str]]]:
    """Each (frame, object)'s latest mask revision and its box. §1.4 wants one record per object per frame; a
    repeat is joined, never dropped: the union box (fail toward hiding more), listed in the returned set so its
    mask is dropped, since neither mask is that box's size."""
    masks: dict[tuple[int, str], tuple[int, SegmentationMask]] = {}
    boxes: dict[tuple[int, str], _Record] = {}
    repeated: set[tuple[int, str]] = set()
    for r in records:
        key = (r[1], r[2])
        if r[0] == "mask":
            if key not in masks or masks[key][0] <= r[3]:
                masks[key] = (r[3], SegmentationMask(encoding=r[4], payload=r[5], width=r[6], height=r[7]))
        elif key in boxes:
            was = boxes[key]
            boxes[key] = ("box", r[1], r[2], min(was[3], r[3]), min(was[4], r[4]), max(was[5], r[5]),
                          max(was[6], r[6]), r[7])  # fmt: skip
            repeated.add(key)
        else:
            boxes[key] = r
    return masks, boxes, repeated


def _detections(
    results: Sequence[tuple[list[_Record], list[_Diagnostic]]], size: tuple[int, int] | None
) -> list[Detection]:
    """The parsed chunks' records as detections, failing closed on anything that would misplace or drop one."""
    errors = [d for _, ds in results for d in ds if d[0] == "error"]
    # Meta's parser keeps a line it can't read as a frame record as free text, without a diagnostic. One that has
    # record syntax is a frame we couldn't read: fail closed, like a dropped line (prose is only logged).
    stray = sum(1 for records, _ in results for r in records if r[0] == "text")
    if stray:
        raise MetaIncomplete(f"SAM stream has {stray} line(s) that aren't frame records", eof=False)
    if errors:
        raise MetaIncomplete(f"SAM parser dropped {len(errors)} line(s): {errors[0][1]} at line {errors[0][2]}",
                             eof=False)  # fmt: skip
    spaces = {(r[1], r[2]) for records, _ in results for r in records if r[0] == "space"}
    if size is not None and spaces - {(str(size[0]), str(size[1]))}:
        # Every coordinate is in the box tokens' w x h space; any other space than the proxy's would misplace them.
        raise MetaIncomplete(f"SAM answered in a {sorted(spaces)[0]} space, not the proxy's {size[0]}x{size[1]}",
                             eof=False)  # fmt: skip
    masks, boxes, repeated = _collect([r for records, _ in results for r in records if r[0] != "space"])
    if repeated:
        log.warning("SAM repeated an object on a frame; boxes joined", extra={"count": len(repeated)})
    detections: list[Detection] = []
    for (f, oid), r in boxes.items():
        mask = masks[(f, oid)][1] if (f, oid) in masks and (f, oid) not in repeated else None
        box = (int(r[3]), int(r[4]), int(r[5]), int(r[6]))
        if mask is not None and (mask.width, mask.height) != (box[2] - box[0], box[3] - box[1]):
            # §1.4: a mask is box-sized; any other size would be placed wrong and under-hide.
            raise MetaIncomplete(f"SAM mask {mask.width}x{mask.height} isn't its box's size (frame {f})", eof=False)
        detections.append(Detection(frame=f, object_id=oid, box=box, mask=mask, confidence=r[7]))
    return detections


async def parse_video_events(
    events: Sequence[Mapping[str, Any]], *, size: tuple[int, int] | None = None
) -> Segmentation:
    """Parse one SAM video stream's events (live or replayed) into detections, failing closed.

    An incomplete outcome is ``MetaIncomplete`` (``eof`` when the stream just stopped); an error diagnostic means
    the parser dropped a line, so the request is ``MetaIncomplete`` too (§10.6, vector S5); a refusal is
    ``MetaRefusal``. Records arrive in any frame order and frames without objects are simply absent (§1.4). Meta's
    parser decodes every mask to validate it (pure Python), so long streams are parsed in a process pool by lines.
    """
    try:
        async with parse_responses_stream(_aiter(events), _LaneText()) as parsed:
            text, outcome = await parsed.final_result()
    except ResponsesStreamRefusalError as exc:
        raise MetaRefusal.of(str(exc)) from exc
    except ResponsesStreamError as exc:
        raise MetaIncomplete(f"SAM stream unusable: {exc.code}", eof=False) from exc
    if outcome.status != "completed":
        reason = getattr(outcome, "reason", None)
        raise MetaIncomplete(f"SAM stream incomplete ({reason})", eof=reason == "eof")
    pixels = sum(int(h) * int(w) for h, w in _MASK_SIZE.findall(text))
    parts = parallel.workers() * 2 if pixels >= PARALLEL_MIN_PIXELS else 1
    # In a worker thread: parsing a long stream takes seconds, and other SAM streams of the job are still being
    # read on this event loop meanwhile.
    results = await asyncio.to_thread(parallel.map_in_pool, parse_lines, _chunks(text, parts), parallel=parts > 1)
    detections = _detections(results, size)
    completed = next((e for e in reversed(events) if e.get("type") == "response.completed"), None)
    response: Any = completed.get("response") if completed else None
    units, _ = video_meter(cast(Mapping[str, Any], response) if isinstance(response, Mapping) else {})
    billed = units.get("frames")
    return Segmentation(
        detections=tuple(sorted(detections, key=lambda d: (d.frame, int(d.object_id)))),
        frames_billed=int(billed) if billed is not None else None,
    )
