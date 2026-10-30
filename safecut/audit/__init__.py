"""audit: ``redacted.mp4`` → ``audit.json`` (detector on every frame + red-team + auto-patch; WP4 step 2).

``run(job_dir, replay=…)`` picks what answers each question:

* the detector: EgoBlur Gen 2 when its weights are installed, else the bundled YuNet (``detectors.load_detector``);
  it runs locally in both modes;
* the red-team: live Muse Spark, or in replay the answers recorded from a live run (``raw/redteam/frames.json``), or
  for a **synthetic** job the ground-truth oracle (``raw/redteam/synthetic_truth.json``, or the label file a
  synthetic recording's ``raw/manifest.json`` names). A replay with none of these has
  no red-team answer at all: every sampled frame is unresolved (``audit_failed``), never clean.

Per-frame CPU timings and the models that answered go to ``raw/audit/run.json`` (WP4: if a 30 s clip at
1280 px takes over 3 minutes on CPU, the detector belongs on a GPU; ``gpu.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path

from safecut import open_weight, pipeline
from safecut.audit.detectors import AuditorUnavailable, Detector, load_detector
from safecut.audit.loop import audit_job
from safecut.audit.opinion import Ask
from safecut.audit.redteam import Answer, LiveRedTeam, RedTeam, ReplayRedTeam, SyntheticRedTeam
from safecut.audit.truth import load_labels, manifest_truth
from safecut.config import Settings, load_settings
from safecut.contracts import Audit, Job, Plan, load
from safecut.meta.budget import Caller
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
    job = load(job_dir / "job.json", Job)
    plan_of = lambda: load(job_dir / "plan.json", Plan)  # noqa: E731 -- the oracle re-reads the current plan
    if (job_dir / SYNTHETIC_TRUTH).exists():
        return SyntheticRedTeam.load(job_dir / SYNTHETIC_TRUTH, plan_of, job.width, job.height)
    labels = manifest_truth(job_dir)
    if labels is not None:
        truth = load_labels(labels, width=job.width, height=job.height, frames=job.frames)
        return SyntheticRedTeam(truth.frames, plan_of, job.width, job.height)
    return NoRedTeam()


async def _live(job_dir: Path, settings: Settings, detector: Detector, client: MetaClient | None) -> Audit:
    job = load(job_dir / "job.json", Job)
    # The job's own caller (judge, pilot, owner …): its caps hold, and the open-weight gate reads its code kind.
    caller = pipeline.job_caller(job_dir, settings) if (job_dir / pipeline.INTAKE).exists() else Caller.local()
    eligible = not job.open_weight_attempted and open_weight.enabled_for(
        settings, consented=job.consented, code_kind=caller.code_kind
    )
    # The service's one spend ledger: the daily, code and pilot-pool caps count every job's calls, not just this one.
    ledger = pipeline.job_ledger(settings)
    async with AsyncExitStack() as stack:
        if client is None:
            client = await stack.enter_async_context(
                MetaClient(settings, job_id=job.job_id, caller=caller, ledger=ledger, cost_path=job_dir / "cost.jsonl")
            )
        meta = client
        opinion: Ask | None = None
        if eligible:
            baseten = open_weight.open_weight_client(settings, job_id=job.job_id, caller=caller, ledger=ledger,
                                                     cost_path=job_dir / "cost.jsonl")  # fmt: skip
            stack.push_async_callback(baseten.aclose)

            async def ask(frames: Sequence[tuple[int, str]], words: str) -> open_weight.SecondOpinion:
                return await open_weight.second_opinion(baseten, settings, consented=job.consented, frames=frames,
                                                        kept_clear=words)  # fmt: skip

            opinion = ask

        audit, _ = await audit_job(job_dir, detector=detector, redteam=LiveRedTeam(meta, settings, job_dir),
                                   opinion=opinion, opinion_grid_ok=settings.open_weight_grid_ok)  # fmt: skip
        return audit


def auditor_available(settings: Settings) -> bool:
    """Whether the audit can run here (WP5 answers ``POST /start`` with 503 ``auditor_unavailable`` when it can't):
    EgoBlur when its weights are installed, else the bundled YuNet, whose weights must be present and unaltered."""
    try:
        load_detector(settings)
    except AuditorUnavailable:
        return False
    return True


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


__all__ = ["AUDIT", "RECORDED", "SYNTHETIC_TRUTH", "NoRedTeam", "auditor_available", "replay_redteam", "run"]
