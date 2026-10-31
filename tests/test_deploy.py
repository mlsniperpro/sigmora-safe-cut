"""E7: scripts/deploy-check.sh against a real local API (uvicorn, replay) and a stand-in web server, plus the
deploy files' shape. ``deploy/modal_app.py`` is checked by its syntax tree here, since the ``deploy`` dependency
group (Modal) isn't in the default install; ``scripts/entry-check.sh`` E7 imports it with every group installed."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from safecut import pipeline
from safecut.api.app import demo_stamp, hero_job_id
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
    recording = ROOT / "fixtures" / "jobs" / "demo"
    source = json.loads((recording / "raw" / "manifest.json").read_text())["source"]
    with store.update(job_id) as state:
        state.status, state.synthetic = "done", True
        # Built from the current recording and code, so the API serves it instead of rebuilding it at startup.
        state.demo_stamp = demo_stamp(recording, ROOT / source)
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
        url = f"http://127.0.0.1:{port}"
        # A healthy deployment has finished confirming its demo build (the stamp check hashes the package, slow on a
        # loaded machine): the check's own short wait then judges the deployment, not this machine's load.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if json.loads(urllib.request.urlopen(f"{url}/healthz", timeout=5).read())["demos_building"] is False:  # noqa: S310 -- our own local API
                    break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.2)
        yield url
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


def deploy_check(
    *args: str, replay_ok: bool = True, yunet_ok: bool = True, **extra: str
) -> subprocess.CompletedProcess[str]:
    """The API under test runs in demo mode (no Meta key in tests) and audits on CPU (no GPU here), which the check
    accepts only when told to."""
    # The fixture's API has built its demo job before the check runs, so the cold-start wait stays short here.
    flags = ("DEPLOY_REPLAY_OK", "DEPLOY_YUNET_OK", "DEPLOY_EXPECT_COLD")
    env = {k: v for k, v in os.environ.items() if k not in flags} | {"DEPLOY_DEMO_WAIT_S": "5"} | extra
    if replay_ok:
        env["DEPLOY_REPLAY_OK"] = "1"
    if yunet_ok:
        env["DEPLOY_YUNET_OK"] = "1"
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


MODAL_APP = ROOT / "deploy" / "modal_app.py"


def modal_tree() -> ast.Module:
    return ast.parse(MODAL_APP.read_text())


def constants(tree: ast.Module) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


def decorator_kwargs(node: ast.FunctionDef | ast.ClassDef, name: str, tree: ast.Module) -> dict[str, Any]:
    """The keyword arguments of ``@app.<name>(...)`` on ``node``, module constants resolved."""
    known = constants(tree)
    for deco in node.decorator_list:
        if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr == name:
            out: dict[str, Any] = {}
            for kw in deco.keywords:
                assert kw.arg is not None
                value = kw.value
                if isinstance(value, ast.Name) and value.id in known:
                    out[kw.arg] = known[value.id]
                else:
                    try:
                        out[kw.arg] = ast.literal_eval(value)
                    except ValueError:
                        out[kw.arg] = ast.unparse(value)
            return out
    raise AssertionError(f"{node.name} has no @app.{name}(...)")


def test_modal_app_defines_the_api_worker_volume_and_cron() -> None:
    tree = modal_tree()
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    assert {"cleanup", "egoblur_detect", "pipeline_worker_smoke", "ledger_smoke"} <= functions.keys()
    api = classes["SafeCutApi"]
    methods = {n.name: n for n in api.body if isinstance(n, ast.FunctionDef)}
    assert {"boot", "api", "hold", "shutdown"} <= methods.keys()
    decorators = {name: [ast.unparse(d) for d in m.decorator_list] for name, m in methods.items()}
    assert decorators["boot"] == ["modal.enter()"]
    assert decorators["api"] == ["modal.asgi_app(label='safecut-api')"]
    assert decorators["hold"] == ["modal.method()"]
    assert decorators["shutdown"] == ["modal.exit()"]
    source = MODAL_APP.read_text()
    assert 'Volume.from_name("safecut-jobs"' in source
    assert 'Volume.from_name("safecut-models"' in source
    assert "return create_app(service=self.service)" in source
    # Every queued action holds the container up; a replaced container never waits for its jobs.
    assert "Service(settings, keepalive=_keepalive, wait_on_stop=False)" in source


def test_the_api_scales_to_zero_and_never_scales_out_to_two_copies() -> None:
    tree = modal_tree()
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SafeCutApi")
    kwargs = decorator_kwargs(api, "cls", tree)
    assert kwargs["min_containers"] == 0  # sleeps when no one uses it
    assert kwargs["max_containers"] == 1  # one container: in-process limits, one SQLite ledger writer
    # Longer than the per-minute rate window (a sleep can't reset an open window) and than the web app's awake
    # window would need, short enough that an idle tail costs cents.
    assert 60 < kwargs["scaledown_window"] <= 600
    assert (kwargs["cpu"], kwargs["memory"]) == (1.0, 2048)
    assert kwargs["timeout"] == "60 * 60"
    concurrent = [ast.unparse(d) for d in api.decorator_list if "concurrent" in ast.unparse(d)]
    assert concurrent == ["modal.concurrent(max_inputs=64)"]  # hold inputs share the one container


def web_constant(path: str, name: str) -> int:
    source = (ROOT / "web" / "src" / "lib" / path).read_text()
    found = [line for line in source.splitlines() if line.startswith(f"export const {name} = ")]
    assert len(found) == 1, f"{name} not found once in {path}"
    return int(found[0].split("=", 1)[1].strip().rstrip(";").replace("_", ""))


def test_the_web_app_counts_the_api_awake_only_inside_its_scaledown_window() -> None:
    """The web app treats the API as awake for a while after an answer and only then uses the short timeout; that
    while must end before Modal can put the container to sleep, or a cold start would hit the short timeout."""
    tree = modal_tree()
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SafeCutApi")
    kwargs = decorator_kwargs(api, "cls", tree)
    scaledown_ms = kwargs["scaledown_window"] * 1000
    assert web_constant("wake.ts", "AWAKE_FOR_MS") < scaledown_ms
    assert web_constant("wake.ts", "WAKING_AFTER_MS") < web_constant("api.ts", "COLD_START_TIMEOUT_MS")
    assert web_constant("api.ts", "REQUEST_TIMEOUT_MS") < web_constant("api.ts", "COLD_START_TIMEOUT_MS")


def test_the_cron_runs_on_the_smallest_container_and_wakes_stranded_jobs() -> None:
    tree = modal_tree()
    cleanup = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cleanup")
    kwargs = decorator_kwargs(cleanup, "function", tree)
    assert (kwargs["cpu"], kwargs["memory"], kwargs["min_containers"]) == (0.125, 128, 0)
    assert kwargs["scaledown_window"] <= 2
    assert kwargs["schedule"] == "modal.Period(minutes=15)"
    body = ast.unparse(cleanup)
    assert "store.sweep()" in body
    assert "store.active()" in body
    assert "_api().hold.spawn(job_id)" in body


def test_egoblur_runs_on_a_gpu_function_with_the_weights_and_the_handoff_volume() -> None:
    tree = modal_tree()
    detect = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "egoblur_detect")
    kwargs = decorator_kwargs(detect, "function", tree)
    assert kwargs["gpu"] == ["L4", "T4"]
    assert kwargs["image"] == "gpu_image"
    # The render arrives on the handoff Volume: committing the jobs Volume from the API would reload it, which Modal
    # refuses while the API holds the ledger's SQLite files open there.
    assert kwargs["volumes"] == "{AUDIT: audit, '/models': models}"
    assert kwargs["min_containers"] == 0
    assert kwargs["max_containers"] == 4  # a burst of audits can't buy unbounded GPUs
    assert kwargs["scaledown_window"] <= 60
    assert "audit.reload()" in ast.unparse(detect)  # sees the render the API committed
    source = MODAL_APP.read_text()
    assert 'Volume.from_name("safecut-audit"' in source
    api = next(n for n in modal_tree().body if isinstance(n, ast.ClassDef) and n.name == "SafeCutApi")
    assert decorator_kwargs(api, "cls", modal_tree())["volumes"] == "{'/data': jobs, AUDIT: audit}"
    source = MODAL_APP.read_text()
    assert 'uv_sync(str(ROOT), groups=["audit"], frozen=True)' in source  # torch only in the GPU image
    api_image = source.split("gpu_image = (")[0].split("image = (", 1)[1]
    assert ".uv_sync(str(ROOT), frozen=True)" in api_image  # the API container stays slim: no audit group, no torch
    assert "groups=" not in api_image
    assert '"SAFECUT_AUDIT_GPU": "1"' in api_image


def test_the_gpu_price_matches_the_gpu_container() -> None:
    """``SAFECUT_AUDIT_GPU_USD_PER_HOUR`` prices the dearest GPU it may get (L4 $0.80/h) plus its cpu and memory at
    ``modal billing rates`` (CPU $0.0473 per core-hour, memory $0.008 per GiB-hour), and its idle tail matches."""
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    tree = modal_tree()
    detect = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "egoblur_detect")
    kwargs = decorator_kwargs(detect, "function", tree)
    hourly = 0.80 + kwargs["cpu"] * 0.0473 + kwargs["memory"] / 1024 * 0.008
    settings = Settings()
    assert settings.audit_gpu_usd_per_hour >= hourly
    assert settings.audit_gpu_usd_per_hour - hourly < 0.05
    assert settings.audit_gpu_idle_s == kwargs["scaledown_window"]


def test_deploy_workflow_skips_without_secrets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "::notice title=Deploy skipped::" in workflow
    assert workflow.count("if: steps.gate.outputs.run == 'true'") >= 5
    assert (
        "modal deploy --strategy recreate deploy/modal_app.py" in workflow
    )  # a deploy overlaps two for seconds at most


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


def test_the_image_ships_every_data_file_the_package_reads() -> None:
    """Modal's add_local_python_source keeps only .py files by default; the prompts and YuNet weights must ship."""
    from modal.file_pattern_matcher import FilePatternMatcher  # noqa: PLC0415 -- the deploy group's own matcher

    tree = ast.parse((ROOT / "deploy" / "modal_app.py").read_text())
    ignore = next(
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SOURCE_IGNORE" for t in node.targets)
    )
    assert "ignore=SOURCE_IGNORE" in (ROOT / "deploy" / "modal_app.py").read_text()
    matcher = FilePatternMatcher(*ignore)
    data = [p for p in (ROOT / "safecut").rglob("*") if p.is_file() and p.suffix not in (".py", ".pyc")]
    data = [p for p in data if "__pycache__" not in p.parts]
    assert any(p.suffix == ".txt" and "prompts" in p.parts for p in data)
    assert any(p.suffix == ".onnx" for p in data)
    dropped = [str(p.relative_to(ROOT)) for p in data if matcher(p.relative_to(ROOT / "safecut"))]
    assert dropped == []
    assert matcher(Path("scout/__pycache__/x.cpython-312.pyc"))


