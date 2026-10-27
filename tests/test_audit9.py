"""Tests for audit #9: linear SSE line splitting, the breaker's trial-only close, a response log that
survives an unreadable file and counts across calls, refused IDs kept visible, the shielded settle under
a saturated executor, and probe b in the store-less configuration."""

from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import respx
from hypothesis import given
from hypothesis import strategies as st

from safecut.config import Settings
from safecut.meta import sam
from safecut.meta.budget import LocalLedger
from safecut.meta.retry import CircuitBreaker
from safecut.meta.sse import aiter_sse_lines
from scripts.probes import probes
from tests import test_probes_replay as replay
from tests.conftest import Harness


async def _split(chunks: list[bytes]) -> list[str]:
    async def gen() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    return [line async for line in aiter_sse_lines(gen())]


def _reference(data: bytes) -> list[str]:
    lines = re.split(r"\r\n|\r|\n", data.decode("utf-8", errors="replace"))
    if lines and lines[-1] == "":
        lines.pop()
    return lines


@given(
    st.lists(st.sampled_from(["a", "é", " ", "\r", "\n", "\r\n", "data: x", "\u0085"]), max_size=40),
    st.lists(st.integers(min_value=1, max_value=7), min_size=1, max_size=10),
)
def test_splitting_matches_the_reference_for_any_chunking(pieces: list[str], cuts: list[int]) -> None:
    data = "".join(pieces).encode()
    chunks: list[bytes] = []
    i, k = 0, 0
    while i < len(data):
        size = cuts[k % len(cuts)]
        chunks.append(data[i : i + size])
        i, k = i + size, k + 1
    assert asyncio.run(_split(chunks)) == _reference(data)


def test_a_multi_megabyte_line_splits_in_linear_time() -> None:
    line = b"data: " + b"x" * (8 << 20)
    chunks = [line[i : i + 4096] for i in range(0, len(line), 4096)] + [b"\n\n"]
    started = time.perf_counter()
    lines = asyncio.run(_split(chunks))
    assert time.perf_counter() - started < 2.0  # quadratic re-scanning took ~7 s here
    assert len(lines[0]) == len(line)
    assert lines[1:] == [""]


def test_a_late_success_never_closes_an_open_breaker() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == "open"
    breaker.record_success()  # a call that started before the breaker opened
    assert breaker.state == "open"
    now[0] += 61
    assert breaker.before_call() is True
    breaker.record_success(True)
    assert breaker.state == "closed"


async def test_an_unreadable_log_still_deletes_in_memory_ids_and_counts_once(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    log = sam.ResponseLog(tmp_path)
    log.path.mkdir()  # responses.json is a directory: every read and write fails
    log.note("resp_B")
    route = mock_api.delete("/responses/resp_B").mock(return_value=httpx.Response(200, json={"deleted": True}))
    assert await log.delete_pending(h.client) == 1
    assert await log.delete_pending(h.client) == 1  # cumulative, and never requested twice
    assert route.call_count == 1


def test_refused_ids_stay_visible(tmp_path: Path) -> None:
    log = sam.ResponseLog(tmp_path)
    log.note("resp:with.colon")
    log.note("resp:with.colon")
    assert log.refused == ["resp:with.colon"]
    assert log.requested() == 0


async def test_the_settle_runs_even_when_cancelled_while_queued(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    loop = asyncio.get_running_loop()
    gate = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(pool)
    blocker = loop.run_in_executor(None, gate.wait)  # the only worker is busy: the settle stays queued
    ran: list[str] = []
    task = asyncio.create_task(h.client._ledger_after(lambda: ran.append("settled")))  # pyright: ignore[reportPrivateUsage] -- the shielded settle itself
    await asyncio.sleep(0.01)
    task.cancel()
    gate.set()
    await blocker
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("the cancellation must be re-raised")
    assert ran == ["settled"]


async def test_probe_b_runs_without_store_and_deletes(settings: Settings, tmp_path: Path) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    replay.SAM_CREATED.clear()
    deleted: list[str] = []
    with respx.mock(assert_all_called=False) as router:
        _replay_routes(router, deleted)
        results = await probes.run(["b"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    b = results["b"]
    assert "error" not in b, b
    assert b["store_false_sent"] is False
    assert b["response_ids_refused"] == 0
    # Every SAM response created is deleted (the store-less check deletes its one twice, on purpose).
    assert set(deleted) == set(replay.SAM_CREATED)
    assert len(replay.SAM_CREATED) >= 6  # 4 concepts, the store-less check, the fps hint


def _replay_routes(router: respx.MockRouter, deleted: list[str]) -> None:
    uploads = iter(range(1, 100))
    router.post(f"{replay.BASE}/files").mock(
        side_effect=lambda _: httpx.Response(200, json={"id": f"file-{next(uploads)}"})
    )
    router.delete(url__regex=rf"{replay.BASE}/files/file-\d+").mock(return_value=httpx.Response(200, json={}))
    router.get(f"{replay.BASE}/files").mock(return_value=httpx.Response(200, json={"data": []}))
    router.post(f"{replay.BASE}/responses").mock(side_effect=replay._responses)  # pyright: ignore[reportPrivateUsage] -- reuse the replay SAM answers

    def delete(request: httpx.Request) -> httpx.Response:
        deleted.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"deleted": True})

    router.delete(url__regex=rf"{replay.BASE}/responses/[A-Za-z0-9_-]+").mock(side_effect=delete)
