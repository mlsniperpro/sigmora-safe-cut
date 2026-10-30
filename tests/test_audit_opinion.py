"""WP4: the open-weight second opinion inside the audit (PRE-A §3.8, redteam.md "Second opinion"): at most once per
job, advisory until the grid is confirmed, never blocking, copied into re-runs; Baseten stubbed."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from safecut import contracts, open_weight
from safecut.audit.detectors import YuNet
from safecut.audit.loop import audit_job
from safecut.audit.redteam import SyntheticRedTeam
from safecut.audit.truth import load_labels
from safecut.contracts import Audit, Job, Plan, dump, load
from safecut.decide import run as decide_run
from safecut.guard import run as guard_run
from safecut.meta.errors import BudgetExceeded
from safecut.render import render
from tests.safety_jobs import make_job


def consented_job(tmp_path: Path) -> Path:
    job_dir = make_job(tmp_path)
    job = load(job_dir / "job.json", Job)
    dump(job.model_copy(update={"consented": True}), job_dir / "job.json")
    decide_run(job_dir)
    guard_run(job_dir)
    render(job_dir)
    return job_dir


class Opinion:
    def __init__(self, hit_on: int | None = None, fail: bool = False) -> None:
        self.calls, self.hit_on, self.fail = 0, hit_on, fail

    async def __call__(self, frames: Sequence[tuple[int, str]], words: str) -> open_weight.SecondOpinion:
        self.calls += 1
        assert all(url.startswith("data:image/jpeg;base64,") for _, url in frames)
        if self.fail:
            raise BudgetExceeded("baseten cap", cap="baseten_job", limit_usd=0.5, needed_usd=0.9)
        answer = []
        for f, _ in frames:
            found = []
            if f == self.hit_on:
                found = [open_weight.RedteamFinding(kind="text", detail="a sign", text="SALE", box=(10, 300, 200, 400),
                                                    confidence="low")]  # fmt: skip
            answer.append(open_weight.RedteamFrame(frame=f, findings=found))
        return open_weight.SecondOpinion(model="meta-models/muse-spark-open-1026", frames=answer, failed_batches=0,
                                         errors=[])  # fmt: skip


def audit(job_dir: Path, opinion: Opinion, *, grid_ok: bool = False) -> Audit:
    redteam = SyntheticRedTeam.load(job_dir / "raw/redteam/synthetic_truth.json",
                                    lambda: load(job_dir / "plan.json", Plan), 320, 240)  # fmt: skip
    got, _ = asyncio.run(audit_job(job_dir, detector=YuNet(), redteam=redteam, opinion=opinion,
                                   opinion_grid_ok=grid_ok))  # fmt: skip
    return got


def test_the_opinion_runs_once_and_stays_advisory(tmp_path: Path) -> None:
    job_dir = consented_job(tmp_path)
    opinion = Opinion(hit_on=30)
    first = audit(job_dir, opinion)
    assert opinion.calls == 1
    assert load(job_dir / "job.json", Job).open_weight_attempted
    assert (first.open_weight.status, first.open_weight.model) == ("ok", "meta-models/muse-spark-open-1026")
    assert first.open_weight.findings == 1
    assert {e.frame // 30 for e in first.redteam_open} == {0, 1}
    assert not [leak for leak in first.leaks if leak.detector == "redteam_open"]  # advisory: never patched
    assert first.unresolved == 0
    contracts.validate_job_dir(job_dir)
    second = audit(job_dir, opinion)  # a re-run never asks again, and keeps what it said
    assert opinion.calls == 1
    assert second.open_weight == first.open_weight
    assert second.redteam_open == first.redteam_open
    contracts.validate_job_dir(job_dir)


def test_with_the_grid_confirmed_its_leaks_are_patched_within_the_cap(tmp_path: Path) -> None:
    job_dir = consented_job(tmp_path)
    got = audit(job_dir, Opinion(hit_on=30), grid_ok=True)
    (leak,) = [leak for leak in got.leaks if leak.detector == "redteam_open"]
    assert leak.patched_item is not None
    assert got.passes == 2
    assert got.unresolved == 0
    contracts.validate_job_dir(job_dir)


def test_a_budget_stop_leaves_the_opinion_off_and_never_blocks(tmp_path: Path) -> None:
    job_dir = consented_job(tmp_path)
    got = audit(job_dir, Opinion(fail=True))
    assert got.open_weight.status == "off"
    assert load(job_dir / "job.json", Job).open_weight_attempted  # attempted: it never runs again
    assert got.unresolved == 0
    contracts.validate_job_dir(job_dir)


def test_labels_are_scaled_to_the_prepared_clip() -> None:
    labels = load_labels(Path("fixtures/jobs/demo/truth/SC-A-91.json"), width=320, height=180, frames=360)
    assert labels.frames[0][0].box[2] <= 320
    assert labels.should_hide["e1"] is False