def health_stub(
    body: dict[str, object], delay_s: float = 0.0, demo: dict[str, object] | None = None
) -> tuple[ThreadingHTTPServer, str]:
    """A stand-in API whose /healthz answers ``body`` after ``delay_s`` (a container waking up), and whose demo job
    (when given) answers ``demo``."""
    pages = {"/healthz": body, **({"/v1/demo/demo": demo} if demo is not None else {})}

    class Health(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                time.sleep(delay_s)
            found = pages.get(self.path.split("?")[0])
            payload = json.dumps(found).encode() if found is not None else b"{}"
            self.send_response(200 if found is not None else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # the base class's own parameter name
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


LIVE = {"status": "ok", "mode": "live", "key": True, "meta": "ok", "audit_gpu": True, "demos_building": False,
        "demos_current": ["demo"], "keepalive": True}  # fmt: skip


@pytest.mark.parametrize(
    ("body", "delay_s", "expect_cold", "line"),
    [
        ({**LIVE, "uptime_s": 1.0}, 1.5, "1", "ok    API woke from a cold start: answered in"),
        ({**LIVE, "uptime_s": 900.0}, 0.0, "1", "FAIL  API was already up 900.0 s: no cold start right after"),
        ({**LIVE, "uptime_s": 900.0}, 0.0, "", "ok    API already awake (up 900.0 s)"),
        (LIVE, 0.0, "", "FAIL  API /healthz has no uptime_s"),
        ({**LIVE, "uptime_s": 1.0}, 0.0, "", "ok    API audits with EgoBlur on the GPU function"),
        ({**LIVE, "uptime_s": 1.0, "audit_gpu": False}, 0.0, "", "FAIL  API doesn't audit on the GPU"),
    ],
)
def test_deploy_check_proves_a_cold_wake_and_the_gpu_audit(
    body: dict[str, object], delay_s: float, expect_cold: str, line: str
) -> None:
    server, url = health_stub(body, delay_s)
    try:
        result = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0",
                              DEPLOY_EXPECT_COLD=expect_cold, SPOOF_N="1")  # fmt: skip
    finally:
        server.shutdown()
    assert line in result.stdout, result.stdout


def test_deploy_check_waits_out_a_cold_start_longer_than_its_other_requests() -> None:
    server, url = health_stub({**LIVE, "uptime_s": 0.5}, delay_s=3.0)
    try:
        slow = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0", SPOOF_N="1",
                            DEPLOY_WAKE_TIMEOUT_S="1")  # fmt: skip
        patient = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0", SPOOF_N="1")
    finally:
        server.shutdown()
    assert "FAIL  API /healthz answered 000" in slow.stdout
    assert "ok    API woke from a cold start" in patient.stdout


