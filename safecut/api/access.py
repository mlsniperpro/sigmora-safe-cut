"""Who may call the API, and how much they may spend (WP5 step 2; UI-SPEC §8 requests 17, 20, 21).

Two ways in: a judge/public/pilot/recording/owner **access code** (``SAFECUT_ACCESS_CODES``, sent in the body of
``POST /v1/codes/check`` and ``POST /v1/jobs`` and then bound to the job), or a Sigmora **service key**
(``SAFECUT_SERVICE_KEYS``, ``Authorization: Bearer <key>`` on ``POST /v1/jobs``). Every request that can start
paid work re-checks the bound code: revoked → ``401``, outside its window → ``401 code_not_active``. Reading,
reviewing and deleting a job need only its link.
"""

from __future__ import annotations

import hmac
import logging
import math
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from safecut.config import AccessCode, Settings
from safecut.meta.budget import LocalLedger
from safecut.pipeline import code_id

log = logging.getLogger(__name__)

#: PRE-A §9.2 / §10.3: a job's worst-case estimate is max($1.12, seconds × $2.24 / 60).
ESTIMATE_FLOOR_USD = 1.12
ESTIMATE_PER_MINUTE_USD = 2.24
MAX_UPLOAD_BYTES = 157_286_400  # 150 × 1024 × 1024 (UI-SPEC §10.2)
MAX_DURATION_S = 60.05  # 60 s plus a 0.05 s container tolerance (UI-SPEC §10.2)


