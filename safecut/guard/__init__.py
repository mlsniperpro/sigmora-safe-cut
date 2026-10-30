"""guard: ``decisions.json`` + ``tracks.json`` → ``plan.json`` (the leak guard, WP3 step 5).

``run(job_dir)`` reads ``job.json``, ``tracks.json`` and ``decisions.json`` (and ``audit.json`` when an earlier audit
flagged an item it read through, which then renders solid), and writes ``plan.json``. No API call: ``replay``
changes nothing.
"""

from __future__ import annotations

from pathlib import Path

from safecut.contracts import Audit, Decisions, Job, Tracks, dump, load
from safecut.guard.plan import plan

PLAN = "plan.json"


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """Write ``plan.json`` and return its path."""
    del replay  # no API call in this stage
    audit_path = job_dir / "audit.json"
    built = plan(
        load(job_dir / "job.json", Job),
        load(job_dir / "tracks.json", Tracks),
        load(job_dir / "decisions.json", Decisions),
        load(audit_path, Audit) if audit_path.exists() else None,
    )
    return dump(built, job_dir / PLAN)


__all__ = ["PLAN", "plan", "run"]
