"""SAFECUT-MODAL: the API sleeps when idle, and a started job still finishes.

* The real thing: a local API (uvicorn, replay, the real stages on the synthetic demo clip) is killed with SIGKILL
  mid-analysis and again mid-audit, as a container that is scaled down or preempted would be; a fresh process on
  the same jobs folder (the Volume) finishes the job with a receipt that verifies, and every stage that had
  finished before a kill is never run (or paid for) again.
* The keep-alive: every queued action asks for a ``hold`` input (Modal keeps a container up while an input is in
  flight); ``hold`` waits out the job, resumes one nothing is moving, and fails one stalled past the limit.
* State that must survive a sleep: the paid-action limit and the daily cap live on the Volume.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from safecut import contracts
from safecut.api import app as app_module
from safecut.api.access import ApiRefusal, RateLimiter, StoredRateLimiter, check_caps
from safecut.api.app import STALL_LIMIT, Service, create_app
from safecut.api.store import JobStore
from safecut.contracts import Receipt, load
from safecut.meta.budget import CapLimit
from safecut.pipeline import read_log
from tests.test_api import (
    JUDGE,
    fake_stages,  # noqa: F401 -- autouse here too: the API suite's stand-in stages
    run_to,
    settings_for,
    upload_clip,
)
from tests.test_deploy import free_port

ROOT = Path(__file__).resolve().parent.parent
CODE = "scale-to-zero-judge-code"


# ---------------------------------------------------------------------------------------------- kill and restart


class LocalApi:
    """``uvicorn safecut.api.app:create_app`` in replay on one jobs folder, killable like a container."""

    def __init__(self, jobs: Path) -> None:
        self.jobs = jobs
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        env = {
            **os.environ,
            "SAFECUT_REPLAY": "1",
            "SAFECUT_JOBS_DIR": str(self.jobs),
            "SAFECUT_PUBLIC_URL": self.url,
            "SAFECUT_URL_SECRET": "s2z-url-key",
            "SAFECUT_ACCESS_CODES": json.dumps([{"code": CODE, "kind": "judge"}]),
            "SAFECUT_CODE_WINDOWS": json.dumps({"judge": [None, None]}),
            "SAFECUT_RATE_LIMIT_PER_MIN": "2000",
            "SAFECUT_PAID_ACTIONS_PER_HOUR": "200",
        }
        self.proc = subprocess.Popen(  # noqa: S603 -- fixed argv: this interpreter and uvicorn
            [sys.executable, "-m", "uvicorn", "--factory", "safecut.api.app:create_app", "--host", "127.0.0.1",
             "--port", str(self.port), "--log-level", "warning", "--no-proxy-headers"],
            env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/healthz", timeout=2).status_code == 200:
                    return
            except httpx.TransportError:
                time.sleep(0.2)
        raise AssertionError("the local API didn't start")

    def kill(self) -> None:
        """SIGKILL: no shutdown hook, no drain, nothing flushed, as when a container goes away."""
        assert self.proc is not None
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=10)

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)


@pytest.fixture
def local_api(tmp_path: Path) -> Iterator[LocalApi]:
    api = LocalApi(tmp_path / "jobs")
    yield api
    api.stop()


def state_of(api: LocalApi, job_id: str) -> dict[str, Any]:
    return json.loads((api.jobs / job_id / "state.json").read_text())


def wait_for(check: Callable[[], bool], what: str, timeout_s: float = 240) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def finished(api: LocalApi, job_id: str) -> set[str]:
    return {e["stage"] for e in read_log(api.jobs / job_id) if e.get("event") == "done"}


def started(api: LocalApi, job_id: str, stage: str) -> bool:
    return any(e.get("stage") == stage and e.get("event") == "start" for e in read_log(api.jobs / job_id))


def poll(api: LocalApi, job_id: str, status: str) -> dict[str, Any]:
    found: dict[str, Any] = {}

    def reached() -> bool:
        found.update(httpx.get(f"{api.url}/v1/jobs/{job_id}", timeout=10).json())
        assert found["status"] not in ("failed", "needs_you"), found
        return found["status"] == status

    wait_for(reached, f"{job_id} to reach {status}")
    return found


def test_a_job_finishes_when_its_container_is_killed_mid_analysis_and_mid_audit(local_api: LocalApi) -> None:
    manifest = json.loads((ROOT / "fixtures/jobs/demo/raw/manifest.json").read_text())
    clip = ROOT / manifest["source"]
    local_api.start()
    created = httpx.post(f"{local_api.url}/v1/jobs", json={"code": CODE, "size_bytes": clip.stat().st_size,
                         "content_type": "video/mp4", "file_name": "clip.mp4"}, timeout=10).json()  # fmt: skip
    job_id = created["job_id"]
    put = httpx.put(created["upload_url"], content=clip.read_bytes(), headers={"Content-Type": "video/mp4"}, timeout=30)
    assert put.status_code == 200, put.text
    assert httpx.post(f"{local_api.url}/v1/jobs/{job_id}/start", timeout=10).status_code == 202

    # Killed once tracking has finished and the scene pass is under way: the container goes, the job is stranded.
    wait_for(lambda: "track" in finished(local_api, job_id), "track to finish")
    local_api.kill()
    before = finished(local_api, job_id)
    assert state_of(local_api, job_id)["status"] == "processing"
    assert "guard" not in before

    local_api.start()  # the next input wakes a fresh container; its start resumes the job
    poll(local_api, job_id, "review")

    assert httpx.post(f"{local_api.url}/v1/jobs/{job_id}/render", timeout=10).status_code == 202
    wait_for(lambda: started(local_api, job_id, "audit"), "the audit to start")
    local_api.kill()
    assert "audit" not in finished(local_api, job_id)
    assert state_of(local_api, job_id)["status"] == "rendering"
    local_api.start()
    job = poll(local_api, job_id, "done")
    assert job["stage"] == "done"

    job_dir = local_api.jobs / job_id
    contracts.validate_job_dir(job_dir)  # the receipt's hash chain and every cross-file rule
    receipt = load(job_dir / "receipt.json", Receipt)
    assert receipt.audit.unresolved == 0
    # No stage that finished is ever run again: one `done` per stage, so no finished stage's calls repeat.
    done = Counter(e["stage"] for e in read_log(job_dir) if e.get("event") == "done")
    assert set(done.values()) == {1}, done
    assert {"prepare", "track", "guard", "render", "audit", "receipt"} <= done.keys()
    starts = Counter(e["stage"] for e in read_log(job_dir) if e.get("event") == "start")
    assert starts["track"] == 1  # finished before the first kill: never started again
    assert starts["audit"] == 2  # interrupted once, run again from its inputs


# ---------------------------------------------------------------------------------------------- the keep-alive


@pytest.fixture
def make_service(tmp_path: Path) -> Iterator[Callable[..., tuple[TestClient, Service]]]:
    """The API suite's service, on its stand-in stages (``tests.test_api.fake_stages``, autouse)."""
    from tests.test_api import recordings  # noqa: PLC0415 -- the API tests' fake recording

    made: list[TestClient] = []

    def make(keepalive: Callable[[str], None] | None = None, **overrides: Any) -> tuple[TestClient, Service]:
        fixtures = recordings(tmp_path) if not made else tmp_path / "fixtures" / "jobs"
        svc = Service(settings_for(tmp_path, **overrides), fixtures=fixtures, keepalive=keepalive)
        client = TestClient(create_app(service=svc, background=False))
        client.__enter__()
        made.append(client)
        return client, svc

    yield make
    for client in made:
        client.__exit__(None, None, None)


