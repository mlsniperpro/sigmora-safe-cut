"""Failure injection: random outcome sequences never break the accounting or the typed-error contract.

Invariants, for any sequence of server behaviours:
1. a call returns or raises a ``MetaError`` (``BudgetExceeded`` included), nothing else;
2. the ledger's job total equals the sum of ``usd`` over ``cost.jsonl`` (no lost or double charge);
3. the server sees at most ``policy.attempts`` requests per call;
4. every ``estimated`` line carries the reserved estimate, every measured one the metered amount or 0.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr

from safecut.config import Settings
from safecut.contracts import read_cost_lines
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaError
from safecut.meta.retry import RetryPolicy
from tests.conftest import BASE, completed, stream_response, text_response

OUTCOMES = ["ok", "429", "500", "503", "504", "400", "402", "connect", "read_timeout", "garbage", "eof", "no_usage"]
ESTIMATE = 0.05
METERED = 0.002


def _respond(kind: str) -> httpx.Response:
    if kind == "ok":
        return stream_response(completed(text_response("x", usage={"input_tokens": 10, "output_tokens": 1})))
    if kind == "no_usage":
        return stream_response(completed({"id": "r", "status": "completed", "output": []}))
    if kind == "eof":
        return stream_response({"type": "response.output_text.delta", "delta": "x"})
    if kind == "garbage":
        return httpx.Response(200, content=b"data: {broken\n\n")
    if kind == "connect":
        raise httpx.ConnectError("down")
    if kind == "read_timeout":
        raise httpx.ReadTimeout("slow")
    return httpx.Response(int(kind), json={"error": {"message": kind}})


def _meter(response: object) -> tuple[dict[str, float], float | None]:
    if isinstance(response, dict) and "usage" in response:
        return {"n": 1}, METERED
    return {}, None


@given(
    calls=st.lists(st.lists(st.sampled_from(OUTCOMES), min_size=1, max_size=5), min_size=1, max_size=6),
    attempts=st.integers(1, 4),
    cap=st.sampled_from([0.04, 0.2, 3.0]),
)
def test_accounting_survives_any_failure_sequence(calls: list[list[str]], attempts: int, cap: float) -> None:
    asyncio.run(_scenario(calls, attempts, cap))


async def _scenario(calls: list[list[str]], attempts: int, cap: float) -> None:
    ledger = LocalLedger()
    with tempfile.TemporaryDirectory() as tmp:
        cost_path = Path(tmp) / "cost.jsonl"
        settings = Settings(model_api_key=SecretStr("k"), job_usd_cap=cap)

        async def no_sleep(_: float) -> None:
            return None

        client = MetaClient(
            settings,
            job_id="j_chaos",
            caller=Caller.local("eval"),
            ledger=ledger,
            cost_path=cost_path,
            sleep=no_sleep,
            jitter=lambda: 0.0,
        )
        spec = CallSpec(
            stage="chaos",
            model="muse-spark-1.3",
            estimate_usd=ESTIMATE,
            estimate_units={"n": 0},
            policy=RetryPolicy(attempts=attempts),
            timeout=httpx.Timeout(5.0),
            total_timeout_s=5.0,
        )
        with respx.mock(base_url=BASE, assert_all_called=False) as router:
            for script in calls:
                queue = list(script)
                route = router.post("/responses").mock(
                    side_effect=lambda _r, q=queue: _respond(q.pop(0) if q else "ok")
                )
                before = route.call_count
                with contextlib.suppress(MetaError):
                    await client.stream(spec, {"model": "muse-spark-1.3"}, meter=_meter)
                assert route.call_count - before <= attempts
        await client.aclose()
        lines = list(read_cost_lines(cost_path))
        assert sum(line.usd for line in lines) == pytest.approx(ledger.spent("job:j_chaos"))
        for line in lines:
            if line.estimated:
                assert line.usd == ESTIMATE
            elif not line.stage.startswith("budget:"):
                assert line.usd in (0.0, METERED)
        assert ledger.spent("job:j_chaos") <= cap + ESTIMATE
