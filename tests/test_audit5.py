"""Tests for audit #5: lost-ack reserves, upload records under cancellation and faults, orphan reconciliation,
replay at the transport, cost-write faults, 5xx retry classes, effort agreement and the PRE-A §12 rows."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from safecut import contracts as c
from safecut.config import Settings, load_settings
from safecut.meta import responses, sam
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaBadRequest, MetaConfigError, MetaUnavailable, classify
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy
from tests.conftest import Harness, completed, stream_response

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _spec(**kw: Any) -> CallSpec:
    base: dict[str, Any] = {
        "stage": "s",
        "model": "muse-spark-1.3",
        "estimate_usd": 0.05,
        "estimate_units": {"n": 0},
        "policy": RetryPolicy(attempts=4),
        "timeout": httpx.Timeout(5.0),
        "total_timeout_s": 30.0,
    }
    return CallSpec(**(base | kw))


def _meter(_: object) -> tuple[dict[str, float], float]:
    return {"n": 1}, 0.002


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 300)
    return path


# --- M1: a reserve whose ack was lost ------------------------------------------------------


class _LostAck(LocalLedger):
    """Commits the first reservation, then fails as if the answer never arrived."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
        self.calls += 1
        super().reserve(call_id, job_id, usd, limits)
        if self.calls == 1:
            raise OSError("ack lost")


async def test_a_retried_reserve_reuses_the_reservation(
    settings: Settings, tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={"id": "r1"}))
    ledger = _LostAck()
    client = MetaClient(settings, job_id="j1", caller=Caller.local(), ledger=ledger, cost_path=tmp_path / "c.jsonl")
    result = await client.request("POST", "thing", _spec(), meter=_meter)
    await client.aclose()
    assert result.body == {"id": "r1"}
    assert (ledger.calls, route.call_count) == (2, 1)
    assert ledger.spent("job:j1") == pytest.approx(0.002)  # one reservation, settled at the measured cost


def test_ledger_reserve_is_idempotent_only_on_the_same_terms() -> None:
    ledger = LocalLedger()
    job = CapLimit("job", "job:a", 1.0)
    ledger.reserve("c1", "a", 0.6, [job])
    ledger.reserve("c1", "a", 0.6, [job])  # the retry after a lost ack
    assert ledger.spent("job:a") == pytest.approx(0.6)
    for args in (("b", 0.6, [job]), ("a", 0.5, [job]), ("a", 0.6, [])):
        with pytest.raises(ValueError, match="different terms"):
            ledger.reserve("c1", *args)


class _Conflicting(LocalLedger):
    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
        raise ValueError("call_id already reserved with different terms")


async def test_ledger_refusals_are_typed(settings: Settings, tmp_path: Path, mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}))
    client = MetaClient(
        settings, job_id="j", caller=Caller.local(), ledger=_Conflicting(), cost_path=tmp_path / "c.jsonl"
    )
    with pytest.raises(MetaUnavailable, match="refused"):
        await client.request("POST", "thing", _spec(), meter=_meter)
    await client.aclose()
    assert route.call_count == 0


# --- M2: the record after a successful upload -----------------------------------------------


