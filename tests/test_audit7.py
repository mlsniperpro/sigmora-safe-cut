"""Tests for audits #7 and #8 (both at 2568819): SSE lines split only on SSE line endings, settle/release
surviving cancellation, the breaker's 60 s window, response-ID hygiene and a failure-proof response log,
and four open-weight batches in flight."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut import open_weight
from safecut.config import OpenWeightPrice, Settings
from safecut.contracts import ContractError
from safecut.meta import responses, sam
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.retry import CircuitBreaker
from safecut.meta.sse import aiter_sse, aiter_sse_lines
from tests.conftest import Harness, completed, stream_response, text_response

BT = "https://inference.baseten.co/v1"


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _events(*parts: bytes) -> list[dict[str, object]]:
    return [event async for event in aiter_sse(aiter_sse_lines(_chunks(*parts)))]


@pytest.mark.parametrize("separator", [" ", " ", "\u0085"])
async def test_unicode_line_separators_stay_inside_an_event(separator: str) -> None:
    payload = json.dumps({"type": "x", "text": f"a{separator}b"}, ensure_ascii=False)
    events = await _events(f"data: {payload}\n\n".encode())
    assert events == [{"type": "x", "text": f"a{separator}b"}]


async def test_line_endings_split_across_chunks() -> None:
    one, two = json.dumps({"n": 1}), json.dumps({"n": 2})
    # "\r\n" split between chunks must be one line ending, not a line end plus a blank line (= dispatch).
    events = await _events(b"event: e\r", f"\ndata: {one}\r".encode(), b"\n\r\n", f"data: {two}\r\r".encode())
    assert events == [{"n": 1, "type": "e"}, {"n": 2}]
    # A multi-byte character split between chunks decodes intact.
    encoded = f"data: {json.dumps({'t': 'é'}, ensure_ascii=False)}\n\n".encode()
    cut = encoded.index("é".encode()) + 1
    assert await _events(encoded[:cut], encoded[cut:]) == [{"t": "é"}]


async def test_a_stream_with_u2028_in_the_answer_completes_once(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/responses").mock(return_value=stream_response(completed(text_response("line two"))))
    message = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    body = {"model": "muse-spark-1.3", "max_output_tokens": 50, "input": [message], "store": False}
    result = await responses.create(h.client, body, stage="role", effort="omit", count=False)
    assert route.call_count == 1
    assert responses.output_text(result.response) == "line two"


async def test_a_cancel_never_skips_the_ledger_settle(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    ran: list[str] = []
    task = asyncio.create_task(h.client._ledger_after(lambda: ran.append("settled")))  # pyright: ignore[reportPrivateUsage] -- the shielded settle itself
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ran == ["settled"]


def test_the_breaker_counts_failures_in_60_s_not_in_a_row() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for _ in range(4):
        breaker.record_failure()
        now[0] += 1
    breaker.record_success()  # another endpoint answered: SAM is still failing
    breaker.record_failure()
    assert breaker.state == "open"
    now[0] += 61
    assert breaker.before_call() is True  # the half-open trial
    breaker.record_success(True)
    assert breaker.state == "closed"


@pytest.mark.parametrize("bad", ["resp_1/../../files/file-abc", "resp?x=1", "resp#f", "", "r" * 129])
def test_response_ids_must_be_plain_tokens(tmp_path: Path, bad: str) -> None:
    log = sam.ResponseLog(tmp_path)
    log.note(bad)
    assert log.index().root == []


async def test_a_corrupt_response_log_is_refused_before_spending(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    route = mock_api.post("/responses").mock(return_value=httpx.Response(500))
    log = sam.ResponseLog(tmp_path)
    log.path.write_text("{not json")
    with pytest.raises(ContractError):
        await sam.segment_video(
            h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60, responses=log
        )
    assert route.call_count == 0


async def test_an_unwritable_response_log_keeps_the_result_and_the_id(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    usage = {"video_frames_processed": 60}
    mock_api.post("/responses").mock(
        return_value=stream_response(completed({"id": "resp_OK", "status": "completed", "usage": usage}))
    )
    deleted = mock_api.delete("/responses/resp_OK").mock(return_value=httpx.Response(200, json={"deleted": True}))
    log = sam.ResponseLog(tmp_path)

    def disk_full(*_: object) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(sam, "dump", disk_full)
    result = await sam.segment_video(
        h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60, responses=log
    )
    assert result.usd == pytest.approx(0.012)  # measured, not an estimate: the result wasn't lost
    assert await log.delete_pending(h.client) == 1
    assert deleted.call_count == 1


async def test_four_open_weight_batches_run_at_once(tmp_path: Path) -> None:
    price = OpenWeightPrice.model_validate({"in": 1.25, "out": 4.25})
    cfg = Settings(
        baseten_api_key=SecretStr("bt"),
        open_weight_audit="on",
        open_weight_code_kinds=("owner",),
        open_weight_price=price,
        open_weight_job_usd_cap=5.0,
    )
    client = open_weight.open_weight_client(
        cfg, job_id="j", caller=Caller.local("owner"), ledger=LocalLedger(), cost_path=tmp_path / "c.jsonl"
    )
    live, peak = 0, 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        live -= 1
        content = json.loads(request.content)["messages"][1]["content"]
        sent = [int(p["text"].split()[1].rstrip(":")) for p in content if p.get("text", "").startswith("Frame ")]
        answer = json.dumps({"frames": [{"frame": f, "findings": []} for f in sent]})
        chunks = [
            {"id": "c", "choices": [{"delta": {"content": answer}}]},
            {"id": "c", "choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"id": "c", "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
        ]
        return httpx.Response(200, content="".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode())

    frames = [(i, "data:image/jpeg;base64,AA") for i in range(40)]
    with respx.mock(base_url=BT) as router:
        router.post("/chat/completions").mock(side_effect=slow)
        result = await open_weight.second_opinion(client, cfg, consented=True, frames=frames)
    await client.aclose()
    assert len(result.frames) == 40
    assert peak == open_weight.MAX_PARALLEL == 4
