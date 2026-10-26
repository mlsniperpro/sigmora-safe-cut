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
#: ``usd`` is ``None`` when the response carries no usage: billing is unknown, so the estimate is kept.
Meter = Callable[[Mapping[str, Any]], tuple[Units, float | None]]

#: Parameters that are no-ops or 400s on Responses (PRE-A §3.6); the client refuses to send them.
FORBIDDEN_PARAMS = frozenset(
    {
        "temperature",
        "top_p",
        "stop",
        "n",
        "logprobs",
        "logit_bias",
        "response_format",
        "truncation",
        "previous_response_id",
    }
)
#: A 5xx that arrives after this long was being processed, so it may have been billed (PRE-A §10.2).
SLOW_FAILURE_S = 30.0
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
    #: False for best-effort helpers (the free token count): their failures say nothing about the
    #: endpoints that matter, so they neither open nor are refused by the circuit breaker.
    breaker: bool = True
    #: The endpoint takes ``store`` (every Responses model; SAM unless SAFECUT_SAM_SEND_STORE=false).
    store_param: bool = True


@dataclass(frozen=True)
class CallResult:
    body: Any
    headers: Mapping[str, str]
    request_id: str | None
    attempts: int
    usd: float
    #: An earlier attempt failed after the server may have processed it (e.g. an upload that timed out).
    maybe_orphaned: bool = False


@dataclass(frozen=True)
class StreamResult:
    events: list[dict[str, Any]]
    response: dict[str, Any]
    request_id: str | None
    attempts: int
    usd: float


class _SentFlag:
    """Set by an attempt right before it sends its request."""

    def __init__(self) -> None:
        self.sent = False

    def mark(self) -> None:
        self.sent = True


@dataclass
class _Attempt:
    """What one attempt produced. ``error`` set with ``billed`` means: account, then raise it."""

    value: Any = None
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    request_id: str | None = None
    units: Units = field(default_factory=dict[str, float])
    usd: float | None = 0.0
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


def _status_failure(
    status: int, body: Any, headers: Mapping[str, str], rid: str | None, elapsed: float
) -> _AttemptFailed:
    """An HTTP error status. A 504, or any 5xx after :data:`SLOW_FAILURE_S`, may have been processed."""
    accepted = status == 504 or (status >= 500 and elapsed > SLOW_FAILURE_S)
    return _AttemptFailed(
        classify(status, body, request_id=rid),
        accepted=accepted,
        retry_after=parse_retry_after(headers.get("retry-after")),
    )


