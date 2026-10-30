"""The Meta transport: typed errors, retries, backoff, breaker, cost accounting (PRE-A §10, §11.4, §11.5)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from hypothesis import given
from hypothesis import strategies as st

from safecut import config
from safecut.config import ConfigError, Settings
from safecut.meta import cost
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import (
    BudgetExceeded,
    MetaAuthError,
    MetaBadRequest,
    MetaBillingError,
    MetaConfigError,
    MetaFileGone,
    MetaIncomplete,
    MetaRateLimited,
    MetaRefusal,
    MetaUnavailable,
    classify,
)
from safecut.meta.responses import meter_for
from safecut.meta.retry import CircuitBreaker, RetryPolicy, backoff_seconds, parse_retry_after
from tests.conftest import Harness, completed, stream_response, text_response


def _spec(*, attempts: int = 4, estimate: float = 0.01, stage: str = "role", model: str = "muse-spark-1.3") -> CallSpec:
    return CallSpec(
        stage=stage,
        model=model,
        estimate_usd=estimate,
        estimate_units={"input": 1, "cached": 0, "output": 1, "reasoning": 0},
        policy=RetryPolicy(attempts=attempts),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=30.0,
    )


def _meter(body: object) -> tuple[dict[str, float], float]:
    return {"n": 1}, 0.002


def _err(status: int, code: str | None = None, *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"message": "x", "type": "t", "param": None, "code": code}}, headers=headers
    )


# --- classify (R3, R13, §10.3) ------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected", "retryable"),
    [
        (401, {"error": {"message": "bad key"}}, MetaAuthError, False),
        (403, None, MetaAuthError, False),
        (402, {"error": {"message": "insufficient balance"}}, MetaBillingError, False),
        (404, None, MetaConfigError, False),
        (404, {"error": {"code": "file_not_found", "param": None}}, MetaFileGone, False),
        (404, {"error": {"code": "model_not_found"}}, MetaConfigError, False),
        (404, {"error": {"code": "something_else"}}, MetaBadRequest, False),
        (400, {"error": {"message": "bad effort", "param": "reasoning"}}, MetaConfigError, False),
        (400, {"error": {"message": "Unsupported parameter: foo"}}, MetaConfigError, False),
        (400, {"error": {"message": "bad input", "param": "input"}}, MetaBadRequest, False),
        (413, None, MetaBadRequest, False),
        (422, {"error": "nope"}, MetaBadRequest, False),
        (429, None, MetaRateLimited, True),
        (500, None, MetaUnavailable, True),
        (503, {"error": {"type": "service_overloaded"}}, MetaUnavailable, True),
        (504, None, MetaUnavailable, False),
    ],
)
def test_classify(status: int, body: object, expected: type[Exception], retryable: bool) -> None:
    err = classify(status, body, request_id="req_1")
    assert type(err) is expected
    assert err.retryable is retryable
    assert err.status == status
    assert err.request_id == "req_1"


# --- retry policy and backoff (R1, R2, R5) ------------------------------------


def test_backoff_schedule_and_retry_after() -> None:
    assert [backoff_seconds(a, None, 0.0) for a in (1, 2, 3, 4, 5, 6, 7)] == [1, 2, 4, 8, 16, 30, 30]
    assert backoff_seconds(1, None, 0.5) == 1.5
    assert backoff_seconds(1, 7.0, 0.0) == 7.0
    assert backoff_seconds(3, 1.0, 0.0) == 4.0
    with pytest.raises(MetaUnavailable, match="exceeds"):
        backoff_seconds(1, 121.0, 0.0)
    with pytest.raises(ValueError, match="start at 1"):
        backoff_seconds(0, None, 0.0)


def test_parse_retry_after() -> None:
    now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    assert parse_retry_after("7", now=now) == 7.0
    assert parse_retry_after(" 60 ", now=now) == 60.0
    assert parse_retry_after("Mon, 26 Oct 2026 12:00:30 GMT", now=now) == 30.0
    assert parse_retry_after("Mon, 26 Oct 2026 11:00:00 GMT", now=now) == 0.0
    assert parse_retry_after("-5", now=now) == 0.0
    for bad in (None, "", "soon", "nan", "inf"):
        assert parse_retry_after(bad, now=now) is None


@given(st.text(max_size=40))
def test_parse_retry_after_never_raises(value: str) -> None:
    result = parse_retry_after(value)
    assert result is None or result >= 0


def test_policy_attempts() -> None:
    assert RetryPolicy.for_responses("medium").attempts == 4
    assert RetryPolicy.for_responses("max").attempts == 2
    assert RetryPolicy.for_responses("xhigh").attempts == 2
    assert RetryPolicy.for_sam().attempts == 2
    asr = RetryPolicy.for_asr()
    assert asr.allows(1, 500)
    assert not asr.allows(2, 500)
    assert asr.allows(3, 503)
    assert not asr.allows(4, 503)


def test_breaker_opens_half_opens_and_closes() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for _ in range(5):
        breaker.before_call()
        breaker.record_failure()
    assert breaker.state == "open"
    with pytest.raises(MetaUnavailable, match="breaker"):
        breaker.before_call()
    now[0] = 61.0
    trial = breaker.before_call()  # the one trial call
    assert trial is True
    with pytest.raises(MetaUnavailable):
        breaker.before_call()  # a second concurrent trial is refused
    breaker.record_failure()  # a late, non-trial failure re-opens but keeps the trial slot taken
    assert breaker.state == "open"
    now[0] = 122.0
    with pytest.raises(MetaUnavailable):
        breaker.before_call()  # the trial hasn't reported yet
    breaker.record_failure(trial)
    now[0] = 183.0
    trial = breaker.before_call()
    breaker.record_success(trial)
    assert breaker.state == "closed"
    assert breaker.before_call() is False


def test_breaker_window_forgets_old_failures() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for t in (0, 10, 20, 30, 70):
        now[0] = float(t)
        breaker.record_failure()
    assert breaker.state == "closed"


# --- cost vectors (§11.4) -----------------------------------------------------


def test_cost_vectors() -> None:
    m = "muse-spark-1.3"
    assert cost.responses_usd(m, input_tokens=47_000, cached_tokens=0, output_tokens=4_000) == pytest.approx(0.07575)
    assert cost.responses_usd(m, input_tokens=47_000, cached_tokens=45_000, output_tokens=4_000) == pytest.approx(
        0.02625
    )
    assert cost.responses_usd(m, input_tokens=17_000, cached_tokens=0, output_tokens=16_000) == pytest.approx(0.08925)
    worst = cost.responses_estimate(m, counted=17_000, fallback=0, max_output_tokens=48_000)
    assert worst == pytest.approx(0.22525)
    assert cost.sam_video_usd(240) == pytest.approx(0.048)
    assert cost.sam_video_usd(7 * 900) == pytest.approx(1.26)
    assert cost.asr_usd(cost.asr_billed_seconds(30_500)) == pytest.approx(0.0015)
    assert cost.asr_usd(cost.asr_billed_seconds(59_999)) == pytest.approx(0.00295)
    assert cost.sam_video_estimate(10) == pytest.approx(cost.sam_video_usd(50))
    assert config.max_output_tokens("muse-spark-1.3", "max") == 48_000
    assert config.max_output_tokens("muse-wonder-1.0", "max") == 24_000
    assert config.max_output_tokens("muse-spark-1.2", "omit") == 16_000


def test_cost_rejects_bad_input() -> None:
    with pytest.raises(cost.UnknownPrice):
        cost.token_price("muse-mystery-9")
    with pytest.raises(ValueError, match="cached"):
        cost.responses_usd("muse-spark-1.3", input_tokens=10, cached_tokens=11, output_tokens=0)
    for fn in (cost.sam_video_usd, cost.sam_image_usd, cost.asr_billed_seconds):
        with pytest.raises(ValueError, match="non-negative"):
            fn(-1)


@given(
    i=st.integers(0, 10**7),
    c=st.integers(0, 10**7),
    o=st.integers(0, 10**6),
    extra=st.integers(1, 10**5),
)
def test_responses_cost_is_monotone(i: int, c: int, o: int, extra: int) -> None:
    c = min(c, i)
    base = cost.responses_usd("muse-spark-1.3", input_tokens=i, cached_tokens=c, output_tokens=o)
    assert base >= 0
    assert cost.responses_usd("muse-spark-1.3", input_tokens=i + extra, cached_tokens=c, output_tokens=o) > base
    assert cost.responses_usd("muse-spark-1.3", input_tokens=i, cached_tokens=c, output_tokens=o + extra) > base
    worst = cost.responses_estimate("muse-spark-1.3", counted=i, fallback=0, max_output_tokens=o)
    assert worst >= base


@given(
    st.recursive(
        st.none() | st.booleans() | st.integers() | st.text(max_size=5),
        lambda kids: st.dictionaries(st.text(max_size=25), kids, max_size=5),
    )
)
def test_usage_units_tolerates_any_shape(usage: object) -> None:
    units = cost.usage_units(usage if isinstance(usage, dict) else None)
    assert set(units) == {"input", "cached", "output", "reasoning"}
    assert all(v >= 0 for v in units.values())
    assert units["cached"] <= units["input"]


def test_usage_units_reads_the_documented_fields() -> None:
    usage = {
        "input_tokens": 1000,
        "input_tokens_details": {"cached_tokens": 900},
        "output_tokens": 300,
        "output_tokens_details": {"reasoning_tokens": 120},
    }
    assert cost.usage_units(usage) == {"input": 1000, "cached": 900, "output": 300, "reasoning": 120}


# --- budget ledger (§10.2, R12) ------------------------------------------------


def test_ledger_reserve_settle_release(ledger: LocalLedger) -> None:
    job = CapLimit("job", "job:a", 1.0)
    ledger.reserve("c1", "a", 0.6, [job])
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve("c2", "a", 0.5, [job])
    assert info.value.cap == "job"
    ledger.release("c1")
    ledger.release("c1")  # idempotent
    ledger.reserve("c3", "a", 0.5, [job])
    ledger.settle("c3", 0.2)
    ledger.settle("c3", 0.9)  # idempotent: the first settle wins
    assert ledger.spent("job:a") == pytest.approx(0.2)
    with pytest.raises(KeyError):
        ledger.settle("missing", 0.1)
    with pytest.raises(ValueError, match="different terms"):
        ledger.reserve("c3", "a", 0.1, [job])
    with pytest.raises(ValueError, match="negative"):
        ledger.reserve("c4", "a", -1, [job])


def test_ledger_names_the_first_cap_that_fails(ledger: LocalLedger) -> None:
    limits = [CapLimit("job", "job:a", 5.0), CapLimit("daily", "daily:2026-11-05", 0.1)]
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve("c1", "a", 0.2, limits)
    assert info.value.cap == "daily"
    assert ledger.spent("job:a") == 0


def test_ledger_sweeps_expired_reservations_as_charges() -> None:
    class Later(datetime):
        offset = timedelta(0)

        @classmethod
        def now(cls, tz: object = None) -> Later:  # type: ignore[override]  # reason: a test clock
            return datetime.now(UTC) + cls.offset  # type: ignore[return-value]  # reason: a test clock

    ledger = LocalLedger(clock=Later)
    ledger.reserve("c1", "a", 0.3, [CapLimit("job", "job:a", 1.0)])
    assert ledger.sweep_expired() == []
    Later.offset = timedelta(hours=3)
    assert ledger.sweep_expired() == ["c1"]
    assert ledger.spent("job:a") == pytest.approx(0.3)
    ledger.settle("c1", 0.0)  # no-op: no longer open
    assert ledger.spent("job:a") == pytest.approx(0.3)


@given(
    st.lists(st.tuples(st.floats(0, 1, allow_nan=False), st.sampled_from(["settle", "release", "keep"])), max_size=40)
)
def test_ledger_never_lets_spend_pass_the_cap(ops: list[tuple[float, str]]) -> None:
    ledger = LocalLedger()
    cap = CapLimit("job", "job:p", 2.0)
    for n, (usd, action) in enumerate(ops):
        try:
            ledger.reserve(f"c{n}", "p", usd, [cap])
        except BudgetExceeded:
            continue
        if action == "settle":
            ledger.settle(f"c{n}", usd / 2)
        elif action == "release":
            ledger.release(f"c{n}")
        assert ledger.spent("job:p") <= 2.0 + 1e-9


def test_daily_caller_bucket(settings: Settings) -> None:
    caller = Caller.daily(settings, "judge", "code-1")
    assert caller.limits_at(datetime(2026, 11, 5, 23, 0, tzinfo=UTC)) == (CapLimit("daily", "daily:2026-11-05", 3.0),)
    # A job still running after midnight UTC counts against the new day's bucket (audit #5 L7).
    assert caller.limits_at(datetime(2026, 11, 6, 0, 30, tzinfo=UTC)) == (CapLimit("daily", "daily:2026-11-06", 3.0),)


# --- request(): retries and cost lines (R1, R2, R3, R5, R12, R13) --------------


async def test_r1_two_429s_then_success(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=[_err(429), _err(429), httpx.Response(200, json={"id": "r_ok"})])
    result = await h.client.request("POST", "thing", _spec(), meter=_meter, json_body={})
    assert result.body == {"id": "r_ok"}
    assert result.attempts == 3
    assert h.sleeps == [1.0, 2.0]
    lines = h.costs()
    assert [(line.usd, line.estimated) for line in lines] == [(0, False), (0, False), (0.002, False)]
    assert [line.attempt for line in lines] == [1, 2, 3]
    assert lines[2].request_id == "r_ok"


async def test_r2_retry_after_is_honoured(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=[_err(429, headers={"Retry-After": "7"}), httpx.Response(200, json={})])
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert h.sleeps == [7.0]


async def test_retry_after_above_cap_stops(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=_err(503, headers={"Retry-After": "600"}))
    with pytest.raises(MetaUnavailable, match="exceeds"):
        await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 1


async def test_r3_400_is_not_retried(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=_err(400))
    with pytest.raises(MetaBadRequest):
        await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 1
    assert h.sleeps == []


async def test_r5_503_four_times(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=_err(503))
    with pytest.raises(MetaUnavailable):
        await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 4
    assert h.sleeps == [1.0, 2.0, 4.0]
    assert all(line.usd == 0 for line in h.costs())


async def test_r13_402_billing(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=_err(402))
    with pytest.raises(MetaBillingError):
        await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 1
    assert [(line.usd, line.estimated) for line in h.costs()] == [(0, False)]


async def test_connect_error_is_released_read_timeout_is_estimated(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, ledger: LocalLedger
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(
        side_effect=[httpx.ConnectError("down"), httpx.ReadTimeout("slow"), httpx.Response(200, json={})]
    )
    await h.client.request("POST", "thing", _spec(estimate=0.05), meter=_meter)
    lines = h.costs()
    assert [(line.usd, line.estimated) for line in lines] == [(0, False), (0.05, True), (0.002, False)]
    assert lines[1].units == {"input": 1, "cached": 0, "output": 1, "reasoning": 0}
    assert ledger.spent("job:j_test") == pytest.approx(0.052)


async def test_non_json_success_body_is_retried_as_unavailable(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=[httpx.Response(200, content=b"<html>"), httpx.Response(200, json={})])
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert [line.estimated for line in h.costs()] == [True, False]


async def test_r12_budget_stop_makes_no_request(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings
) -> None:
    h = make_harness(cfg=settings.model_copy(update={"job_usd_cap": 0.01}))
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(BudgetExceeded) as info:
        await h.client.request("POST", "thing", _spec(estimate=0.5), meter=_meter)
    assert info.value.cap == "job"
    assert route.call_count == 0
    (line,) = h.costs()
    assert (line.stage, line.cap, line.usd, line.attempt, line.request_id) == ("budget:role", "job", 0, 0, None)


async def test_caller_cap_line_is_written(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    caller = Caller(code_kind="eval", limits=(CapLimit("test_line", "test_line", 0.001),))
    h = make_harness(caller=caller)
    with pytest.raises(BudgetExceeded):
        await h.client.request("POST", "thing", _spec(estimate=0.01), meter=_meter)
    (line,) = h.costs()
    assert line.cap == "test_line"


async def test_r6_breaker_opens_after_five_failed_calls(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=_err(503))
    for _ in range(5):
        with pytest.raises(MetaUnavailable):
            await h.client.request("POST", "thing", _spec(attempts=1), meter=_meter)
    calls = route.call_count
    with pytest.raises(MetaUnavailable, match="breaker"):
        await h.client.request("POST", "thing", _spec(attempts=1), meter=_meter)
    assert route.call_count == calls


async def test_auth_errors_do_not_open_the_breaker(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(return_value=_err(401))
    for _ in range(6):
        with pytest.raises(MetaAuthError):
            await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert h.client.breaker.state == "closed"


async def test_throttle_delays_the_next_request(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    low = {"x-ratelimit-remaining-requests": "10", "x-ratelimit-limit-requests": "3000"}
    mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}, headers=low))
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert len(h.sleeps) == 1
    assert 0 < h.sleeps[0] <= config.THROTTLE_DELAY_S


async def test_key_is_sent_and_never_logged(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(side_effect=[_err(503), httpx.Response(200, json={})])
    caplog.set_level("DEBUG")
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test-not-a-real-key"
    assert "sk-test" not in caplog.text
    assert "sk-test" not in h.cost_path.read_text()


def test_client_needs_a_key(tmp_path: object, ledger: LocalLedger) -> None:

    with pytest.raises(ConfigError, match="MODEL_API_KEY"):
        MetaClient(Settings(), job_id="j", caller=Caller.local(), ledger=ledger, cost_path="/dev/null")


# --- stream(): terminal events, eof, refusals (R7, R8, R9) ---------------------


async def test_stream_completed_is_metered(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    usage = {"input_tokens": 47_000, "input_tokens_details": {"cached_tokens": 45_000}, "output_tokens": 4_000}
    resp = text_response('{"ok": true}', usage=usage)
    route = mock_api.post("/responses").mock(
        return_value=stream_response({"type": "response.created", "response": {"id": "resp_1"}}, completed(resp))
    )

    result = await h.client.stream(
        _spec(), {"model": "muse-spark-1.3", "store": False}, meter=meter_for("muse-spark-1.3")
    )
    assert result.response["id"] == "resp_1"
    assert result.usd == pytest.approx(0.02625)
    assert route.calls[0].request.content.find(b'"stream":true') >= 0
    (line,) = h.costs()
    assert line.units == {"input": 47_000, "cached": 45_000, "output": 4_000, "reasoning": 0}
    assert line.request_id == "resp_1"


async def test_r8_eof_then_complete(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    delta = {"type": "response.output_text.delta", "delta": "x"}
    mock_api.post("/responses").mock(
        side_effect=[stream_response(delta), stream_response(delta, completed(text_response("x")))]
    )
    result = await h.client.stream(_spec(attempts=2), {"model": "sam-3.1", "store": False}, meter=_meter)
    assert result.attempts == 2
    assert [line.estimated for line in h.costs()] == [True, False]


async def test_r9_eof_twice_is_incomplete(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/responses").mock(return_value=stream_response({"type": "response.output_text.delta", "delta": "x"}))
    with pytest.raises(MetaIncomplete) as info:
        await h.client.stream(_spec(attempts=2), {"model": "sam-3.1", "store": False}, meter=_meter)
    assert info.value.eof
    assert len(h.costs()) == 2


async def test_r7_deep_effort_timeouts_stop_after_two(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/responses").mock(side_effect=httpx.ReadTimeout("slow"))
    spec = _spec(attempts=RetryPolicy.for_responses("max").attempts)
    with pytest.raises(MetaUnavailable):
        await h.client.stream(spec, {"model": "muse-spark-1.3", "store": False}, meter=_meter)
    assert route.call_count == 2
    assert all(line.estimated for line in h.costs())


async def test_server_incomplete_is_billed_and_not_retried(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    resp = text_response("{") | {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}
    route = mock_api.post("/responses").mock(
        return_value=stream_response({"type": "response.incomplete", "response": resp})
    )
    with pytest.raises(MetaIncomplete, match="max_output_tokens") as info:
        await h.client.stream(_spec(), {"model": "muse-spark-1.3", "store": False}, meter=_meter)
    assert not info.value.eof
    assert route.call_count == 1
    assert [(line.usd, line.estimated) for line in h.costs()] == [(0.002, False)]


async def test_refusals(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    refused = {
        "id": "r",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}],
    }
    mock_api.post("/responses").mock(
        side_effect=[
            stream_response(completed(refused)),
            stream_response({"type": "response.refusal.delta", "delta": "no"}),
        ]
    )
    with pytest.raises(MetaRefusal):
        await h.client.stream(_spec(), {"model": "m", "store": False}, meter=_meter)
    with pytest.raises(MetaRefusal):
        await h.client.stream(_spec(), {"model": "m", "store": False}, meter=_meter)


async def test_stream_failed_event_is_retried(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/responses").mock(
        side_effect=[
            stream_response({"type": "response.failed", "response": {}}),
            stream_response(completed(text_response("x"))),
        ]
    )
    result = await h.client.stream(_spec(), {"model": "m", "store": False}, meter=_meter)
    assert result.attempts == 2
    assert h.sleeps == [1.0]


async def test_stream_http_error_and_malformed_data(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/responses").mock(
        side_effect=[
            _err(401),
            httpx.Response(200, content=b"data: {not json}\n\n"),
            httpx.Response(200, content=b"data: {not json}\n\n"),
        ]
    )
    with pytest.raises(MetaAuthError):
        await h.client.stream(_spec(), {"model": "m", "store": False}, meter=_meter)
    with pytest.raises(MetaUnavailable, match="malformed"):
        await h.client.stream(_spec(attempts=2), {"model": "m", "store": False}, meter=_meter)


async def test_stream_total_timeout(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()

    async def endless():  # type: ignore[no-untyped-def]  # reason: async generator for respx
        while True:
            yield b'data: {"type": "response.output_text.delta", "delta": "x"}\n\n'

            await asyncio.sleep(0.01)

    mock_api.post("/responses").mock(return_value=httpx.Response(200, content=endless()))
    spec = CallSpec(
        stage="s",
        model="m",
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=0.05,
    )
    with pytest.raises(MetaUnavailable, match="total time"):
        await h.client.stream(spec, {"model": "m", "store": False}, meter=_meter)


async def test_system_caller_logs_null_job(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings
) -> None:
    caller = Caller.daily(settings, "system", None)
    h = make_harness(job_id=None, caller=caller)
    mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}))
    await h.client.request("POST", "thing", _spec(stage="healthz"), meter=_meter)
    (line,) = h.costs()
    assert line.job_id is None
    assert line.code_kind == "system"


async def test_half_open_trial_that_gets_a_4xx_closes_the_breaker(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    now = [0.0]
    h = make_harness()
    h.client.breaker = CircuitBreaker(clock=lambda: now[0])
    route = mock_api.post("/thing").mock(return_value=_err(503))
    for _ in range(5):
        with pytest.raises(MetaUnavailable):
            await h.client.request("POST", "thing", _spec(attempts=1), meter=_meter)
    now[0] = 61.0
    route.mock(return_value=_err(400))
    with pytest.raises(MetaBadRequest):
        await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert h.client.breaker.state == "closed"
    route.mock(return_value=httpx.Response(200, json={}))
    await h.client.request("POST", "thing", _spec(), meter=_meter)


async def test_half_open_trial_stopped_by_budget_frees_the_trial(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    now = [0.0]
    h = make_harness()
    h.client.breaker = CircuitBreaker(clock=lambda: now[0])
    route = mock_api.post("/thing").mock(return_value=_err(503))
    for _ in range(5):
        with pytest.raises(MetaUnavailable):
            await h.client.request("POST", "thing", _spec(attempts=1), meter=_meter)
    now[0] = 61.0
    with pytest.raises(BudgetExceeded):
        await h.client.request("POST", "thing", _spec(estimate=99.0), meter=_meter)
    route.mock(return_value=httpx.Response(200, json={}))
    await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert h.client.breaker.state == "closed"


# --- audit #1 findings: unknown usage, slow 5xx, cancellation, guards --------------


async def test_completed_without_usage_keeps_the_estimate(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, ledger: LocalLedger
) -> None:
    h = make_harness()
    no_usage = {"id": "r", "status": "completed", "output": []}
    mock_api.post("/responses").mock(return_value=stream_response(completed(no_usage)))
    result = await h.client.stream(
        _spec(estimate=0.2), {"model": "muse-spark-1.3", "store": False}, meter=meter_for("muse-spark-1.3")
    )
    assert result.usd == pytest.approx(0.2)
    (line,) = h.costs()
    assert (line.usd, line.estimated) == (pytest.approx(0.2), True)
    assert ledger.spent("job:j_test") == pytest.approx(0.2)


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 0, "output_tokens": 0}, {"input_tokens": "7"}])
def test_meter_treats_missing_usage_as_unknown(usage: object) -> None:
    response = {} if usage is None else {"usage": usage}
    assert meter_for("muse-spark-1.3")(response) == ({}, None)


async def test_504_and_slow_5xx_count_as_accepted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(return_value=_err(504))
    with pytest.raises(MetaUnavailable):
        await h.client.request("POST", "thing", _spec(estimate=0.05), meter=_meter)
    assert [(line.usd, line.estimated) for line in h.costs()] == [(0.05, True)]

    now = [0.0]

    def slow_then_fail(_: httpx.Request) -> httpx.Response:
        now[0] += 31.0
        return _err(500)

    slow = make_harness()
    slow.client._clock = lambda: now[0]  # pyright: ignore[reportPrivateUsage] -- the injected test clock
    mock_api.post("/slow").mock(side_effect=slow_then_fail)
    with pytest.raises(MetaUnavailable):
        await slow.client.request("POST", "slow", _spec(attempts=1, estimate=0.05), meter=_meter)
    assert [line.estimated for line in slow.costs()] == [True]


async def test_cancel_before_send_releases_and_after_send_charges(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, ledger: LocalLedger
) -> None:
    gate = asyncio.Event()
    sent = asyncio.Event()
    h = make_harness()

    async def hang(_: httpx.Request) -> httpx.Response:
        sent.set()
        await gate.wait()
        return httpx.Response(200, json={})

    mock_api.post("/hang").mock(side_effect=hang)
    task = asyncio.create_task(h.client.request("POST", "hang", _spec(estimate=0.05), meter=_meter))
    # Cancelled once the request is on the wire (a fixed sleep raced it on a loaded machine: cancelled before send).
    await asyncio.wait_for(sent.wait(), timeout=30)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [(line.usd, line.estimated) for line in h.costs()] == [(0.05, True)]

    held = asyncio.Semaphore(0)
    queued = make_harness()
    queued.client._inflight = held  # pyright: ignore[reportPrivateUsage] -- force the wait before sending
    task = asyncio.create_task(queued.client.request("POST", "hang", _spec(estimate=0.05), meter=_meter))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Queued behind the process slot it never reserved (audit #13), so there is nothing to release or log.
    assert queued.costs() == []
    assert ledger.spent("job:j_test") == pytest.approx(0.05)


async def test_cancel_during_throttle_releases(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, ledger: LocalLedger
) -> None:
    h = make_harness()

    async def never(_: float) -> None:
        await asyncio.Event().wait()

    h.client._sleep = never  # pyright: ignore[reportPrivateUsage] -- block inside the throttle wait
    h.client._throttle_until = float("inf")  # pyright: ignore[reportPrivateUsage]
    task = asyncio.create_task(h.client.request("POST", "thing", _spec(estimate=0.05), meter=_meter))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ledger.spent("job:j_test") == 0


async def test_total_timeout_on_plain_requests(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()

    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    mock_api.post("/slow").mock(side_effect=slow)
    spec = CallSpec(
        stage="s",
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=0.05,
    )
    with pytest.raises(MetaUnavailable, match="total time"):
        await h.client.request("POST", "slow", spec, meter=_meter)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"model": "muse-spark-1.3-contributor"}, "Contributor"),
        ({"model": "muse-spark-1.3", "store": True}, "store"),
        ({"model": "muse-spark-1.3", "store": False, "temperature": 0.2}, "ignored or rejected"),
        ({}, "no model"),
    ],
)
async def test_stream_guards_agents_rule_6(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, body: dict[str, object], message: str
) -> None:
    h = make_harness()
    route = mock_api.post("/responses").mock(return_value=stream_response(completed(text_response("x"))))
    with pytest.raises(ValueError, match=message):
        await h.client.stream(_spec(), body, meter=_meter)
    assert route.call_count == 0


async def test_request_refuses_contributor_models(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    with pytest.raises(ValueError, match="Contributor"):
        await h.client.request("POST", "chat/completions", _spec(), meter=_meter, json_body={"model": "x-contributor"})


def test_job_id_and_system_caller_must_agree(settings: Settings, ledger: LocalLedger) -> None:
    with pytest.raises(ValueError, match="system"):
        MetaClient(settings, job_id=None, caller=Caller.local(), ledger=ledger, cost_path="/dev/null")
    caller = Caller.daily(settings, "system", None)
    with pytest.raises(ValueError, match="system"):
        MetaClient(settings, job_id="j", caller=caller, ledger=ledger, cost_path="/dev/null")


def test_free_calls_pass_a_spent_cap(ledger: LocalLedger) -> None:
    job = CapLimit("job", "job:z", 1.0)
    ledger.reserve("c1", "z", 1.0, [job])
    ledger.settle("c1", 1.5)
    ledger.reserve("c2", "z", 0.0, [job])  # a delete or a token count is never blocked
    with pytest.raises(BudgetExceeded):
        ledger.reserve("c3", "z", 0.01, [job])


def test_ledger_file_is_shared_safely(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    one, two = LocalLedger(path), LocalLedger(path)
    cap = CapLimit("job", "job:s", 1.0)
    one.reserve("a", "s", 0.6, [cap])
    with pytest.raises(BudgetExceeded):
        two.reserve("b", "s", 0.6, [cap])
    one.close()
    two.close()