async def test_cancel_while_recording_an_upload_keeps_its_id(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    posted = asyncio.Event()

    async def upload(_: httpx.Request) -> httpx.Response:
        posted.set()
        return httpx.Response(200, json={"id": "file-777"})

    mock_api.post("/files").mock(side_effect=upload)
    store = FileStore(h.client, tmp_path / "job")
    await store._index_lock.acquire()  # a concurrent update is writing files.json
    task = asyncio.create_task(store.upload(clip, "sam_proxy.mp4"))
    await posted.wait()
    await asyncio.sleep(0.01)
    task.cancel()
    store._index_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task
    (entry,) = store.index().root
    assert entry.file_id == "file-777"
    assert not store.index().all_deleted  # the receipt can't claim files_deleted over it


async def test_a_failed_record_deletes_the_upload_by_id(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    clip: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-778"}))
    deleted = mock_api.delete("/files/file-778").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    real_record = store._record

    async def failing_record(entry: c.FileEntry) -> None:
        if entry.file_id is not None:
            raise OSError("disk full")
        await real_record(entry)

    monkeypatch.setattr(store, "_record", failing_record)
    with pytest.raises(OSError, match="disk full"):
        await store.upload(clip, "sam_proxy.mp4")
    assert deleted.call_count == 1


async def test_a_failed_record_and_delete_leave_an_orphan(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    clip: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-779"}))
    mock_api.delete("/files/file-779").mock(return_value=httpx.Response(400, json={"error": {"message": "no"}}))
    store = FileStore(h.client, tmp_path / "job")
    real_record = store._record

    async def failing_record(entry: c.FileEntry) -> None:
        if entry.file_id is not None:
            raise OSError("disk full")
        await real_record(entry)

    monkeypatch.setattr(store, "_record", failing_record)
    with pytest.raises(OSError, match="disk full"):
        await store.upload(clip, "sam_proxy.mp4")
    (entry,) = store.index().root
    assert entry.orphan
    assert not store.index().all_deleted


# --- L2: orphan reconciliation --------------------------------------------------------------


async def test_reconcile_keeps_the_orphan_open_when_the_listing_fails(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = FileStore(h.client, tmp_path / "job")
    orphan = c.FileEntry(name="sam_proxy.mp4", sha256="a" * 64, file_id=None, created_at=c.now_utc(), orphan=True)
    c.dump(c.FilesIndex([orphan]), store.index_path)
    mock_api.get("/files").mock(return_value=httpx.Response(400, json={"error": {"message": "bad"}}))
    with pytest.raises(MetaBadRequest):
        await store.delete_all()
    assert not store.index().all_deleted


async def test_reconcile_never_deletes_a_recorded_copy_or_another_jobs(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = FileStore(h.client, tmp_path / "job")
    now = c.now_utc()
    entries = [
        c.FileEntry(name="sam_proxy.mp4", sha256="a" * 64, file_id="file-1", created_at=now, deleted_at=now),
        c.FileEntry(name="sam_proxy.mp4", sha256="a" * 64, file_id=None, created_at=now, orphan=True),
    ]
    c.dump(c.FilesIndex(entries), store.index_path)
    listing = [
        {"id": "file-1", "filename": "j_test-sam_proxy.mp4", "bytes": 1, "created_at": time.time()},
        {"id": "file-2", "filename": "j_other-sam_proxy.mp4", "bytes": 1, "created_at": time.time()},
        {"id": "file-3", "filename": "j_test-sam_proxy.mp4", "bytes": 1, "created_at": time.time()},
    ]
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": listing}))
    gone = mock_api.delete("/files/file-3").mock(return_value=httpx.Response(200, json={"deleted": True}))
    assert await store.delete_all() is True
    assert gone.call_count == 1
    assert sorted(str(e.file_id) for e in store.index().root if e.file_id) == ["file-1", "file-3"]


# --- L3, L4, L5, L6 -------------------------------------------------------------------------


async def test_replay_mode_refuses_live_calls(settings: Settings, tmp_path: Path, mock_api: respx.MockRouter) -> None:
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}))
    ledger = LocalLedger()
    client = MetaClient(
        settings.model_copy(update={"replay": True}),
        job_id="j",
        caller=Caller.local(),
        ledger=ledger,
        cost_path=tmp_path / "c.jsonl",
    )
    with pytest.raises(MetaConfigError, match="REPLAY"):
        await client.request("POST", "thing", _spec(), meter=_meter)
    await client.aclose()
    assert route.call_count == 0
    assert ledger.spent("job:j") == 0


async def test_a_failed_cost_write_keeps_the_result_and_the_charge(
    settings: Settings, tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={"id": "r1"}))
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("")
    ledger = LocalLedger()
    client = MetaClient(settings, job_id="j", caller=Caller.local(), ledger=ledger, cost_path=blocked / "c.jsonl")
    result = await client.request("POST", "thing", _spec(), meter=_meter)
    await client.aclose()
    assert result.body == {"id": "r1"}
    assert route.call_count == 1
    assert ledger.spent("job:j") == pytest.approx(0.002)


@pytest.mark.parametrize(("status", "retryable"), [(500, True), (502, True), (503, True), (501, False), (505, False)])
def test_only_documented_5xx_are_retried(status: int, retryable: bool) -> None:
    assert classify(status, None).retryable is retryable


async def test_effort_must_match_the_body(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/responses").mock(return_value=httpx.Response(500))
    body = {"model": "muse-spark-1.3", "max_output_tokens": 10, "reasoning": {"effort": "max"}, "input": "hi"}
    with pytest.raises(ValueError, match="effort"):
        await responses.create(h.client, body, stage="role", effort="medium", count=False)
    assert route.call_count == 0


# --- M4: PRE-A §12 rows ---------------------------------------------------------------------


def test_sam_delete_responses_follows_send_store() -> None:
    assert load_settings({}).delete_sam_responses is False
    assert load_settings({"SAFECUT_SAM_SEND_STORE": "false"}).delete_sam_responses is True
    off = load_settings({"SAFECUT_SAM_SEND_STORE": "false", "SAFECUT_SAM_DELETE_RESPONSES": "0"})
    assert off.delete_sam_responses is False


async def test_sam_responses_are_logged_and_deleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    usage = {"video_frames_processed": 60}
    ids = iter(["resp_1", "resp_2", "resp_3"])

    def answer(_: httpx.Request) -> httpx.Response:
        return stream_response(completed({"id": next(ids), "status": "completed", "usage": usage}))

    mock_api.post("/responses").mock(side_effect=answer)
    mock_api.delete("/responses/resp_1").mock(return_value=httpx.Response(200, json={"deleted": True}))
    mock_api.delete("/responses/resp_2").mock(return_value=httpx.Response(404, json={"error": {"message": "gone"}}))
    mock_api.delete("/responses/resp_3").mock(return_value=httpx.Response(400, json={"error": {"message": "no"}}))
    log = sam.ResponseLog(tmp_path)
    body = sam.video_body(cfg, file_id="file-1", text="face")
    for _ in range(3):
        await sam.segment_video(h.client, body, sam_frames=60, responses=log)
    assert [e.response_id for e in log.index().root] == ["resp_1", "resp_2", "resp_3"]
    assert await log.delete_pending(h.client) == 2  # 404 counts as done; the 400 stays pending
    assert log.index().pending == ["resp_3"]
    c.load(log.path, c.ResponsesIndex)


async def test_sam_without_a_log_is_refused_before_spending(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    route = mock_api.post("/responses").mock(return_value=httpx.Response(500))
    with pytest.raises(ValueError, match="ResponseLog"):
        await sam.segment_video(h.client, sam.video_body(cfg, file_id="file-1", text="face"), sam_frames=60)
    assert route.call_count == 0


def _example(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    return job_dir


def test_receipt_counts_match_responses_json(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    entry = {"response_id": "resp_1", "requested_at": "2026-10-27T10:05:00Z"}
    (job_dir / "responses.json").write_text(json.dumps([entry]))
    with pytest.raises(c.ContractError, match="responses_delete_requested"):
        c.validate_job_dir(job_dir)


def test_new_section_12_fields() -> None:
    job = json.loads((EXAMPLE / "job.json").read_text())
    assert c.Job.model_validate(job).open_weight_attempted is False
    with pytest.raises(ValidationError):
        c.Job.model_validate(job | {"open_weight_attempted": "yes"})
    receipt = c.load(EXAMPLE / "receipt.json", c.Receipt)
    assert (receipt.cost_usd_baseten, receipt.data_handling.responses_delete_requested) == (0, 0)
    handling = receipt.data_handling.model_dump(mode="json")
    del handling["responses_delete_requested"]
    with pytest.raises(ValidationError, match="responses_delete_requested"):
        c.DataHandling.model_validate(handling)
