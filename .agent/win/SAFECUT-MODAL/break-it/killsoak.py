"""Kill soak: the scale-to-zero API is killed (SIGKILL) at random moments, over and over, while jobs run.

Each round starts a fresh local API (uvicorn, replay, the real stages on the synthetic demo clip) on one jobs
folder, starts a job, kills the process at a random moment during analysis (and again during publishing), restarts
it, and repeats until the job is done. Every job must end ``done`` with a receipt that verifies, every stage must
log exactly one ``done``, and no job may be left mid-action. Usage, from the repo root:
``N=5 KILLS=2 SEED=1 uv run python .agent/win/SAFECUT-MODAL/break-it/killsoak.py``
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from safecut import contracts  # noqa: E402
from safecut.pipeline import read_log  # noqa: E402
from tests.test_scale_to_zero import CODE, LocalApi  # noqa: E402

N = int(os.environ.get("N", "5"))
KILLS = int(os.environ.get("KILLS", "2"))
rng = random.Random(int(os.environ.get("SEED", "1")))  # noqa: S311 -- reproducible kill timings, not security
CLIP = ROOT / json.loads((ROOT / "fixtures/jobs/demo/raw/manifest.json").read_text())["source"]


def need(ok: bool, what: object) -> None:
    """A broken invariant stops the run, naming it (``assert`` would vanish under ``python -O``)."""
    if not ok:
        raise SystemExit(f"BROKEN: {what}")


def status(api: LocalApi, job_id: str) -> str:
    return str(json.loads((api.jobs / job_id / "state.json").read_text())["status"])


def drive(api: LocalApi, job_id: str, until: str, kills: int) -> int:
    """Run the job to ``until``, killing and restarting the API up to ``kills`` times on the way."""
    done_kills = 0
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        state = status(api, job_id)
        if state == until:
            return done_kills
        if state in ("failed", "needs_you"):
            raise SystemExit(f"{job_id} ended {state}: {json.loads((api.jobs / job_id / 'state.json').read_text())}")
        if done_kills < kills:
            time.sleep(rng.uniform(0.2, 6.0))
            if status(api, job_id) == until:
                return done_kills
            api.kill()
            done_kills += 1
            api.start()
        else:
            time.sleep(0.2)
    raise SystemExit(f"{job_id} never reached {until}")


def main() -> None:
    jobs = Path(tempfile.mkdtemp(prefix="killsoak-")) / "jobs"
    api = LocalApi(jobs)
    api.start()
    total_kills = 0
    try:
        for n in range(N):
            body = {"code": CODE, "size_bytes": CLIP.stat().st_size, "content_type": "video/mp4", "file_name": "c.mp4"}
            created = httpx.post(f"{api.url}/v1/jobs", json=body, timeout=10).json()
            job_id = created["job_id"]
            httpx.put(created["upload_url"], content=CLIP.read_bytes(), headers={"Content-Type": "video/mp4"},
                      timeout=30).raise_for_status()  # fmt: skip
            need(
                httpx.post(f"{api.url}/v1/jobs/{job_id}/start", timeout=10).status_code == 202,
                'httpx.post(f"{api.url}/v1/jobs/{job_id}/start", timeout=10).status_code == 202',
            )
            total_kills += drive(api, job_id, "review", rng.randint(1, KILLS))
            need(
                httpx.post(f"{api.url}/v1/jobs/{job_id}/render", timeout=30).status_code == 202,
                'httpx.post(f"{api.url}/v1/jobs/{job_id}/render", timeout=30).status_code == 202',
            )
            total_kills += drive(api, job_id, "done", rng.randint(1, KILLS))
            job_dir = jobs / job_id
            contracts.validate_job_dir(job_dir)
            done = Counter(e["stage"] for e in read_log(job_dir) if e.get("event") == "done")
            need(set(done.values()) == {1}, done)
            print(json.dumps({"job": n, "job_id": job_id, "kills_so_far": total_kills, "stages_done": len(done)}))
        active = [j.name for j in jobs.iterdir() if j.is_dir() and (j / "state.json").is_file()
                  and status(api, j.name) in ("processing", "rendering", "retry_later")]  # fmt: skip
        need(not active, active)
        print(f"KILLSOAK: PASS ({N} jobs, {total_kills} SIGKILLs, every job done, receipts verify, no stage twice)")
    finally:
        api.stop()


if __name__ == "__main__":
    main()