def test_the_smoke_checks_name_what_failed() -> None:
    from deploy.checks import ledger_problems, post_deploy_problems, pre_deploy_problems  # noqa: PLC0415 -- imported in the test that uses it

    ran = {"exit": 0, "unresolved": 0, "receipt": True, "redacted": True}
    probe = {"gpu": "NVIDIA L4", "refused": None, "detail": None, "frames": 360}
    assert pre_deploy_problems({**ran, "gpu_probe": probe}) == []
    assert pre_deploy_problems(ran) == ["the GPU function wasn't probed"]
    refused = pre_deploy_problems({**ran, "gpu_probe": {**probe, "refused": "altered_weights", "detail": "x"}})
    assert refused == ["the GPU function refused: altered_weights (x)"]
    assert "no GPU or no frames" in pre_deploy_problems({**ran, "gpu_probe": {**probe, "frames": 0}})[0]
    assert len(pre_deploy_problems({"exit": 1, "unresolved": 2, "receipt": False, "gpu_probe": probe})) == 3
    on_gpu = {**ran, "auditor": "egoblur-gen2", "auditor_device": "cuda:NVIDIA L4"}
    assert post_deploy_problems(on_gpu) == []
    fell_back = post_deploy_problems({**ran, "auditor": "yunet-face", "auditor_device": "cpu"})
    assert len(fell_back) == 2
    assert "not egoblur-gen2" in fell_back[0]
    assert "not a named GPU" in fell_back[1]
    assert ledger_problems({"ok": True}) == []
    assert ledger_problems({"ok": False, "error": "x"})


def test_the_deploy_workflow_proves_the_gpu_audit_and_a_cold_wake_after_deploying() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    steps = workflow.split("    steps:\n", 1)[1]
    smoke, deploy, verify, urls = (
        steps.index("uv run modal run deploy/modal_app.py"),
        steps.index("uv run modal deploy --strategy recreate deploy/modal_app.py"),
        steps.index("uv run python -m deploy.verify_deploy"),
        steps.index("bash scripts/deploy-check.sh"),
    )
    assert smoke < deploy < verify < urls
    assert 'DEPLOY_EXPECT_COLD: "1"' in workflow
    assert "SAFECUT_DEPLOY_AUDIT" not in workflow  # torch never goes into the API image
    assert workflow.count("if: steps.gate.outputs.run == 'true'") >= 6


