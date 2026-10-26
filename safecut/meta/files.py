"""Files API with client-side idempotency and guaranteed cleanup through ``files.json`` (PRE-A §10.4)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any, cast

import httpx

from safecut import config
from safecut.contracts import FILE_ID_PATTERN, FileEntry, FilesIndex, dump, load, now_utc
from safecut.meta.client import CallSpec, MetaClient, Units
from safecut.meta.errors import MetaConfigError, MetaError, MetaFileGone
from safecut.meta.retry import RetryPolicy

INDEX_NAME = "files.json"
_CHUNK = 1 << 20
_FILE_ID = re.compile(FILE_ID_PATTERN)


def sha256_file(path: Path) -> str:
    """Stream the file through SHA-256 (never loads it whole)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _no_cost(_: Any) -> tuple[Units, float]:
    return {}, 0.0


def _spec(stage: str, timeout_s: float) -> CallSpec:
    return CallSpec(
        stage=stage,
        model=None,
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy.for_files(),
        timeout=httpx.Timeout(timeout_s, connect=config.CONNECT_TIMEOUT_S),
        total_timeout_s=timeout_s,
        # Cleanup (list, delete) must work exactly when Meta has been failing: never refused by the breaker.
        breaker=stage != "files",
    )


def upload_timeout(size_bytes: int) -> float:
    return config.FILES_UPLOAD_BASE_S + (size_bytes / 1_000_000) * config.FILES_UPLOAD_PER_MB_S


@dataclass(frozen=True)
class _Upload:
    """What identifies one upload's copies in the team-wide file listing."""

    name: str
    digest: str
    remote_name: str
    size: int
    started: datetime


