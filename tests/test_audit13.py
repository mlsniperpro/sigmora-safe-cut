"""Tests for audit #13: ledger work survives repeated cancellation, queued calls hold no budget, a SAM response
is never deleted while its stream is open, free calls never need the ledger, and probe c's length clips."""

from __future__ import annotations

import asyncio
import subprocess
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import imageio_ffmpeg
import respx

from safecut import contracts as c
from safecut.config import Settings
from safecut.meta import sam
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import Harness, completed, sse, stream_response


def _spec(estimate: float, lane: str = "responses") -> CallSpec:
    return CallSpec(
        stage="s",
        model="muse-spark-1.3",
        estimate_usd=estimate,
        estimate_units={},
        policy=RetryPolicy(attempts=1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
        lane=lane,  # pyright: ignore[reportArgumentType] -- a Lane literal
    )


def _meter(_: object) -> tuple[dict[str, float], float]:
    return {"n": 1}, 0.001


async def test_a_second_cancel_never_strands_the_release(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    loop = asyncio.get_running_loop()
    gate = threading.Event()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
    blocker = loop.run_in_executor(None, gate.wait)  # the release stays queued while we cancel twice
    ran: list[str] = []
    task = asyncio.create_task(h.client._ledger_after(lambda: ran.append("released")))  # pyright: ignore[reportPrivateUsage] -- the shielded ledger call
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.sleep(0.01)
    gate.set()
    await blocker
    done, _ = await asyncio.wait({task})
    assert task in done
    assert task.cancelled()
    assert ran == ["released"]


async def test_queued_calls_hold_no_budget(settings: Settings, tmp_path: Path, mock_api: respx.MockRouter) -> None:
    # Cap $1, six calls estimated at $0.30, three in flight at once: the queued three must not be refused.
    cfg = settings.model_copy(update={"job_usd_cap": 1.0})
    ledger = LocalLedger()
    client = MetaClient(cfg, job_id="j", caller=Caller.local(), ledger=ledger, cost_path=tmp_path / "c.jsonl")

    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"id": "r"})

    mock_api.post("/thing").mock(side_effect=slow)
    results = await asyncio.gather(*(client.request("POST", "thing", _spec(0.30), meter=_meter) for _ in range(6)))
    await client.aclose()
    assert len(results) == 6
    assert ledger.spent("job:j") == 6 * 0.001


async def test_an_open_sam_stream_is_never_deleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    log = sam.ResponseLog(tmp_path)
    release, streaming = asyncio.Event(), asyncio.Event()
    usage = {"video_frames_processed": 60}

    async def slow_stream() -> AsyncIterator[bytes]:
        yield sse({"type": "response.created", "response": {"id": "resp_2", "status": "in_progress"}})
        streaming.set()  # resumed: the client has read (and logged) response.created
        await release.wait()
        yield sse(completed({"id": "resp_2", "status": "completed", "usage": usage}))

    answers = iter(
        [
            httpx.Response(200, content=slow_stream(), headers={"content-type": "text/event-stream"}),
            stream_response(completed({"id": "resp_1", "status": "completed", "usage": usage})),
        ]
    )
    mock_api.post("/responses").mock(side_effect=lambda _: next(answers))
    deleted: list[str] = []

    def delete(request: httpx.Request) -> httpx.Response:
        deleted.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"deleted": True})

    mock_api.delete(url__regex=r".*/responses/resp_\d").mock(side_effect=delete)
    body = sam.video_body(cfg, file_id="file-1", text="face")
    second = asyncio.create_task(sam.segment_video(h.client, body, sam_frames=60, responses=log))
    await streaming.wait()
    assert "resp_2" in [e.response_id for e in log.index().root]
    await sam.segment_video(h.client, body, sam_frames=60, responses=log)
    assert await log.delete_pending(h.client) == 1
    assert deleted == ["resp_1"]  # resp_2 is still streaming
    release.set()
    await second
    assert await log.delete_pending(h.client) == 2
    assert deleted == ["resp_1", "resp_2"]


class _LedgerDown(LocalLedger):
    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
        raise OSError("ledger down")


async def test_cleanup_works_while_the_ledger_is_down(
    settings: Settings, tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    client = MetaClient(
        settings, job_id="j_test", caller=Caller.local(), ledger=_LedgerDown(), cost_path=tmp_path / "c.jsonl"
    )
    store = FileStore(client, tmp_path / "job")
    entry = c.FileEntry(name="sam_proxy.mp4", sha256="a" * 64, file_id="file-5", created_at=c.now_utc())
    c.dump(c.FilesIndex([entry]), store.index_path)
    gone = mock_api.delete("/files/file-5").mock(return_value=httpx.Response(200, json={"deleted": True}))
    assert await store.delete_all() is True
    await client.aclose()
    assert gone.call_count == 1


def test_probe_c_length_clips_have_the_asked_length(tmp_path: Path) -> None:
    clip = tmp_path / "long.mp4"
    probes.make_long_clip(clip, 3)
    out = subprocess.run(  # noqa: S603 -- fixed argv, bundled ffmpeg
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(clip),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    frames = sum(1 for line in out.splitlines() if line and not line.startswith("#"))
    assert frames == 3 * 8
