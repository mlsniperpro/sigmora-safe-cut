"""decide: tracks + roles → ``decisions.json`` (deny by default; WP3 steps 1-4).

``run(job_dir)`` reads ``job.json`` and ``tracks.json`` (required) and ``roles.json``, ``scene.json`` and
``transcript.json`` (each optional: a missing file holds every keep, API-NOTES §12), applies the policy, keeps
any audit patches an earlier ``decisions.json`` carries (a patch is never lost, API-NOTES §12), replays the
creator's ``review.json`` edits when there are any, and writes ``decisions.json``. It makes no API call, so
``replay`` changes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safecut.contracts import Decisions

DECISIONS = "decisions.json"
REVIEW = "review.json"

# The package imports nothing heavy at load time: coverage (``--cov=safecut.decide.policy``) and the stage
# registry import ``safecut.decide`` first, and numpy refuses a second load if it is pulled in before measurement.


def policy_decisions(job_dir: Path) -> Decisions:
    """The policy's decisions plus the audit patches already in ``decisions.json``, before any creator edit."""
    from safecut.contracts import Decisions, Job, Roles, Scene, Tracks, Transcript, load  # noqa: PLC0415 -- see above
    from safecut.decide.policy import Inputs, decide  # noqa: PLC0415 -- see above

    def optional[M: (Roles, Scene, Transcript, Decisions)](name: str, model: type[M]) -> M | None:
        return load(job_dir / name, model) if (job_dir / name).exists() else None

    inputs = Inputs(
        job=load(job_dir / "job.json", Job),
        tracks=load(job_dir / "tracks.json", Tracks),
        roles=optional("roles.json", Roles),
        scene=optional("scene.json", Scene),
        transcript=optional("transcript.json", Transcript),
    )
    decided = decide(inputs)
    previous = optional(DECISIONS, Decisions)
    patches = [item for item in previous.items if item.origin == "audit_patch"] if previous is not None else []
    return Decisions(items=[*decided.items, *patches])


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """Write ``decisions.json`` and return its path."""
    from safecut.contracts import dump, load  # noqa: PLC0415 -- see above
    from safecut.decide.review import CoverSpotEdit, ReviewLog, apply_review  # noqa: PLC0415 -- see above

    del replay  # no API call in this stage
    decisions = policy_decisions(job_dir)
    if (job_dir / REVIEW).exists():
        # A covered spot's patch is already among the kept audit patches; the other edits replay on the policy.
        edits = [edit for edit in load(job_dir / REVIEW, ReviewLog).root if not isinstance(edit, CoverSpotEdit)]
        decisions = apply_review(decisions, edits).decisions
    return dump(decisions, job_dir / DECISIONS)


__all__ = ["DECISIONS", "REVIEW", "policy_decisions", "run"]
