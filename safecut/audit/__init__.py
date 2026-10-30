"""audit: ``redacted.mp4`` → ``audit.json`` (detector on every frame + red-team + auto-patch; WP4 step 2).

``run(job_dir, replay=…)`` picks what answers each question:

* the detector: EgoBlur Gen 2 when its weights are installed, else the bundled YuNet (``detectors.load_detector``);
  it runs locally in both modes;
* the red-team: live Muse Spark, or in replay the answers recorded from a live run (``raw/redteam/frames.json``), or
  for a **synthetic** job the ground-truth oracle (``raw/redteam/synthetic_truth.json``). A replay with neither has
  no red-team answer at all: every sampled frame is unresolved (``audit_failed``), never clean.

Per-frame CPU timings and the models that answered go to ``raw/audit/run.json`` (WP4: if a 30 s clip at
1280 px takes over 3 minutes on CPU, the detector belongs on a GPU; ``gpu.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from safecut.audit.detectors import Detector, load_detector
from safecut.audit.loop import audit_job
from safecut.audit.redteam import Answer, LiveRedTeam, RedTeam, ReplayRedTeam, SyntheticRedTeam
from safecut.config import Settings, load_settings
from safecut.contracts import Audit, Job, Plan, load
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import MetaClient
from safecut.render.draw import Frame

AUDIT = "audit.json"
RECORDED = Path("raw/redteam/frames.json")
SYNTHETIC_TRUTH = Path("raw/redteam/synthetic_truth.json")


class NoRedTeam:
    """A replay with nothing recorded: no frame is answered, so every one counts as unresolved."""

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        del approved, bar
        return Answer(missing=[f for f, _ in frames])


def replay_redteam(job_dir: Path) -> RedTeam:
    if (job_dir / RECORDED).exists():
        return ReplayRedTeam.load(job_dir / RECORDED)
    if (job_dir / SYNTHETIC_TRUTH).exists():
        job = load(job_dir / "job.json", Job)
        return SyntheticRedTeam.load(
            job_dir / SYNTHETIC_TRUTH, lambda: load(job_dir / "plan.json", Plan), job.width, job.height
        )
    return NoRedTeam()


async def _live(job_dir: Path, settings: Settings, detector: Detector, client: MetaClient | None) -> Audit:
    job = load(job_dir / "job.json", Job)
    if client is not None:
        audit, _ = await audit_job(job_dir, detector=detector, redteam=LiveRedTeam(client, settings, job_dir))
    else:
        async with MetaClient(settings, job_id=job.job_id, caller=Caller.local(), ledger=LocalLedger(),
                              cost_path=job_dir / "cost.jsonl") as own:  # fmt: skip
            audit, _ = await audit_job(job_dir, detector=detector, redteam=LiveRedTeam(own, settings, job_dir))
    return audit


def run(
    job_dir: Path,
    *,
    replay: bool = False,
    settings: Settings | None = None,
    detector: Detector | None = None,
    redteam: RedTeam | None = None,
    client: MetaClient | None = None,
) -> Path:
    """Write ``audit.json`` (and, after patches, ``decisions.json``, ``plan.json`` and the re-rendered video)."""
    settings = settings or load_settings()
    detector = detector or load_detector(settings)
    if redteam is None and not (replay or settings.replay):
        asyncio.run(_live(job_dir, settings, detector, client))
        return job_dir / AUDIT
    chosen = redteam or replay_redteam(job_dir)
    asyncio.run(audit_job(job_dir, detector=detector, redteam=chosen))
    return job_dir / AUDIT


__all__ = ["AUDIT", "RECORDED", "SYNTHETIC_TRUTH", "NoRedTeam", "replay_redteam", "run"]
