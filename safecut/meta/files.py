"""Files API with client-side idempotency and guaranteed cleanup through ``files.json`` (PRE-A §10.4)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any, cast

import httpx

from safecut import config
from safecut.contracts import FileEntry, FilesIndex, dump, load, now_utc
from safecut.meta.client import CallSpec, MetaClient, Units
from safecut.meta.errors import MetaConfigError, MetaError, MetaFileGone, MetaUnavailable
from safecut.meta.retry import RetryPolicy

INDEX_NAME = "files.json"
_CHUNK = 1 << 20


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
    )


def upload_timeout(size_bytes: int) -> float:
    return config.FILES_UPLOAD_BASE_S + (size_bytes / 1_000_000) * config.FILES_UPLOAD_PER_MB_S


class FileStore:
    """Uploads for one job. Every upload is recorded in ``files.json`` before it is used."""

    def __init__(self, client: MetaClient, job_dir: str | Path) -> None:
        if client.job_id is None:
            raise ValueError("a FileStore belongs to a job: the client needs a job_id")
        self.client = client
        self.job_id = client.job_id
        self.job_dir = Path(job_dir)
        self._lock = asyncio.Lock()

    @property
    def index_path(self) -> Path:
        return self.job_dir / INDEX_NAME

    def index(self) -> FilesIndex:
        if not self.index_path.exists():
            return FilesIndex([])
        return load(self.index_path, FilesIndex)

    def _save(self, entries: list[FileEntry]) -> None:
        dump(FilesIndex(entries), self.index_path)

    async def upload(self, path: str | Path, name: str, *, mime: str = "video/mp4") -> str:
        """Upload ``path`` as ``name`` (e.g. ``sam_proxy.mp4``) and return its file ID.

        Idempotent: if ``files.json`` already holds a live upload of the same bytes under ``name``, its
        ID is returned without a request.
        """
        path = Path(path)
        size, digest = await asyncio.to_thread(lambda: (path.stat().st_size, sha256_file(path)))
        async with self._lock:
            entries = list(self.index().root)
            for entry in entries:
                if entry.name == name and entry.sha256 == digest and entry.file_id and entry.deleted_at is None:
                    return entry.file_id
            started = now_utc()
            remote_name = f"{self.job_id}-{name}"
            handles: list[IO[bytes]] = []

            def body() -> dict[str, Any]:
                handle = path.open("rb")
                handles.append(handle)
                return {"file": (remote_name, handle, mime)}

            try:
                result = await self.client.request(
                    "POST",
                    "files",
                    _spec("files", upload_timeout(size)),
                    meter=_no_cost,
                    files=body,
                    data={
                        "purpose": "user_data",
                        "expires_after[anchor]": "created_at",
                        "expires_after[seconds]": str(config.FILES_EXPIRES_AFTER_S),
                    },
                )
            except MetaUnavailable:
                await self._recover_orphans(
                    entries, name=name, digest=digest, remote_name=remote_name, size=size, started=started
                )
                raise
            finally:
                for handle in handles:
                    handle.close()
            file_id = _file_id(result.body)
            entries.append(FileEntry(name=name, sha256=digest, file_id=file_id, created_at=now_utc()))
            self._save(entries)
            return file_id

    async def _recover_orphans(
        self, entries: list[FileEntry], *, name: str, digest: str, remote_name: str, size: int, started: datetime
    ) -> None:
        """An upload failed after it may have reached the server: find and delete what it left behind."""
        try:
            listing = await self.client.request(
                "GET",
                "files",
                _spec("files", config.FILES_DELETE_TIMEOUT_S),
                meter=_no_cost,
                params={"purpose": "user_data", "limit": "10000", "order": "desc"},
            )
            found = _matching_uploads(listing.body, remote_name, size, started.timestamp() - 60)
        except MetaError:
            entries.append(FileEntry(name=name, sha256=digest, file_id=None, created_at=now_utc(), orphan=True))
            self._save(entries)
            return
        for file_id in found:
            entries.append(FileEntry(name=name, sha256=digest, file_id=file_id, created_at=now_utc()))
        self._save(entries)
        for entry in [e for e in entries if e.file_id in found]:
            await self._delete_entry(entries, entry)

    async def _delete_entry(self, entries: list[FileEntry], entry: FileEntry) -> None:
        if entry.file_id is None:
            return
        # A 404 file_not_found means it's already gone, which is what we wanted.
        with contextlib.suppress(MetaFileGone):
            await self.client.request(
                "DELETE", f"files/{entry.file_id}", _spec("files", config.FILES_DELETE_TIMEOUT_S), meter=_no_cost
            )
        index = entries.index(entry)
        entries[index] = entry.model_copy(update={"deleted_at": now_utc()})
        self._save(entries)

    async def delete_all(self) -> bool:
        """Delete every live upload of this job. Returns ``FilesIndex.all_deleted`` (the receipt's flag).

        A failed delete leaves its entry undeleted (the hourly sweeper retries it) and is re-raised after
        the others were tried, so one failure never strands the rest.
        """
        async with self._lock:
            entries = list(self.index().root)
            first_error: MetaError | None = None
            for entry in [e for e in entries if e.file_id and e.deleted_at is None]:
                try:
                    await self._delete_entry(entries, entry)
                except MetaError as exc:
                    first_error = first_error or exc
            if first_error is not None:
                raise first_error
            return FilesIndex(entries).all_deleted

    def stale(self, *, older_than: timedelta = timedelta(hours=6)) -> list[FileEntry]:
        """Entries the hourly sweeper should delete: live and older than ``older_than``."""
        cutoff = now_utc() - older_than
        return [e for e in self.index().root if e.file_id and e.deleted_at is None and e.created_at < cutoff]


def _file_id(body: Any) -> str:
    if isinstance(body, dict):
        fid = cast(dict[str, Any], body).get("id")
        if isinstance(fid, str) and fid.startswith(("file-", "file_")):
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
        if (
            entry.get("filename") == remote_name
            and entry.get("bytes") == size
            and isinstance(created, int | float)
            and created >= not_before
            and isinstance(entry.get("id"), str)
        ):
            found.append(cast(str, entry["id"]))
    return found
