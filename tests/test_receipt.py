"""WP4 step 3: the privacy receipt. The full SAFETY chain on a synthetic job ends in a receipt that validates against
every other job file; tampering breaks the hash; re-renders chain; the page is self-contained and holds no private
red-team text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecut import contracts, pipeline
from safecut.audit import run as audit_run
from safecut.config import Settings
from safecut.contracts import Audit, ContractError, CostLine, Receipt, append_cost_line, load
from safecut.decide import run as decide_run
from safecut.guard import run as guard_run
from safecut.receipt import RECEIPT, RECEIPT_HTML, ReceiptError, history, verify_chain
from safecut.receipt import run as receipt_run
from safecut.receipt.__main__ import main as cli
from safecut.receipt.build import BASETEN_NOTE, SYNTHETIC_NOTE, YUNET_NOTE, build, data_handling
from safecut.render import render
from tests.safety_jobs import make_job

SETTINGS = Settings(egoblur_model="yunet-face")


@pytest.fixture
def job_dir(tmp_path: Path) -> Path:
    job_dir = make_job(tmp_path)
    for stage in (decide_run, guard_run):
        stage(job_dir)
    pipeline.approve(job_dir, how="auto_policy")
    render(job_dir)
    audit_run(job_dir, replay=True, settings=SETTINGS)
    return job_dir


def test_the_receipt_matches_every_job_file(job_dir: Path) -> None:
    receipt_run(job_dir, settings=SETTINGS)
    contracts.validate_job_dir(job_dir)  # items, audit counts, models, store claims, costs: cross-checked
    receipt = load(job_dir / RECEIPT, Receipt)
    assert [i.thumbnail for i in receipt.items] == ["thumbs/i_1.jpg", "thumbs/i_2.jpg"]
    assert receipt.models["auditor"] == "yunet-face"
    assert receipt.models["scene"] == "muse-spark-1.3"
    assert "redteam" not in receipt.models  # the synthetic oracle is no model
    assert receipt.data_handling.no_store_param == ["muse-voice-transcribe-1.0"]
    assert set(receipt.data_handling.store_by_model.values()) == {False}
    assert receipt.data_handling.notes == [SYNTHETIC_NOTE, YUNET_NOTE]
    assert receipt.prev_hash is None
    assert verify_chain([receipt])


def test_tampering_with_any_field_breaks_the_hash(job_dir: Path) -> None:
    receipt_run(job_dir, settings=SETTINGS)
    raw = json.loads((job_dir / RECEIPT).read_text())
    raw["items"][1]["decision"] = "keep"
    raw["items"][1]["style"] = None
    (job_dir / RECEIPT).write_text(json.dumps(raw))
    with pytest.raises(ContractError, match="hash"):
        load(job_dir / RECEIPT, Receipt)
    assert cli(["verify", str(job_dir / RECEIPT)]) == 1
    with pytest.raises(ContractError):
        receipt_run(job_dir, settings=SETTINGS)  # never chains from a tampered receipt
    (job_dir / RECEIPT).unlink()
    receipt_run(job_dir, settings=SETTINGS)
    forged = load(job_dir / RECEIPT, Receipt).model_copy(update={"cost_usd": 99.0})  # unvalidated copy
    assert not verify_chain([forged])


def test_a_re_render_chains_from_the_previous_receipt(job_dir: Path) -> None:
    receipt_run(job_dir, settings=SETTINGS)
    first = load(job_dir / RECEIPT, Receipt)
    receipt_run(job_dir, settings=SETTINGS)
    second = load(job_dir / RECEIPT, Receipt)
    assert second.prev_hash == first.hash
    chain = history(job_dir)
    assert [r.hash for r in chain] == [first.hash, second.hash]
    assert verify_chain(chain)
    assert not verify_chain([second, first])
    assert cli(["verify", str(job_dir / "receipts" / f"{first.hash}.json"), str(job_dir / RECEIPT)]) == 0
    assert cli(["nope"]) == 2


def test_the_page_is_self_contained_and_says_what_happened(job_dir: Path) -> None:
    (job_dir / "audit.json").write_text((job_dir / "audit.json").read_text())
    receipt_run(job_dir, settings=SETTINGS)
    page = (job_dir / RECEIPT_HTML).read_text()
    assert "Audit passed" in page
    assert "synthetic ground-truth oracle" in page
    assert "none was called" in page
    assert page.count("data:image/jpeg;base64,") == 2
    assert "http://" not in page
    assert "https://" not in page
    assert load(job_dir / RECEIPT, Receipt).hash in page
    assert "<script" not in page
    # Auto-approved: the page never claims a creator's review, nor more than the audit checked.
    assert "accepted without review (auto-approve)" in page
    assert "approved by the creator" not in page
    assert "Every output frame was checked" not in page


def test_a_blocked_audit_is_receipted_as_blocked_and_costs_add_up(job_dir: Path) -> None:
    audit = json.loads((job_dir / "audit.json").read_text())
    audit.update({"unresolved": 2, "blocked_reason": "audit_failed"})
    (job_dir / "audit.json").write_text(json.dumps(audit))
    line = CostLine.model_validate({
        "ts": "2026-10-30T12:00:00Z", "provider": "meta", "job_id": "j_synth", "stage": "redteam",
        "model": "muse-spark-1.3", "attempt": 1, "units": {"input": 1000.0}, "usd": 0.0123, "estimated": False,
        "request_id": "r1", "code_kind": "owner", "code_id": None,
    })  # fmt: skip
    append_cost_line(line, job_dir / "cost.jsonl")
    receipt_run(job_dir, settings=SETTINGS)
    contracts.validate_job_dir(job_dir)
    receipt = load(job_dir / RECEIPT, Receipt)
    assert receipt.cost_usd == pytest.approx(0.0123)
    assert (receipt.audit.unresolved, receipt.audit.blocked_reason) == (2, "audit_failed")
    assert "Publishing blocked" in (job_dir / RECEIPT_HTML).read_text()
    assert SYNTHETIC_NOTE not in receipt.data_handling.notes  # a paid call: "no model was called" would be false


def test_a_second_opinion_on_baseten_is_disclosed(job_dir: Path) -> None:
    audit = load(job_dir / "audit.json", Audit)
    models = {"auditor": "yunet-face", "open_weight": "meta-models/muse-spark-open-1026"}
    handling = data_handling(job_dir, models, audit)
    assert BASETEN_NOTE in handling.notes
    assert "meta-models/muse-spark-open-1026" in handling.no_store_param
    assert BASETEN_NOTE not in data_handling(job_dir, {"auditor": "yunet-face"}, audit).notes


def test_no_receipt_before_the_audit(tmp_path: Path) -> None:
    job_dir = make_job(tmp_path)
    decide_run(job_dir)
    with pytest.raises(ReceiptError):
        build(job_dir, SETTINGS)


def test_no_receipt_without_the_creators_approval(job_dir: Path) -> None:
    (job_dir / "approval.json").unlink()
    with pytest.raises(ReceiptError, match="approval"):
        receipt_run(job_dir, settings=SETTINGS)


def test_the_example_job_receipt_still_verifies() -> None:
    """The contract change (removed_by_creator, written only when true) leaves sealed receipts' hashes intact."""
    receipt = load(Path("fixtures/contracts/j_example/receipt.json"), Receipt)
    assert verify_chain([receipt])