def test_the_cost_tables_match_the_code_and_the_containers() -> None:
    """Every copy of the cost table is what ``python -m deploy.costs`` prints, and its sizes are the deployed ones."""
    from deploy import costs  # noqa: PLC0415 -- imported in the test that uses it

    table = costs.table()
    for doc in ("docs/DEPLOY-COSTS.md", "docs/SUBMISSION.md", "web/README.md"):
        assert f"```text\n{table}\n```" in (ROOT / doc).read_text(), doc
    tree = modal_tree()
    known = constants(tree)
    api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SafeCutApi")
    by_name = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    api_kw = decorator_kwargs(api, "cls", tree)
    cron_kw = decorator_kwargs(by_name["cleanup"], "function", tree)
    gpu_kw = decorator_kwargs(by_name["egoblur_detect"], "function", tree)
    assert (api_kw["cpu"], api_kw["memory"], known["API_SCALEDOWN_S"]) == (
        costs.API_CPU,
        costs.API_GIB * 1024,
        costs.API_SCALEDOWN_S,
    )
    assert (cron_kw["cpu"], cron_kw["memory"], cron_kw["scaledown_window"]) == (
        costs.CRON_CPU,
        costs.CRON_GIB * 1024,
        costs.CRON_SCALEDOWN_S,
    )
    assert (gpu_kw["cpu"], gpu_kw["memory"], known["GPU_SCALEDOWN_S"]) == (
        costs.GPU_CPU,
        costs.GPU_GIB * 1024,
        costs.GPU_SCALEDOWN_S,
    )
    # The ledger's per-job GPU reservation (safecut/api/access.py) is the table's worst case.
    from safecut.api.access import GPU_SCANS_PER_JOB  # noqa: PLC0415 -- imported in the test that uses it
    from safecut.config import Settings  # noqa: PLC0415 -- imported in the test that uses it

    settings = Settings()
    assert GPU_SCANS_PER_JOB * settings.audit_gpu_timeout_s + settings.audit_gpu_idle_s == costs.JOB_GPU_WORST_S
    assert costs.hourly(costs.GPU_CPU, costs.GPU_GIB, "L4") <= settings.audit_gpu_usd_per_hour


@pytest.mark.parametrize(
    ("egoblur", "line"),
    [
        ({"model": "egoblur-gen2", "faces": 0, "plates": 0, "device": "cuda:NVIDIA L4"},
         "ok    API: the demo job, built in the API container, was audited by egoblur-gen2 on cuda:NVIDIA L4"),
        ({"model": "yunet-face", "faces": 0, "plates": None, "device": "cpu"},
         "FAIL  API: the demo job was audited by yunet-face on cpu, not EgoBlur on a GPU"),
        ({"model": "egoblur-gen2", "faces": 0, "plates": 0},
         "FAIL  API: the demo job was audited by egoblur-gen2 on an unnamed device"),
    ],
)  # fmt: skip
def test_deploy_check_proves_the_api_containers_own_gpu_path(egoblur: dict[str, object], line: str) -> None:
    """The demo job is built inside the API container at startup, through the same handoff and GPU function as a
    judge's job: its audit is the post-deploy proof that path works there, not just in a smoke container."""
    demo = {"mode": "replay", "synthetic": True, "video_url": "/nowhere.mp4", "audit": {"egoblur": egoblur}}
    server, url = health_stub({**LIVE, "uptime_s": 1.0}, demo=demo)
    try:
        result = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0", SPOOF_N="1")
    finally:
        server.shutdown()
    assert line in result.stdout, result.stdout


def test_the_gpu_optional_switch_reaches_every_gpu_check() -> None:
    """One repository variable, for a hotfix during a GPU outage: the pre-deploy probe, the post-deploy job and the
    URL check's demo audit all warn instead of failing; nothing else is relaxed."""
    from deploy.checks import post_deploy_problems, pre_deploy_problems  # noqa: PLC0415 -- imported in the test that uses it

    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "SAFECUT_DEPLOY_GPU_OPTIONAL: ${{ vars.SAFECUT_DEPLOY_GPU_OPTIONAL }}" in workflow
    assert "DEPLOY_YUNET_OK: ${{ vars.SAFECUT_DEPLOY_GPU_OPTIONAL }}" in workflow
    assert 'os.environ.get("SAFECUT_DEPLOY_GPU_OPTIONAL")' in (ROOT / "deploy" / "verify_deploy.py").read_text()
    assert 'os.environ.get("SAFECUT_DEPLOY_GPU_OPTIONAL")' in MODAL_APP.read_text()
    ran = {"exit": 0, "unresolved": 0, "receipt": True, "redacted": True}
    yunet = {**ran, "auditor": "yunet-face", "auditor_device": "cpu", "gpu_fallback": "timeout: x"}
    assert len(post_deploy_problems(yunet)) == 3
    assert post_deploy_problems(yunet, gpu_required=False) == []
    assert pre_deploy_problems(ran, gpu_required=False) == []
    broken = {**yunet, "exit": 1}
    assert post_deploy_problems(broken, gpu_required=False)  # a job that didn't run still fails the deploy
    assert "SAFECUT_DEPLOY_GPU_OPTIONAL" in (ROOT / "BLOCKED.md").read_text()


