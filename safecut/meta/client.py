"""The Meta Model API transport: one attempt loop for every call (PRE-A §10.1–10.3, §10.5).

Each attempt reserves its worst-case estimate against the caps, runs under the process concurrency
bound, and is accounted honestly in ``cost.jsonl``: rejected before processing → released, ``usd 0``;
accepted then lost → kept as an ``estimated`` charge; completed → the actual cost from ``usage``.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
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
from pydantic import ValidationError

from safecut import __version__, config
from safecut.config import Provider, Settings
from safecut.contracts import CostLine, append_cost_line, now_utc
from safecut.meta.budget import Caller, CapLimit, Ledger, job_limit
from safecut.meta.errors import (
    BudgetExceeded,
    MetaBadRequest,
    MetaConfigError,
    MetaError,
    MetaIncomplete,
    MetaRefusal,
    MetaUnavailable,
    ReplayRefused,
    classify,
)
from safecut.meta.retry import CircuitBreaker, RetryAfterTooLong, RetryPolicy, backoff_seconds, parse_retry_after
from safecut.meta.sse import SSEDecodeError, aiter_sse, aiter_sse_lines

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
    #: Every call has a deadline: a server dripping a body never holds a call (or its budget slot) forever.
    total_timeout_s: float = config.DEFAULT_TOTAL_TIMEOUT_S
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


class _ChatAccumulator:
    """Assembles a streamed Chat Completions answer from its chunks."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.finish: str | None = None
        self.usage: Any = None
        self.rid: str | None = None
        self.seen = False

    def add(self, chunk: Mapping[str, Any]) -> None:
        self.seen = True
        if self.rid is None and isinstance(chunk.get("id"), str):
            self.rid = cast(str, chunk["id"])
        self.usage = chunk.get("usage") or self.usage
        choices = chunk.get("choices")
        for choice in cast(list[Any], choices if isinstance(choices, list) else []):
            if not isinstance(choice, Mapping):
                continue
            choice_map = cast(Mapping[str, Any], choice)
            delta = choice_map.get("delta")
            if isinstance(delta, Mapping):
                content = cast(Mapping[str, Any], delta).get("content")
                if isinstance(content, str):
                    self.parts.append(content)
            if isinstance(choice_map.get("finish_reason"), str):
                self.finish = cast(str, choice_map["finish_reason"])

    def answer(self) -> dict[str, Any]:
        return {"id": self.rid, "text": "".join(self.parts), "finish_reason": self.finish, "usage": self.usage}


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
    if 300 <= status < 400:
        # Redirects are never followed and never success: the path or host is wrong.
        return _AttemptFailed(MetaConfigError(f"unexpected redirect (HTTP {status})", status=status), accepted=False)
    accepted = status == 504 or (status >= 500 and elapsed > SLOW_FAILURE_S)
    return _AttemptFailed(
        classify(status, body, request_id=rid),
        accepted=accepted,
        retry_after=parse_retry_after(headers.get("retry-after")),
    )


async def outlive_cancel(task: asyncio.Future[Any]) -> None:
    """Wait for ``task`` to finish without ever cancelling it, however many cancellations arrive meanwhile.

    ``await task`` would pass a second cancellation into the shielded task (a timeout plus a user cancel, a
    TaskGroup teardown), stranding the ledger or file record it was writing. The caller re-raises its own
    cancellation afterwards.
    """
    while not task.done():
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait({task})


def _report_response_id(event: Mapping[str, Any], on_response_id: Callable[[str], None]) -> None:
    response = event.get("response")
    if isinstance(response, Mapping):
        rid = cast(Mapping[str, Any], response).get("id")
        if isinstance(rid, str) and rid:
            on_response_id(rid)


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


#: Transport errors raised before any byte reached Meta.
_NEVER_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,  # the egress proxy refused CONNECT
    httpx.UnsupportedProtocol,
    httpx.LocalProtocolError,  # h11 refused to write the request (e.g. a malformed header)
)


_SCRUB_DEPTH = 64


