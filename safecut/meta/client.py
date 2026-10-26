"""The Meta Model API transport: one attempt loop for every call (PRE-A §10.1–10.3, §10.5).

Each attempt reserves its worst-case estimate against the caps, runs under the process concurrency
bound, and is accounted honestly in ``cost.jsonl``: rejected before processing → released, ``usd 0``;
accepted then lost → kept as an ``estimated`` charge; completed → the actual cost from ``usage``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import orjson

from safecut import __version__, config
from safecut.config import Settings
from safecut.contracts import CostLine, append_cost_line, now_utc
from safecut.meta.budget import Caller, Ledger, job_limit
from safecut.meta.errors import (
    BudgetExceeded,
    MetaError,
    MetaIncomplete,
    MetaRefusal,
    MetaUnavailable,
    classify,
)
from safecut.meta.retry import CircuitBreaker, RetryAfterTooLong, RetryPolicy, backoff_seconds, parse_retry_after
from safecut.meta.sse import SSEDecodeError, aiter_sse

log = logging.getLogger("safecut.meta")

Units = dict[str, float]
#: Turns a completed response (decoded body or final ``response`` object) into ``(units, usd)``.
Meter = Callable[[Mapping[str, Any]], tuple[Units, float]]
Lane = Literal["sam", "responses", "other"]

_EMPTY: Mapping[str, Any] = {}


@dataclass(frozen=True)
class CallSpec:
    """What one logical call is: its stage, model, worst-case cost and retry/timeouts."""

    stage: str
    model: str | None
    estimate_usd: float
    estimate_units: Units
    policy: RetryPolicy
    timeout: httpx.Timeout
    lane: Lane = "other"
    total_timeout_s: float | None = None


@dataclass(frozen=True)
class CallResult:
    body: Any
    headers: Mapping[str, str]
    request_id: str | None
    attempts: int
    usd: float


@dataclass(frozen=True)
class StreamResult:
    events: list[dict[str, Any]]
    response: dict[str, Any]
    request_id: str | None
    attempts: int
    usd: float


@dataclass
class _Attempt:
    """What one attempt produced. ``error`` set with ``billed`` means: account, then raise it."""

    value: Any = None
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    request_id: str | None = None
    units: Units = field(default_factory=dict[str, float])
    usd: float = 0.0
    error: MetaError | None = None


class _AttemptFailed(Exception):
    """An attempt failed. ``accepted`` means the server may have processed (and billed) it."""

    def __init__(self, error: MetaError, *, accepted: bool, retry_after: float | None = None) -> None:
        super().__init__(str(error))
        self.error = error
        self.accepted = accepted
        self.retry_after = retry_after


def _decode(raw: bytes) -> Any:
    if not raw.strip():
        return None
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None


def _request_id(headers: Mapping[str, str], body: Any) -> str | None:
    if isinstance(body, dict):
        rid = cast(dict[str, Any], body).get("id")
        if isinstance(rid, str):
            return rid
    return headers.get("x-request-id")


def _transport_failure(exc: httpx.TransportError) -> _AttemptFailed:
    """Connect-phase errors never reached the server; anything later may have been processed."""
    rejected = isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout)
    kind = "timeout" if isinstance(exc, httpx.TimeoutException) else "connection error"
    return _AttemptFailed(MetaUnavailable(f"{kind}: {type(exc).__name__}"), accepted=not rejected)


class MetaClient:
    """Async client for ``https://api.meta.ai/v1`` (or another OpenAI-style base such as Baseten's).

    Use one per job; share ``http``/``breaker``/``inflight`` across jobs in one process.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        job_id: str | None,
        caller: Caller,
        ledger: Ledger,
        cost_path: str | Path,
        http: httpx.AsyncClient | None = None,
        breaker: CircuitBreaker | None = None,
        inflight: asyncio.Semaphore | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.settings = settings
        self.job_id = job_id
        self.caller = caller
        self.ledger = ledger
        self.cost_path = Path(cost_path)
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=config.MAX_CONNECTIONS),
            timeout=httpx.Timeout(60.0, connect=config.CONNECT_TIMEOUT_S),
        )
        self.base_url = (base_url or settings.meta_base_url).rstrip("/")
        self._key = api_key if api_key is not None else settings.api_key()
        self.breaker = breaker or CircuitBreaker(clock=clock)
        self._inflight = inflight or asyncio.Semaphore(config.PROCESS_INFLIGHT)
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock
        self._throttle_until = 0.0

    async def __aenter__(self) -> MetaClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # -- helpers ------------------------------------------------------------

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "User-Agent": f"safecut/{__version__}"}

    def _log_cost(
        self, spec: CallSpec, *, attempt: int, units: Units, usd: float, estimated: bool, rid: str | None
    ) -> None:
        line = CostLine(
            ts=now_utc(),
            job_id=self.job_id,
            stage=spec.stage,
            model=spec.model,
            attempt=attempt,
            units=units,
            usd=usd,
            estimated=estimated,
            request_id=rid,
            code_kind=self.caller.code_kind,
            code_id=self.caller.code_id,
        )
        append_cost_line(line, self.cost_path)

    def _log_budget_stop(self, spec: CallSpec, exc: BudgetExceeded) -> None:
        line = CostLine(
            ts=now_utc(),
            job_id=self.job_id,
            stage=f"budget:{spec.stage}",
            model=spec.model,
            attempt=0,
            units={},
            usd=0,
            estimated=False,
            request_id=None,
            cap=exc.cap,
            code_kind=self.caller.code_kind,
            code_id=self.caller.code_id,
        )
        append_cost_line(line, self.cost_path)

    def _note_rate_headers(self, headers: Mapping[str, str]) -> None:
        for kind in ("requests", "tokens"):
            try:
                remaining = float(headers[f"x-ratelimit-remaining-{kind}"])
                limit = float(headers[f"x-ratelimit-limit-{kind}"])
            except (KeyError, ValueError):
                continue
            if limit > 0 and remaining < config.THROTTLE_FRACTION * limit:
                self._throttle_until = self._clock() + config.THROTTLE_DELAY_S
                log.warning("throttled", extra={"kind": kind, "remaining": remaining, "limit": limit})

    def _limits(self) -> list[Any]:
        limits = list(self.caller.limits)
        if self.job_id is not None:
            limits.insert(0, job_limit(self.settings, self.job_id))
        return limits

    # -- the attempt loop ---------------------------------------------------

    async def _run(self, spec: CallSpec, attempt_fn: Callable[[], Awaitable[_Attempt]]) -> tuple[_Attempt, int]:
        self.breaker.before_call()
        attempt = 0
        while True:
            attempt += 1
            call_id = f"{self.job_id or 'system'}:{spec.stage}:{uuid.uuid4().hex}"
            try:
                self.ledger.reserve(call_id, self.job_id, spec.estimate_usd, self._limits())
            except BudgetExceeded as exc:
                self._log_budget_stop(spec, exc)
                self.breaker.abandon_trial()
                raise
            wait = self._throttle_until - self._clock()
            if wait > 0:
                await self._sleep(wait)
            try:
                async with self._inflight:
                    outcome = await attempt_fn()
            except _AttemptFailed as failed:
                if failed.accepted:
                    self.ledger.settle(call_id, spec.estimate_usd)
                    self._log_cost(
                        spec,
                        attempt=attempt,
                        units=spec.estimate_units,
                        usd=spec.estimate_usd,
                        estimated=True,
                        rid=None,
                    )
                else:
                    self.ledger.release(call_id)
                    self._log_cost(
                        spec, attempt=attempt, units={}, usd=0.0, estimated=False, rid=failed.error.request_id
                    )
                error = failed.error
                if error.retryable and spec.policy.allows(attempt, error.status):
                    try:
                        delay = backoff_seconds(attempt, failed.retry_after, self._jitter())
                    except RetryAfterTooLong as too_long:
                        self.breaker.record_failure()
                        raise too_long from error
                    log.info("retrying", extra={"stage": spec.stage, "attempt": attempt, "delay_s": delay})
                    await self._sleep(delay)
                    continue
                if error.retryable:
                    self.breaker.record_failure()
                else:
                    # The server answered (a 4xx, a refusal): it's up, whatever this request's fault.
                    self.breaker.record_success()
                raise error from None
            except BaseException:
                # Cancellation or a bug mid-attempt: billing is unknown, so keep the estimate.
                self.breaker.abandon_trial()
                self.ledger.settle(call_id, spec.estimate_usd)
                self._log_cost(
                    spec, attempt=attempt, units=spec.estimate_units, usd=spec.estimate_usd, estimated=True, rid=None
                )
                raise
            self.ledger.settle(call_id, outcome.usd)
            self._log_cost(
                spec, attempt=attempt, units=outcome.units, usd=outcome.usd, estimated=False, rid=outcome.request_id
            )
            self.breaker.record_success()
            if outcome.error is not None:
                raise outcome.error
            return outcome, attempt

    # -- plain requests -----------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        spec: CallSpec,
        *,
        meter: Meter,
        json_body: Any = None,
        files: Callable[[], Any] | None = None,
        data: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> CallResult:
        """One non-streamed call with retries. The response body must be JSON (or empty on DELETE)."""

        async def attempt() -> _Attempt:
            # ``files`` is a factory so every attempt sends a fresh body (open file handles are single-use).
            try:
                resp = await self._http.request(
                    method,
                    self.url(path),
                    headers=self._headers(),
                    json=json_body,
                    files=files() if files is not None else None,
                    data=data,
                    params=params,
                    timeout=spec.timeout,
                )
            except httpx.TransportError as exc:
                raise _transport_failure(exc) from exc
            body = _decode(resp.content)
            rid = _request_id(resp.headers, body)
            if resp.status_code >= 400:
                raise _AttemptFailed(
                    classify(resp.status_code, body, request_id=rid),
                    accepted=False,
                    retry_after=parse_retry_after(resp.headers.get("retry-after")),
                )
            if body is None and resp.content.strip():
                raise _AttemptFailed(
                    MetaUnavailable("response body is not JSON", status=resp.status_code), accepted=True
                )
            self._note_rate_headers(resp.headers)
            units, usd = meter(cast(Mapping[str, Any], body) if isinstance(body, dict) else _EMPTY)
            return _Attempt(value=body, headers=dict(resp.headers), request_id=rid, units=units, usd=usd)

        outcome, attempts = await self._run(spec, attempt)
        return CallResult(outcome.value, outcome.headers, outcome.request_id, attempts, outcome.usd)

    # -- streamed Responses -------------------------------------------------

    async def stream(self, spec: CallSpec, body: Mapping[str, Any], *, meter: Meter) -> StreamResult:
        """``POST /responses`` with ``stream: true``; collects events up to the terminal one, with retries.

        A stream that ends without a terminal event is ``MetaIncomplete(eof=True)`` (retryable). A server
        ``incomplete`` status or a refusal is accounted at its actual usage and raised without retry.
        """
        payload = dict(body) | {"stream": True}

        async def attempt() -> _Attempt:
            events: list[dict[str, Any]] = []
            try:
                async with self._http.stream(
                    "POST", self.url("responses"), headers=self._headers(), json=payload, timeout=spec.timeout
                ) as resp:
                    if resp.status_code >= 400:
                        raw = await resp.aread()
                        parsed = _decode(raw)
                        raise _AttemptFailed(
                            classify(resp.status_code, parsed, request_id=resp.headers.get("x-request-id")),
                            accepted=False,
                            retry_after=parse_retry_after(resp.headers.get("retry-after")),
                        )
                    self._note_rate_headers(resp.headers)
                    async with asyncio.timeout(spec.total_timeout_s):
                        async for event in aiter_sse(resp.aiter_lines()):
                            events.append(event)
                            terminal = self._terminal(event, meter)
                            if terminal is not None:
                                terminal.value = events
                                return terminal
            except httpx.TransportError as exc:
                failure = _transport_failure(exc)
                failure.accepted = failure.accepted or bool(events)
                raise failure from exc
            except TimeoutError as exc:
                raise _AttemptFailed(MetaUnavailable("stream exceeded its total time limit"), accepted=True) from exc
            except SSEDecodeError as exc:
                raise _AttemptFailed(MetaUnavailable(f"malformed stream: {exc}"), accepted=True) from exc
            raise _AttemptFailed(MetaIncomplete("stream ended without a terminal event", eof=True), accepted=True)

        outcome, attempts = await self._run(spec, attempt)
        events = cast(list[dict[str, Any]], outcome.value)
        final = next((e["response"] for e in reversed(events) if isinstance(e.get("response"), dict)), None)
        response = cast(dict[str, Any], final) if final is not None else {}
        return StreamResult(events, response, outcome.request_id, attempts, outcome.usd)

    @staticmethod
    def _terminal(event: Mapping[str, Any], meter: Meter) -> _Attempt | None:
        kind = event.get("type")
        if kind in ("response.failed", "error"):
            raise _AttemptFailed(MetaUnavailable(f"stream reported {kind}"), accepted=True)
        if kind in ("response.refusal.delta", "response.refusal.done"):
            raise _AttemptFailed(MetaRefusal("the model refused"), accepted=True)
        if kind not in ("response.completed", "response.incomplete"):
            return None
        response = event.get("response")
        response_map = cast(Mapping[str, Any], response) if isinstance(response, Mapping) else _EMPTY
        rid = response_map.get("id")
        units, usd = meter(response_map)
        outcome = _Attempt(request_id=rid if isinstance(rid, str) else None, units=units, usd=usd)
        status = response_map.get("status")
        if kind == "response.incomplete" or status == "incomplete":
            details = response_map.get("incomplete_details")
            reason = cast(Mapping[str, Any], details).get("reason") if isinstance(details, Mapping) else None
            outcome.error = MetaIncomplete(f"response incomplete: {reason or 'unknown reason'}", eof=False)
        refusal = _find_refusal(response_map)
        if refusal is not None:
            outcome.error = MetaRefusal(f"the model refused: {refusal[:200]}")
        return outcome


def _find_refusal(response: Mapping[str, Any]) -> str | None:
    output = response.get("output")
    if not isinstance(output, list):
        return None
    for item in cast(list[Any], output):
        if not isinstance(item, Mapping):
            continue
        content = cast(Mapping[str, Any], item).get("content")
        if not isinstance(content, list):
            continue
        for part in cast(list[Any], content):
            if isinstance(part, Mapping) and cast(Mapping[str, Any], part).get("type") == "refusal":
                return str(cast(Mapping[str, Any], part).get("refusal") or "")
    return None
