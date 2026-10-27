"""Tests for audit #19: patches in an item's extend/backfill frames and merged items with gaps validate, model
output never reaches error text, a budget stop survives a failed cost write, and the probe cap spans runs."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel

from safecut import contracts as c
from safecut.config import Settings
from safecut.meta import responses
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import BudgetExceeded
from safecut.meta.responses import InvalidOutputError
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import Harness, completed, stream_response, text_response

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _example(tmp_path: Path) -> Path:
    """The example job without its receipt, which would (rightly) disagree with the edited files."""
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    (job_dir / "receipt.json").unlink()
    return job_dir


def _edit(job_dir: Path, name: str, change: Callable[[Any], None]) -> None:
    data = json.loads((job_dir / name).read_text())
    change(data)
    (job_dir / name).write_text(json.dumps(data))


def test_a_patch_on_an_extend_frame_validates(tmp_path: Path) -> None:
    # i_2 (face:2, frames 5-9) is rendered one frame past its track by the guard's extend: a flagged leak there
    # names it as the item read through and the item re-rendered.
    job_dir = _example(tmp_path)
    entry = {"item_id": "i_2", "shape": "box", "box": [100, 300, 170, 392], "mask": None, "style": "solid",
             "grid": None, "source": "decision"}  # fmt: skip
    _edit(job_dir, "plan.json", lambda d: d["frames"]["10"].append(entry))
    leak = {"frame": 10, "box": [100, 300, 170, 392], "kind": "text", "detector": "redteam", "patched_item": "i_2",
            "flag": "redaction_too_weak", "through_item": "i_2"}  # fmt: skip
    _edit(job_dir, "audit.json", lambda d: d["leaks"].append(leak))
    assert "audit.json" in c.validate_job_dir(job_dir)


def test_a_merged_item_needs_no_entry_in_its_tracks_gap(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def add_track(d: Any) -> None:
        late = json.loads(json.dumps(next(t for t in d["tracks"] if t["track_id"] == "screen:1")))
        late.update({"track_id": "screen:2", "first": 10, "last": 11, "boxes": {"10": late["boxes"]["1"]}})
        late["sam_object"]["object_id"] = "7"
        d["tracks"].append(late)

    _edit(job_dir, "tracks.json", add_track)
    _edit(
        job_dir,
        "decisions.json",
        lambda d: next(i for i in d["items"] if i["item_id"] == "i_3")["track_ids"].append("screen:2"),
    )

    def plan_late(d: Any) -> None:
        entry = next(e for e in d["frames"]["5"] if e["item_id"] == "i_3")
        for frame in ("10", "11"):
            d["frames"].setdefault(frame, []).append(entry)

    _edit(job_dir, "plan.json", plan_late)
    # Frames 6-9 lie between the two tracks: no entry is required there (audit #19).
    loaded = c.validate_job_dir(job_dir)
    assert "plan.json" in loaded


class _Verdict(BaseModel):
    role: str


async def test_invalid_model_output_never_reaches_the_error_text(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    card = "4111111111111111"
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(200, json={"input_tokens": 10}))
    mock_api.post("/responses").mock(return_value=stream_response(completed(text_response(f'{{"role": {card}}}'))))
    message = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
    body = {
        "model": "muse-spark-1.3",
        "max_output_tokens": 50,
        "store": False,
        "reasoning": {"effort": "medium"},
        "input": [message],
    }
    with pytest.raises(InvalidOutputError) as info:
        await responses.create_json(h.client, _Verdict, body, stage="role", effort="medium")
    assert card not in str(info.value)


async def test_a_budget_stop_survives_a_failed_cost_write(settings: Settings, tmp_path: Path) -> None:
    blocked = tmp_path / "cost.jsonl"
    blocked.mkdir()  # every cost write fails
    ledger = LocalLedger()
    caller = Caller(code_kind="owner", limits=(CapLimit("code", "c", 0.01),))
    client = MetaClient(settings, job_id="j", caller=caller, ledger=ledger, cost_path=blocked)
    spec = CallSpec(
        stage="s",
        model="muse-spark-1.3",
        estimate_usd=0.05,
        estimate_units={},
        policy=RetryPolicy(attempts=1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )
    with pytest.raises(BudgetExceeded):
        await client.request("POST", "thing", spec, meter=lambda _: ({}, 0.0))
    await client.aclose()


def test_the_probe_cap_counts_earlier_runs(tmp_path: Path) -> None:
    cost = tmp_path / "cost.jsonl"
    line = {"ts": "2026-10-27T10:00:00Z", "provider": "meta", "job_id": "probe_b", "stage": "probe_b",
            "model": "sam-3.1", "attempt": 1, "units": {}, "usd": 5.9, "estimated": False, "request_id": "r",
            "code_kind": "owner", "code_id": None}  # fmt: skip
    c.append_cost_line(c.CostLine.model_validate(line), cost)
    ledger = probes.seeded_ledger(cost)
    assert ledger.spent("wp0-probes") == pytest.approx(5.9)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("next", "probe_c", 0.2, [CapLimit("code", "wp0-probes", probes.PROBE_BUDGET_USD)])
    c.append_cost_line(c.CostLine.model_validate(line | {"usd": 0.5}), cost)
    with pytest.raises(BudgetExceeded):
        probes.seeded_ledger(cost)  # $6.40 already spent: a new container refuses to start
