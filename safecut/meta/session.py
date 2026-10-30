"""A Meta client for one job run outside the API service (CLI stage runs, ``go-live``, eval).

The service (WP5) builds its clients with the shared ledger, breaker and daily caps. A stage run on its own gets
a local owner client whose in-memory ledger is seeded with the job's spend so far (``cost.jsonl``), so the job
cap counts every earlier stage of the same job, not just this process.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from safecut.config import Settings
from safecut.contracts import Intake, load, read_cost_lines
from safecut.meta.budget import Caller, Ledger, LocalLedger, job_limit
from safecut.meta.client import MetaClient

COST = "cost.jsonl"


def job_ledger(settings: Settings, job_id: str, cost_path: Path) -> LocalLedger:
    """A ledger already holding this job's earlier Meta spend (measured and possibly billed) under its cap.

    Raises ``BudgetExceeded`` when the earlier spend alone is over the job cap: nothing more may be sent.
    """
    ledger = LocalLedger()
    lines = list(read_cost_lines(cost_path)) if cost_path.exists() else []
    spent = sum(line.usd for line in lines if line.provider == "meta" and line.job_id == job_id)
    if spent > 0:
        ledger.reserve(f"seed:{job_id}", job_id, spent, [job_limit(settings, job_id)])
        ledger.settle(f"seed:{job_id}", spent)
    return ledger


def _service_caps(job_dir: Path, settings: Settings) -> tuple[Caller, Ledger] | None:
    """A job that came through an access code counts against the service's shared caps (WP5's caller and SQLite
    ledger); a local run (no code in ``intake.json``, or no intake) uses the job-seeded ledger above."""
    intake = job_dir / "intake.json"
    if not intake.exists() or load(intake, Intake).code_kind is None:
        return None
    from safecut import pipeline  # noqa: PLC0415 -- the pipeline imports the stages that import this module

    return pipeline.job_caller(job_dir, settings), pipeline.job_ledger(settings)


@asynccontextmanager
async def job_client(job_dir: Path, settings: Settings, *, caller: Caller | None = None) -> AsyncGenerator[MetaClient]:
    """A client for ``job_dir`` (job ID = the directory name), logging to its ``cost.jsonl``."""
    cost_path = job_dir / COST
    service = None if caller is not None else _service_caps(job_dir, settings)
    client = MetaClient(
        settings,
        job_id=job_dir.name,
        caller=caller or (service[0] if service else Caller.local()),
        ledger=service[1] if service else job_ledger(settings, job_dir.name, cost_path),
        cost_path=cost_path,
    )
    try:
        yield client
    finally:
        await client.aclose()
