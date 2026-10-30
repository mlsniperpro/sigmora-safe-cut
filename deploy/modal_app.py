"""The Safe Cut API on Modal (WP5 step 3): ``modal deploy deploy/modal_app.py``.

- ``api``: the FastAPI app (``safecut.api.app``). One container: the per-IP rate limits and the spend ledger
  (SQLite on the Volume) are in-process, so the service never runs a second copy that could double-spend. The
  pipeline runs in that container's worker threads (``SAFECUT_WORKERS``), so a job's files and its state never
  cross containers.
- ``cleanup``: the 24 h deletion job, every 15 minutes, on the same Volume (the API also refuses and deletes any
  job past its ``deletes_at`` on sight, and sweeps in-process, so a late cron never extends a job's life).
- ``pipeline_worker_smoke``: runs the synthetic demo job end to end, in replay, in a fresh container from the
  deployed image (ffmpeg, every stage, the contracts); the deploy workflow calls it before declaring success.

Secrets come only from the Modal secret ``safecut-secrets`` (``MODEL_API_KEY``, ``SAFECUT_ACCESS_CODES``,
``SAFECUT_SERVICE_KEYS``, ``SAFECUT_URL_SECRET``, ``SAFECUT_PUBLIC_URL``, ``SAFECUT_CORS_ORIGINS``); see
``BLOCKED.md``. Job directories live on the Volume ``safecut-jobs`` at ``/data/jobs``.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
JOBS = "/data/jobs"
APP_NAME = "safecut"

#: ``SAFECUT_DEPLOY_AUDIT=1`` at deploy time builds the image with the ``audit`` group (EgoBlur + torch), once the
#: gated weights are on the ``safecut-models`` Volume (BLOCKED.md). Without it the audit runs the bundled YuNet
#: face detector on OpenCV (the main dependencies ship it), and audit.json and the receipt say so.
AUDIT_GROUPS = ["audit"] if os.environ.get("SAFECUT_DEPLOY_AUDIT") == "1" else []

image = (
    modal.Image.debian_slim(python_version="3.12")
    .env({"SAFECUT_JOBS_DIR": JOBS, "SAFECUT_TRUST_PROXY": "1"})
    .uv_sync(str(ROOT), groups=AUDIT_GROUPS, frozen=True)
    .add_local_python_source("safecut", "eval")
    .add_local_dir(str(ROOT / "fixtures" / "jobs"), "/root/fixtures/jobs")
    .add_local_dir(str(ROOT / "fixtures" / "clips"), "/root/fixtures/clips")
)

app = modal.App(APP_NAME, image=image)
jobs = modal.Volume.from_name("safecut-jobs", create_if_missing=True)
models = modal.Volume.from_name("safecut-models", create_if_missing=True)
secrets = [modal.Secret.from_name("safecut-secrets")]


@app.function(
    volumes={"/data": jobs, "/models": models},
    secrets=secrets,
    cpu=4.0,
    memory=8192,
    min_containers=1,
    max_containers=1,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=64)
@modal.asgi_app(label="safecut-api")
def api() -> Any:
    from safecut.api.app import create_app, production_problems  # noqa: PLC0415 -- inside the container
    from safecut.config import load_settings  # noqa: PLC0415 -- inside the container

    settings = load_settings()
    problems = production_problems(settings)
    if problems:  # a weak judge code or URL key is refused at startup, never served
        raise RuntimeError("safecut-secrets isn't fit for production: " + "; ".join(problems))
    return create_app(settings)


@app.function(volumes={"/data": jobs}, secrets=secrets, schedule=modal.Period(minutes=15), timeout=10 * 60)
def cleanup() -> list[str]:
    """Delete every unpinned job older than ``SAFECUT_JOB_TTL_HOURS`` (24 h) from the Volume."""
    from safecut.api.store import JobStore  # noqa: PLC0415 -- inside the container
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
    return removed


@app.function(timeout=20 * 60)
def pipeline_worker_smoke() -> dict[str, object]:
    """``safecut run`` on the synthetic demo clip, replayed, offline: proves the image can run every stage."""
    import json  # noqa: PLC0415 -- inside the container
    import subprocess  # noqa: PLC0415 -- inside the container
    import sys  # noqa: PLC0415 -- inside the container
    import tempfile  # noqa: PLC0415 -- inside the container

    manifest = json.loads(Path("/root/fixtures/jobs/demo/raw/manifest.json").read_text())
    clip = Path("/root") / manifest["source"]
    out = Path(tempfile.mkdtemp()) / "smoke"
    proc = subprocess.run(  # noqa: S603 -- fixed argv: this interpreter, our CLI, our paths
        [
            sys.executable,
            "-m",
            "safecut.cli",
            "run",
            str(clip),
            "--out",
            str(out),
            "--replay",
            "--replay-from",
            "/root/fixtures/jobs/demo",
            "--auto-approve-policy",
        ],
        capture_output=True,
        text=True,
        timeout=15 * 60,
        check=False,
    )
    audit = json.loads((out / "audit.json").read_text()) if (out / "audit.json").is_file() else None
    return {
        "exit": proc.returncode,
        "tail": proc.stdout[-400:] + proc.stderr[-400:],
        "unresolved": audit["unresolved"] if audit else None,
        "receipt": (out / "receipt.json").is_file(),
        "redacted": (out / "redacted.mp4").is_file(),
    }


@app.local_entrypoint()
def smoke() -> None:
    """``modal run deploy/modal_app.py``: the smoke run, failing loudly."""
    result = pipeline_worker_smoke.remote()
    print(result)
    if result["exit"] != 0 or result["unresolved"] != 0 or not result["receipt"] or not result["redacted"]:
        raise SystemExit(f"smoke run failed: {result}")
