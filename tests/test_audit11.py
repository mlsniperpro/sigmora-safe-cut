"""Tests for audit #11: a failed open-weight opinion keeps its entries in audit.json, and a malformed box keeps
its finding as a whole-frame one instead of failing the batch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from safecut import open_weight
from safecut.contracts import Audit

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"
ENTRY = {"frame": 0, "finding": "none"}


def _audit(status: str, **summary: Any) -> dict[str, Any]:
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    model = None if status == "off" else "meta-models/muse-spark-open-1026"
    audit["open_weight"] = {"model": model, "status": status, **summary}
    audit["redteam_open"] = [ENTRY]
    return audit


def test_a_failed_opinion_keeps_its_entries() -> None:
    audit = Audit.model_validate(_audit("failed", frames=8, findings=1))
    assert audit.open_weight.status == "failed"
    assert len(audit.redteam_open) == 1


def test_an_opinion_that_never_ran_has_no_entries() -> None:
    with pytest.raises(ValidationError, match="ran"):
        Audit.model_validate(_audit("off"))


@pytest.mark.parametrize("box", [[327.5, 462, 556, 550], "none", [1, 2, 3], [True, 2, 3, 4], None])
def test_a_malformed_box_is_a_whole_frame_finding(box: Any) -> None:
    good = {"kind": "text", "detail": "a name", "text": "AMINA K.", "box": [1, 2, 3, 4], "confidence": "high"}
    bad = {"kind": "face", "detail": "a face", "box": box, "confidence": "low"}  # no "text" key either
    answer = {"text": json.dumps({"frames": [{"frame": 0, "findings": [good, bad]}]}), "finish_reason": "stop"}
    parsed = open_weight.complete_answer(answer, [0])
    kept_good, kept_bad = parsed.frames[0].findings
    assert kept_good.box == (1, 2, 3, 4)
    assert kept_bad.box is None  # fail closed: WP4 treats it as the whole frame
    assert kept_bad.text is None
