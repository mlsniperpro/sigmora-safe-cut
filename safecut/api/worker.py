"""Runs pipeline actions for the API in background threads and keeps each job's ``state.json`` current.

Three actions: ``analyse`` (prepare … guard, then ``review``), ``publish`` (render → audit → receipt, then ``done``,
or ``needs_you`` when the audit couldn't run or finish) and ``audit`` ("Run the audit again": the audit on the
existing render, then the receipt). Failures become UI-SPEC §8 request 1's ``failure.reason`` values; a transient
Meta failure re-queues the job **once**, five minutes later (``retry_later``), and fails it as ``upstream`` if the
retry fails too.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from safecut import pipeline
from safecut.api.access import Access, ApiRefusal, next_midnight
from safecut.api.store import Failure, FailureReason, JobNotFound, JobState, JobStore, StageName
from safecut.config import Settings
from safecut.contracts import Audit, load, validate_job_dir
from safecut.meta.errors import (
    BudgetExceeded,
    MetaAuthError,
    MetaBadRequest,
    MetaBillingError,
    MetaConfigError,
    MetaIncomplete,
    MetaRateLimited,
    MetaRefusal,
    MetaUnavailable,
)
from safecut.stages import STAGES, Stage, phase

log = logging.getLogger("safecut.api.worker")

Action = Literal["analyse", "publish", "audit"]
RETRY_DELAY = timedelta(minutes=5)

_CAP_REASON: dict[str, FailureReason] = {
    "job": "job_cap",
    "daily": "daily_cap",
    "code": "code_cap",
    "pilot_pool": "pilot_pool_cap",
}


class MediaRejected(pipeline.PipelineError):
    """``prepare`` refused the clip: too long, too large, or not a readable video (UI-SPEC §8 request 17)."""

    def __init__(
        self,
        reason: Literal["too_long", "too_large", "bad_media"],
        message: str,
        *,
        duration_s: float | None = None,
        size_bytes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason: Literal["too_long", "too_large", "bad_media"] = reason
        self.duration_s = duration_s
        self.size_bytes = size_bytes


def failure_for(exc: BaseException, stage: StageName | None) -> tuple[Failure, bool]:
    """``(failure, transient)``: the reason the UI shows, and whether one re-queue may fix it."""
    detail = f"{type(exc).__name__}: {exc}"[:300]
    reason: FailureReason = "internal"
    transient = False
    extra: dict[str, float | int] = {}
    reject = _media_rejection(exc)
    if reject is not None:
        reason = reject.reason
        if reject.duration_s:
            extra["duration_s"] = reject.duration_s
        if reject.size_bytes:
            extra["size_bytes"] = reject.size_bytes
    elif isinstance(exc, pipeline.JobCapReached):
        reason = "job_cap"
    elif isinstance(exc, BudgetExceeded):
        reason = _CAP_REASON.get(exc.cap, "internal")
    elif isinstance(exc, MetaAuthError | MetaConfigError | MetaBillingError):
        reason = "config"
    elif isinstance(exc, MetaBadRequest):
        reason = "bad_request"
    elif isinstance(exc, MetaRefusal):
        reason = "refusal"
    elif isinstance(exc, MetaIncomplete):
        reason = "incomplete"
    elif isinstance(exc, MetaUnavailable | MetaRateLimited):
        reason, transient = "upstream", True
    return Failure(stage=stage, reason=reason, detail=detail, **extra), transient  # pyright: ignore[reportArgumentType] -- extra keys are Failure's own


#: ``prepare``'s rejection reasons (``safecut.prepare.PrepareError.reason``) → the UI's (UI-SPEC §8 request 17).
#: ``no_source`` isn't the creator's clip being bad (the job folder lost its upload), so it stays ``internal``.
_MEDIA_REASONS: dict[str, Literal["too_long", "too_large", "bad_media"]] = {
    "too_long": "too_long",
    "too_large": "too_large",
    "bad_media": "bad_media",
    "unreadable": "bad_media",
    "no_video": "bad_media",
}
_DURATION = re.compile(r"^(\d+(?:\.\d+)?) s is over")
_SIZE = re.compile(r"^(\d+) bytes is over")


def _media_rejection(exc: BaseException) -> MediaRejected | None:
    """A ``prepare`` rejection, whichever module raised it: :class:`MediaRejected`, or any exception carrying one
    of ``prepare``'s ``reason`` codes. The clip's length or size comes from the exception's attributes, or from the
    start of its message (``"61.20 s is over …"``, ``"157286401 bytes is over …"``)."""
    if isinstance(exc, MediaRejected):
        return exc
    reason = _MEDIA_REASONS.get(str(getattr(exc, "reason", "")))
    if reason is None:
        return None
    duration = getattr(exc, "duration_s", None)
    size = getattr(exc, "size_bytes", None)
    if duration is None and (match := _DURATION.match(str(exc))):
        duration = float(match.group(1))
    if size is None and (match := _SIZE.match(str(exc))):
        size = int(match.group(1))
    return MediaRejected(
        reason,
        str(exc),
        duration_s=duration if isinstance(duration, int | float) else None,
        size_bytes=size if isinstance(size, int) else None,
    )


class Worker:
    """A bounded pool of pipeline threads. ``submit`` returns at once; the job's state tells the rest."""

    def __init__(
        self,
        store: JobStore,
        settings: Settings,
        *,
        max_workers: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.access = Access(settings)
        self._pool = ThreadPoolExecutor(max_workers=max_workers or settings.workers, thread_name_prefix="job")
        self._running: dict[str, Future[None]] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._now = clock or (lambda: datetime.now(UTC))

    def busy(self, job_id: str) -> bool:
        with self._lock:
            future = self._running.get(job_id)
            return future is not None and not future.done()

    def submit(self, job_id: str, action: Action) -> Future[None]:
        with self._lock:
            future = self._pool.submit(self._run, job_id, action)
            self._running[job_id] = future
            return future

    def submit_later(self, job_id: str, action: Action, delay_s: float) -> None:
        """The one re-queue, ``delay_s`` from now; it re-checks the job's code when it fires (``_requeue``)."""
        timer = threading.Timer(delay_s, self._requeue, (job_id, action))
        timer.daemon = True
        with self._lock:
            self._timers[job_id] = timer
        timer.start()

    def wait(self, job_id: str, timeout: float = 120) -> None:
        """Block until the job's current action finishes (tests and the CLI's ``serve --once``)."""
        with self._lock:
            future = self._running.get(job_id)
        if future is not None:
            future.result(timeout=timeout)

    def cancel(self, job_id: str) -> None:
        """Drop a pending re-queue (the job was deleted). A running stage finishes and then finds no job."""
        with self._lock:
            timer = self._timers.pop(job_id, None)
        if timer is not None:
            timer.cancel()

    def shutdown(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()
        self._pool.shutdown(wait=True, cancel_futures=True)

    # -- one action -------------------------------------------------------

    def _set(self, job_id: str, **fields: object) -> JobState:
        with self.store.update(job_id) as state:
            for key, value in fields.items():
                setattr(state, key, value)
            return state.model_copy()

    def _run(self, job_id: str, action: Action) -> None:
        try:
            state = self.store.get(job_id)
        except JobNotFound:
            return
        job_dir = self.store.path(job_id)
        replay = state.mode == "replay"
        current: list[StageName | None] = [None]

        def on_stage(stage: Stage) -> None:
            current[0] = stage.name  # type: ignore[assignment] -- every registry name is a StageName
            self._set(job_id, stage=stage.name, stage_reason=None)

        try:
            if action == "analyse":
                self._set(
                    job_id, status="processing", stage="queued", failure=None, retry_at=None, started_at=self._now()
                )
                pipeline.analyse(job_dir, replay=replay, settings=self.settings, on_stage=on_stage)
                self._set(job_id, status="review", stage="review", stage_reason=None)
            else:
                self._set(
                    job_id,
                    status="rendering",
                    stage="audit" if action == "audit" else "render",
                    failure=None,
                    retry_at=None,
                    started_at=self._now(),
                )
                self._publish(job_dir, action, replay=replay, on_stage=on_stage)
        except JobNotFound:
            return  # deleted while running
        except BaseException as exc:
            if not job_dir.is_dir():
                return
            failure, transient = failure_for(exc, current[0] or "queued")
            log.warning("job %s %s failed at %s: %s", job_id, action, current[0], failure.detail)
            self._fail(job_id, action, failure, transient=transient)
            if not isinstance(exc, Exception):
                raise

    def _publish(self, job_dir: Path, action: Action, *, replay: bool, on_stage: Callable[[Stage], None]) -> None:
        pipeline.check_approval(job_dir)
        for stage in phase("publish"):
            if action == "audit" and stage.name == "render":
                continue
            force = action == "audit" and stage.name in ("audit", "receipt")
            if force or not pipeline.is_fresh(job_dir, stage):
                on_stage(stage)
            pipeline.run_stage(job_dir, stage, replay=replay, settings=self.settings, force=force)
            if stage.name == "audit":
                audit = load(job_dir / "audit.json", Audit)
                if audit.blocked_reason in ("audit_failed", "over_budget"):
                    self._set(job_dir.name, status="needs_you", stage="audit", stage_reason=None)
                    return
        # Publishing is gated by the cross-file checks (ARCHITECTURE §3): a job whose files disagree never ends done.
        validate_job_dir(job_dir)
        self._set(job_dir.name, status="done", stage="done", stage_reason=None)

    def _fail(self, job_id: str, action: Action, failure: Failure, *, transient: bool) -> None:
        try:
            state = self.store.get(job_id)
        except JobNotFound:
            return
        if transient and state.requeues == 0:
            retry_at = self._now() + RETRY_DELAY
            self._set(job_id, status="retry_later", retry_at=retry_at, requeues=1, failure=None)
            self.submit_later(job_id, action, RETRY_DELAY.total_seconds())
            return
        retry_at = next_midnight(self._now()) if failure.reason == "daily_cap" else None
        self._set(job_id, status="failed", failure=failure, retry_at=retry_at)

    def _requeue(self, job_id: str, action: Action) -> None:
        """The one re-queue: refused as ``code_not_active`` if the job's code window closed meanwhile."""
        with self._lock:
            self._timers.pop(job_id, None)
        try:
            state = self.store.get(job_id)
        except JobNotFound:
            return
        if state.code_kind is not None or state.service is not None:
            try:
                grant = self.access.job_grant(code_kind=state.code_kind, cid=state.code_id, service=state.service)
                self.access.require_active(grant, now=self._now())
            except ApiRefusal:
                self._set(job_id, status="failed", failure=Failure(stage=state.stage, reason="code_not_active"))
                return
        self.submit(job_id, action)


def stage_index(name: str | None) -> int:
    names = [s.name for s in STAGES]
    return names.index(name) if name in names else -1


__all__ = ["Action", "MediaRejected", "Worker", "failure_for", "stage_index"]