class ApiRefusal(Exception):
    """An HTTP error with the UI-SPEC error body ``{"error": {"code", "message", …}}``."""

    def __init__(
        self, status: int, code: str, message: str, *, retry_after_s: float | None = None, **extra: object
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after_s = retry_after_s
        self.extra = extra

    def body(self) -> dict[str, object]:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


@dataclass(frozen=True)
class Grant:
    """A checked caller: an access code's kind and ID, or a service key's name."""

    kind: str
    code_id: str | None
    service: str | None
    cap_usd: float | None
    valid_from: datetime | None
    valid_until: datetime | None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


class Access:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def window(self, kind: str, entry: AccessCode | None = None) -> tuple[datetime | None, datetime | None]:
        """The code's validity window: its kind's window, narrowed by the entry's own dates."""
        base = self.settings.code_windows[kind]  # type: ignore[index] -- kind is a WindowKind by construction
        start, until = base.start, base.until
        if entry is not None:
            start = max(filter(None, (start, entry.valid_from)), default=None)
            until = min(filter(None, (until, entry.valid_until)), default=None)
        return start, until

    def _grant(self, entry: AccessCode) -> Grant:
        start, until = self.window(entry.kind, entry)
        return Grant(entry.kind, code_id(entry.code.get_secret_value()), None, entry.cap_usd, start, until)

    def check_code(self, code: str) -> Grant:
        """``401`` for an unknown code (constant-time compare against every configured code)."""
        found: AccessCode | None = None
        for entry in self.settings.access_codes:
            if hmac.compare_digest(entry.code.get_secret_value().encode(), code.encode()):
                found = entry
        if found is None:
            raise ApiRefusal(401, "unauthorized", "That code didn't work.")
        return self._grant(found)

    def by_code_id(self, cid: str) -> Grant | None:
        """The grant behind a job's bound code, or None once the code was revoked."""
        for entry in self.settings.access_codes:
            if code_id(entry.code.get_secret_value()) == cid:
                return self._grant(entry)
        return None

    def check_service_key(self, authorization: str | None) -> Grant | None:
        """A ``Bearer`` service key, or None when no Authorization header was sent; ``401`` for a wrong key."""
        if not authorization:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise ApiRefusal(401, "unauthorized", "Use Authorization: Bearer <service key>.")
        found = None
        for entry in self.settings.service_keys:
            if hmac.compare_digest(entry.key.get_secret_value().encode(), token.strip().encode()):
                found = entry
        if found is None:
            raise ApiRefusal(401, "unauthorized", "Unknown service key.")
        start, until = self.window("service")
        return Grant("service", None, found.name, None, start, until)

    def require_active(self, grant: Grant, *, now: datetime | None = None) -> None:
        """``401 code_not_active`` outside the grant's window (both date keys always present)."""
        now = now or datetime.now(UTC)
        if (grant.valid_from and now < grant.valid_from) or (grant.valid_until and now > grant.valid_until):
            raise ApiRefusal(
                401,
                "code_not_active",
                "This code isn't active right now.",
                valid_from=_iso(grant.valid_from),
                valid_until=_iso(grant.valid_until),
            )

    def job_grant(self, *, code_kind: str | None, cid: str | None, service: str | None) -> Grant:
        """Re-check the code a job is bound to, for a paid action on it: revoked → plain ``401``."""
        if service is not None:
            if not any(k.name == service for k in self.settings.service_keys):
                raise ApiRefusal(401, "unauthorized", "The service key for this clip no longer works.")
            start, until = self.window("service")
            return Grant("service", None, service, None, start, until)
        if cid is None or code_kind is None:
            raise ApiRefusal(401, "unauthorized", "This clip has no access code.")
        grant = self.by_code_id(cid)
        if grant is None:
            raise ApiRefusal(401, "unauthorized", "The access code for this clip no longer works.")
        return grant


#: The audit's passes (``safecut.audit.loop.MAX_PASSES``; a test keeps them equal): each scans on the GPU once. A
#: transient failure's one retry is reserved in the ledger call by call, so the caps hold it even past this estimate.
GPU_SCANS_PER_JOB = 3


def estimate_usd(duration_s: float | None, settings: Settings | None = None) -> float:
    """PRE-A §9.2's worst case for a job of this length (the floor when the length is unknown), plus, with
    ``SAFECUT_AUDIT_GPU=1``, the GPU auditor's: every pass's scan at its timeout and the idle tail, at the GPU
    container's hourly rate (the ledger then holds each call to its own reservation). Not for ``yunet-face``, which
    never calls the GPU (``Settings.audit_on_gpu``)."""
    meta = (
        ESTIMATE_FLOOR_USD if duration_s is None else max(ESTIMATE_FLOOR_USD, duration_s * ESTIMATE_PER_MINUTE_USD / 60)
    )
    if settings is None or not settings.audit_on_gpu:
        return meta
    seconds = GPU_SCANS_PER_JOB * settings.audit_gpu_timeout_s + settings.audit_gpu_idle_s
    return meta + seconds * settings.audit_gpu_usd_per_hour / 3600


def next_midnight(now: datetime) -> datetime:
    day = now.astimezone(UTC).date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def check_caps(
    settings: Settings, ledger: LocalLedger, grant: Grant, *, estimate: float, now: datetime | None = None
) -> None:
    """Refuse before any call when a cap can't cover the estimate (UI-SPEC §8 request 1, PRE-A §10.3)."""
    now = now or datetime.now(UTC)
    if estimate > settings.job_usd_cap:
        raise ApiRefusal(422, "job_cap", "This clip would cost more than the per-clip limit.")
    if grant.kind == "pilot":
        if grant.code_id and ledger.spent(f"code:{grant.code_id}") + estimate > (grant.cap_usd or 0):
            raise ApiRefusal(429, "code_cap", "This access code doesn't have enough budget left for this clip.")
        if ledger.spent("pool:pilot") + estimate > settings.pilot_pool_usd:
            raise ApiRefusal(429, "pilot_pool_cap", "The pilot budget has been used up.")
        return
    if grant.kind in ("recording", "owner"):
        if grant.code_id and ledger.spent(f"code:{grant.code_id}") + estimate > (grant.cap_usd or 0):
            raise ApiRefusal(429, "code_cap", "This access code doesn't have enough budget left for this clip.")
        return
    day = now.astimezone(UTC).date().isoformat()
    if ledger.spent(f"daily:{day}") + estimate > settings.daily_usd_cap:
        retry = next_midnight(now)
        raise ApiRefusal(
            429,
            "daily_cap",
            "Safe Cut has reached today's limit.",
            retry_after_s=math.ceil((retry - now).total_seconds()),
            retry_at=_iso(retry),
        )


class RateLimiter:
    """A sliding-window counter per (bucket, client IP), in memory: the API runs as one container (PRE-A
    ``research/modal.md``), so one process sees every request. Old windows are pruned as they are touched."""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()
        self._monotonic = monotonic

    def hit(self, bucket: str, client: str, *, limit: int, window_s: float) -> None:
        """Count one request; ``429 rate_limited`` (with ``Retry-After``) when the window is full."""
        now = self._monotonic()
        key = (bucket, client)
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < window_s]
            if len(recent) >= limit:
                self._hits[key] = recent
                wait = max(1, math.ceil(window_s - (now - recent[0])))
                raise ApiRefusal(429, "rate_limited", "Too many tries in a short time.", retry_after_s=wait)
            recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > 50_000:  # bound memory under a flood of distinct IPs
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < window_s}