def guard_body(body: Mapping[str, Any], *, store_param: bool = True) -> None:
    """AGENTS rule 6 at the transport: Standard models only, ``store`` never true, no ignored params."""
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("request body has no model")
    config.ensure_standard_model(model)
    if store_param and body.get("store") is not False:
        raise ValueError("store must be sent as false (AGENTS rule 6)")
    if not store_param and "store" in body:
        raise ValueError("this model takes no store parameter; don't send one")
    sent_forbidden = FORBIDDEN_PARAMS & set(body)
    if sent_forbidden:
        raise ValueError(f"parameters ignored or rejected by the Responses API: {sorted(sent_forbidden)}")


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
        if (job_id is None) != (caller.code_kind == "system"):
            raise ValueError("job_id is None exactly for system callers (healthz, the startup probe)")
        self.settings = settings
        self.job_id = job_id
        self.caller = caller
        self.ledger = ledger
        self.cost_path = Path(cost_path)
        self._owns_http = http is None
        # trust_env=False: no HTTPS_PROXY or netrc from the environment ever sees the key (AGENTS rule 7).
        self._http = http or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=config.MAX_CONNECTIONS),
            timeout=httpx.Timeout(60.0, connect=config.CONNECT_TIMEOUT_S),
            trust_env=False,
        )
        allowed = frozenset().union(*config.ALLOWED_HOSTS.values())
        self.base_url = config.trusted_base_url(base_url or settings.meta_base_url, allowed)
        self._key = api_key if api_key is not None else settings.api_key()
        self.breaker = breaker or CircuitBreaker(clock=clock)
        # Process-wide bound: pass one shared semaphore to every client in a process (WP5 does).
        self._inflight = inflight or asyncio.Semaphore(config.PROCESS_INFLIGHT)
        # Per-job bounds (PRE-A §10.1): one client serves one job.
        self._lanes: dict[Lane, asyncio.Semaphore] = {
            "sam": asyncio.Semaphore(config.JOB_SAM_INFLIGHT),
            "responses": asyncio.Semaphore(config.JOB_RESPONSES_INFLIGHT),
            "other": asyncio.Semaphore(config.PROCESS_INFLIGHT),
        }
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

    async def _run(
        self, spec: CallSpec, attempt_fn: Callable[[Callable[[], None]], Awaitable[_Attempt]]
    ) -> tuple[_Attempt, int, bool]:
        """Run attempts until one succeeds or the policy says stop. Returns ``(outcome, attempts, orphaned)``.

        ``attempt_fn`` calls its argument right before it sends the request, so a cancellation that lands
        before anything was sent releases the reservation instead of charging it.
        """
        breaker = self.breaker if spec.breaker else None
        trial = breaker.before_call() if breaker else False
        attempt = 0
        maybe_processed = False
        while True:
            attempt += 1
            call_id = f"{self.job_id or 'system'}:{spec.stage}:{uuid.uuid4().hex}"
            try:
                self.ledger.reserve(call_id, self.job_id, spec.estimate_usd, self._limits())
            except BudgetExceeded as exc:
                self._log_budget_stop(spec, exc)
                if breaker:
                    breaker.abandon_trial(trial)
                raise
            except BaseException:
                if breaker:
                    breaker.abandon_trial(trial)
                raise
            sent = _SentFlag()
            try:
                wait = self._throttle_until - self._clock()
                if wait > 0:
                    await self._sleep(wait)
                async with self._lanes[spec.lane], self._inflight:
                    outcome = await attempt_fn(sent.mark)
            except _AttemptFailed as failed:
                self._account(spec, call_id, attempt, charged=failed.accepted, rid=failed.error.request_id)
                maybe_processed = maybe_processed or failed.accepted
                delay = self._retry_delay(spec, attempt, failed, maybe_processed, breaker=breaker, trial=trial)
                log.info("retrying", extra={"stage": spec.stage, "attempt": attempt, "delay_s": delay})
                try:
                    await self._sleep(delay)
                except BaseException:
                    if breaker:
                        breaker.abandon_trial(trial)
                    raise
                continue
            except BaseException:
                # Cancellation or a bug mid-attempt: once the request was sent, billing is unknown.
                if breaker:
                    breaker.abandon_trial(trial)
                self._account(spec, call_id, attempt, charged=sent.sent, rid=None)
                raise
            if outcome.usd is None:
                # Completed, but without usage: we can't measure it, so the reserved estimate stands.
                self._account(spec, call_id, attempt, charged=True, rid=outcome.request_id)
            else:
                self.ledger.settle(call_id, outcome.usd)
                self._log_cost(
                    spec, attempt=attempt, units=outcome.units, usd=outcome.usd, estimated=False, rid=outcome.request_id
                )
            if breaker:
                breaker.record_success(trial)
            if outcome.error is not None:
                outcome.error.maybe_processed = True
                raise outcome.error
            return outcome, attempt, maybe_processed

    def _retry_delay(
        self,
        spec: CallSpec,
        attempt: int,
        failed: _AttemptFailed,
        maybe_processed: bool,
        *,
        breaker: CircuitBreaker | None,
        trial: bool,
    ) -> float:
        """The wait before the next attempt, or raise the final typed error (updating the breaker)."""
        error = failed.error
        error.maybe_processed = maybe_processed
        if error.retryable and spec.policy.allows(attempt, error.status):
            try:
                return backoff_seconds(attempt, failed.retry_after, self._jitter())
            except RetryAfterTooLong as too_long:
                if breaker:
                    breaker.record_failure(trial)
                too_long.maybe_processed = maybe_processed
                raise too_long from error
        if breaker and error.retryable:
            breaker.record_failure(trial)
        elif breaker:
            # The server answered (a 4xx, a refusal): it's up, whatever this request's fault.
            breaker.record_success(trial)
        raise error from None

    def _account(self, spec: CallSpec, call_id: str, attempt: int, *, charged: bool, rid: str | None) -> None:
        """Charged: keep the estimate as an ``estimated`` line. Not charged: release it at ``usd 0``."""
        if charged:
            self.ledger.settle(call_id, spec.estimate_usd)
            self._log_cost(
                spec, attempt=attempt, units=spec.estimate_units, usd=spec.estimate_usd, estimated=True, rid=rid
            )
        else:
            self.ledger.release(call_id)
            self._log_cost(spec, attempt=attempt, units={}, usd=0.0, estimated=False, rid=rid)

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
        payload: Any = json_body
        model: Any = cast(Mapping[str, Any], json_body).get("model") if isinstance(json_body, Mapping) else None
        if isinstance(model, str):
            config.ensure_standard_model(model)

        async def attempt(mark_sent: Callable[[], None]) -> _Attempt:
            # ``files`` is a factory so every attempt sends a fresh body (open file handles are single-use).
            started = self._clock()
            try:
                async with asyncio.timeout(spec.total_timeout_s):
                    mark_sent()
                    resp = await self._http.request(
                        method,
                        self.url(path),
                        headers=self._headers(),
                        json=payload,
                        files=files() if files is not None else None,
                        data=data,
                        params=params,
                        timeout=spec.timeout,
                    )
            except httpx.TransportError as exc:
                raise _transport_failure(exc) from exc
            except httpx.HTTPError as exc:
                # Decoding errors, redirect loops: the request went out, so billing is unknown.
                raise _AttemptFailed(MetaUnavailable(f"HTTP error: {type(exc).__name__}"), accepted=True) from exc
            except TimeoutError as exc:
                raise _AttemptFailed(MetaUnavailable("request exceeded its total time limit"), accepted=True) from exc
            body = _decode(resp.content)
            rid = _request_id(resp.headers, body)
            if resp.status_code >= 400:
                raise _status_failure(resp.status_code, body, resp.headers, rid, self._clock() - started)
            if body is None and resp.content.strip():
                raise _AttemptFailed(
                    MetaUnavailable("response body is not JSON", status=resp.status_code), accepted=True
                )
            self._note_rate_headers(resp.headers)
            units, usd = meter(cast(Mapping[str, Any], body) if isinstance(body, dict) else _EMPTY)
            return _Attempt(value=body, headers=dict(resp.headers), request_id=rid, units=units, usd=usd)

        outcome, attempts, orphaned = await self._run(spec, attempt)
        usd = spec.estimate_usd if outcome.usd is None else outcome.usd
        return CallResult(outcome.value, outcome.headers, outcome.request_id, attempts, usd, orphaned)

    # -- streamed Responses -------------------------------------------------

    async def stream(self, spec: CallSpec, body: Mapping[str, Any], *, meter: Meter) -> StreamResult:
        """``POST /responses`` with ``stream: true``; collects events up to the terminal one, with retries.

        A stream that ends without a terminal event is ``MetaIncomplete(eof=True)`` (retryable). A server
        ``incomplete`` status or a refusal is accounted at its actual usage and raised without retry.
        """
        guard_body(body, store_param=spec.store_param)
        payload = dict(body) | {"stream": True}

        async def attempt(mark_sent: Callable[[], None]) -> _Attempt:
            events: list[dict[str, Any]] = []
            refused: list[str] = []
            started = self._clock()
            try:
                mark_sent()
                async with self._http.stream(
                    "POST", self.url("responses"), headers=self._headers(), json=payload, timeout=spec.timeout
                ) as resp:
                    if resp.status_code >= 400:
                        parsed = _decode(await resp.aread())
                        raise _status_failure(
                            resp.status_code,
                            parsed,
                            resp.headers,
                            resp.headers.get("x-request-id"),
                            self._clock() - started,
                        )
                    self._note_rate_headers(resp.headers)
                    async with asyncio.timeout(spec.total_timeout_s):
                        async for event in aiter_sse(resp.aiter_lines()):
                            events.append(event)
                            if event.get("type") in ("response.refusal.delta", "response.refusal.done"):
                                # Keep reading: the terminal event carries the usage to bill.
                                refused.append(str(event.get("delta") or event.get("refusal") or ""))
                                continue
                            terminal = self._terminal(event, meter)
                            if terminal is not None:
                                terminal.value = events
                                if refused and terminal.error is None:
                                    terminal.error = MetaRefusal(f"the model refused: {''.join(refused)[:200]}")
                                return terminal
            except httpx.TransportError as exc:
                failure = _transport_failure(exc)
                failure.accepted = failure.accepted or bool(events)
                raise failure from exc
            except httpx.HTTPError as exc:
                raise _AttemptFailed(MetaUnavailable(f"HTTP error: {type(exc).__name__}"), accepted=True) from exc
            except TimeoutError as exc:
                raise _AttemptFailed(MetaUnavailable("stream exceeded its total time limit"), accepted=True) from exc
            except SSEDecodeError as exc:
                raise _AttemptFailed(MetaUnavailable(f"malformed stream: {exc}"), accepted=True) from exc
            if refused:
                raise _AttemptFailed(MetaRefusal(f"the model refused: {''.join(refused)[:200]}"), accepted=True)
            raise _AttemptFailed(MetaIncomplete("stream ended without a terminal event", eof=True), accepted=True)

        outcome, attempts, _ = await self._run(spec, attempt)
        events = cast(list[dict[str, Any]], outcome.value)
        final = next((e["response"] for e in reversed(events) if isinstance(e.get("response"), dict)), None)
        response = cast(dict[str, Any], final) if final is not None else {}
        usd = spec.estimate_usd if outcome.usd is None else outcome.usd
        return StreamResult(events, response, outcome.request_id, attempts, usd)

    @staticmethod
    def _terminal(event: Mapping[str, Any], meter: Meter) -> _Attempt | None:
        kind = event.get("type")
        if kind in ("response.failed", "error"):
            raise _AttemptFailed(MetaUnavailable(f"stream reported {kind}"), accepted=True)
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