@pytest.mark.parametrize(
    ("health", "line"),
    [
        ({"demos_building": False, "demos_current": ["demo"]},
         "ok    API: the demo 'demo' was built (or confirmed) by this deploy's code"),
        ({"demos_building": False, "demos_current": []},
         "FAIL  API: this deploy's code didn't build the demo 'demo' (the one served, if any, is an earlier deploy's)"),
        ({"demos_building": True, "demos_current": []}, "FAIL  API: the demo build didn't finish within 0 s"),
    ],
)  # fmt: skip
def test_deploy_check_judges_this_deploys_demo_never_an_earlier_one(health: dict[str, object], line: str) -> None:
    """A redeploy keeps serving the previous demo while it builds its own: the check waits for this code's build, and a
    demo only an earlier deploy built never passes it."""
    egoblur = {"model": "egoblur-gen2", "faces": 0, "plates": 0, "device": "cuda:NVIDIA L4"}
    demo = {"mode": "replay", "synthetic": True, "video_url": "/nowhere.mp4", "audit": {"egoblur": egoblur}}
    server, url = health_stub({**LIVE, "uptime_s": 1.0, **health}, demo=demo)
    try:
        result = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0", SPOOF_N="1")
    finally:
        server.shutdown()
    assert line in result.stdout, result.stdout


class _Call:
    def __init__(self, answer: dict[str, object] | Exception) -> None:
        self.answer = answer
        self.cancelled: list[bool] = []

    def get(self, timeout: float) -> dict[str, object]:
        del timeout
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def cancel(self, terminate_containers: bool = False) -> None:
        self.cancelled.append(terminate_containers)


@pytest.mark.parametrize(
    ("put_fails", "spawn", "expected"),
    [
        (False, {"gpu": "NVIDIA L4", "frames": {"0": []}}, {"gpu": "NVIDIA L4", "refused": None, "frames": 1}),
        (True, None, {"refused": "error"}),
        (False, RuntimeError("the function isn't deployed"), {"refused": "error"}),
        (False, TimeoutError("no output"), {"refused": "timeout"}),
        (False, {"refused": "no_gpu", "detail": "no CUDA device"}, {"refused": "no_gpu"}),
    ],
)
def test_the_pre_deploy_probe_reports_every_gpu_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, put_fails: bool, spawn: object, expected: dict[str, object]
) -> None:
    """Every way the GPU probe can fail becomes a probe record (so SAFECUT_DEPLOY_GPU_OPTIONAL can waive it), never a
    crash of the smoke; a call it gives up on is cancelled with its container."""
    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    (tmp_path / "job.json").write_text(json.dumps({"frames": 1}))
    calls: list[_Call] = []

    class Handoff:
        def put(self, out: Path, sha: str) -> str:
            del out, sha
            if put_fails:
                raise RuntimeError("there are open files preventing the operation")
            return "smoke-0123456789abcdef"

    def spawner(request: dict[str, object]) -> _Call:
        del request
        if isinstance(spawn, RuntimeError):
            raise spawn
        call = _Call(spawn if isinstance(spawn, (dict, Exception)) else {})
        calls.append(call)
        return call

    monkeypatch.setattr(modal_app, "egoblur_detect", type("Fn", (), {"spawn": staticmethod(spawner)}))
    probe = modal_app._probe_gpu(Handoff(), tmp_path, "0" * 64)  # pyright: ignore[reportPrivateUsage] -- the unit under test
    assert {k: probe[k] for k in expected} == expected
    if expected.get("refused") in ("timeout", "no_gpu"):
        assert calls[0].cancelled == [True]


@pytest.mark.parametrize(
    ("keepalive", "expect_cold", "line"),
    [
        (True, "1", "ok    API: its keepalive reached Modal"),
        (False, "", "FAIL  API: its keepalive failed (SafeCutApi.hold.spawn)"),
        (None, "1", "FAIL  API: no keepalive was tried after the cold start"),
        (None, "", "ok    API: no keepalive tried"),
    ],
)
def test_deploy_check_proves_the_keepalive_reaches_modal(keepalive: bool | None, expect_cold: str, line: str) -> None:
    """The call that keeps a started job's container up is the same one every start makes for the demo build: a real
    deploy proves it reached Modal."""
    server, url = health_stub({**LIVE, "uptime_s": 1.0, "keepalive": keepalive})
    try:
        result = deploy_check(url, "-", replay_ok=False, yunet_ok=False, DEPLOY_DEMO_WAIT_S="0", SPOOF_N="1",
                              DEPLOY_EXPECT_COLD=expect_cold)  # fmt: skip
    finally:
        server.shutdown()
    assert line in result.stdout, result.stdout


def test_deploy_check_waits_for_the_keepalives_outcome_after_a_cold_wake() -> None:
    """The keepalive runs on its own thread after the container starts: the first /healthz may say null. The check
    waits for the outcome instead of failing a healthy deploy."""
    # null (the spawn hasn't answered), then a gateway error between polls, then the outcome.
    answers: list[dict[str, object] | None] = [{**LIVE, "uptime_s": 1.0, "keepalive": None}, None,
                                               {**LIVE, "uptime_s": 3.0, "keepalive": True}]  # fmt: skip

    class Waking(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/healthz":
                self.send_response(404)
                self.end_headers()
                return
            body = answers.pop(0) if len(answers) > 1 else answers[0]
            self.send_response(200 if body is not None else 503)
            self.send_header("Content-Type", "application/json" if body is not None else "text/plain")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode() if body is not None else b"upstream connect error")

        def log_message(self, format: str, *args: object) -> None:  # the base class's own parameter name
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Waking)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = deploy_check(f"http://127.0.0.1:{server.server_address[1]}", "-", replay_ok=False, yunet_ok=False,
                              DEPLOY_DEMO_WAIT_S="30", SPOOF_N="1", DEPLOY_EXPECT_COLD="1")  # fmt: skip
    finally:
        server.shutdown()
    assert "ok    API: its keepalive reached Modal" in result.stdout, result.stdout
    assert "no keepalive was tried" not in result.stdout


