"""One retry policy for every Meta call (PRE-A §10.2): attempts, backoff, Retry-After, circuit breaker."""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from safecut import config
from safecut.meta.errors import MetaUnavailable


@dataclass(frozen=True)
class RetryPolicy:
    """How many attempts a call gets (first try included)."""

    attempts: int
    asr_500_attempts: int | None = None

    @classmethod
    def for_responses(cls, effort: str) -> RetryPolicy:
        deep = effort in ("xhigh", "max")
        return cls(attempts=config.ATTEMPTS_DEEP_EFFORT if deep else config.ATTEMPTS_DEFAULT)

    @classmethod
    def for_sam(cls) -> RetryPolicy:
        return cls(attempts=config.ATTEMPTS_SAM)

    @classmethod
    def for_asr(cls) -> RetryPolicy:
        return cls(attempts=config.ATTEMPTS_DEFAULT, asr_500_attempts=config.ATTEMPTS_ASR_500)

    @classmethod
    def for_files(cls) -> RetryPolicy:
        return cls(attempts=config.ATTEMPTS_DEFAULT)

    def allows(self, attempt: int, status: int | None) -> bool:
        """May attempt number ``attempt + 1`` run after attempt ``attempt`` failed with ``status``?"""
        limit = self.attempts
        if status == 500 and self.asr_500_attempts is not None:
            limit = min(limit, self.asr_500_attempts)
        return attempt < limit


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Seconds from a ``Retry-After`` header (delta-seconds or HTTP-date); ``None`` if absent or bad."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    if math.isnan(seconds) or math.isinf(seconds):
        return None
    return max(0.0, seconds)


class RetryAfterTooLong(MetaUnavailable):
    """The server asked us to wait longer than :data:`config.RETRY_AFTER_CAP_S`: stop retrying."""

    default_retryable = False


def backoff_seconds(attempt: int, retry_after: float | None, jitter: float) -> float:
    """Wait before attempt ``attempt + 1``: ``min(30, 2^(attempt-1)) + jitter``, at least ``Retry-After``.

    ``jitter`` is drawn from ``uniform(0, 1)`` by the caller (tests pass 0). A ``Retry-After`` above the
    120 s cap raises :class:`RetryAfterTooLong`.
    """
    if attempt < 1:
        raise ValueError("attempt numbers start at 1")
    base = min(config.BACKOFF_CAP_S, config.BACKOFF_BASE_S * 2 ** (attempt - 1)) + jitter
    if retry_after is None:
        return base
    if retry_after > config.RETRY_AFTER_CAP_S:
        raise RetryAfterTooLong(f"Retry-After {retry_after:.0f}s exceeds the {config.RETRY_AFTER_CAP_S:.0f}s cap")
    return max(retry_after, base)


@dataclass
class CircuitBreaker:
    """Counts calls that failed after all their attempts. Five in 60 s open it for 60 s, then one trial."""

    clock: Callable[[], float] = time.monotonic
    failures: int = config.BREAKER_FAILURES
    window_s: float = config.BREAKER_WINDOW_S
    open_s: float = config.BREAKER_OPEN_S
    _recent: deque[float] = field(default_factory=deque[float])
    _opened_at: float | None = None
    _trial_in_flight: bool = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self.clock() - self._opened_at < self.open_s:
            return "open"
        return "half_open"

    def before_call(self) -> bool:
        """Raise :class:`MetaUnavailable` without a request while open; admit one trial when half-open.

        Returns whether this call is the half-open trial; pass that back to ``record_*``/``abandon_trial``.
        """
        state = self.state
        if state == "open" or (state == "half_open" and self._trial_in_flight):
            raise MetaUnavailable("circuit breaker open: Meta calls are failing, try again shortly")
        if state == "half_open":
            self._trial_in_flight = True
            return True
        return False

    def record_success(self, trial: bool = False) -> None:
        """An answered call while open or half-open (the trial, or a late call) proves the service is up:
        close the breaker. While closed it changes nothing: PRE-A §10.2/R6 counts five failed calls within
        60 s, not five in a row, so a partial outage (one endpoint failing while others answer) still opens it.
        """
        del trial  # any answered call closes an open breaker, trial or not
        if self._opened_at is None:
            return
        self._recent.clear()
        self._opened_at = None
        self._trial_in_flight = False

    def abandon_trial(self, trial: bool = True) -> None:
        """The trial call ended without telling us anything (budget stop, cancellation): allow another."""
        if trial:
            self._trial_in_flight = False

    def record_failure(self, trial: bool = False) -> None:
        now = self.clock()
        if self._opened_at is not None:
            # Open or half-open: a failure (the trial's, or a late call's) re-opens the full window.
            # Only the trial itself frees the trial slot, so a late failure can't admit a second trial.
            self._opened_at = now
            if trial:
                self._trial_in_flight = False
            return
        self._recent.append(now)
        while self._recent and now - self._recent[0] > self.window_s:
            self._recent.popleft()
        if len(self._recent) >= self.failures:
            self._opened_at = now
            self._recent.clear()
