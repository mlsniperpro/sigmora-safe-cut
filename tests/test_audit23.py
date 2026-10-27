"""Tests for audit #23: an exclusion needs a matching concept and an overlapping box, an audit must account for
every frame, and only the half-open trial closes the breaker."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from safecut import contracts as c
from safecut.meta.errors import BreakerOpen
from safecut.meta.retry import CircuitBreaker

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"
FACE_1_ON_5 = [604, 100, 704, 220]  # i_1 (kept, face:1) on frame 5


def _example(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    (job_dir / "receipt.json").unlink()  # it would (rightly) disagree with the edited audit
    return job_dir


def _edit_audit(job_dir: Path, change: Callable[[Any], None]) -> None:
    data = json.loads((job_dir / "audit.json").read_text())
    change(data)
    (job_dir / "audit.json").write_text(json.dumps(data))


def _hit(kind: str, box: list[int]) -> dict[str, Any]:
    return {"frame": 5, "finding": "hit", "kind": kind, "text": None, "detail": "d", "box": box,
            "confidence": "high", "excluded_by": "i_1"}  # fmt: skip


@pytest.mark.parametrize(
    ("kind", "box", "message"),
    [
        ("face", [900, 500, 1000, 560], "whose box there doesn't overlap the finding"),  # a bystander elsewhere
        ("person", FACE_1_ON_5, r"a person finding can't be excluded by i_1 \(\['face'\]\)"),
        ("text", FACE_1_ON_5, "a text finding can't be excluded"),
        ("misaligned_redaction", FACE_1_ON_5, "a misaligned_redaction finding can't be excluded"),
        ("other", FACE_1_ON_5, "a other finding can't be excluded"),
    ],
)
def test_an_exclusion_needs_the_items_concept_and_box(tmp_path: Path, kind: str, box: list[int], message: str) -> None:
    job_dir = _example(tmp_path)
    _edit_audit(job_dir, lambda d: d["redteam"].append(_hit(kind, box)))
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_a_matching_overlapping_exclusion_validates(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit_audit(job_dir, lambda d: d["redteam"].append(_hit("face", [650, 150, 720, 240])))
    assert "audit.json" in c.validate_job_dir(job_dir)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"frames_scanned": 0, "passes": 0, "leaks": [], "redteam": []}, "12 frames weren't scanned"),
        ({"frames_scanned": 99999}, "frames_scanned 99999 > the job's 12 frames"),
        ({"passes": 0}, "a publishable audit ran no red-team pass"),
    ],
)
def test_an_audit_accounts_for_every_frame(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    job_dir = _example(tmp_path)
    _edit_audit(job_dir, lambda d: d.update(change))
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_an_unscanned_audit_that_blocks_publishing_validates(tmp_path: Path) -> None:
    # PRE-A §12: EgoBlur never ran → frames_scanned 0, its frames counted in `unresolved`.
    job_dir = _example(tmp_path)
    change = {"frames_scanned": 0, "unresolved": 12, "blocked_reason": "audit_failed"}
    _edit_audit(job_dir, lambda d: d.update(change))
    assert "audit.json" in c.validate_job_dir(job_dir)


def test_a_late_success_never_closes_a_half_open_breaker() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for _ in range(5):
        breaker.record_failure()
    now[0] = 61.0
    trial = breaker.before_call()
    assert trial
    breaker.record_success(False)  # a call admitted before the breaker opened
    assert breaker.state == "half_open"
    with pytest.raises(BreakerOpen):
        breaker.before_call()  # the trial is still in flight
    breaker.record_failure(trial)
    assert breaker.state == "open"