# ---------------------------------------------------------------------------------------------- the Modal glue, run


def _method(name: str) -> Any:
    """A ``SafeCutApi`` method's own function (modal 1.6.2 wraps each in a PartialFunction)."""
    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    return vars(modal_app.SafeCutApi._get_user_cls())[name]._get_raw_f()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType] -- modal 1.6.2's own accessors


def test_the_hold_input_lasts_as_long_as_the_services_hold() -> None:
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    asked: list[str] = []
    api = SimpleNamespace(service=SimpleNamespace(hold=lambda job_id: asked.append(job_id) or "review"))
    assert _method("hold")(api, "j_1") == "review"
    assert asked == ["j_1"]
    stopped: list[bool] = []
    _method("shutdown")(SimpleNamespace(service=SimpleNamespace(stop=lambda *, wait: stopped.append(wait))))
    assert stopped == [False]  # a replaced container never waits for its jobs


def test_boot_refuses_weak_secrets_and_otherwise_starts_a_held_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    import safecut.api.app as api_app  # noqa: PLC0415 -- patched where boot imports from
    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    made: list[dict[str, Any]] = []

    class FakeService:
        def __init__(self, settings: Any, **kwargs: Any) -> None:
            del settings
            made.append(kwargs)

        def start(self) -> bool:
            made.append({"started": True})
            return True

    monkeypatch.setattr(api_app, "Service", FakeService)
    monkeypatch.setattr(api_app, "production_problems", lambda settings: ["SAFECUT_URL_SECRET is unset"])
    api = SimpleNamespace()
    with pytest.raises(RuntimeError, match="isn't fit for production"):
        _method("boot")(api)
    assert made == []  # nothing served on weak secrets
    monkeypatch.setattr(api_app, "production_problems", lambda settings: [])
    _method("boot")(api)
    assert made == [{"keepalive": modal_app._keepalive, "wait_on_stop": False}, {"started": True}]  # pyright: ignore[reportPrivateUsage] -- the hook under test
    assert isinstance(api.service, FakeService)  # kept on the instance: hold, api and shutdown all use it
    held: list[str] = []
    api.service.hold = lambda job_id: held.append(job_id) or "done"  # type: ignore[attr-defined] -- the booted service, extended for the check
    assert _method("hold")(api, "j_2") == "done"
    assert held == ["j_2"]


def test_the_keepalive_spawns_this_containers_hold_inside_the_modal_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager  # noqa: PLC0415 -- a recording permit, local to this test
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used
    from safecut.audit import gpu  # noqa: PLC0415 -- patched where the keepalive imports from

    inside: list[bool] = []
    spawned: list[tuple[str, bool]] = []

    @contextmanager
    def permit() -> Any:
        inside.append(True)
        yield
        inside.pop()

    monkeypatch.setattr(gpu, "modal_permitted", permit)
    monkeypatch.setattr(modal_app, "_api", lambda: SimpleNamespace(
        hold=SimpleNamespace(spawn=lambda job_id: spawned.append((job_id, bool(inside))))))  # fmt: skip
    modal_app._keepalive("j_1")  # pyright: ignore[reportPrivateUsage] -- the hook under test
    assert spawned == [("j_1", True)]


def test_the_cron_sweeps_jobs_and_handoffs_commits_and_wakes_jobs_mid_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta  # noqa: PLC0415 -- imported in the test that uses it
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    calls: list[str] = []

    def volume(name: str) -> Any:
        return SimpleNamespace(reload=lambda: calls.append(f"{name}.reload"),
                               commit=lambda: calls.append(f"{name}.commit"))  # fmt: skip

    jobs_dir, handoff = tmp_path / "jobs", tmp_path / "audit"
    store = JobStore(jobs_dir, ttl=timedelta(hours=24), cleanup_every=timedelta(minutes=15))
    active = store.create(mode="replay").job_id
    with store.update(active) as state:
        state.status = "processing"
    old = handoff / "j_gone-0123456789abcdef"
    old.mkdir(parents=True)
    os.utime(old, (1_000, 1_000))
    woken: list[str] = []
    monkeypatch.setenv("SAFECUT_JOBS_DIR", str(jobs_dir))
    monkeypatch.setattr(modal_app, "jobs", volume("jobs"))
    monkeypatch.setattr(modal_app, "audit", volume("audit"))
    monkeypatch.setattr(modal_app, "AUDIT", str(handoff))
    monkeypatch.setattr(modal_app, "_api", lambda: SimpleNamespace(hold=SimpleNamespace(spawn=woken.append)))
    result = modal_app.cleanup._raw_f_()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType] -- modal 1.6.2's raw function
    assert result == {"removed": [], "handoffs": [old.name], "resumed": [active]}
    assert not old.exists()
    assert woken == [active]
    assert calls == ["jobs.reload", "jobs.commit", "audit.reload", "audit.commit"]