def test_every_queued_action_asks_to_keep_the_container_up(make_service: Callable[..., Any]) -> None:
    held: list[str] = []
    client, svc = make_service(keepalive=held.append)
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    run_to(client, svc, job_id, "render", "done")
    wait_for(lambda: len(held) == 2, "both keepalives", timeout_s=10)  # spawned from threads of their own
    assert held == [job_id, job_id]
    wait_for(lambda: svc.worker.keepalive_ok is True, "the keepalive's outcome", timeout_s=10)
    assert client.get("/healthz").json()["keepalive"] is True


def test_a_slow_keepalive_never_holds_up_the_request(make_service: Callable[..., Any]) -> None:
    release = threading.Event()
    client, svc = make_service(keepalive=lambda _job: release.wait(30))
    job_id = upload_clip(client)
    started = time.monotonic()
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    assert time.monotonic() - started < 5  # the platform's answer isn't awaited under the job's lock
    svc.worker.wait(job_id)
    release.set()


def test_a_job_that_keeps_taking_its_container_down_fails(make_service: Callable[..., Any]) -> None:
    """Each restart that finds the job mid-action counts; past MAX_RESUMES it fails instead of waking a new
    container every 15 minutes until the 24 h deletion."""
    client, svc = make_service()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    for _ in range(app_module.MAX_RESUMES):
        with svc.store.update(job_id) as state:
            state.status, state.stage, state.started_at = "processing", "track", datetime.now(UTC)
        assert svc.recover() == [job_id]
        svc.worker.wait(job_id)
    assert svc.store.get(job_id).resumes == 0  # each resumed run reached review, which resets the count
    with svc.store.update(job_id) as state:
        state.status, state.stage, state.resumes = "processing", "track", app_module.MAX_RESUMES
    assert svc.recover() == []
    failed = client.get(f"/v1/jobs/{job_id}").json()
    assert failed["status"] == "failed"
    assert failed["failure"]["reason"] == "internal"


def test_a_failing_keepalive_never_fails_the_request(make_service: Callable[..., Any]) -> None:
    def broken(job_id: str) -> None:
        raise ConnectionError(f"Modal unreachable for {job_id}")

    client, svc = make_service(keepalive=broken)
    assert client.get("/healthz").json()["keepalive"] is None  # none tried yet
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")  # 202, and the job still runs
    wait_for(lambda: svc.worker.keepalive_ok is False, "the keepalive's outcome", timeout_s=10)
    assert client.get("/healthz").json()["keepalive"] is False  # and a deploy check sees it


def test_hold_lasts_until_the_job_stops(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage]

    def slow(job: str, action: Any) -> None:
        gate.wait(10)
        real(job, action)

    svc.worker._run_action = slow  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in for the test, on purpose
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    result: list[str] = []
    holder = threading.Thread(target=lambda: result.append(svc.hold(job_id, poll_s=0.02)))
    holder.start()
    time.sleep(0.3)
    assert holder.is_alive()  # the job is still running: the input stays open
    gate.set()
    holder.join(30)
    assert result == ["review"]
    assert svc.hold("j_0000000000000000000000", poll_s=0.01) == "gone"


