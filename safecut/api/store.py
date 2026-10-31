"""Where the API keeps jobs: one directory per job under ``SAFECUT_JOBS_DIR``, plus ``state.json`` for what the
pipeline files can't say (who started it, its status and stage, the upload it expects, when it is deleted).

Job IDs are 128-bit random tokens: the job link is the capability that authorises reading, editing and deleting
a job (UI-SPEC §8 request 17), so it must be unguessable.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from safecut.contracts import ContractError, dump, load

STATE = "state.json"
JOB_ID_PATTERN = r"^j_[A-Za-z0-9_-]{22}$"

JobStatus = Literal["created", "processing", "retry_later", "review", "rendering", "done", "needs_you", "failed"]
#: A job in one of these is being worked on: ``Service.recover`` resumes it after a restart.
ACTIVE: tuple[JobStatus, ...] = ("processing", "rendering", "retry_later")
StageName = Literal[
    "queued",
    "prepare",
    "track",
    "transcribe",
    "scene",
    "roles",
    "miss_loop",
    "decide",
    "guard",
    "review",
    "render",
    "audit",
    "receipt",
    "done",
]
FailureReason = Literal[
    "internal",
    "upstream",
    "job_cap",
    "daily_cap",
    "code_cap",
    "pilot_pool_cap",
    "config",
    "bad_request",
    "refusal",
    "incomplete",
    "code_not_active",
    "too_long",
    "too_large",
    "bad_media",
]
CodeKindName = Literal["judge", "public", "pilot", "recording", "owner", "service"]


class Failure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: StageName | None = None
    reason: FailureReason | None = None
    duration_s: float | None = Field(default=None, gt=0)
    size_bytes: int | None = Field(default=None, gt=0)
    #: For the operator only; never sent to the browser (it may name internals).
    detail: str | None = None


class UploadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size_bytes: int = Field(gt=0)
    content_type: Literal["video/mp4", "video/quicktime"]
    file_name: str = Field(min_length=1, max_length=255)
    expires_at: datetime
    received: bool = False


class JobState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(pattern=JOB_ID_PATTERN)
    mode: Literal["live", "replay"]
    status: JobStatus
    stage: StageName | None = None
    stage_reason: Literal["audit_patch"] | None = None
    failure: Failure | None = None
    created_at: datetime
    updated_at: datetime
    deletes_at: datetime
    retry_at: datetime | None = None
    #: Who started it: an access code (by ID, never the code itself) or a service key (by name).
    code_id: str | None = None
    code_kind: CodeKindName | None = None
    service: str | None = None
    upload: UploadSpec | None = None
    pinned: bool = False
    #: A pinned demo job's build stamp (its recording, its clip and the code): a different stamp rebuilds it.
    demo_stamp: str | None = None
    started_at: datetime | None = None
    #: How many times a ``retry_later`` job was re-queued (once at most, UI-SPEC §8 request 1).
    requeues: int = 0
    #: Restarts that found this job mid-action (``Service.recover``); reset when an action finishes. A job that keeps
    #: taking its container down with it fails after ``MAX_RESUMES`` instead of waking a new one forever.
    resumes: int = Field(default=0, ge=0)
    #: The clip length in seconds, once known (for the cap estimate and ``eta_s``).
    duration_s: float | None = None
    #: A replay of synthetic recordings (the drawn test clip): every response says so (AGENTS rule 9).
    synthetic: bool = False


def new_job_id() -> str:
    return "j_" + secrets.token_urlsafe(16)


class JobNotFound(LookupError):
    def __init__(self, job_id: str, *, expired: bool = False) -> None:
        super().__init__(job_id)
        self.expired = expired


class JobStore:
    """Job directories under one root, with a lock per job for state updates within this process."""

    def __init__(self, root: Path, *, ttl: timedelta, cleanup_every: timedelta) -> None:
        self.root = root
        self.ttl = ttl
        self.cleanup_every = cleanup_every
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()
        #: Held across the two renames of ``replace_pinned``; ``get`` takes it only when a job folder looks missing.
        self._swap = threading.Lock()

    def path(self, job_id: str) -> Path:
        return self.root / job_id

    def _lock(self, job_id: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(job_id, threading.RLock())

    def deletes_at(self, created_at: datetime) -> datetime:
        """The latest time the cleanup will have removed a job: its TTL plus one cleanup interval."""
        return created_at + self.ttl + self.cleanup_every

    def create(
        self,
        *,
        mode: Literal["live", "replay"],
        now: datetime | None = None,
        job_id: str | None = None,
        pinned: bool = False,
        **fields: object,
    ) -> JobState:
        now = now or datetime.now(UTC)
        job_id = job_id or new_job_id()
        state = JobState.model_validate(
            {
                "job_id": job_id,
                "mode": mode,
                "status": "created",
                "created_at": now,
                "updated_at": now,
                "deletes_at": self.deletes_at(now),
                "pinned": pinned,
                **fields,
            }
        )
        self.path(job_id).mkdir(parents=True, exist_ok=False)
        dump(state, self.path(job_id) / STATE)
        return state

    def get(self, job_id: str, *, now: datetime | None = None) -> JobState:
        """The job's state; a job past ``deletes_at`` is deleted on sight and reported expired."""
        if not _valid_id(job_id):
            raise JobNotFound(job_id)
        path = self.path(job_id) / STATE
        if not path.is_file():
            with self._swap:  # a replace_pinned in its two renames: wait the microseconds, then look again
                if not path.is_file():
                    raise JobNotFound(job_id)
        try:
            state = load(path, JobState)
        except ContractError:
            # Gone between the check and the read: a swap in flight. Read again once it is done.
            with self._swap:
                if not path.is_file():
                    raise JobNotFound(job_id) from None
                try:
                    state = load(path, JobState)
                except ContractError:
                    raise JobNotFound(job_id) from None
        if not state.pinned and (now or datetime.now(UTC)) >= state.deletes_at:
            self.delete(job_id)
            raise JobNotFound(job_id, expired=True)
        return state

    @contextmanager
    def update(self, job_id: str) -> Generator[JobState]:
        """Read-modify-write one job's state under its lock: mutate the yielded copy, and it is saved on exit."""
        with self._lock(job_id):
            state = self.get(job_id)
            yield state
            state.updated_at = datetime.now(UTC)
            if self.path(job_id).is_dir():
                dump(JobState.model_validate(state.model_dump()), self.path(job_id) / STATE)

    def replace_pinned(self, job_id: str, built: Path, *, now: datetime | None = None, **fields: object) -> JobState:
        """Swap a fully built folder in as the pinned job ``job_id`` (the demo), replacing any earlier one: its state
        is written into ``built`` first, then two renames under the swap lock, which ``get`` honours on a miss, so a
        reader sees the old job or the new one, never neither. If the second rename fails the old job is put back."""
        now = now or datetime.now(UTC)
        state = JobState.model_validate(
            {"job_id": job_id, "mode": "replay", "status": "done", "stage": "done", "created_at": now,
             "updated_at": now, "deletes_at": self.deletes_at(now), "pinned": True, **fields}
        )  # fmt: skip
        dump(state, built / STATE)
        target = self.path(job_id)
        doomed = self.root / f"{DELETING}{job_id}-{secrets.token_hex(4)}"
        with self._lock(job_id), self._swap:
            had = target.exists()
            if had:
                target.rename(doomed)
            try:
                built.rename(target)
            except BaseException:
                if had:
                    doomed.rename(target)
                raise
        if had:
            _reap(doomed)
        return state

    def delete(self, job_id: str) -> bool:
        """Remove the whole job directory (every upload, response, render and receipt). True if it existed."""
        if not _valid_id(job_id):
            return False
        with self._lock(job_id):
            target = self.path(job_id)
            if not target.exists():
                return False
            # Renamed first, atomically: the job is gone for every reader at once, a stage still writing into it
            # can't make the removal fail, and anything it re-creates under the old path has no state (a 404,
            # reaped by the sweep).
            doomed = self.root / f"{DELETING}{job_id}-{secrets.token_hex(4)}"
            target.rename(doomed)
        _reap(doomed)
        return True

    def reap_orphan(self, job_id: str) -> bool:
        """Remove ``job_id``'s directory if it has no state: what a stage still running wrote after the job was
        deleted (``dump`` re-creates parent folders). True if something was removed."""
        if not _valid_id(job_id):
            return False
        with self._lock(job_id):
            target = self.path(job_id)
            if not target.is_dir() or (target / STATE).exists():
                return False
            doomed = self.root / f"{DELETING}{job_id}-{secrets.token_hex(4)}"
            target.rename(doomed)
        _reap(doomed)
        return True

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and _valid_id(p.name))

    def active(self) -> list[str]:
        """Jobs mid-action on disk (not pinned demo jobs): what a container that went to sleep may have left."""
        found: list[str] = []
        for job_id in self.ids():
            try:
                state = self.get(job_id)
            except (JobNotFound, ContractError):
                continue
            if not state.pinned and state.status in ACTIVE:
                found.append(job_id)
        return found

    def sweep(self, *, now: datetime | None = None) -> list[str]:
        """The 24 h deletion job: remove every unpinned job created more than the TTL ago (and any directory
        whose state can't be read, which can't be trusted to expire on its own). Returns the removed IDs."""
        now = now or datetime.now(UTC)
        removed: list[str] = []
        for job_id in self.ids():
            try:
                state = load(self.path(job_id) / STATE, JobState)
            except ContractError:
                if (self.path(job_id) / STATE).exists():
                    # Present but not valid (a deploy whose schema moved on, a torn write): its own created_at
                    # still decides, so a schema change never deletes live jobs early nor keeps one past its TTL.
                    created = _created_at(self.path(job_id) / STATE)
                    expired = (now - created if created else _age(self.path(job_id), now)) >= self.ttl
                else:
                    # No state at all: what a stage re-created after its job was deleted. A job is created with
                    # its state in the same breath, so only one older than a minute is reaped.
                    expired = _age(self.path(job_id), now) > STATELESS_GRACE
            else:
                expired = not state.pinned and now >= state.created_at + self.ttl
            if expired and self.delete(job_id):
                removed.append(job_id)
        for leftover in self.root.glob(f"{DELETING}*"):
            _reap(leftover)  # a deletion a crash or a busy writer left half done
        building = self.root / BUILDING
        for leftover in building.iterdir() if building.is_dir() else ():
            if _age(leftover, now) > BUILD_GRACE:
                _reap(leftover)  # a demo build whose container died before it finished
        return removed