def _json_ready(payload: Any) -> None:
    """Refuse a body JSON can't carry (NaN, a set, a lone surrogate) before any reservation: httpx would fail
    to encode it only after the attempt was marked sent, and bill a request that never left."""
    try:
        json.dumps(payload, allow_nan=False, ensure_ascii=False).encode()  # as httpx encodes it
    except (TypeError, ValueError) as exc:
        raise MetaBadRequest(f"request body can't be sent as JSON: {type(exc).__name__}") from exc


def _transport_failure(exc: httpx.TransportError) -> _AttemptFailed:
    """Errors before any byte reached Meta (connect phase, a proxy refusing CONNECT, a bad URL scheme) are
    rejected; anything later may have been processed."""
    rejected = isinstance(exc, _NEVER_SENT)
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
        provider: Provider = "meta",
    ) -> None:
        if (job_id is None) != (caller.code_kind == "system"):
            raise ValueError("job_id is None exactly for system callers (healthz, the startup probe)")
        self.settings = settings
        self.provider: Provider = provider
        self.job_id = job_id
        self.caller = caller
        self.ledger = ledger
        self.cost_path = Path(cost_path)
        self._owns_http = http is None
        # httpx's default trust_env: the operator's CA bundle and egress proxy apply (cloud sandboxes need
        # both). That is infrastructure the operator configures, not the geo-workaround AGENTS rule 7 bans;
        # the key can only go to the pinned provider host (trusted_base_url below).
        self._http = http or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=config.MAX_CONNECTIONS),
            timeout=httpx.Timeout(60.0, connect=config.CONNECT_TIMEOUT_S),
        )
        # Each provider's key may only go to that provider's host: never a Meta key to Baseten or back.
        field = "open_weight_base_url" if provider == "baseten" else "meta_base_url"
        default_url = settings.open_weight_base_url if provider == "baseten" else settings.meta_base_url
        self.base_url = config.trusted_base_url(base_url or default_url, config.ALLOWED_HOSTS[field])
        default_key = settings.open_api_key if provider == "baseten" else settings.api_key
        # Replay mode refuses every live call (ReplayRefused) before a key is needed, so it runs without one.
        self._key = api_key if api_key is not None else ("" if settings.replay else default_key())
        self.breaker = breaker or CircuitBreaker(clock=clock)
        # Process-wide bound: pass one shared semaphore to every client in a process (WP5 does).
        self._inflight = inflight or asyncio.Semaphore(config.PROCESS_INFLIGHT)
        # Per-job bounds (PRE-A §10.1): one client serves one job.
        self._lanes: dict[Lane, asyncio.Semaphore] = {
            "sam": asyncio.Semaphore(config.JOB_SAM_INFLIGHT),
            "responses": asyncio.Semaphore(
                config.BASETEN_INFLIGHT if provider == "baseten" else config.JOB_RESPONSES_INFLIGHT
            ),
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

    def _scrub(self, body: Any, depth: int = 0) -> Any:
        """An error body with our own key masked: servers echo it ("Invalid API key: sk-…"), and error text
        ends up in exceptions and logs. Nesting past 64 levels is dropped (it can't be a real error body, and
        walking it would overflow the stack)."""
        if depth > _SCRUB_DEPTH:
            return "[too deep]"
        if isinstance(body, str):
            return body.replace(self._key, "[redacted]") if self._key else body
        if isinstance(body, dict):
            return {k: self._scrub(v, depth + 1) for k, v in cast(dict[str, Any], body).items()}
        if isinstance(body, list):
            return [self._scrub(v, depth + 1) for v in cast(list[Any], body)]
        return body

    def _log_cost(
        self, spec: CallSpec, *, attempt: int, units: Units, usd: float, estimated: bool, rid: str | None
    ) -> None:
        try:
            line = CostLine(
                ts=now_utc(),
                provider=self.provider,
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
        except (OSError, ValidationError):
            # A failed write (or a meter bug that yields an invalid line) must not lose a billed result (a
            # retry would bill it again) or skip the ledger settle that follows; the ledger still holds it.
            log.exception("cost.jsonl write failed", extra={"stage": spec.stage, "usd": usd, "estimated": estimated})

    def _log_budget_stop(self, spec: CallSpec, exc: BudgetExceeded) -> None:
        line = CostLine(
            ts=now_utc(),
            provider=self.provider,
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
        try:
            append_cost_line(line, self.cost_path)
        except OSError:
            # The stop itself stands: the caller still gets its BudgetExceeded, never a raw OSError.
            log.exception("cost.jsonl write failed for a budget stop", extra={"stage": spec.stage})

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

    def _limits(self) -> list[CapLimit]:
        if self.provider == "baseten":
            # Baseten credits are a separate pot: only its own per-job cap applies, never the Meta caps.
            key = f"baseten_job:{self.job_id or 'system'}"
            return [CapLimit("baseten_job", key, self.settings.open_weight_job_usd_cap)]
        limits = list(self.caller.limits_at(now_utc()))
        if self.job_id is not None:
            limits.insert(0, job_limit(self.settings, self.job_id))
        return limits

    async def _ledger(self, fn: Callable[[], None], *, attempts: int = 2) -> None:
        """A ledger call, bounded and typed (PRE-A §10.2). A call that raised or got no answer within 10 s is
        retried once (a cold start), with the same ``call_id``: every ledger call is idempotent per ``call_id``, so
        a first attempt that lands late never doubles a reservation. Then the fault or stall is ``MetaUnavailable``
        and no request is sent. ``BudgetExceeded`` passes
        through; a refusal (``KeyError``/``ValueError``, e.g. a conflicting call_id) is ``MetaUnavailable`` too, so
        callers only ever see ``MetaError``."""
        for attempt in range(1, attempts + 1):
            try:
                await asyncio.wait_for(asyncio.to_thread(fn), timeout=config.BUDGET_RESERVE_TIMEOUT_S)
            except BudgetExceeded:
                raise
            except (KeyError, ValueError) as exc:
                raise MetaUnavailable(f"the budget ledger refused the call: {exc}") from exc
            except TimeoutError as exc:
                # A reserve that lands after both attempts expires after 2.5 h as an estimated charge (fail closed).
                if attempt == attempts:
                    raise MetaUnavailable("the budget ledger did not answer in time; no request was sent") from exc
            except Exception as exc:
                if attempt == attempts:
                    raise MetaUnavailable(f"the budget ledger failed: {type(exc).__name__}") from exc
            else:
                return

    async def _reserve(self, call_id: str, usd: float) -> None:
        """Reserve, shielded from cancellation: a reserve that lands after a cancel is released, not leaked."""
        task = asyncio.ensure_future(
            self._ledger(functools.partial(self.ledger.reserve, call_id, self.job_id, usd, self._limits()))
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await outlive_cancel(task)
            if not task.cancelled() and task.exception() is None:
                await self._ledger_after(lambda: self.ledger.release(call_id))
            raise

    async def preflight(self, spec: CallSpec, usd: float) -> None:
        """Check that ``usd`` (every call of a multi-call pass) fits every cap now, spending nothing: reserve
        and release at once. A stop raises ``BudgetExceeded`` and writes the ``budget:<stage>`` line."""
        if self.settings.replay:
            raise ReplayRefused("SAFECUT_REPLAY is on: live calls are refused (use the saved responses)")
        call_id = f"{self.job_id or 'system'}:{spec.stage}:preflight:{uuid.uuid4().hex}"
        try:
            await self._reserve(call_id, usd)
        except BudgetExceeded as exc:
            self._log_budget_stop(spec, exc)
            raise
        await self._ledger_after(lambda: self.ledger.release(call_id))

    # -- the attempt loop ---------------------------------------------------

    async def _run(
        self, spec: CallSpec, attempt_fn: Callable[[Callable[[], None]], Awaitable[_Attempt]]
    ) -> tuple[_Attempt, int, bool]:
        """Run attempts until one succeeds or the policy says stop. Returns ``(outcome, attempts, orphaned)``.

        ``attempt_fn`` calls its argument right before it sends the request, so a cancellation that lands
        before anything was sent releases the reservation instead of charging it.
        """
        if self.settings.replay:
            # Replay mode serves saved responses from the job directory: a stage that reaches the
            # transport anyway would spend live credits, so it is refused here, before any reservation.
            raise ReplayRefused("SAFECUT_REPLAY is on: live calls are refused (use the saved responses)")
        breaker = self.breaker if spec.breaker else None
        trial = breaker.before_call() if breaker else False
        try:
            return await self._attempts(spec, attempt_fn, breaker, trial)
        except BaseException:
            # Budget stop, cancellation (even mid-backoff), a final error: never strand the trial slot.
            # After record_success/record_failure(trial) the slot is already free, so this is a no-op.
            if breaker:
                breaker.abandon_trial(trial)
            raise

    async def _attempts(
        self,
        spec: CallSpec,
        attempt_fn: Callable[[Callable[[], None]], Awaitable[_Attempt]],
        breaker: CircuitBreaker | None,
        trial: bool,
    ) -> tuple[_Attempt, int, bool]:
        attempt = 0
        maybe_processed = False
        while True:
            attempt += 1
            wait = self._throttle_until - self._clock()
            if wait > 0:
                await self._sleep(wait)
            sent = _SentFlag()
            done: _Attempt | None = None
            delay = 0.0
            # Reserve only once this attempt holds its lane and process slots: a call queued behind them
            # must not hold budget, or concurrent calls trip a cap they would never reach (false stops).
            async with self._lanes[spec.lane], self._inflight:
                call_id = await self._reserve_attempt(spec, maybe_processed)
                try:
                    outcome = await attempt_fn(sent.mark)
                except _AttemptFailed as failed:
                    await self._account(spec, call_id, attempt, charged=failed.accepted, rid=failed.error.request_id)
                    maybe_processed = maybe_processed or failed.accepted
                    delay = self._retry_delay(spec, attempt, failed, maybe_processed, breaker=breaker, trial=trial)
                except BaseException:
                    # Cancellation or a bug mid-attempt: once the request was sent, billing is unknown.
                    await asyncio.shield(self._account(spec, call_id, attempt, charged=sent.sent, rid=None))
                    raise
                else:
                    await self._settle(spec, call_id, attempt, outcome)
                    done = outcome
            if done is None:  # a failed attempt the policy retries: back off outside the lane
                log.info("retrying", extra={"stage": spec.stage, "attempt": attempt, "delay_s": delay})
                await self._sleep(delay)
                continue
            if breaker:
                breaker.record_success(trial)
            if done.error is not None:
                done.error.maybe_processed = True
                raise done.error
            return done, attempt, maybe_processed

    async def _reserve_attempt(self, spec: CallSpec, maybe_processed: bool) -> str | None:
        """Reserve one attempt's estimate; ``None`` for a free call (files, deletes, token counts), which never
        touches the ledger, so cleanup still works while the ledger is down."""
        if spec.estimate_usd <= 0:
            return None
        call_id = f"{self.job_id or 'system'}:{spec.stage}:{uuid.uuid4().hex}"
        try:
            await self._reserve(call_id, spec.estimate_usd)
        except MetaError as exc:
            # An earlier attempt may have been processed (an accepted timeout): the caller must still
            # learn that, or an upload it never heard about escapes files.json (PRE-A §10.4).
            exc.maybe_processed = exc.maybe_processed or maybe_processed
            if isinstance(exc, BudgetExceeded):
                self._log_budget_stop(spec, exc)
            raise
        return call_id

    async def _settle(self, spec: CallSpec, call_id: str | None, attempt: int, outcome: _Attempt) -> None:
        if outcome.usd is None:
            # Completed, but without usage: we can't measure it, so the reserved estimate stands.
            await self._account(spec, call_id, attempt, charged=True, rid=outcome.request_id)
            return
        # cost.jsonl first: it's the record of truth, so a ledger fault can't lose a billed call.
        self._log_cost(
            spec, attempt=attempt, units=outcome.units, usd=outcome.usd, estimated=False, rid=outcome.request_id
        )
        if call_id is not None:
            await self._ledger_after(lambda: self.ledger.settle(call_id, cast(float, outcome.usd)))

    async def _ledger_after(self, fn: Callable[[], None]) -> None:
        """Settle or release after a call: a ledger fault is logged loudly, never allowed to lose the result.

        Shielded: a cancellation that lands while the ledger call is queued still lets it run (else the
        reservation would stay open against cost.jsonl), then re-raises. A fault leaves the reservation
        to expire after 2.5 h as an estimated charge (fail closed).
        """
        task = asyncio.ensure_future(self._ledger_call(fn))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await outlive_cancel(task)
            raise

    async def _ledger_call(self, fn: Callable[[], None]) -> None:
        try:
            await asyncio.wait_for(asyncio.to_thread(fn), timeout=config.BUDGET_RESERVE_TIMEOUT_S)
        except Exception:
            log.exception("budget ledger settle/release failed; the reservation will expire as a charge")

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
        if breaker and (error.retryable or isinstance(error, MetaUnavailable)):
            # A 504 is not retried, but it is still an outage signal (PRE-A §10.2).
            breaker.record_failure(trial)
        elif breaker:
            # The server answered (a 4xx, a refusal): it's up, whatever this request's fault.
            breaker.record_success(trial)
        raise error from None

    async def _account(
        self, spec: CallSpec, call_id: str | None, attempt: int, *, charged: bool, rid: str | None
    ) -> None:
        """Charged: keep the estimate as an ``estimated`` line. Not charged: release it at ``usd 0``."""
        if charged:
            self._log_cost(
                spec, attempt=attempt, units=spec.estimate_units, usd=spec.estimate_usd, estimated=True, rid=rid
            )
            if call_id is not None:
                await self._ledger_after(lambda: self.ledger.settle(call_id, spec.estimate_usd))
        else:
            self._log_cost(spec, attempt=attempt, units={}, usd=0.0, estimated=False, rid=rid)
            if call_id is not None:
                await self._ledger_after(lambda: self.ledger.release(call_id))

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
        if payload is not None:
            _json_ready(payload)
        model: Any = cast(Mapping[str, Any], json_body).get("model") if isinstance(json_body, Mapping) else None
        if isinstance(model, str):
            config.ensure_standard_model(model)

        async def attempt(mark_sent: Callable[[], None]) -> _Attempt:
            # ``files`` is a factory so every attempt sends a fresh body (open file handles are single-use).
            started = self._clock()
            # Build the multipart body first: a factory that fails (a missing file) sent nothing, so it must
            # not be charged as a sent request.
            body_files = files() if files is not None else None
            try:
                async with asyncio.timeout(spec.total_timeout_s):
                    mark_sent()
                    resp = await self._http.request(
                        method,
                        self.url(path),
                        headers=self._headers(),
                        json=payload,
                        files=body_files,
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
            if resp.status_code >= 300:
                raise _status_failure(resp.status_code, self._scrub(body), resp.headers, rid, self._clock() - started)
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

    async def stream(
        self,
        spec: CallSpec,
        body: Mapping[str, Any],
        *,
        meter: Meter,
        on_response_id: Callable[[str], None] | None = None,
    ) -> StreamResult:
        """``POST /responses`` with ``stream: true``; collects events up to the terminal one, with retries.

        A stream that ends without a terminal event is ``MetaIncomplete(eof=True)`` (retryable). A server
        ``incomplete`` status or a refusal is accounted at its actual usage and raised without retry.
        ``on_response_id`` is called with each attempt's response ID as soon as an event carries it (the
        first is ``response.created``), so a stored response is known even if the attempt then fails.
        """
        guard_body(body, store_param=spec.store_param)
        payload = dict(body) | {"stream": True}
        _json_ready(payload)

        async def attempt(mark_sent: Callable[[], None]) -> _Attempt:
            events: list[dict[str, Any]] = []
            refused: list[str] = []
            started = self._clock()
            try:
                mark_sent()
                async with self._http.stream(
                    "POST", self.url("responses"), headers=self._headers(), json=payload, timeout=spec.timeout
                ) as resp:
                    if resp.status_code >= 300:
                        async with asyncio.timeout(spec.total_timeout_s):  # a dripping error body is bounded too
                            parsed = _decode(await resp.aread())
                        raise _status_failure(
                            resp.status_code,
                            self._scrub(parsed),
                            resp.headers,
                            resp.headers.get("x-request-id"),
                            self._clock() - started,
                        )
                    self._note_rate_headers(resp.headers)
                    async with asyncio.timeout(spec.total_timeout_s):
                        async for event in aiter_sse(aiter_sse_lines(resp.aiter_bytes())):
                            events.append(event)
                            if on_response_id is not None:
                                _report_response_id(event, on_response_id)
                            if event.get("type") in ("response.refusal.delta", "response.refusal.done"):
                                # Keep reading: the terminal event carries the usage to bill.
                                refused.append(str(event.get("delta") or event.get("refusal") or ""))
                                continue
                            terminal = self._terminal(event, meter)
                            if terminal is not None:
                                terminal.value = events
                                if refused and terminal.error is None:
                                    terminal.error = MetaRefusal.of("".join(refused))
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
                raise _AttemptFailed(MetaRefusal.of("".join(refused)), accepted=True)
            raise _AttemptFailed(MetaIncomplete("stream ended without a terminal event", eof=True), accepted=True)

        outcome, attempts, _ = await self._run(spec, attempt)
        events = cast(list[dict[str, Any]], outcome.value)
        final = next((e["response"] for e in reversed(events) if isinstance(e.get("response"), dict)), None)
        response = cast(dict[str, Any], final) if final is not None else {}
        usd = spec.estimate_usd if outcome.usd is None else outcome.usd
        return StreamResult(events, response, outcome.request_id, attempts, usd)

    async def stream_chat(self, spec: CallSpec, body: Mapping[str, Any], *, meter: Meter) -> CallResult:
        """``POST /chat/completions`` streamed (Baseten's OpenAI-compatible API), with retries.

        Returns the assembled answer as ``{"id", "text", "finish_reason", "usage"}``. A stream that ends with
        no ``finish_reason`` is ``MetaIncomplete(eof=True)``; usage comes from the final usage chunk.
        """
        model = body.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("request body has no model")
        config.ensure_standard_model(model)
        payload = dict(body) | {"stream": True, "stream_options": {"include_usage": True}}
        _json_ready(payload)

        async def attempt(mark_sent: Callable[[], None]) -> _Attempt:
            started = self._clock()
            acc = _ChatAccumulator()
            try:
                mark_sent()
                async with self._http.stream(
                    "POST", self.url("chat/completions"), headers=self._headers(), json=payload, timeout=spec.timeout
                ) as resp:
                    if resp.status_code >= 300:
                        async with asyncio.timeout(spec.total_timeout_s):  # a dripping error body is bounded too
                            parsed = _decode(await resp.aread())
                        rid_header = resp.headers.get("x-request-id")
                        raise _status_failure(
                            resp.status_code, self._scrub(parsed), resp.headers, rid_header, self._clock() - started
                        )
                    async with asyncio.timeout(spec.total_timeout_s):
                        async for chunk in aiter_sse(aiter_sse_lines(resp.aiter_bytes())):
                            acc.add(chunk)
            except httpx.TransportError as exc:
                failure = _transport_failure(exc)
                failure.accepted = failure.accepted or acc.seen
                raise failure from exc
            except httpx.HTTPError as exc:
                raise _AttemptFailed(MetaUnavailable(f"HTTP error: {type(exc).__name__}"), accepted=True) from exc
            except TimeoutError as exc:
                raise _AttemptFailed(MetaUnavailable("stream exceeded its total time limit"), accepted=True) from exc
            except SSEDecodeError as exc:
                raise _AttemptFailed(MetaUnavailable(f"malformed stream: {exc}"), accepted=True) from exc
            if acc.finish is None:
                raise _AttemptFailed(
                    MetaIncomplete("chat stream ended without a finish_reason", eof=True), accepted=True
                )
            answer = acc.answer()
            units, usd = meter(answer)
            return _Attempt(value=answer, request_id=acc.rid, units=units, usd=usd)

        outcome, attempts, orphaned = await self._run(spec, attempt)
        usd = spec.estimate_usd if outcome.usd is None else outcome.usd
        return CallResult(outcome.value, outcome.headers, outcome.request_id, attempts, usd, orphaned)

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
            outcome.error = MetaRefusal.of(refusal)
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
