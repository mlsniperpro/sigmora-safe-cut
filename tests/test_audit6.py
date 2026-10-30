"""Tests for audit #6: SAM response IDs kept on every attempt, wrong-path 404s on response deletes, our key
masked in server error text, and the effort check when a body sends no reasoning."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
import respx

from safecut.config import Settings
from safecut.meta import responses, sam
from safecut.meta.client import CallSpec
from safecut.meta.errors import MetaAuthError, MetaIncomplete
from safecut.meta.retry import RetryPolicy
from tests.conftest import FAKE_KEY, Harness, completed, sse, stream_response

USAGE = {"video_frames_processed": 60}


def _created(rid: str) -> dict[str, object]:
    return {"type": "response.created", "response": {"id": rid, "status": "in_progress"}}


def _no_store(settings: Settings) -> Settings:
    return settings.model_copy(update={"sam_send_store": False})


async def test_an_incomplete_sam_response_is_still_logged(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = _no_store(settings)
    h = make_harness(cfg=cfg)
    incomplete = {"type": "response.incomplete", "response": {"id": "resp_INC", "status": "incomplete", "usage": USAGE}}
    mock_api.post("/responses").mock(return_value=stream_response(_created("resp_INC"), incomplete))
    log = sam.ResponseLog(tmp_path)
    with pytest.raises(MetaIncomplete):
        await sam.segment_video(
            h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60, responses=log
        )
    assert log.index().pending == ["resp_INC"]


async def test_a_retried_sam_attempt_logs_both_responses(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = _no_store(settings)
    h = make_harness(cfg=cfg)
    cut = stream_response(_created("resp_CUT"))  # eof after response.created: retried
    ok = stream_response(_created("resp_OK"), completed({"id": "resp_OK", "status": "completed", "usage": USAGE}))
    mock_api.post("/responses").mock(side_effect=[cut, ok])
    log = sam.ResponseLog(tmp_path)
    result = await sam.segment_video(
        h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60, responses=log
    )
    assert result.attempts == 2
    assert log.index().pending == ["resp_CUT", "resp_OK"]


async def test_a_cancelled_sam_stream_is_still_logged(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = _no_store(settings)
    h = make_harness(cfg=cfg)

    async def created_then_hang() -> AsyncIterator[bytes]:
        yield sse(_created("resp_HANG"))
        await asyncio.Event().wait()

    mock_api.post("/responses").mock(
        return_value=httpx.Response(200, content=created_then_hang(), headers={"content-type": "text/event-stream"})
    )
    log = sam.ResponseLog(tmp_path)
    task = asyncio.create_task(
        sam.segment_video(h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60, responses=log)
    )
    for _ in range(200):
        if log.path.exists():
            break
        await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert log.index().pending == ["resp_HANG"]


async def test_an_empty_404_on_a_response_delete_is_a_failure(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    log = sam.ResponseLog(tmp_path)
    log.note("resp_A")
    log.note("resp_B")
    mock_api.delete("/responses/resp_A").mock(return_value=httpx.Response(404))  # wrong path: no error body
    mock_api.delete("/responses/resp_B").mock(
        return_value=httpx.Response(404, json={"error": {"message": "No response found"}})
    )
    assert await log.delete_pending(h.client) == 1
    assert log.index().pending == ["resp_A"]


async def test_our_key_is_masked_in_server_error_text(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(
        return_value=httpx.Response(401, json={"error": {"message": f"Invalid API key: {FAKE_KEY}"}})
    )
    spec = CallSpec(
        stage="s",
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(attempts=1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )
    with pytest.raises(MetaAuthError) as info:
        await h.client.request("POST", "thing", spec, meter=lambda _: ({}, 0.0))
    assert FAKE_KEY not in str(info.value)
    assert "[redacted]" in str(info.value)


async def test_effort_without_reasoning_must_be_omit(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/responses").mock(return_value=httpx.Response(500))
    body = {"model": "muse-spark-1.3", "max_output_tokens": 10, "input": "hi"}
    with pytest.raises(ValueError, match="omit"):
        await responses.create(h.client, body, stage="role", effort="max", count=False)
    assert route.call_count == 0