#: A deleted job's directory while it's removed (never a valid job ID, so nothing serves it).
DELETING = ".deleting-"
#: Where a pinned demo job is built before ``replace_pinned`` swaps it in (``Service._precompute``); skipped by ``ids``.
BUILDING = ".building"
#: A build folder this old belongs to a container that died mid-build: the sweep removes it.
BUILD_GRACE = timedelta(hours=2)
STATELESS_GRACE = timedelta(minutes=1)


def _reap(path: Path) -> None:
    """Remove a renamed job directory; a writer that still has a file open there can make one pass fail."""
    for _ in range(5):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.05)


def _created_at(path: Path) -> datetime | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["created_at"]
        created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return created if created.tzinfo else created.replace(tzinfo=UTC)


def _age(path: Path, now: datetime) -> timedelta:
    try:
        return now - datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return timedelta(0)


def sweep_handoff(root: Path, *, older_than_s: float = 3600.0, now: float | None = None) -> list[str]:
    """Remove the GPU auditor's handoff folders an audit left behind (a container that died mid-audit). The cleanup cron
    runs it; it lives here, not in ``safecut.audit``, so the cron's small container never imports the pipeline."""
    if not root.is_dir():
        return []
    cutoff = (time.time() if now is None else now) - older_than_s
    removed: list[str] = []
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(folder.name)
    return removed


def _valid_id(job_id: str) -> bool:
    return re.fullmatch(JOB_ID_PATTERN, job_id) is not None
