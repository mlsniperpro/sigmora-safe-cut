"""Files API with client-side idempotency and guaranteed cleanup through ``files.json`` (PRE-A §10.4)."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import re
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any, cast

import httpx

from safecut import config
from safecut.contracts import FILE_ID_PATTERN, FileEntry, FilesIndex, dump, load, now_utc
from safecut.meta.client import CallSpec, MetaClient, Units, outlive_cancel
from safecut.meta.errors import BreakerOpen, MetaBadRequest, MetaConfigError, MetaError, MetaFileGone
from safecut.meta.retry import RetryPolicy

INDEX_NAME = "files.json"
_CHUNK = 1 << 20
_FILE_ID = re.compile(FILE_ID_PATTERN)
#: What one step of a delete sweep may fail with (a Meta error, a disk fault writing files.json, an unreadable
#: files.json) without stopping the rest of the sweep; the first one is re-raised after it.
_SWEEP_ERRORS = (MetaError, OSError, ValueError)


def sha256_file(path: Path) -> str:
    """Stream the file through SHA-256 (never loads it whole)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _no_cost(_: Any) -> tuple[Units, float]:
    return {}, 0.0


def _spec(stage: str, timeout_s: float, units: Units | None = None) -> CallSpec:
    return CallSpec(
        stage=stage,
        model=None,
        estimate_usd=0.0,
        estimate_units=units or {},
        policy=RetryPolicy.for_files(),
        timeout=httpx.Timeout(timeout_s, connect=config.CONNECT_TIMEOUT_S),
        total_timeout_s=timeout_s,
        # Cleanup (list, delete) must work exactly when Meta has been failing: never refused by the breaker.
        breaker=stage != "files:cleanup",
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
        units: Units = {"bytes": float(up.size)}  # PRE-A §10.5: a Files line records its bytes, at $0

        def body() -> dict[str, Any]:
            handle = path.open("rb")
            handles.append(handle)
            return {"file": (up.remote_name, handle, mime)}

        try:
            result = await self.client.request(
                "POST",
                "files",
                _spec("files", upload_timeout(up.size), units),
                meter=lambda _: (units, 0.0),
                files=body,
                data={
                    "purpose": "user_data",
                    "expires_after[anchor]": "created_at",
                    "expires_after[seconds]": str(config.FILES_EXPIRES_AFTER_S),
                },
            )
            file_id = _file_id(result.body)
        except BreakerOpen:
            raise  # refused before anything was sent
        except MetaError:
            # Any other failure may have left a copy, even a fast 5xx (the server stored the file, then failed)
            # or a timeout whose copy lands after our listing: recover what's there now, and leave an orphan so
            # delete_all lists again at the segment's end.
            await self._recover_or_record(up)
            raise
        except BaseException:
            # Cancelled (or worse) mid-upload: we can't list now, so record that a copy may exist.
            # files_deleted then stays false and the sweeper or the 6 h expiry removes it.
            await asyncio.shield(self._record_orphan(up))
            raise
        finally:
            for handle in handles:
                handle.close()
        earlier_failed = result.attempts > 1 or result.maybe_orphaned
        try:
            await _finish(self._keep(file_id, up))
        except BaseException:
            # The record failed or was cancelled: an earlier attempt's copy is still unaccounted for.
            if earlier_failed:
                await asyncio.shield(self._record_orphan(up))
            raise
        if earlier_failed:
            # An earlier attempt may have left a copy before it failed: clean it up (and re-list at the end).
            await self._recover_or_record(up)
        return file_id

    async def _keep(self, file_id: str, up: _Upload) -> None:
        """Record a successful upload. If recording fails, this frame is the only one that knows the copy: delete
        it by ID, or failing that record an orphan, so ``files_deleted`` can never be claimed over it."""
        try:
            await self._record(FileEntry(name=up.name, sha256=up.digest, file_id=file_id, created_at=now_utc()))
        except Exception:
            try:
                await self.client.request(
                    "DELETE", f"files/{file_id}", _spec("files:cleanup", config.FILES_DELETE_TIMEOUT_S), meter=_no_cost
                )
            except MetaFileGone:
                pass
            except Exception:
                with contextlib.suppress(Exception):
                    await self._record_orphan(up)
            raise

    async def _recover_or_record(self, up: _Upload) -> None:
        """Recover the copies a failed attempt left, then always record an orphan: a copy that lands after this
        listing is still found when ``delete_all`` reconciles orphans at the segment's end (files_deleted
        stays false until then)."""
        try:
            await self._recover_orphans(up)
        except MetaError:
            pass  # any copy found is already in files.json (undeleted), so the sweeper retries it
        finally:
            await asyncio.shield(self._record_orphan(up))

    async def _record_orphan(self, up: _Upload) -> None:
        await self._record(FileEntry(name=up.name, sha256=up.digest, file_id=None, created_at=now_utc(), orphan=True))

    async def mark_gone(self, file_id: str) -> None:
        """Meta answered ``file_not_found`` for ``file_id``: record it deleted so the next upload re-sends."""
        await self._mark_deleted(file_id)

    async def reupload(self, path: str | Path, name: str, *, gone: str, mime: str = "video/mp4") -> str:
        """The ``MetaFileGone`` recovery (PRE-A §10.4): forget ``gone`` and upload ``path`` again."""
        await self.mark_gone(gone)
        return await self.upload(path, name, mime=mime)

    async def call_with_reupload[T](
        self,
        path: str | Path,
        name: str,
        file_id: str,
        call: Callable[[str], Awaitable[T]],
        *,
        mime: str = "video/mp4",
    ) -> T:
        """PRE-A §10.3 / vector R10: ``call(file_id)``; on ``file_not_found`` re-upload ``path`` once and repeat
        the call with the new id. A second ``file_not_found`` is a ``MetaBadRequest`` (the stage fails closed)."""
        try:
            return await call(file_id)
        except MetaFileGone:
            new_id = await self.reupload(path, name, gone=file_id, mime=mime)
        try:
            return await call(new_id)
        except MetaFileGone as exc:
            raise MetaBadRequest(
                f"{name}: file_not_found again after one re-upload", status=exc.status, request_id=exc.request_id
            ) from exc

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
            return  # the caller records the orphan either way
        known = {e.file_id for e in self.index().root if e.file_id}
        found = [
            f
            for f in _matching_uploads(listing.body, up.remote_name, up.size, up.started.timestamp() - 60)
            if f not in known
        ]
        # Record every copy before deleting any: a delete that fails mid-loop must not leave a later copy
        # unrecorded (files_deleted would then be claimed over it). Then try every delete.
        copies = [FileEntry(name=up.name, sha256=up.digest, file_id=f, created_at=now_utc()) for f in found]
        if copies:
            await self._change(lambda entries: entries.extend(copies))
        await self._delete_each(found)

    async def _delete_each(self, file_ids: list[str]) -> None:
        """Delete every ID, carrying on past failures; the first failure is re-raised after the rest."""
        first_error: Exception | None = None
        for file_id in file_ids:
            try:
                await self._delete(file_id)
            except _SWEEP_ERRORS as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    async def _delete(self, file_id: str) -> None:
        # A 404 file_not_found means it's already gone, which is what we wanted.
        with contextlib.suppress(MetaFileGone):
            await self.client.request(
                "DELETE", f"files/{file_id}", _spec("files:cleanup", config.FILES_DELETE_TIMEOUT_S), meter=_no_cost
            )
        await self._mark_deleted(file_id)

    async def reconcile_orphans(self) -> None:
        """Resolve orphan entries: list ``/files``, delete every unrecorded copy of each orphan's name, then
        mark the orphan resolved (``deleted_at`` set), so a cancelled upload doesn't block ``files_deleted``.

        Each name is reconciled under its upload lock, so an upload in flight is never mistaken for an orphan.
        A failed listing or delete leaves that name's orphan open (the sweeper or the 6 h expiry covers it); the
        other names are still reconciled, and the first failure is raised after them.
        """
        first_error: Exception | None = None
        for name in sorted({e.name for e in self.index().root if e.orphan and e.deleted_at is None}):
            try:
                await self._reconcile_name(name)
            except _SWEEP_ERRORS as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    async def _reconcile_name(self, name: str) -> None:
        async with self._name_locks.setdefault(name, asyncio.Lock()):
            orphans = [e for e in self.index().root if e.name == name and e.orphan and e.deleted_at is None]
            if not orphans:
                return
            listing = await self.client.request(
                "GET",
                "files",
                _spec("files:cleanup", config.FILES_DELETE_TIMEOUT_S),
                meter=_no_cost,
                params={"purpose": "user_data", "limit": "10000", "order": "desc"},
            )
            not_before = min(e.created_at for e in orphans).timestamp() - config.FILES_EXPIRES_AFTER_S
            known = {e.file_id for e in self.index().root if e.file_id}
            remote = f"{self.job_id}-{name}"
            found = [f for f in _matching_uploads(listing.body, remote, None, not_before) if f not in known]
            sha = orphans[0].sha256
            copies = [FileEntry(name=name, sha256=sha, file_id=f, created_at=now_utc()) for f in found]
            if copies:
                await self._change(lambda entries: entries.extend(copies))
            await self._delete_each(found)  # a failure raises here: the orphan stays open for the sweeper
            await self._change(functools.partial(_resolve_orphans, name))

    async def delete_all(self) -> bool:
        """Delete every live upload of this job and resolve its orphans. Returns ``FilesIndex.all_deleted``
        (the receipt's flag). Call it once the job's uploads have finished.

        A failed delete leaves its entry undeleted (the hourly sweeper retries it) and is re-raised after
        the others were tried, so one failure never strands the rest.
        """
        first_error: Exception | None = None
        try:
            await self.reconcile_orphans()
        except _SWEEP_ERRORS as exc:
            first_error = exc
        for entry in [e for e in self.index().root if e.file_id and e.deleted_at is None]:
            try:
                await self._delete(cast(str, entry.file_id))
            except _SWEEP_ERRORS as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
        return self.index().all_deleted

    def stale(self, *, older_than: timedelta = timedelta(hours=6)) -> list[FileEntry]:
        """Entries the hourly sweeper should delete: live and older than ``older_than``."""
        cutoff = now_utc() - older_than
        return [e for e in self.index().root if e.file_id and e.deleted_at is None and e.created_at < cutoff]


def _resolve_orphans(name: str, entries: list[FileEntry]) -> None:
    for i, entry in enumerate(entries):
        if entry.name == name and entry.orphan and entry.deleted_at is None:
            entries[i] = entry.model_copy(update={"deleted_at": now_utc()})


async def _finish(coro: Coroutine[Any, Any, None]) -> None:
    """Run ``coro`` to its end even if the caller is cancelled meanwhile; the cancellation is re-raised after."""
    task = asyncio.ensure_future(coro)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await outlive_cancel(task)
        raise


def _file_id(body: Any) -> str:
    if isinstance(body, dict):
        fid = cast(dict[str, Any], body).get("id")
        if isinstance(fid, str) and _FILE_ID.fullmatch(fid):
            return fid
    raise MetaConfigError("upload response has no file id (expected 'file-…' or 'file_…')")


def _matching_uploads(body: Any, remote_name: str, size: int | None, not_before: float) -> list[str]:
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
            and (size is None or entry.get("bytes") == size)
            and isinstance(created, int | float)
            and created >= not_before
            and isinstance(file_id, str)
            and _FILE_ID.fullmatch(file_id)
        ):
            found.append(file_id)
    return found