def test_hold_resumes_a_job_nothing_is_moving(make_service: Callable[..., Any]) -> None:
    """A container that went to sleep mid-job left it `processing` on the Volume; the cron's hold input wakes a new
    container whose worker isn't tracking it, and hold resumes it."""
    client, svc = make_service()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    with svc.store.update(job_id) as state:
        state.status, state.stage, state.started_at = "processing", "guard", datetime.now(UTC)
    assert svc.store.active() == [job_id]
    assert svc.hold(job_id, poll_s=0.01, limit_s=60) == "review"


def test_recover_never_runs_a_job_twice(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage]
    runs: list[str] = []

    def slow(job: str, action: Any) -> None:
        runs.append(action)
        gate.wait(10)
        real(job, action)

    svc.worker._run_action = slow  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in for the test, on purpose
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    time.sleep(0.1)
    assert svc.recover() == []  # tracked by this process: left alone
    gate.set()
    svc.worker.wait(job_id)
    assert runs == ["analyse"]


def test_a_stalled_job_fails_instead_of_holding_the_container_forever(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    with svc.store.update(job_id) as state:
        state.status, state.stage = "processing", "roles"
        state.started_at = datetime.now(UTC) - STALL_LIMIT - timedelta(minutes=1)
    assert svc.hold(job_id, poll_s=0.01, limit_s=60) == "failed"
    failed = client.get(f"/v1/jobs/{job_id}").json()
    assert failed["failure"]["reason"] == "internal"
    assert failed["failure"]["stage"] == "roles"  # failed by the stall rule where it stalled, never re-run
    assert "stalled" in svc.store.get(job_id).failure.detail  # type: ignore[union-attr] -- set by the stall rule
    assert not svc.worker.tracking(job_id)
    assert svc.store.active() == []


def test_hold_gives_up_at_its_limit(make_service: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    with svc.store.update(job_id) as state:
        state.status, state.stage, state.started_at = "retry_later", "scene", datetime.now(UTC)
    monkeypatch.setattr(svc.worker, "tracking", lambda _job: True)  # a re-queue timer that's still pending
    assert svc.hold(job_id, poll_s=0.01, limit_s=0.05) == "retry_later"
    assert app_module.HOLD_LIMIT_S < 60 * 60  # under the API function's timeout


def test_start_runs_once_whoever_calls_it(make_service: Callable[..., Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Modal's container start (``@modal.enter``) and the ASGI lifespan both call it: one recovery, one set of
    background loops."""
    _client, svc = make_service()
    calls: list[str] = []
    monkeypatch.setattr(svc, "recover", lambda: calls.append("recover") or [])
    monkeypatch.setattr(svc, "cleanup_loop", lambda: None)
    monkeypatch.setattr(svc, "build_demo_jobs", list)
    assert svc.start()
    assert not svc.start()
    with TestClient(create_app(service=svc)):
        pass
    assert calls == ["recover"]


def test_healthz_says_how_long_the_container_has_been_up(make_service: Callable[..., Any]) -> None:
    client, _svc = make_service(audit_gpu=True)
    body = client.get("/healthz").json()
    assert 0 <= body["uptime_s"] < 60
    assert body["audit_gpu"] is True


# ---------------------------------------------------------------------------------------------- state across a sleep


def test_the_paid_action_limit_survives_a_restart(tmp_path: Path) -> None:
    clock = [1_000.0]
    path = tmp_path / "ratelimit.sqlite"
    first = StoredRateLimiter(path, clock=lambda: clock[0])
    for _ in range(3):
        first.hit("paid", "203.0.113.5", limit=3, window_s=3600)
    first.close()
    restarted = StoredRateLimiter(path, clock=lambda: clock[0])  # a fresh container on the same Volume
    with pytest.raises(ApiRefusal) as refused:
        restarted.hit("paid", "203.0.113.5", limit=3, window_s=3600)
    assert refused.value.status == 429
    assert refused.value.retry_after_s == 3600
    restarted.hit("paid", "198.51.100.1", limit=3, window_s=3600)  # another client has its own window
    clock[0] += 3600
    restarted.hit("paid", "203.0.113.5", limit=3, window_s=3600)  # the hour passed


def test_a_corrupt_limit_store_is_moved_aside_never_taking_the_api_down(tmp_path: Path) -> None:
    path = tmp_path / "ratelimit.sqlite"
    path.write_bytes(b"not a database, left half-written by a container that died" * 50)
    limiter = StoredRateLimiter(path)
    limiter.hit("paid", "203.0.113.5", limit=1, window_s=3600)
    with pytest.raises(ApiRefusal):
        limiter.hit("paid", "203.0.113.5", limit=1, window_s=3600)
    assert [p.name for p in tmp_path.glob("ratelimit.sqlite.corrupt-*")]
    limiter.close()  # a store that fails mid-request counts that request in memory instead
    limiter.hit("paid", "198.51.100.1", limit=1, window_s=3600)
    with pytest.raises(ApiRefusal):
        limiter.hit("paid", "198.51.100.1", limit=1, window_s=3600)


def test_the_api_only_sleeps_after_a_quiet_spell_longer_than_the_per_minute_window() -> None:
    """In memory on purpose: the container only sleeps after API_SCALEDOWN_S with no input at all, longer than the
    60 s window, so by the time a restart forgets a window that window has already closed."""
    import ast  # noqa: PLC0415 -- imported in the test that uses it

    tree = ast.parse((ROOT / "deploy" / "modal_app.py").read_text())
    scaledown = next(
        ast.literal_eval(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "API_SCALEDOWN_S" for t in n.targets)
    )
    assert scaledown > 60


def test_the_per_minute_limit_is_in_memory(tmp_path: Path) -> None:
    svc = Service(settings_for(tmp_path))
    try:
        assert isinstance(svc.limiter, RateLimiter)
        assert isinstance(svc.paid_limiter, StoredRateLimiter)
    finally:
        svc.stop()


def test_a_restart_never_resets_the_paid_limit_through_the_api(make_service: Callable[..., Any]) -> None:
    client, _svc = make_service(paid_actions_per_hour=2)
    for _ in range(2):
        client.post("/v1/jobs/j_0000000000000000000000/start")
    restarted, _ = make_service(paid_actions_per_hour=2)  # same jobs folder: the Volume
    refused = restarted.post("/v1/jobs/j_0000000000000000000000/start")
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "rate_limited"


def test_the_daily_cap_holds_across_a_restart(make_service: Callable[..., Any]) -> None:
    _client, svc = make_service(daily_usd_cap=3.0)
    day = datetime.now(UTC).date().isoformat()
    svc.ledger.reserve("spent-before-sleep", None, 2.5, [CapLimit("daily", f"daily:{day}", 3.0)])
    _again, restarted = make_service(daily_usd_cap=3.0)
    grant = restarted.access.check_code(JUDGE)
    with pytest.raises(ApiRefusal) as refused:
        check_caps(restarted.settings, restarted.ledger, grant, estimate=1.12)
    assert refused.value.code == "daily_cap"


def test_active_lists_only_unpinned_jobs_mid_action(tmp_path: Path) -> None:
    store = JobStore(tmp_path, ttl=timedelta(hours=24), cleanup_every=timedelta(minutes=15))
    for status in ("created", "processing", "review", "rendering", "retry_later", "done", "failed", "needs_you"):
        job_id = store.create(mode="replay").job_id
        with store.update(job_id) as state:
            state.status = status  # type: ignore[assignment] -- every status in turn, on purpose
    pinned = store.create(mode="replay", job_id="j_demo000000000000000000", pinned=True).job_id
    with store.update(pinned) as state:
        state.status = "processing"
    assert sorted(store.get(j).status for j in store.active()) == ["processing", "rendering", "retry_later"]


# ---------------------------------------------------------------------------------------------- round-2 audit fixes


def test_the_container_stays_up_while_the_demo_job_builds(
    make_service: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building the demo isn't a job action: start() asks for a hold of its own, which lasts until the build ends."""
    held: list[str] = []
    _client, svc = make_service(keepalive=held.append)
    gate = threading.Event()
    monkeypatch.setattr(svc, "recover", list)
    monkeypatch.setattr(svc, "cleanup_loop", lambda: None)
    monkeypatch.setattr(svc, "build_demo_jobs", lambda: gate.wait(10) and [])
    svc.start()
    wait_for(lambda: held == [app_module.DEMO_HOLD], "the demo build's keepalive", timeout_s=10)
    result: list[str] = []
    holder = threading.Thread(target=lambda: result.append(svc.hold(app_module.DEMO_HOLD)))
    holder.start()
    time.sleep(0.2)
    assert holder.is_alive()
    gate.set()
    holder.join(10)
    assert result == ["built"]


def test_a_demo_the_gpu_couldnt_audit_is_rebuilt_but_not_on_every_wake(
    make_service: Callable[..., Any], tmp_path: Path
) -> None:
    from safecut.api.app import DEMO_GPU_RETRY, demo_stamp  # noqa: PLC0415 -- imported in the test that uses it
    from safecut.contracts import Audit, dump  # noqa: PLC0415 -- imported in the test that uses it

    recording = ROOT / "fixtures" / "jobs" / "demo"
    clip = ROOT / json.loads((recording / "raw" / "manifest.json").read_text())["source"]
    assert demo_stamp(recording, clip) != demo_stamp(recording, clip, audit_gpu=True)
    _client, svc = make_service(audit_gpu=True)
    job_id = svc.store.create(mode="replay", pinned=True).job_id
    audit = load(ROOT / "fixtures" / "contracts" / "j_example" / "audit.json", Audit)
    dump(audit.model_copy(update={"egoblur": audit.egoblur.model_copy(update={"device": "cpu"})}),
         svc.store.path(job_id) / "audit.json")  # fmt: skip
    fresh = svc.store.get(job_id)
    assert not svc._retry_gpu(job_id, fresh)  # pyright: ignore[reportPrivateUsage] -- built just now: kept
    old = fresh.model_copy(update={"created_at": fresh.created_at - DEMO_GPU_RETRY - timedelta(minutes=1)})
    assert svc._retry_gpu(job_id, old)  # pyright: ignore[reportPrivateUsage] -- YuNet, hours ago: try the GPU again
    on_gpu = audit.model_copy(update={"egoblur": audit.egoblur.model_copy(update={"device": "cuda:NVIDIA L4"})})
    dump(on_gpu, svc.store.path(job_id) / "audit.json")
    assert not svc._retry_gpu(job_id, old)  # pyright: ignore[reportPrivateUsage]


def test_a_restarted_job_starts_its_resume_count_afresh(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    with svc.store.update(job_id) as state:
        state.status, state.resumes = "failed", app_module.MAX_RESUMES
    run_to(client, svc, job_id, "start", "review")
    assert svc.store.get(job_id).resumes == 0


def test_a_locked_limit_store_counts_in_memory_without_moving_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3  # noqa: PLC0415 -- imported in the test that uses it

    path = tmp_path / "ratelimit.sqlite"
    StoredRateLimiter(path).hit("paid", "203.0.113.5", limit=5, window_s=3600)

    def locked(_path: Path) -> sqlite3.Connection:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(StoredRateLimiter, "_open", staticmethod(locked))
    limiter = StoredRateLimiter(path)
    limiter.hit("paid", "198.51.100.1", limit=1, window_s=3600)
    with pytest.raises(ApiRefusal):
        limiter.hit("paid", "198.51.100.1", limit=1, window_s=3600)
    assert not list(tmp_path.glob("*.corrupt-*"))  # a transient error never throws the hour's window away


def test_the_demo_builds_child_can_import_modal_as_this_process_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Modal client outside site-packages (the runtime's own mount) is named for the child, which appends it to
    the end of sys.path on first use: nothing there can shadow the standard library or the child's own packages."""
    import importlib.util  # noqa: PLC0415 -- imported in the test that uses it

    from safecut.audit import gpu  # noqa: PLC0415 -- imported in the test that uses it

    assert gpu.child_env({"PYTHONPATH": "/somewhere"}) == {"PYTHONPATH": "/somewhere"}  # this venv's modal: untouched
    mount = tmp_path / "pkg"
    (mount / "modal").mkdir(parents=True)
    (mount / "modal" / "__init__.py").write_text("MOUNTED = True\n")
    spec = importlib.util.spec_from_file_location("modal", mount / "modal" / "__init__.py")
    with monkeypatch.context() as patched:
        patched.setattr(importlib.util, "find_spec", lambda name: spec if name == "modal" else None)
        env = gpu.child_env({"PYTHONPATH": "/somewhere"})
    assert env == {"PYTHONPATH": "/somewhere", gpu.MODAL_PATH_ENV: str(mount.resolve())}  # never on PYTHONPATH
    # The child: modal isn't importable until the named folder is on sys.path, appended last.
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv(gpu.MODAL_PATH_ENV, str(mount.resolve()))
    sentinel = object()

    def importer(name: str) -> object:
        assert name == "modal"
        if str(mount.resolve()) not in sys.path:
            raise ModuleNotFoundError("No module named 'modal'")
        return sentinel

    monkeypatch.setattr(gpu.importlib, "import_module", importer)
    assert gpu._modal() is sentinel  # pyright: ignore[reportPrivateUsage] -- the loader under test
    assert sys.path[-1] == str(mount.resolve())  # last: the standard library and the child's packages win
    monkeypatch.delenv(gpu.MODAL_PATH_ENV)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(mount.resolve())])
    with pytest.raises(ModuleNotFoundError):
        gpu._modal()  # pyright: ignore[reportPrivateUsage] -- no folder named: the import error stands


def test_the_served_demo_stays_up_while_it_is_rebuilt_and_if_the_rebuild_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rebuild (a new deploy's code, a GPU retry) runs beside the served demo: /v1/demo keeps answering throughout,
    and a build that fails leaves the old demo in place."""
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    svc = Service(Settings(replay=True, jobs_dir=str(tmp_path / "jobs")))
    job_id = app_module.hero_job_id("demo")
    try:
        assert svc.build_demo_jobs() == ["demo"]
        with svc.store.update(job_id) as state:
            state.demo_stamp = "an older build"
        during: list[str] = []
        real = subprocess.run

        def failing(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            during.append(svc.store.get(job_id).status)  # what /v1/demo serves while the child runs
            return subprocess.CompletedProcess(args, 1, "", "the child failed")

        monkeypatch.setattr(app_module.subprocess, "run", failing)
        assert svc.build_demo_jobs() == []
        monkeypatch.setattr(app_module.subprocess, "run", real)
        assert during == ["done"]
        kept = svc.store.get(job_id)
        assert (kept.status, kept.demo_stamp) == ("done", "an older build")
        assert (svc.store.path(job_id) / "receipt.json").is_file()
        assert not (svc.store.root / app_module.BUILDING / job_id).exists()  # the scratch build is cleaned up
        assert svc.build_demo_jobs() == ["demo"]  # and the next good build replaces it
        assert svc.store.get(job_id).demo_stamp != "an older build"
        contracts.validate_job_dir(svc.store.path(job_id))
    finally:
        svc.stop()


def test_the_demo_job_builds_through_the_real_child_process(tmp_path: Path) -> None:
    """The demo is built by a ``safecut run --replay`` child with the environment ``child_env`` gives it: it must
    come up (an environment that broke the child's imports once took the demo away)."""
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    svc = Service(Settings(replay=True, jobs_dir=str(tmp_path / "jobs")))
    try:
        assert svc.build_demo_jobs() == ["demo"]
        state = svc.store.get(app_module.hero_job_id("demo"))
        assert (state.status, state.pinned, state.synthetic) == ("done", True, True)
    finally:
        svc.stop()


# ---------------------------------------------------------------------------------------------- round-4 audit fixes


def test_readers_never_see_the_demo_missing_while_it_is_swapped(tmp_path: Path) -> None:
    """A thread reads the demo's state as /v1/demo does, nonstop, through a full rebuild and swap: never a miss."""
    from safecut.api.store import JobNotFound  # noqa: PLC0415 -- imported in the test that uses it
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    svc = Service(Settings(replay=True, jobs_dir=str(tmp_path / "jobs")))
    job_id = app_module.hero_job_id("demo")
    try:
        assert svc.build_demo_jobs() == ["demo"]
        with svc.store.update(job_id) as state:
            state.demo_stamp = "an older build"
        misses, reads, stop = [0], [0], threading.Event()

        def reader() -> None:
            while not stop.is_set():
                try:
                    assert svc.store.get(job_id).status == "done"
                except JobNotFound:
                    misses[0] += 1
                reads[0] += 1

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            assert svc.build_demo_jobs() == ["demo"]
        finally:
            stop.set()
            thread.join(10)
        assert reads[0] > 1000
        assert misses[0] == 0
        assert svc.store.get(job_id).demo_stamp != "an older build"
    finally:
        svc.stop()


def test_a_swap_that_fails_halfway_puts_the_old_demo_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta as td  # noqa: PLC0415 -- imported in the test that uses it

    from safecut.api.store import BUILDING, JobStore  # noqa: PLC0415 -- imported in the test that uses it

    store = JobStore(tmp_path, ttl=td(hours=24), cleanup_every=td(minutes=15))
    job_id = store.create(mode="replay", pinned=True, demo_stamp="old").job_id
    (store.path(job_id) / "receipt.json").write_text("{}")
    built = tmp_path / BUILDING / job_id
    built.mkdir(parents=True)
    real = Path.rename

    def failing(self: Path, target: Path) -> Path:
        if self == built:
            raise OSError("the Volume refused the rename")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", failing)
    with pytest.raises(OSError, match="refused"):
        store.replace_pinned(job_id, built, demo_stamp="new")
    monkeypatch.setattr(Path, "rename", real)
    assert store.get(job_id).demo_stamp == "old"
    assert (store.path(job_id) / "receipt.json").is_file()


def test_the_sweep_removes_a_demo_build_a_dead_container_left(tmp_path: Path) -> None:
    from safecut.api.store import BUILD_GRACE, BUILDING, JobStore  # noqa: PLC0415 -- imported in the test that uses it

    store = JobStore(tmp_path, ttl=timedelta(hours=24), cleanup_every=timedelta(minutes=15))
    stale = tmp_path / BUILDING / "j_stale0000000000000000"
    fresh = tmp_path / BUILDING / "j_fresh0000000000000000"
    for folder in (stale, fresh):
        folder.mkdir(parents=True)
    old = time.time() - BUILD_GRACE.total_seconds() - 60
    os.utime(stale, (old, old))
    store.sweep()
    assert not stale.exists()
    assert fresh.exists()


def test_healthz_says_whether_this_containers_demo_is_built(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    body = client.get("/healthz").json()
    assert (body["demos_building"], body["demos_current"]) == (True, [])
    svc.demos_current.add("demo")
    svc._demo_built.set()  # pyright: ignore[reportPrivateUsage]
    body = client.get("/healthz").json()
    assert (body["demos_building"], body["demos_current"]) == (False, ["demo"])


def test_a_replaced_container_stops_without_waiting_for_its_jobs(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage]

    def slow(job: str, action: Any) -> None:
        gate.wait(20)
        real(job, action)

    svc.worker._run_action = slow  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in for the test, on purpose
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    started = time.monotonic()
    svc.stop(wait=False)
    assert time.monotonic() - started < 2  # the next container resumes the job; this one goes at once
    gate.set()


# ---------------------------------------------------------------------------------------------- round-5 audit fixes


def test_a_replaced_container_closes_its_app_without_waiting_for_a_running_job(tmp_path: Path) -> None:
    """Modal ends the ASGI lifespan (which stops the service) before ``@modal.exit``: with ``wait_on_stop=False``
    closing the app mid-job is bounded, and the job stays mid-action on the Volume for the next container."""
    from tests.test_api import recordings  # noqa: PLC0415 -- imported in the test that uses it

    svc = Service(settings_for(tmp_path), fixtures=recordings(tmp_path), wait_on_stop=False)
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage]

    def slow(job: str, action: Any) -> None:
        gate.wait(30)
        real(job, action)

    svc.worker._run_action = slow  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in for the test, on purpose
    client = TestClient(create_app(service=svc, background=False))
    client.__enter__()
    job_id = upload_clip(client)
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    started = time.monotonic()
    client.__exit__(None, None, None)  # the lifespan's shutdown, as Modal runs it
    assert time.monotonic() - started < 3
    assert svc.store.get(job_id).status == "processing"  # resumable by the next container's start
    gate.set()


def test_job_threads_never_keep_a_finished_interpreter_alive() -> None:
    """ThreadPoolExecutor's threads are joined at interpreter exit; the worker's are daemons, so a container whose
    service stopped exits at once, its running job left to the next container."""
    script = (
        "import threading, time\n"
        "from safecut.api.worker import DaemonPool\n"
        "pool = DaemonPool(2, name='job')\n"
        "pool.submit(time.sleep, 60)\n"
        "time.sleep(0.2)\n"
        "pool.shutdown(wait=False, cancel_futures=True)\n"
        "print('stopped', flush=True)\n"
    )
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30, check=False)  # noqa: S603 -- fixed argv: this interpreter and our own code
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "stopped"
    assert time.monotonic() - started < 15  # not the 60 s job


def test_the_daemon_pool_runs_cancels_and_reports_like_an_executor() -> None:
    from safecut.api.worker import DaemonPool  # noqa: PLC0415 -- imported in the test that uses it

    pool = DaemonPool(1, name="t")
    gate = threading.Event()

    def blocked() -> None:
        gate.wait(10)

    first = pool.submit(blocked)
    wait_for(first.running, "the first task to start", timeout_s=5)
    queued = pool.submit(time.sleep, 0)
    boom = ValueError("stage failed")

    def failing() -> None:
        raise boom

    def raising() -> None:
        failing()

    pool.shutdown(wait=False, cancel_futures=True)
    assert queued.cancelled()  # never started
    gate.set()
    assert first.result(5) is None
    with pytest.raises(RuntimeError, match="after shutdown"):
        pool.submit(raising)
    other = DaemonPool(1, name="u")
    failed = other.submit(raising)
    with pytest.raises(ValueError, match="stage failed"):
        failed.result(5)
    other.shutdown(wait=True)


def test_a_render_queued_after_a_long_review_is_resumed_not_failed_as_stalled(
    make_service: Callable[..., Any],
) -> None:
    """The stall clock runs from when an action is queued: a job reviewed for hours, then sent to render just before
    its container went away, is resumed by the next one."""
    client, svc = make_service()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    with svc.store.update(job_id) as state:
        state.started_at = datetime.now(UTC) - STALL_LIMIT - timedelta(hours=2)  # analysed long ago
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage]

    def held(job: str, action: Any) -> None:
        gate.wait(20)
        real(job, action)

    svc.worker._run_action = held  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in action
    assert client.post(f"/v1/jobs/{job_id}/render").status_code == 202
    assert datetime.now(UTC) - svc.store.get(job_id).started_at < timedelta(minutes=1)  # type: ignore[operator] -- set on queueing
    # The container goes before the render starts; the next one's recover resumes it rather than failing it.
    svc.worker.shutdown(wait=False)  # drops the queued render, as a container going away does
    gate.set()
    successor = Service(svc.settings, fixtures=svc.fixtures)
    try:
        assert successor.recover() == [job_id]
        successor.worker.wait(job_id)
        assert successor.store.get(job_id).status == "done"
    finally:
        successor.stop()


def test_queueing_an_audit_starts_its_stall_clock(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    run_to(client, svc, job_id, "render", "done")
    with svc.store.update(job_id) as state:  # the audit couldn't finish; the creator comes back hours later
        state.status = "needs_you"
        state.started_at = datetime.now(UTC) - STALL_LIMIT - timedelta(hours=2)
    assert client.post(f"/v1/jobs/{job_id}/audit").status_code == 202
    assert datetime.now(UTC) - svc.store.get(job_id).started_at < timedelta(minutes=1)  # type: ignore[operator] -- set on queueing
    svc.worker.wait(job_id)


# ---------------------------------------------------------------------------------------------- round-14 audit fixes


@pytest.mark.parametrize("audit_gpu", [False, True])
def test_the_up_front_cap_check_counts_the_gpu(make_service: Callable[..., Any], audit_gpu: bool) -> None:
    """Meta's $1.12 floor fits what is left; Meta's plus the GPU's worst case ($1.37) doesn't. A judge's start
    ($1.70 of a $3 day spent) and a pilot code's job creation ($4.70 of its $6 spent) are refused only with the GPU
    audit on."""
    from pydantic import SecretStr  # noqa: PLC0415 -- imported in the test that uses it

    from safecut.pipeline import code_id  # noqa: PLC0415 -- imported in the test that uses it
    from tests.test_api import PILOT, _spend  # noqa: PLC0415 -- the API suite's ledger helper and pilot code

    client, svc = make_service(replay=False, model_api_key=SecretStr("sk-test"), daily_usd_cap=3.0, audit_gpu=audit_gpu)
    job_id = upload_clip(client)
    _spend(svc, f"daily:{datetime.now(UTC).date().isoformat()}", 1.70)
    _spend(svc, f"code:{code_id(PILOT)}", 4.70, "code")
    body = {"code": PILOT, "size_bytes": 10, "content_type": "video/mp4", "file_name": "a.mp4"}
    created = client.post("/v1/jobs", json=body)
    started = client.post(f"/v1/jobs/{job_id}/start")
    if audit_gpu:
        assert (created.status_code, created.json()["error"]["code"]) == (429, "code_cap")
        assert (started.status_code, started.json()["error"]["code"]) == (429, "daily_cap")
    else:
        assert created.status_code == 201
        assert started.status_code == 202
        svc.worker.wait(job_id)


def test_a_re_queued_job_restarts_its_stall_clock(make_service: Callable[..., Any]) -> None:
    client, svc = make_service()
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    long_ago = datetime.now(UTC) - timedelta(minutes=30)
    with svc.store.update(job_id) as state:
        state.status, state.stage, state.started_at = "processing", "track", long_ago
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage] -- held so the re-queued state can be read

    def held(job: str, action: Any) -> None:
        gate.wait(20)
        real(job, action)

    svc.worker._run_action = held  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in action
    assert svc.recover() == [job_id]
    assert svc.store.get(job_id).started_at > long_ago + timedelta(minutes=29)  # type: ignore[operator] -- set on re-queue
    gate.set()
    svc.worker.wait(job_id)


def test_switching_the_gpu_audit_on_rebuilds_the_demo(tmp_path: Path) -> None:
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    built: list[bool] = []

    def make(audit_gpu: bool) -> Service:
        svc = Service(Settings(replay=True, jobs_dir=str(tmp_path / "jobs"), audit_gpu=audit_gpu))

        def precompute(job_id: str, recording: Path, clip: Path, stamp: str) -> None:
            del recording, clip
            built.append(audit_gpu)
            scratch = tmp_path / "scratch" / str(len(built)) / job_id
            scratch.mkdir(parents=True)
            svc.store.replace_pinned(job_id, scratch, demo_stamp=stamp)

        svc._precompute = precompute  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in build
        return svc

    for audit_gpu in (False, False, True):
        svc = make(audit_gpu)
        try:
            assert svc.build_demo_jobs() == ["demo"]
        finally:
            svc.stop()
    assert built == [False, True]  # reused while the setting stayed; rebuilt when the GPU audit was switched on


def test_the_stored_limit_uses_wall_clock_time(tmp_path: Path) -> None:
    """Monotonic clocks restart with each machine: a window kept across containers must be in wall time."""
    import sqlite3  # noqa: PLC0415 -- imported in the test that uses it

    path = tmp_path / "ratelimit.sqlite"
    StoredRateLimiter(path).hit("paid", "203.0.113.5", limit=5, window_s=3600)
    (at,) = sqlite3.connect(path).execute("SELECT at FROM hit").fetchone()
    assert abs(at - time.time()) < 60


# ---------------------------------------------------------------------------------------------- round-15 audit fixes


def test_a_keepalive_that_arrives_before_the_state_is_saved_still_holds(make_service: Callable[..., Any]) -> None:
    """The hold input can reach this container before the request that queued the job has saved "processing": it
    must still last until the job stops, never return on the stale "created"."""
    holds: list[str] = []
    started = threading.Event()
    client, svc = make_service(keepalive=lambda job: (started.set(), holds.append(svc.hold(job, poll_s=0.01))))
    job_id = upload_clip(client)
    gate = threading.Event()
    real = svc.worker._run_action  # pyright: ignore[reportPrivateUsage] -- held so the race window stays open

    def held(job: str, action: Any) -> None:
        gate.wait(20)
        real(job, action)

    svc.worker._run_action = held  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage] -- a stand-in action
    assert client.post(f"/v1/jobs/{job_id}/start").status_code == 202
    assert started.wait(10)
    time.sleep(0.3)
    assert holds == []  # still holding while the job is queued or running
    gate.set()
    wait_for(lambda: holds != [], "the hold to end", timeout_s=30)
    assert holds == ["review"]


# ---------------------------------------------------------------------------------------------- round-19 audit fixes


def test_the_documented_limits_hold_their_order() -> None:
    """The numbers the docs state, and the order the design needs: a stalled job fails (45 min) inside one hold input
    (55 min) inside the function's hour; a job that keeps dying fails on its fourth restart."""
    assert timedelta(minutes=45) == STALL_LIMIT
    assert STALL_LIMIT.total_seconds() < app_module.HOLD_LIMIT_S < 60 * 60
    assert app_module.MAX_RESUMES == 3


def test_a_re_queue_waiting_out_its_delay_also_holds_the_container(make_service: Callable[..., Any]) -> None:
    """A retry_later job a restart finds is re-queued after its delay on a timer, which isn't an input: the
    container is held up for it too, or it could sleep before the timer fires."""
    held: list[str] = []
    client, svc = make_service(keepalive=held.append)
    job_id = upload_clip(client)
    run_to(client, svc, job_id, "start", "review")
    with svc.store.update(job_id) as state:
        state.status, state.stage = "retry_later", "scene"
        state.retry_at = datetime.now(UTC) + timedelta(minutes=5)
        state.started_at = datetime.now(UTC)
    held.clear()
    assert svc.recover() == [job_id]
    wait_for(lambda: held == [job_id], "the re-queue's keepalive", timeout_s=10)
    assert svc.worker.tracking(job_id)  # the timer is pending
    svc.worker.cancel(job_id)


# ---------------------------------------------------------------------------------------------- round-21 audit fixes


@pytest.mark.parametrize(("failures", "ok"), [(0, True), (2, True), (3, False)])
def test_a_keepalive_is_retried_briefly_before_the_job_is_left_to_the_cron(failures: int, ok: bool) -> None:
    """One control-plane blip mustn't leave a running job without a hold: the spawn is tried three times, with short
    backoff, before the job is left to the cron."""
    from safecut.api import worker  # noqa: PLC0415 -- the private helper under test

    calls: list[str] = []
    slept: list[float] = []

    def flaky(job_id: str) -> None:
        calls.append(job_id)
        if len(calls) <= failures:
            raise ConnectionError("Modal control plane: 503")

    assert worker._spawn_hold(flaky, "j_1", sleep=slept.append) is ok  # pyright: ignore[reportPrivateUsage]
    assert calls == ["j_1"] * min(failures + 1, 3)
    assert slept == list(worker.HOLD_RETRY_DELAYS_S[: min(failures, 2)])
    assert sum(worker.HOLD_RETRY_DELAYS_S) < 5  # bounded: the job's thread never waits long on the platform


# ---------------------------------------------------------------------------------------------- round-22 audit fixes


def test_the_demo_hold_ends_when_the_container_is_replaced(
    make_service: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Like a job's hold, the demo build's hold returns once the service stops: a replaced container's input doesn't
    stay open until the build (or the hour) ends."""
    _client, svc = make_service(keepalive=lambda job_id: None)
    gate = threading.Event()
    monkeypatch.setattr(svc, "recover", list)
    monkeypatch.setattr(svc, "cleanup_loop", lambda: None)
    monkeypatch.setattr(svc, "build_demo_jobs", lambda: gate.wait(20) and [])
    svc.start()
    result: list[str] = []
    holder = threading.Thread(target=lambda: result.append(svc.hold(app_module.DEMO_HOLD, poll_s=0.05)))
    holder.start()
    time.sleep(0.2)
    assert holder.is_alive()  # the build is still running
    svc.stop(wait=False)
    holder.join(5)
    assert result == ["building"]
    gate.set()