def test_the_gpu_function_reloads_the_handoff_then_serves_from_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """egoblur_detect: the Volume is reloaded before every request, and one GpuServer per container reads renders from
    the handoff mount with the weights from the models mount."""
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used
    from safecut.audit import gpu  # noqa: PLC0415 -- patched where the function imports from

    events: list[object] = []

    class FakeServer:
        def __init__(self, root: Path, weights: Path) -> None:
            events.append(("server", root, weights))

        def serve(self, request: dict[str, Any]) -> dict[str, Any]:
            events.append(("serve", request["job"]))
            return {"gpu": "NVIDIA L4"}

    monkeypatch.setattr(gpu, "GpuServer", FakeServer)
    monkeypatch.setattr(modal_app, "audit", SimpleNamespace(reload=lambda: events.append("reload")))
    monkeypatch.setattr(modal_app, "_server", None)
    raw = modal_app.egoblur_detect._raw_f_  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType] -- modal 1.6.2's raw function
    assert raw({"job": "a"}) == {"gpu": "NVIDIA L4"}
    raw({"job": "b"})
    assert events == ["reload", ("server", Path(modal_app.AUDIT), Path(modal_app.WEIGHTS)), ("serve", "a"),
                      "reload", ("serve", "b")]  # fmt: skip


def test_the_ledger_smoke_proves_the_ledger_and_the_limiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    monkeypatch.setattr(modal_app, "JOBS", str(tmp_path))
    result = modal_app.ledger_smoke._raw_f_()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType] -- modal 1.6.2's raw function
    assert result == {"ok": True, "spent": pytest.approx(0.2), "limiter_remembers": True}
    assert list(tmp_path.iterdir()) == []  # it cleans up after itself on the Volume


def test_the_api_imports_nothing_heavy() -> None:
    """Cold start (the brief): importing the API leaves scipy, torch and Modal to the code that needs them."""
    script = "import sys, safecut.api.app; print(sorted(m for m in ('scipy', 'torch', 'modal') if m in sys.modules))"
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=False)  # noqa: S603 -- fixed argv: this interpreter and our own code
    assert proc.returncode == 0, proc.stderr[-500:]
    assert proc.stdout.strip() == "[]"


# ---------------------------------------------------------------------------------------------- round-24 audit fixes


@pytest.mark.parametrize(
    ("result", "optional", "code"),
    [
        ({"auditor": "egoblur-gen2", "auditor_device": "cuda:NVIDIA L4"}, None, 0),
        ({"auditor": "yunet-face", "auditor_device": "cpu", "gpu_fallback": "timeout: x"}, None, 1),
        ({"auditor": "yunet-face", "auditor_device": "cpu", "gpu_fallback": "timeout: x"}, "1", 0),
        ({"auditor": "egoblur-gen2", "auditor_device": "cuda:NVIDIA L4", "exit": 1}, "1", 1),
    ],
)
def test_the_post_deploy_check_runs_the_deployed_job_with_the_gpu_audit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], result: dict[str, Any], optional: str | None,
    code: int,
) -> None:  # fmt: skip
    """``deploy.verify_deploy`` itself: it calls the deployed smoke with ``audit_gpu=True``, and its exit code is the
    checks' verdict (a job that didn't run fails even with the GPU-optional switch)."""
    import modal  # noqa: PLC0415 -- the deploy group, imported where it is used

    from deploy import verify_deploy  # noqa: PLC0415 -- the deploy group, imported where it is used

    calls: list[tuple[str, str, dict[str, object]]] = []
    answer = {"exit": 0, "unresolved": 0, "receipt": True, "redacted": True, **result}

    class Smoke:
        def __init__(self, app: str, name: str) -> None:
            self.where = (app, name)

        def remote(self, **kwargs: object) -> dict[str, Any]:
            calls.append((*self.where, kwargs))
            return answer

    monkeypatch.setattr(modal.Function, "from_name", Smoke)
    if optional is None:
        monkeypatch.delenv("SAFECUT_DEPLOY_GPU_OPTIONAL", raising=False)
    else:
        monkeypatch.setenv("SAFECUT_DEPLOY_GPU_OPTIONAL", optional)
    assert verify_deploy.main() == code
    assert calls == [("safecut", "pipeline_worker_smoke", {"audit_gpu": True})]
    out = capsys.readouterr().out
    assert ("FAIL" in out) is (code == 1)
    if code == 0 and result["auditor"] == "egoblur-gen2":
        assert "audited by egoblur-gen2 on cuda:NVIDIA L4" in out


# ---------------------------------------------------------------------------------------------- round-26 audit fixes


HEALTHY_SMOKE = {"exit": 0, "unresolved": 0, "receipt": True, "redacted": True,
                 "gpu_probe": {"refused": None, "gpu": "NVIDIA L4", "frames": 3}}  # fmt: skip


