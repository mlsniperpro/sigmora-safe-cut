"""Live smoke tests against the real Meta Model API. Deselected by default (``-m "not live"``).

Run with ``MODEL_API_KEY`` set: ``uv run pytest -m live``. Spend: one minimal Muse Spark call
(≤ $0.003) plus free status, model-list and token-count calls; logged to ``jobs/live/cost.jsonl``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from safecut.config import load_settings
from safecut.contracts import read_cost_lines
from safecut.meta import responses
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaIncomplete
from safecut.meta.retry import RetryPolicy
from safecut.meta.status import fetch_status

pytestmark = pytest.mark.live
COST_PATH = Path(__file__).resolve().parent.parent / "jobs" / "live" / "cost.jsonl"


def _client() -> MetaClient:
    caller = Caller(code_kind="owner", limits=(CapLimit("code", "live-tests", 0.05),))
    return MetaClient(load_settings(), job_id="live_smoke", caller=caller, ledger=LocalLedger(), cost_path=COST_PATH)


async def test_status_is_reachable() -> None:
    async with httpx.AsyncClient(trust_env=False) as http:
        status = await fetch_status(http, load_settings().meta_base_url)
    assert status.is_alive


async def test_key_lists_the_configured_models() -> None:
    settings = load_settings()
    spec = CallSpec(
        stage="live_models",
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(attempts=2),
        timeout=httpx.Timeout(30.0),
        total_timeout_s=60.0,
    )
    async with _client() as client:
        result = await client.request("GET", "models", spec, meter=lambda _: ({}, 0.0))
    ids = {m["id"] for m in result.body["data"]}
    assert {settings.role_model, settings.sam_model} <= ids


async def test_minimal_spark_call_is_metered() -> None:
    settings = load_settings()
    body = responses.build_body(
        settings.role_model,
        [{"role": "user", "content": [{"type": "input_text", "text": "Reply with the word ok."}]}],
        effort="minimal",
        max_output_tokens=512,
    )
    before = len(list(read_cost_lines(COST_PATH)))
    async with _client() as client:
        try:
            result = await responses.create(client, body, stage="live_smoke", effort="minimal")
        except MetaIncomplete:
            pass  # reasoning used the whole budget: still a working, billed call (PRE-A §10.7)
        else:
            assert result.response.get("status") == "completed"
    paid = [line for line in list(read_cost_lines(COST_PATH))[before:] if line.stage == "live_smoke"]
    assert paid
    assert all(not line.estimated and 0 < line.usd < 0.01 for line in paid)
