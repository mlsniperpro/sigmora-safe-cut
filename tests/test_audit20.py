"""Tests for audit #20: the publish gate checks regions, not just frames (a hit needs a leak on its box, a patch
must cover the leak's box, an exclusion must be a kept item), refusals carry no model text, and the probe
start-up survives a damaged cost record."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from safecut import contracts as c
from safecut.meta.errors import MetaRefusal
from scripts.probes import probes

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"
HIT = {"frame": 10, "finding": "hit", "kind": "text", "text": "A", "detail": "a name", "box": [900, 500, 1000, 560],
       "confidence": "high", "excluded_by": None}  # fmt: skip


def _example(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    (job_dir / "receipt.json").unlink()  # it would (rightly) disagree with the edited audit
    return job_dir


def _edit_audit(job_dir: Path, change: Callable[[Any], None]) -> None:
    data = json.loads((job_dir / "audit.json").read_text())
    change(data)
    (job_dir / "audit.json").write_text(json.dumps(data))


def test_a_hit_needs_a_leak_on_its_own_box() -> None:
    # The example already has a face leak on frame 10; a text hit elsewhere on that frame isn't covered by it.
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    with pytest.raises(ValidationError, match="neither excluded nor a leak on its box"):
        c.Audit.model_validate(audit | {"redteam": [*audit["redteam"], HIT]})


@pytest.mark.parametrize("item", ["i_3", "i_2", "p_1"])
def test_only_a_kept_item_can_exclude_a_hit(tmp_path: Path, item: str) -> None:
    job_dir = _example(tmp_path)
    _edit_audit(job_dir, lambda d: d["redteam"].append(HIT | {"excluded_by": item}))
    with pytest.raises(c.ContractError, match=f"excluded_by {item}, which isn't a kept item"):
        c.validate_job_dir(job_dir)


def test_a_patch_must_cover_the_leak_box(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def move(d: Any) -> None:
        d["leaks"][0]["box"] = [900, 500, 1000, 560]  # p_1 hides [200, 200, 260, 280]
        d["redteam"] = [r for r in d["redteam"] if r["finding"] == "none"]

    _edit_audit(job_dir, move)
    with pytest.raises(c.ContractError, match=r"p_1 doesn't cover box \[900, 500, 1000, 560\] on frame 10"):
        c.validate_job_dir(job_dir)


def test_a_spot_cover_must_hide_all_its_frames(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    spot = {"spot_id": "s1", "first": 0, "last": 2, "boxes": {"2": [200, 200, 260, 280]}, "covered_by": "p_1"}
    _edit_audit(job_dir, lambda d: d["spots"].append(spot))
    with pytest.raises(c.ContractError, match=r"spot s1 cover: p_1 doesn't hide frames \[0, 1\]"):
        c.validate_job_dir(job_dir)


def test_a_refusal_never_carries_the_model_text() -> None:
    error = MetaRefusal.of("I can read 0712 345 678 on the card, but I won't")
    assert "0712" not in str(error)
    assert "characters" in str(error)
    assert error.refusal_text.startswith("I can read")


def test_a_damaged_cost_record_stops_the_probes_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    (root / "fixtures" / "probes").mkdir(parents=True)
    (root / "fixtures" / "probes" / "cost.jsonl").write_text('{"torn": \n')
    monkeypatch.setattr(probes, "ROOT", root)
    assert probes.main(["a"]) == 2
    assert "is damaged, so the spend so far is unknown" in capsys.readouterr().err
