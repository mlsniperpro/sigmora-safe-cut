"""Spend caps: who started a job (``Caller``) and a single-writer reservation ledger (PRE-A §10.2).

Every Meta attempt reserves its worst-case estimate against each cap that applies before it runs,
then settles the actual cost (or releases the reservation when the request was rejected before
processing). WP5 runs one ledger per service (a single Modal container); local runs use SQLite.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from safecut.config import CapKind, CodeKind, Settings
from safecut.meta.errors import BudgetExceeded

RESERVATION_TTL = timedelta(hours=2, minutes=30)

#: A tiny float tolerance so sums like 0.1 + 0.2 never trip a cap they exactly meet.
_EPS = 1e-9


@dataclass(frozen=True)
class CapLimit:
    """One cap a call counts against: ``key`` names the bucket (a job, a code, a UTC day)."""

    kind: CapKind
    key: str
    limit_usd: float


@dataclass(frozen=True)
class Caller:
    """Who started the job, and the caps (besides the job cap) their spend counts against.

    ``daily_usd`` puts the caller under the shared daily cap. Its bucket is the UTC day of each call, not of
    the job's start, so a job that runs past 00:00 UTC counts against the new day's cap.
    """

    code_kind: CodeKind
    code_id: str | None = None
    limits: tuple[CapLimit, ...] = ()
    daily_usd: float | None = None

    @classmethod
    def local(cls, kind: Literal["owner", "eval"] = "owner") -> Caller:
        """Owner, eval and WP runs that use no access code: only the job cap applies."""
        return cls(code_kind=kind)

    @classmethod
    def daily(cls, settings: Settings, code_kind: CodeKind, code_id: str | None) -> Caller:
        """Judge, public, service and system callers count against the shared daily cap."""
        return cls(code_kind=code_kind, code_id=code_id, daily_usd=settings.daily_usd_cap)

    def limits_at(self, now: datetime) -> tuple[CapLimit, ...]:
        """The caps a call made at ``now`` counts against."""
        if self.daily_usd is None:
            return self.limits
        day = now.astimezone(UTC).date().isoformat()
        return (*self.limits, CapLimit("daily", f"daily:{day}", self.daily_usd))


def job_limit(settings: Settings, job_id: str) -> CapLimit:
    return CapLimit("job", f"job:{job_id}", settings.job_usd_cap)


class Ledger(Protocol):
    """The single-writer interface WP5's ``budget`` function implements over the network."""

    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Sequence[CapLimit]) -> None: ...

    def settle(self, call_id: str, usd: float) -> None: ...

    def release(self, call_id: str) -> None: ...


class LocalLedger:
    """A SQLite-backed ledger (``:memory:`` by default). Thread-safe, and safe across processes on one file.

    ``reserve`` raises :class:`BudgetExceeded` naming the first cap that can't cover the estimate.
    ``reserve`` (with the same terms), ``settle`` and ``release`` are idempotent per ``call_id``; an unknown
    ``call_id`` is an error.
    """

    def __init__(self, path: str | Path = ":memory:", *, clock: type[datetime] = datetime) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS reservation (
                call_id TEXT PRIMARY KEY,
                job_id TEXT,
                usd REAL NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('open', 'settled', 'released', 'expired')),
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reservation_key (
                call_id TEXT NOT NULL REFERENCES reservation(call_id),
                key TEXT NOT NULL,
                PRIMARY KEY (call_id, key)
            );
            CREATE INDEX IF NOT EXISTS reservation_key_by_key ON reservation_key(key);
            """
        )

    def _now(self) -> datetime:
        return self._clock.now(UTC)

    def spent(self, key: str) -> float:
        """Reserved plus settled USD in a bucket (released reservations count 0)."""
        with self._lock:
            return self._spent(key)

    def _spent(self, key: str) -> float:
        row = self._db.execute(
            """SELECT COALESCE(SUM(r.usd), 0) FROM reservation r JOIN reservation_key k USING (call_id)
               WHERE k.key = ? AND r.state != 'released'""",
            (key,),
        ).fetchone()
        return float(row[0])

    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Sequence[CapLimit]) -> None:
        if usd < 0:
            raise ValueError("a reservation can't be negative")
        with self._lock:
            # BEGIN IMMEDIATE takes SQLite's write lock before the sums are read, so two processes
            # sharing one ledger file can't both pass the same stale total.
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if not self._same_reservation(call_id, job_id, usd, limits):
                    self._check_and_insert(call_id, job_id, usd, limits)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _same_reservation(self, call_id: str, job_id: str | None, usd: float, limits: Sequence[CapLimit]) -> bool:
        """A retried ``reserve`` whose ack was lost is a no-op (PRE-A §10.2); other terms under one id are a bug."""
        row = self._db.execute("SELECT job_id, usd FROM reservation WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            return False
        keys = {str(k[0]) for k in self._db.execute("SELECT key FROM reservation_key WHERE call_id = ?", (call_id,))}
        if row[0] != job_id or abs(float(row[1]) - usd) > _EPS or keys != {lim.key for lim in limits}:
            raise ValueError(f"call_id {call_id!r} already reserved with different terms")
        return True

    def _check_and_insert(self, call_id: str, job_id: str | None, usd: float, limits: Sequence[CapLimit]) -> None:
        if usd > 0:  # a free call (files, token counts, deletes) never trips a cap, even one already spent
            for limit in limits:
                spent = self._spent(limit.key)
                if spent + usd > limit.limit_usd + _EPS:
                    raise BudgetExceeded(
                        f"{limit.kind} cap: ${spent:.4f} of ${limit.limit_usd:.2f} used, this call needs ${usd:.4f}",
                        cap=limit.kind,
                        limit_usd=limit.limit_usd,
                        needed_usd=usd,
                    )
        expires = (self._now() + RESERVATION_TTL).isoformat()
        self._db.execute("INSERT INTO reservation VALUES (?, ?, ?, 'open', ?)", (call_id, job_id, usd, expires))
        self._db.executemany(
            "INSERT OR IGNORE INTO reservation_key VALUES (?, ?)", [(call_id, lim.key) for lim in limits]
        )

    def _state(self, call_id: str) -> str:
        row = self._db.execute("SELECT state FROM reservation WHERE call_id = ?", (call_id,)).fetchone()
        if row is None:
            raise KeyError(f"no reservation {call_id!r}")
        return str(row[0])

    def settle(self, call_id: str, usd: float) -> None:
        """Replace the reservation with the actual (or kept estimated) charge. Idempotent."""
        if usd < 0:
            raise ValueError("a charge can't be negative")
        with self._lock:
            if self._state(call_id) != "open":
                return
            self._db.execute("UPDATE reservation SET usd = ?, state = 'settled' WHERE call_id = ?", (usd, call_id))

    def release(self, call_id: str) -> None:
        """The request was rejected before processing: free the reservation. Idempotent."""
        with self._lock:
            if self._state(call_id) != "open":
                return
            self._db.execute("UPDATE reservation SET usd = 0, state = 'released' WHERE call_id = ?", (call_id,))

    def sweep_expired(self) -> list[str]:
        """Keep each expired open reservation as an estimated charge (a killed worker may have spent it)."""
        with self._lock:
            now = self._now().isoformat()
            rows = self._db.execute(
                "SELECT call_id FROM reservation WHERE state = 'open' AND expires_at <= ?", (now,)
            ).fetchall()
            ids = [str(r[0]) for r in rows]
            self._db.executemany("UPDATE reservation SET state = 'expired' WHERE call_id = ?", [(i,) for i in ids])
            return ids

    def close(self) -> None:
        with self._lock:
            self._db.close()
