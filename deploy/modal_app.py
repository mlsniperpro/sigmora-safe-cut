"""The Safe Cut API on Modal (WP5 step 3; lane SAFECUT-MODAL): ``modal deploy deploy/modal_app.py``.

- ``SafeCutApi``: the FastAPI app (``safecut.api.app``), **scaled to zero** when no one uses it. One container at
  most: the per-IP rate limits and the spend ledger (SQLite on the Volume) are in-process, so the service never
  runs a second copy that could double-spend. The pipeline runs in that container's worker threads
  (``SAFECUT_WORKERS``). Modal scales a container down once it has had no input in flight for
  ``scaledown_window``, and a worker thread isn't an input: so every queued job action also spawns the class's own
  ``hold`` method, an input of this same container that lasts until the job stops (``Service.hold``). A started
  job finishes even if every browser tab closes. A container that dies mid-job anyway (a crash, a preemption) is
  replaced on the next input, and its start re-queues every job left mid-action (``Service.recover``).
- ``cleanup``: the 24 h deletion job, every 15 minutes, on the smallest container Modal runs. It also spawns
  ``hold`` for any job still mid-action on the Volume, which wakes the API to resume a job nothing is moving.
- ``egoblur_detect``: EgoBlur Gen 2 on a GPU, reading the render from the handoff Volume ``safecut-audit``
  (``safecut.audit.gpu.Handoff``: the API copies it there and commits; it can't commit the jobs Volume, whose commit
  reloads it, which Modal refuses while the API holds the spend ledger's SQLite files open on it).
  The API container stays slim (no torch); with ``SAFECUT_AUDIT_GPU=1`` (the default here) the audit calls it,
  and runs YuNet when it can't answer, naming whichever ran.
- ``pipeline_worker_smoke`` and ``ledger_smoke``: the deploy workflow's checks (``modal run`` before the deploy,
  ``deploy/verify_deploy.py`` after it).

Secrets come only from the Modal secret ``safecut-secrets`` (``MODEL_API_KEY``, ``SAFECUT_ACCESS_CODES``,
``SAFECUT_SERVICE_KEYS``, ``SAFECUT_URL_SECRET``, ``SAFECUT_PUBLIC_URL``, ``SAFECUT_CORS_ORIGINS``); see
``BLOCKED.md``. Job directories live on the Volume ``safecut-jobs`` at ``/data/jobs``; the EgoBlur weights on
``safecut-models`` at ``/models/egoblur``; renders on their way to the GPU on ``safecut-audit`` at ``/audit``. Sizes
and their cost: ``docs/DEPLOY-COSTS.md``.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import modal

ROOT = Path(__file__).resolve().parent.parent
JOBS = "/data/jobs"
WEIGHTS = "/models/egoblur"
AUDIT = "/audit"
APP_NAME = "safecut"

#: What the image leaves out of the source packages: bytecode only; every data file ships.
SOURCE_IGNORE = ["**/__pycache__", "**/*.pyc"]

#: The API container's quiet spell before it sleeps. Five minutes: a judge reading a result or a receipt between
#: clicks finds it awake, and each sleep costs at most 300 s of an idle 1-core, 2 GiB container (about $0.005).
API_SCALEDOWN_S = 300
#: The GPU container's (``SAFECUT_AUDIT_GPU_IDLE_S`` prices it): an audit's passes run back to back, seconds apart.
GPU_SCALEDOWN_S = 30

image = (
    modal.Image.debian_slim(python_version="3.12")
    .env({"SAFECUT_JOBS_DIR": JOBS, "SAFECUT_TRUST_PROXY": "1", "SAFECUT_AUDIT_GPU": "1"})
    .uv_sync(str(ROOT), frozen=True)
    # The default ignore keeps only .py files: the prompt templates (safecut/scout/prompts/*.txt) and the bundled
    # YuNet weights (safecut/audit/weights/*.onnx) would be missing, and scene, roles and the audit would fail.
    .add_local_python_source("safecut", "eval", ignore=SOURCE_IGNORE)
    .add_local_dir(str(ROOT / "fixtures" / "jobs"), "/root/fixtures/jobs")
    .add_local_dir(str(ROOT / "fixtures" / "clips"), "/root/fixtures/clips")
)
#: EgoBlur's image: the ``audit`` group (egoblur, torch, torchvision, vrs, pinned in pyproject.toml).
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .env({"SAFECUT_JOBS_DIR": JOBS})
    .uv_sync(str(ROOT), groups=["audit"], frozen=True)
    .add_local_python_source("safecut", ignore=SOURCE_IGNORE)
)

app = modal.App(APP_NAME, image=image)
jobs = modal.Volume.from_name("safecut-jobs", create_if_missing=True)
models = modal.Volume.from_name("safecut-models", create_if_missing=True)
audit = modal.Volume.from_name("safecut-audit", create_if_missing=True)
secrets = [modal.Secret.from_name("safecut-secrets")]


def _api() -> Any:
    """A handle on the API class (Modal's stubs type a ``@modal.concurrent`` class as a partial function)."""
    return cast(Any, SafeCutApi)()


def _keepalive(job_id: str) -> None:
    """Spawn this container's own ``hold`` input for the job (``Worker`` calls it whenever an action is queued)."""
    from safecut.audit.gpu import modal_permitted  # noqa: PLC0415 -- inside the container

    with modal_permitted():
        _api().hold.spawn(job_id)


@app.cls(
    volumes={"/data": jobs, AUDIT: audit},
    secrets=secrets,
    # Sized to one container's work: the models are remote and EgoBlur runs on the GPU function, so what runs here
    # is ffmpeg, the render and (as a fallback) YuNet, for at most SAFECUT_WORKERS=2 jobs at once.
    cpu=1.0,
    memory=2048,
    min_containers=0,
    max_containers=1,
    scaledown_window=API_SCALEDOWN_S,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=64)
class SafeCutApi:
    @modal.enter()
    def boot(self) -> None:
        """Container start, before any input: the service, the resumed jobs and the background loops."""
        from safecut.api.app import Service, production_problems  # noqa: PLC0415 -- inside the container
        from safecut.config import load_settings  # noqa: PLC0415 -- inside the container

        settings = load_settings()
        problems = production_problems(settings)
        if problems:  # a weak judge code or URL key is refused at startup, never served
            raise RuntimeError("safecut-secrets isn't fit for production: " + "; ".join(problems))
        # wait_on_stop=False: the ASGI lifespan stops the service before @modal.exit, and must not wait for jobs either.
        self.service = Service(settings, keepalive=_keepalive, wait_on_stop=False)
        self.service.start()

    @modal.asgi_app(label="safecut-api")
    def api(self) -> Any:
        from safecut.api.app import create_app  # noqa: PLC0415 -- inside the container

        return create_app(service=self.service)

    @modal.method()
    def hold(self, job_id: str) -> str:
        """An input that lasts while the job runs, so the container isn't scaled down under it."""
        return self.service.hold(job_id)

    @modal.exit()
    def shutdown(self) -> None:
        # Never wait for a running job here: a redeploy (recreate) waits for this container to go before starting
        # the next, whose start resumes the job; a slow exit would let the two overlap.
        self.service.stop(wait=False)


@app.function(
    volumes={"/data": jobs, AUDIT: audit},
    secrets=secrets,
    schedule=modal.Period(minutes=15),
    timeout=10 * 60,
    # The smallest container Modal runs (its default request), gone two seconds after each sweep.
    cpu=0.125,
    memory=128,
    min_containers=0,
    scaledown_window=2,
)
def cleanup() -> dict[str, list[str]]:
    """Delete every unpinned job older than ``SAFECUT_JOB_TTL_HOURS`` (24 h) from the Volume and any render an audit
    left on the handoff Volume, and wake the API for any job still mid-action (a no-op input when it is already
    working on it)."""
    from safecut.api.store import JobStore, sweep_handoff  # noqa: PLC0415 -- inside the container
    from safecut.config import load_settings  # noqa: PLC0415 -- inside the container

    settings = load_settings()
    jobs.reload()
    store = JobStore(
        Path(settings.jobs_dir),
        ttl=timedelta(hours=settings.job_ttl_hours),
        cleanup_every=timedelta(minutes=settings.cleanup_interval_min),
    )
    removed = store.sweep()
    jobs.commit()
    audit.reload()
    handoffs = sweep_handoff(Path(AUDIT))
    audit.commit()
    active = store.active()
    for job_id in active:
        _api().hold.spawn(job_id)
    return {"removed": removed, "handoffs": handoffs, "resumed": active}


_server: Any = None


@app.function(
    image=gpu_image,
    gpu=["L4", "T4"],  # L4 first (faster per dollar here, docs/DEPLOY-COSTS.md); T4 when no L4 is free
    volumes={AUDIT: audit, "/models": models},
    cpu=2.0,
    memory=6144,
    min_containers=0,
    # The API runs at most SAFECUT_MAX_ACTIVE_JOBS (8) jobs, so at most that many scans at once; four GPUs bound the
    # spend of a burst, and a scan that waits its turn falls back to YuNet at its timeout.
    max_containers=4,
    scaledown_window=GPU_SCALEDOWN_S,
    # No Modal-level retries: the API retries a transient failure once itself, and reserves and prices each call.
    timeout=10 * 60,
)
def egoblur_detect(request: dict[str, Any]) -> dict[str, Any]:
    """One audit scan: EgoBlur Gen 2 on the wanted frames of a job's render (``safecut.audit.gpu.GpuServer``)."""
    from safecut.audit.gpu import GpuServer  # noqa: PLC0415 -- inside the GPU container

    global _server  # noqa: PLW0603 -- one server per container: the weights load once
    audit.reload()  # the caller committed the render to the handoff Volume just before calling
    if _server is None:
        _server = GpuServer(Path(AUDIT), Path(WEIGHTS))
    return _server.serve(request)


#: How long the pre-deploy smoke waits for its GPU probe (a cold GPU container, the weights loading).
GPU_PROBE_TIMEOUT_S = 5 * 60  # with the 15-minute replay run, inside the smoke's 25 minutes


@app.function(volumes={AUDIT: audit}, timeout=25 * 60)
def pipeline_worker_smoke(audit_gpu: bool = False) -> dict[str, object]:
    """``safecut run`` on the synthetic demo clip, replayed: proves the image can run every stage. With
    ``audit_gpu`` (after a deploy) the audit calls the deployed GPU function through the handoff Volume, as the API's
    does; without it (before a deploy) this app's own ``egoblur_detect`` is probed on the render the same way."""
    import json  # noqa: PLC0415 -- inside the container
    import os  # noqa: PLC0415 -- inside the container
    import subprocess  # noqa: PLC0415 -- inside the container
    import sys  # noqa: PLC0415 -- inside the container
    import tempfile  # noqa: PLC0415 -- inside the container

    from safecut.audit.gpu import Handoff, child_env  # noqa: PLC0415 -- inside the container
    from safecut.render import file_sha256  # noqa: PLC0415 -- inside the container

    manifest = json.loads(Path("/root/fixtures/jobs/demo/raw/manifest.json").read_text())
    clip = Path("/root") / manifest["source"]
    out = Path(tempfile.mkdtemp()) / "smoke"
    # The smoke's own ledger, off the jobs Volume: the API container is that Volume's one SQLite writer.
    env = child_env(
        {**os.environ, "SAFECUT_AUDIT_GPU": "1" if audit_gpu else "0", "SAFECUT_JOBS_DIR": tempfile.mkdtemp()}
    )
    proc = subprocess.run(  # noqa: S603 -- fixed argv: this interpreter, our CLI, our paths
        [sys.executable, "-m", "safecut.cli", "run", str(clip), "--out", str(out), "--replay",
         "--replay-from", "/root/fixtures/jobs/demo", "--auto-approve-policy"],
        capture_output=True, text=True, timeout=15 * 60, check=False, env=env,
    )  # fmt: skip
    audited = json.loads((out / "audit.json").read_text()) if (out / "audit.json").is_file() else None
    receipt = json.loads((out / "receipt.json").read_text()) if (out / "receipt.json").is_file() else None
    gpu_record = out / "raw" / "audit" / "gpu.json"
    result: dict[str, object] = {
        "exit": proc.returncode,
        "tail": proc.stdout[-400:] + proc.stderr[-400:],
        "unresolved": audited["unresolved"] if audited else None,
        "receipt": receipt is not None,
        "redacted": (out / "redacted.mp4").is_file(),
        "auditor": receipt["audit"]["auditor"] if receipt else None,
        "auditor_device": receipt["audit"].get("auditor_device") if receipt else None,
        "gpu_fallback": json.loads(gpu_record.read_text()).get("fallback") if gpu_record.is_file() else None,
    }
    if not audit_gpu and audited is not None:
        handoff = Handoff(Path(AUDIT), audit.commit)
        try:
            job = json.loads((out / "job.json").read_text())
            request = {"job": handoff.put(out, file_sha256(out / "redacted.mp4")), "model": "egoblur-gen2",
                       "frames": list(range(job["frames"])), "face_threshold": 0.5, "plate_threshold": 0.5}  # fmt: skip
            call = egoblur_detect.spawn(request)
            try:
                probe = call.get(timeout=GPU_PROBE_TIMEOUT_S)
            except (TimeoutError, modal.exception.TimeoutError):
                call.cancel()
                probe = {"refused": "timeout", "detail": f"no GPU answer in {GPU_PROBE_TIMEOUT_S} s"}
            result["gpu_probe"] = {"gpu": probe.get("gpu"), "refused": probe.get("refused"),
                                   "detail": probe.get("detail"), "frames": len(probe.get("frames") or {})}  # fmt: skip
        finally:
            handoff.close()
            audit.commit()
    return result


@app.function(volumes={"/data": jobs}, timeout=5 * 60)
def ledger_smoke() -> dict[str, object]:
    """The spend ledger and the paid-action limiter are SQLite (WAL) on the jobs Volume: prove both work there,
    from a fresh connection, before the service relies on them (a ledger error would fail every live job closed;
    a limiter that forgot would hand out a fresh hour on every wake)."""
    import uuid  # noqa: PLC0415 -- inside the container

    from safecut.api.access import ApiRefusal, StoredRateLimiter  # noqa: PLC0415 -- inside the container
    from safecut.meta.budget import CapLimit, LocalLedger  # noqa: PLC0415 -- inside the container

    tag = uuid.uuid4().hex
    path = Path(JOBS) / f".ledger-smoke-{tag}.sqlite"
    limits = Path(JOBS) / f".limits-smoke-{tag}.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ledger = LocalLedger(path)
        limit = CapLimit("daily", "daily:smoke", 1.0)
        ledger.reserve("smoke-1", None, 0.25, [limit])
        ledger.settle("smoke-1", 0.2)
        ledger.reserve("smoke-2", None, 0.5, [limit])
        ledger.release("smoke-2")
        reread = LocalLedger(path).spent("daily:smoke")
        StoredRateLimiter(limits).hit("paid", "smoke", limit=1, window_s=3600)
        try:
            StoredRateLimiter(limits).hit("paid", "smoke", limit=1, window_s=3600)
            remembered = False
        except ApiRefusal:
            remembered = True
        return {"ok": abs(reread - 0.2) < 1e-9 and remembered, "spent": reread, "limiter_remembers": remembered}
    except Exception as exc:  # reported to the local entrypoint, which fails the deploy
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        for leftover in [*path.parent.glob(f"{path.name}*"), *limits.parent.glob(f"{limits.name}*")]:
            leftover.unlink(missing_ok=True)


@app.local_entrypoint()
def smoke() -> None:
    """``modal run deploy/modal_app.py``: the pre-deploy smoke runs, failing loudly."""
    import os  # noqa: PLC0415 -- local, on the runner

    from deploy.checks import ledger_problems, pre_deploy_problems  # noqa: PLC0415 -- local, on the runner

    result = pipeline_worker_smoke.remote()
    print(result)
    # SAFECUT_DEPLOY_GPU_OPTIONAL=1 (a repository variable): a GPU outage warns instead of blocking a hotfix; the
    # deployed audit then runs YuNet and says so, until the GPU answers again.
    problems = pre_deploy_problems(result, gpu_required=os.environ.get("SAFECUT_DEPLOY_GPU_OPTIONAL") != "1")
    ledger = ledger_smoke.remote()
    print(ledger)
    problems += ledger_problems(ledger)
    if problems:
        raise SystemExit("smoke run failed: " + "; ".join(problems))
