"""decide: tracks + roles → ``decisions.json`` (deny by default; WP3 steps 1-4).

``run(job_dir)`` reads ``job.json`` and ``tracks.json`` (required) and ``roles.json``, ``scene.json`` and
``transcript.json`` (each optional: a missing file holds every keep, API-NOTES §12), applies the policy, keeps
any audit patches an earlier ``decisions.json`` carries (a patch is never lost, API-NOTES §12), replays the
creator's ``review.json`` edits when there are any, and writes ``decisions.json``. It makes no API call, so
``replay`` changes nothing.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from safecut.contracts import Decisions, Job, Roles, Scene, Tracks, Transcript, dump, load
from safecut.decide.policy import Inputs, decide
from safecut.decide.review import CoverSpotEdit, ReviewLog, apply_review

DECISIONS = "decisions.json"
REVIEW = "review.json"


def _optional[M: BaseModel](path: Path, model: type[M]) -> M | None:
    return load(path, model) if path.exists() else None


def policy_decisions(job_dir: Path) -> Decisions:
    """The policy's decisions plus the audit patches already in ``decisions.json``, before any creator edit."""
    inputs = Inputs(
        job=load(job_dir / "job.json", Job),
        tracks=load(job_dir / "tracks.json", Tracks),
        roles=_optional(job_dir / "roles.json", Roles),
        scene=_optional(job_dir / "scene.json", Scene),
        transcript=_optional(job_dir / "transcript.json", Transcript),
    )
    decided = decide(inputs)
    previous = _optional(job_dir / DECISIONS, Decisions)
    patches = [item for item in previous.items if item.origin == "audit_patch"] if previous is not None else []
    return Decisions(items=[*decided.items, *patches])


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """Write ``decisions.json`` and return its path."""
    del replay  # no API call in this stage
    decisions = policy_decisions(job_dir)
    log = _optional(job_dir / REVIEW, ReviewLog)
    if log is not None:
        # A covered spot's patch is already among the kept audit patches; the other edits replay on the policy.
        edits = [edit for edit in log.root if not isinstance(edit, CoverSpotEdit)]
        decisions = apply_review(decisions, edits).decisions
    return dump(decisions, job_dir / DECISIONS)


__all__ = ["DECISIONS", "REVIEW", "policy_decisions", "run"]