class StoredRateLimiter:
    """:class:`RateLimiter`'s sliding window, kept in SQLite on the jobs Volume beside the spend ledger, for limits
    whose window outlasts a container: the API scales to zero, and a fresh container must not hand a client a
    fresh hour. Wall-clock times, since a monotonic clock restarts with the process.

    Its state is disposable, and the service must not go down with it: a file that won't open (left malformed by a
    container that died mid-write) is moved aside and started afresh, and a query that fails falls back to an
    in-memory window for that request, logged."""

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._clock = clock
        self._fallback = RateLimiter()
        self._db: sqlite3.Connection | None = None
        try:
            self._db = self._open(path)
        except sqlite3.OperationalError:
            # Locked, or an I/O error: transient, never a reason to throw the hour's window away; this container
            # counts in memory until its next start.
            log.exception("rate-limit store %s won't open; counting in memory for this container", path)
        except sqlite3.DatabaseError:  # "file is not a database", "malformed": the file itself is broken
            aside = path.with_name(f"{path.name}.corrupt-{int(clock())}")
            log.exception("rate-limit store %s won't open; moved aside to %s and started afresh", path, aside.name)
            for suffix in ("", "-wal", "-shm"):
                part = path.with_name(path.name + suffix)
                if part.exists():
                    part.replace(aside.with_name(aside.name + suffix))
            self._db = self._open(path)

    @staticmethod
    def _open(path: Path) -> sqlite3.Connection:
        db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        try:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS hit (bucket TEXT NOT NULL, client TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS hit_by_key ON hit(bucket, client, at);
                """
            )
            db.execute("SELECT COUNT(*) FROM hit").fetchone()
        except sqlite3.DatabaseError:
            db.close()
            raise
        return db

    def hit(self, bucket: str, client: str, *, limit: int, window_s: float) -> None:
        """Count one request; ``429 rate_limited`` (with ``Retry-After``) when the window is full."""
        now = self._clock()
        if self._db is None:
            self._fallback.hit(bucket, client, limit=limit, window_s=window_s)
            return
        try:
            full, oldest = self._count(self._db, bucket, client, now, limit=limit, window_s=window_s)
        except sqlite3.Error:
            log.exception("rate-limit store failed; this request is counted in memory")
            self._fallback.hit(bucket, client, limit=limit, window_s=window_s)
            return
        if full:
            wait = max(1, math.ceil(window_s - (now - oldest)))
            raise ApiRefusal(429, "rate_limited", "Too many tries in a short time.", retry_after_s=wait)

    def _count(
        self, db: sqlite3.Connection, bucket: str, client: str, now: float, *, limit: int, window_s: float
    ) -> tuple[bool, float]:
        with self._lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("DELETE FROM hit WHERE bucket = ? AND at <= ?", (bucket, now - window_s))
                rows = db.execute(
                    "SELECT at FROM hit WHERE bucket = ? AND client = ? ORDER BY at", (bucket, client)
                ).fetchall()
                full = len(rows) >= limit
                if not full:
                    db.execute("INSERT INTO hit VALUES (?, ?, ?)", (bucket, client, now))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return full, float(rows[0][0]) if rows else now

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()


__all__ = [
    "MAX_DURATION_S",
    "MAX_UPLOAD_BYTES",
    "Access",
    "ApiRefusal",
    "Grant",
    "RateLimiter",
    "StoredRateLimiter",
    "check_caps",
    "code_id",
    "estimate_usd",
    "next_midnight",
]
