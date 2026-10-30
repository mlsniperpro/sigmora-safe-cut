"""E7: scripts/deploy-check.sh against a real local API (uvicorn, replay) and a stand-in web server, plus the
deploy files' shape. ``deploy/modal_app.py`` is checked by its syntax tree here, since the ``deploy`` dependency
group (Modal) isn't in the default install; ``scripts/entry-check.sh`` E7 imports it with every group installed."""

from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from safecut import pipeline
from safecut.api.app import hero_job_id
from safecut.api.store import JobStore
from safecut.stages import Stage
from tests.fake_stages import CLIP, fake_runner

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash") or "/bin/bash"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A local API in replay with a finished pinned demo job (built here with the stand-in stages)."""
    from datetime import timedelta  # noqa: PLC0415

    monkeypatch.setattr(Stage, "runner", fake_runner)
    jobs = tmp_path / "jobs"
    store = JobStore(jobs, ttl=timedelta(hours=24), cleanup_every=timedelta(minutes=15))
    job_id = hero_job_id("demo")
    store.create(mode="replay", job_id=job_id, pinned=True)
    job_dir = store.path(job_id)
    pipeline.create_job(CLIP, job_dir, mode="replay")
    pipeline.analyse(job_dir, replay=True)
    pipeline.approve(job_dir, how="auto_policy")
    pipeline.publish(job_dir, replay=True)
    with store.update(job_id) as state:
        state.status, state.synthetic = "done", True
    port = free_port()
    env = {
        **os.environ,
        "SAFECUT_JOBS_DIR": str(jobs),
        "SAFECUT_REPLAY": "1",
        "SAFECUT_URL_SECRET": "deploy-test",
        "SAFECUT_CORS_ORIGINS": json.dumps(["http://127.0.0.1:1"]),
    }
    proc = subprocess.Popen(  # noqa: S603 -- fixed argv: this interpreter and uvicorn
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "safecut.api.app:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
            "--no-proxy-headers",
        ],
        env=env,
        cwd=ROOT,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def web_server(csp: bool) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status = 200 if self.path in ("/", "/try", "/privacy") else 404
            self.send_response(status)
            if csp:
                self.send_header(
                    "Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'; object-src 'none'"
                )
                self.send_header("Strict-Transport-Security", "max-age=63072000")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>Safe Cut</title>")

        def log_message(self, format: str, *args: object) -> None:  # the base class's own parameter name
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def deploy_check(*args: str, replay_ok: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
    """The API under test runs in demo mode (no Meta key in tests), which the check accepts only when told to."""
    # The fixture's API has built its demo job before the check runs, so the cold-start wait stays short here.
    env = {k: v for k, v in os.environ.items() if k != "DEPLOY_REPLAY_OK"} | {"DEPLOY_DEMO_WAIT_S": "5"} | extra
    if replay_ok:
        env["DEPLOY_REPLAY_OK"] = "1"
    return subprocess.run(  # noqa: S603 -- fixed argv: bash and our script
        [BASH, str(ROOT / "scripts" / "deploy-check.sh"), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


@pytest.mark.entry("E7:deploy_check")
def test_deploy_check_passes_on_a_healthy_deployment(api: str) -> None:
    server, web = web_server(csp=True)
    try:
        # The API under test allows exactly the web origin passed here.
        proc = deploy_check(api, "-")
        assert proc.returncode == 0, proc.stdout
        assert proc.stdout.splitlines()[-1] == "DEPLOY: PASS"
        assert "the demo job 'demo' replays (synthetic: True)" in proc.stdout
        with_web = deploy_check(api, web)
        assert "FAIL  API: CORS preflight" in with_web.stdout  # this API allows another origin
        assert "ok    web /try: 200" in with_web.stdout
        assert "ok    web: CSP with frame-ancestors" in with_web.stdout
    finally:
        server.shutdown()


def test_deploy_check_fails_loudly(api: str) -> None:
    server, web = web_server(csp=False)
    try:
        proc = deploy_check(api, web, "no-such-hero")
        assert proc.returncode == 1
        assert "FAIL  API: /v1/demo/no-such-hero answered 404" in proc.stdout
        assert "FAIL  web: the landing page's CSP is missing" in proc.stdout
        assert proc.stdout.splitlines()[-1].startswith("DEPLOY: FAIL (")
    finally:
        server.shutdown()
    dead = deploy_check("http://127.0.0.1:9", "-")
    assert dead.returncode == 1
    assert "FAIL  API /healthz answered 000" in dead.stdout
    assert deploy_check().returncode == 2


def test_modal_app_defines_the_api_worker_volume_and_cron() -> None:
    tree = ast.parse((ROOT / "deploy" / "modal_app.py").read_text())
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"api", "cleanup", "pipeline_worker_smoke"} <= functions.keys()
    source = (ROOT / "deploy" / "modal_app.py").read_text()
    assert "@modal.asgi_app(" in source
    assert 'Volume.from_name("safecut-jobs"' in source
    assert "schedule=modal.Period(minutes=15)" in source
    assert "max_containers=1" in source  # one API container: in-process limits and ledger (module docstring)


def test_deploy_workflow_skips_without_secrets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "::notice title=Deploy skipped::" in workflow
    assert workflow.count("if: steps.gate.outputs.run == 'true'") >= 5
    assert "modal deploy deploy/modal_app.py" in workflow


def test_deploy_never_runs_a_forks_code_with_the_secrets() -> None:
    """`workflow_run`'s `branches: [main]` also matches a fork PR whose head branch is called main; the job must
    require a push to this repository's own main before the Modal secrets meet the checked-out code."""
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    block = workflow.split("\n    if: >-\n", 1)[1].split("\n    env:\n", 1)[0]
    condition = " ".join(block.split())
    for clause in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert clause in condition


def test_deploy_check_fails_a_deployment_judges_cant_use(api: str) -> None:
    """Demo mode, or no MODEL_API_KEY, means every judge upload fails: the check says so unless told it's fine."""
    result = deploy_check(api, "-", replay_ok=False)
    assert result.returncode != 0
    assert "isn't live with a Meta key (mode replay" in result.stdout


def test_deploy_check_accepts_a_live_api_with_its_key() -> None:
    """The passing branch, on a stub whose /healthz says what a judge-ready deployment says."""

    class Live(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"status": "ok", "mode": "live", "key": True, "meta": "ok"}).encode()
            self.send_response(200 if self.path == "/healthz" else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body if self.path == "/healthz" else b"{}")

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Live)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = deploy_check(
            f"http://127.0.0.1:{server.server_address[1]}", "-", replay_ok=False, DEPLOY_DEMO_WAIT_S="0"
        )
    finally:
        server.shutdown()
    assert "ok    API runs live, with MODEL_API_KEY set" in result.stdout