@pytest.mark.parametrize(
    "case",
    [
        ({}, {"ok": True}, None, False),
        ({}, {"ok": False, "error": "OperationalError: disk I/O error"}, None, True),
        ({"gpu_probe": {"refused": "no_weights", "detail": "missing"}}, {"ok": True}, None, True),
        ({"gpu_probe": {"refused": "no_weights", "detail": "missing"}}, {"ok": True}, "1", False),
        ({"exit": 1, "tail": "Traceback"}, {"ok": True}, "1", True),
        ({}, {"ok": False, "error": "x"}, "1", True),
    ],
)
def test_the_pre_deploy_smoke_blocks_the_deploy_on_any_problem(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: tuple[dict[str, Any], dict[str, Any], str | None, bool],
) -> None:
    """``modal run deploy/modal_app.py`` itself (the workflow's gate before ``modal deploy``): the worker smoke runs
    without the deployed GPU path, the ledger smoke runs too, and any problem raises; the GPU-optional switch only
    turns a GPU problem into a warning."""
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used

    worker, ledger, optional, blocks = case
    asked: list[tuple[str, dict[str, object]]] = []

    def stand_in(name: str, answer: dict[str, Any]) -> Any:
        def remote(**kwargs: object) -> dict[str, Any]:
            asked.append((name, kwargs))
            return answer

        return SimpleNamespace(remote=remote)

    monkeypatch.setattr(modal_app, "pipeline_worker_smoke", stand_in("worker", {**HEALTHY_SMOKE, **worker}))
    monkeypatch.setattr(modal_app, "ledger_smoke", stand_in("ledger", ledger))
    if optional is None:
        monkeypatch.delenv("SAFECUT_DEPLOY_GPU_OPTIONAL", raising=False)
    else:
        monkeypatch.setenv("SAFECUT_DEPLOY_GPU_OPTIONAL", optional)
    smoke = modal_app.smoke.info.raw_f
    assert smoke is not None
    if blocks:
        with pytest.raises(SystemExit, match="smoke run failed"):
            smoke()
    else:
        assert smoke() is None
    assert asked == [("worker", {}), ("ledger", {})]  # before a deploy: this image's own GPU function is probed
    warned = "::warning title=GPU auditor::" in capsys.readouterr().out
    assert warned is (optional == "1" and "gpu_probe" in worker)


@pytest.mark.parametrize("audit_gpu", [False, True])
def test_the_worker_smoke_reaches_the_deployed_gpu_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, audit_gpu: bool
) -> None:
    """``pipeline_worker_smoke`` runs ``safecut run`` in replay with its own ledger, and the GPU audit on exactly when
    the post-deploy check asks for it; before a deploy it probes this image's own GPU function on the run's render,
    through the handoff Volume, and closes the handoff."""
    import subprocess  # noqa: PLC0415 -- patched for this test
    import tempfile  # noqa: PLC0415 -- imported in the test that uses it
    from types import SimpleNamespace  # noqa: PLC0415 -- stand-ins, local to this test

    from deploy import modal_app  # noqa: PLC0415 -- the deploy group, imported where it is used
    from safecut.audit import gpu  # noqa: PLC0415 -- the handoff, replaced for this test

    real_path = modal_app.Path

    def in_repo(*parts: Any) -> Path:  # the image's /root is the repo here
        path = real_path(*parts)
        return ROOT / path.relative_to("/root") if path.is_relative_to("/root") else path

    ran: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        ran.append((argv, kwargs["env"]))
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True)
        (out / "audit.json").write_text(json.dumps({"unresolved": 0}))
        (out / "receipt.json").write_text(json.dumps({"audit": {"auditor": "yunet-face", "auditor_device": "cpu"}}))
        (out / "redacted.mp4").write_bytes(b"render")
        return subprocess.CompletedProcess(argv, 0, stdout="done", stderr="")

    events: list[tuple[object, ...]] = []

    class FakeHandoff:
        def __init__(self, root: Path, commit: object) -> None:
            events.append(("handoff", str(root), commit))

        def close(self) -> None:
            events.append(("close",))

    def fake_probe(handoff: object, out: Path, sha: str) -> dict[str, object]:
        events.append(("probe", isinstance(handoff, FakeHandoff), (out / "redacted.mp4").is_file(), sha))
        return {"refused": None, "gpu": "NVIDIA L4", "frames": 3}

    volume = SimpleNamespace(commit=lambda: None)
    monkeypatch.setattr(modal_app, "Path", in_repo)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(gpu, "Handoff", FakeHandoff)
    monkeypatch.setattr(modal_app, "audit", volume)
    monkeypatch.setattr(modal_app, "_probe_gpu", fake_probe)
    result = modal_app.pipeline_worker_smoke._raw_f_(audit_gpu=audit_gpu)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType] -- modal 1.6.2's raw function
    [(argv, env)] = ran
    assert env["SAFECUT_AUDIT_GPU"] == ("1" if audit_gpu else "0")
    ledger_dir = Path(env["SAFECUT_JOBS_DIR"])  # its own ledger, off the jobs Volume
    assert ledger_dir.is_relative_to(tempfile.gettempdir())
    assert not ledger_dir.is_relative_to(modal_app.JOBS)
    assert argv[1:4] == ["-m", "safecut.cli", "run"]
    assert "--replay" in argv
    assert result["exit"] == 0
    assert result["auditor"] == "yunet-face"
    if audit_gpu:  # after a deploy: the job's own audit used the deployed GPU; nothing is probed
        assert events == []
        assert "gpu_probe" not in result
    else:
        render_sha = hashlib.sha256(b"render").hexdigest()
        assert events == [("handoff", modal_app.AUDIT, volume.commit), ("probe", True, True, render_sha), ("close",)]
        assert result["gpu_probe"] == {"refused": None, "gpu": "NVIDIA L4", "frames": 3}
