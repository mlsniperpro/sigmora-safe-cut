"""Tests for audit #12: the publish gate tied to the leaks, a reserve failure after an accepted attempt still
reported as maybe processed, a missing box kept as a whole-frame finding, and probe b deleting SAM responses
on its failure paths."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from safecut import contracts as c
from safecut import open_weight
from safecut.config import Settings
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaUnavailable
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests import test_probes_replay as replay
from tests.conftest import narrow_patch, stream_response
from tests.test_audit9 import _replay_routes  # pyright: ignore[reportPrivateUsage] -- the shared replay server

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _audit() -> dict[str, Any]:
    """The example audit without its red-team hit, so a test can swap the leaks freely (audit #18 ties a
    non-excluded hit to a leak on its frame)."""
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    audit["redteam"] = [r for r in audit["redteam"] if r["finding"] == "none"]
    return audit


def _leak(**fields: Any) -> dict[str, Any]:
    return {"frame": 4, "box": [10, 10, 50, 50], "kind": "face", "detector": "egoblur", "patched_item": None} | fields


def test_an_unresolved_leak_must_be_counted() -> None:
    audit = _audit() | {"leaks": [_leak(unresolved=True)], "unresolved": 0, "blocked_reason": None}
    with pytest.raises(ValidationError, match="unresolved 0 is less than the 1 unresolved leaks"):
        c.Audit.model_validate(audit)
    counted = c.Audit.model_validate(audit | {"unresolved": 1, "blocked_reason": "unresolved_leaks"})
    assert not counted.no_unresolved


def test_a_leak_is_patched_flagged_or_unresolved() -> None:
    with pytest.raises(ValidationError, match="neither patched"):
        c.Audit.model_validate(_audit() | {"leaks": [_leak()]})


def test_open_weight_counts_match_its_entries() -> None:
    audit = _audit() | {
        "open_weight": {"model": "m", "status": "ok", "frames": 40, "findings": 7},
        "redteam_open": [{"frame": 0, "finding": "none"}],
    }
    with pytest.raises(ValidationError, match="redteam_open holds 1 frames and 0 findings"):
        c.Audit.model_validate(audit)


def test_a_receipt_may_record_a_blocked_audit() -> None:
    # PRE-A §10.3: the receipt stage runs after [Run the audit again] even when the audit stays blocked.
    receipt = json.loads((EXAMPLE / "receipt.json").read_text())
    blocked = c.ReceiptAudit.model_validate(receipt["audit"] | {"unresolved": 2, "blocked_reason": "unresolved_leaks"})
    assert blocked.unresolved == 2


@pytest.mark.parametrize(
    ("item", "message"), [("i_1", "i_1 is a kept item"), ("p_1", r"p_1 doesn't hide frames \[1\]")]
)
def test_a_patch_must_hide_the_leak_frame(tmp_path: Path, item: str, message: str) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    narrow_patch(job_dir, 2)
    audit = json.loads((job_dir / "audit.json").read_text())
    frame = 1 if item == "p_1" else audit["leaks"][0]["frame"]
    audit["leaks"][0].update({"patched_item": item, "frame": frame})
    audit["redteam"] = [r for r in audit["redteam"] if r["finding"] == "none"]
    (job_dir / "audit.json").write_text(json.dumps(audit))
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


async def test_a_ledger_fault_after_an_accepted_attempt_keeps_maybe_processed(
    settings: Settings, tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    # A paid call (free calls never reserve since audit #13): attempt 1 times out after sending (it may
    # have been processed), attempt 2's reserve fails; the error must still say "maybe processed".
    class FailsSecondReserve(LocalLedger):
        calls = 0

        def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
            self.calls += 1
            if self.calls >= 2:
                raise ValueError("ledger refused")  # → MetaUnavailable, no retry
            super().reserve(call_id, job_id, usd, limits)

    ledger = FailsSecondReserve()
    client = MetaClient(
        settings, job_id="j", caller=Caller.local(), ledger=ledger, cost_path=tmp_path / "c.jsonl", sleep=_no_sleep
    )
    route = mock_api.post("/thing").mock(side_effect=httpx.ReadTimeout("slow"))
    spec = CallSpec(
        stage="s",
        model="muse-spark-1.3",
        estimate_usd=0.05,
        estimate_units={},
        policy=RetryPolicy(attempts=4),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )
    with pytest.raises(MetaUnavailable, match="ledger") as info:
        await client.request("POST", "thing", spec, meter=lambda _: ({}, 0.0))
    await client.aclose()
    assert (route.call_count, ledger.calls) == (1, 2)
    assert info.value.maybe_processed


async def _no_sleep(_: float) -> None:
    return None


def test_a_missing_box_is_a_whole_frame_finding() -> None:
    good = {"kind": "text", "detail": "a name", "text": "A", "box": [1, 2, 3, 4], "confidence": "high"}
    no_box = {"kind": "face", "detail": "a face", "confidence": "low"}
    answer = {"text": json.dumps({"frames": [{"frame": 0, "findings": [good, no_box]}]}), "finish_reason": "stop"}
    kept = open_weight.complete_answer(answer, [0]).frames[0].findings
    assert [f.box for f in kept] == [(1, 2, 3, 4), None]


async def test_probe_b_deletes_sam_responses_on_failure_paths(settings: Settings, tmp_path: Path) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    replay.SAM_CREATED.clear()
    deleted: list[str] = []
    calls = 0

    def sometimes_fails(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if json.loads(request.content)["model"] != "sam-3.1":
            return replay._responses(request)  # pyright: ignore[reportPrivateUsage] -- the replay answers
        calls += 1
        if calls % 2:
            return replay._sam_stream()  # pyright: ignore[reportPrivateUsage] -- the replay SAM stream
        rid = f"resp_failed_{calls}"
        replay.SAM_CREATED.append(rid)
        created = {"type": "response.created", "response": {"id": rid, "status": "in_progress"}}
        return stream_response(created, {"type": "response.failed", "response": {"id": rid, "status": "failed"}})

    with respx.mock(assert_all_called=False) as router:
        _replay_routes(router, deleted)
        router.post(f"{replay.BASE}/responses").mock(side_effect=sometimes_fails)
        results = await probes.run(["b"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    assert "error" not in results["b"], results["b"]  # failed attempts were retried; their responses stay stored
    assert any(rid.startswith("resp_failed_") for rid in replay.SAM_CREATED)
    assert set(deleted) == set(replay.SAM_CREATED)
