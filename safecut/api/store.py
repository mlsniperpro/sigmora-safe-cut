"""Where the API keeps jobs: one directory per job under ``SAFECUT_JOBS_DIR``, plus ``state.json`` for what the
pipeline files can't say (who started it, its status and stage, the upload it expects, when it is deleted).

Job IDs are 128-bit random tokens: the job link is the capability that authorises reading, editing and deleting
a job (UI-SPEC §8 request 17), so it must be unguessable.
"""

from __future__ import annotations

import re
import secrets
import shutil
import threading
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
    started_at: datetime | None = None
    #: How many times a ``retry_later`` job was re-queued (once at most, UI-SPEC §8 request 1).
    requeues: int = 0
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
            raise JobNotFound(job_id)
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

    def delete(self, job_id: str) -> bool:
        """Remove the whole job directory (every upload, response, render and receipt). True if it existed."""
        if not _valid_id(job_id):
            return False
        with self._lock(job_id):
            target = self.path(job_id)
            if not target.exists():
                return False
            shutil.rmtree(target)
            return True

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and _valid_id(p.name))

    def sweep(self, *, now: datetime | None = None) -> list[str]:
        """The 24 h deletion job: remove every unpinned job created more than the TTL ago (and any directory
        whose state can't be read, which can't be trusted to expire on its own). Returns the removed IDs."""
        now = now or datetime.now(UTC)
        removed: list[str] = []
        for job_id in self.ids():
            try:
                state = load(self.path(job_id) / STATE, JobState)
            except ContractError:
                expired = True
            else:
                expired = not state.pinned and now >= state.created_at + self.ttl
            if expired and self.delete(job_id):
                removed.append(job_id)
        return removed


def _valid_id(job_id: str) -> bool:
    return re.fullmatch(JOB_ID_PATTERN, job_id) is not None