class FileStore:
    """Uploads for one job. Every upload is recorded in ``files.json`` before it is used.

    Concurrency: uploads of different names run in parallel (a lock per name); every change to
    ``files.json`` re-reads it under one index lock, so concurrent updates never overwrite each other.
    """

    def __init__(self, client: MetaClient, job_dir: str | Path) -> None:
        if client.job_id is None:
            raise ValueError("a FileStore belongs to a job: the client needs a job_id")
        self.client = client
        self.job_id = client.job_id
        self.job_dir = Path(job_dir)
        self._index_lock = asyncio.Lock()
        self._name_locks: dict[str, asyncio.Lock] = {}

    @property
    def index_path(self) -> Path:
        return self.job_dir / INDEX_NAME

    def index(self) -> FilesIndex:
        if not self.index_path.exists():
            return FilesIndex([])
        return load(self.index_path, FilesIndex)

    async def _change(self, fn: Callable[[list[FileEntry]], None]) -> None:
        """Read ``files.json``, apply ``fn`` to its entries and write it back, under the index lock."""
        async with self._index_lock:
            entries = list(self.index().root)
            fn(entries)
            dump(FilesIndex(entries), self.index_path)

    async def _record(self, entry: FileEntry) -> None:
        await self._change(lambda entries: entries.append(entry))

    async def _mark_deleted(self, file_id: str) -> None:
        def mark(entries: list[FileEntry]) -> None:
            for i, entry in enumerate(entries):
                if entry.file_id == file_id and entry.deleted_at is None:
                    entries[i] = entry.model_copy(update={"deleted_at": now_utc()})

        await self._change(mark)

    async def upload(self, path: str | Path, name: str, *, mime: str = "video/mp4") -> str:
        """Upload ``path`` as ``name`` (e.g. ``sam_proxy.mp4``) and return its file ID.

        Idempotent: if ``files.json`` already holds a live upload of the same bytes under ``name``, its
        ID is returned without a request.
        """
        path = Path(path)
        size, digest = await asyncio.to_thread(lambda: (path.stat().st_size, sha256_file(path)))
        async with self._name_locks.setdefault(name, asyncio.Lock()):
            for entry in self.index().root:
                if entry.name == name and entry.sha256 == digest and entry.file_id and entry.deleted_at is None:
                    return entry.file_id
            up = _Upload(name=name, digest=digest, remote_name=f"{self.job_id}-{name}", size=size, started=now_utc())
            return await self._send(path, up, mime)

    async def _send(self, path: Path, up: _Upload, mime: str) -> str:
        handles: list[IO[bytes]] = []

        def body() -> dict[str, Any]:
            handle = path.open("rb")
            handles.append(handle)
            return {"file": (up.remote_name, handle, mime)}

        try:
            result = await self.client.request(
                "POST",
                "files",
                _spec("files", upload_timeout(up.size)),
                meter=_no_cost,
                files=body,
                data={
                    "purpose": "user_data",
                    "expires_after[anchor]": "created_at",
                    "expires_after[seconds]": str(config.FILES_EXPIRES_AFTER_S),
                },
            )
            file_id = _file_id(result.body)
        except MetaError as exc:
            # Only when some attempt may have reached the server (not a breaker or budget refusal).
            if exc.maybe_processed or isinstance(exc, MetaConfigError):
                await self._recover_orphans(up)
            raise
        except BaseException:
            # Cancelled (or worse) mid-upload: we can't list now, so record that a copy may exist.
            # files_deleted then stays false and the sweeper or the 6 h expiry removes it.
            await asyncio.shield(self._record_orphan(up))
            raise
        finally:
            for handle in handles:
                handle.close()
        await self._record(FileEntry(name=up.name, sha256=up.digest, file_id=file_id, created_at=now_utc()))
        if result.maybe_orphaned:
            # An earlier attempt may have reached the server before it failed: clean up its copy.
            with contextlib.suppress(MetaError):
                await self._recover_orphans(up)
        return file_id

    async def _record_orphan(self, up: _Upload) -> None:
        await self._record(FileEntry(name=up.name, sha256=up.digest, file_id=None, created_at=now_utc(), orphan=True))

    async def mark_gone(self, file_id: str) -> None:
        """Meta answered ``file_not_found`` for ``file_id``: record it deleted so the next upload re-sends."""
        await self._mark_deleted(file_id)

    async def reupload(self, path: str | Path, name: str, *, gone: str, mime: str = "video/mp4") -> str:
        """The ``MetaFileGone`` recovery (PRE-A §10.4): forget ``gone`` and upload ``path`` again."""
        await self.mark_gone(gone)
        return await self.upload(path, name, mime=mime)

    async def _recover_orphans(self, up: _Upload) -> None:
        """An upload may have reached the server without being recorded: find and delete what it left.

        Copies already recorded in ``files.json`` are never touched, so a live upload is never deleted.
        """
        try:
            listing = await self.client.request(
                "GET",
                "files",
                _spec("files:cleanup", config.FILES_DELETE_TIMEOUT_S),
                meter=_no_cost,
                params={"purpose": "user_data", "limit": "10000", "order": "desc"},
            )
        except MetaError:
            await self._record_orphan(up)
            return
        known = {e.file_id for e in self.index().root if e.file_id}
        found = [
            f
            for f in _matching_uploads(listing.body, up.remote_name, up.size, up.started.timestamp() - 60)
            if f not in known
        ]
        for file_id in found:
            await self._record(FileEntry(name=up.name, sha256=up.digest, file_id=file_id, created_at=now_utc()))
            await self._delete(file_id)

    async def _delete(self, file_id: str) -> None:
        # A 404 file_not_found means it's already gone, which is what we wanted.
        with contextlib.suppress(MetaFileGone):
            await self.client.request(
                "DELETE", f"files/{file_id}", _spec("files:cleanup", config.FILES_DELETE_TIMEOUT_S), meter=_no_cost
            )
        await self._mark_deleted(file_id)

    async def delete_all(self) -> bool:
        """Delete every live upload of this job. Returns ``FilesIndex.all_deleted`` (the receipt's flag).

        A failed delete leaves its entry undeleted (the hourly sweeper retries it) and is re-raised after
        the others were tried, so one failure never strands the rest.
        """
        first_error: MetaError | None = None
        for entry in [e for e in self.index().root if e.file_id and e.deleted_at is None]:
            try:
                await self._delete(cast(str, entry.file_id))
            except MetaError as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
        return self.index().all_deleted

    def stale(self, *, older_than: timedelta = timedelta(hours=6)) -> list[FileEntry]:
        """Entries the hourly sweeper should delete: live and older than ``older_than``."""
        cutoff = now_utc() - older_than
        return [e for e in self.index().root if e.file_id and e.deleted_at is None and e.created_at < cutoff]


def _file_id(body: Any) -> str:
    if isinstance(body, dict):
        fid = cast(dict[str, Any], body).get("id")
        if isinstance(fid, str) and _FILE_ID.fullmatch(fid):
            return fid
    raise MetaConfigError("upload response has no file id (expected 'file-…' or 'file_…')")


def _matching_uploads(body: Any, remote_name: str, size: int, not_before: float) -> list[str]:
    if not isinstance(body, dict):
        return []
    data = cast(dict[str, Any], body).get("data")
    if not isinstance(data, list):
        return []
    found: list[str] = []
    for item in cast(list[Any], data):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, Any], item)
        created = entry.get("created_at")
        file_id = entry.get("id")
        if (
            entry.get("filename") == remote_name
            and entry.get("bytes") == size
            and isinstance(created, int | float)
            and created >= not_before
            and isinstance(file_id, str)
            and _FILE_ID.fullmatch(file_id)
        ):
            found.append(file_id)
    return found
