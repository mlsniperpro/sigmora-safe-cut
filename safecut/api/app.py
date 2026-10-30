"""The Safe Cut API (WP5 step 2): upload a clip, follow it, review it, render it, fetch the result, delete it.

Routes and shapes follow UI-SPEC §8 and §10 (``web/src/lib/contracts.ts`` parses every response). Run it with
``uvicorn --factory safecut.api.app:create_app`` (settings from the environment), or build one with
:func:`create_app` in tests.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import subprocess
import sys
import threading
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from imageio_ffmpeg import get_ffmpeg_exe
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from safecut import netguard, pipeline
from safecut.api.access import MAX_UPLOAD_BYTES, Access, ApiRefusal, Grant, RateLimiter, check_caps, estimate_usd
from safecut.api.store import JobNotFound, JobState, JobStore, UploadSpec
from safecut.api.urls import UPLOAD_TTL_S, Signer, expiry
from safecut.api.views import Views, iso
from safecut.api.worker import Worker
from safecut.config import Settings, load_settings
from safecut.contracts import Audit, Decisions, Intake, Job, Plan, dump, load
from safecut.decide import REVIEW, policy_decisions
from safecut.decide.review import ReviewEdit, ReviewError, ReviewLog, apply_review
from safecut.meta.status import StatusUnavailableError, fetch_status
from safecut.stages import INTAKE, RAW_DIR, SOURCE_DIR, stage

log = logging.getLogger("safecut.api")

EDIT = TypeAdapter[ReviewEdit](ReviewEdit)
#: /healthz asks Meta's status endpoint at most this often (PRE-A §10.7: every 5 min before Nov 5, then 1 min).
HEALTH_EVERY_EARLY = timedelta(minutes=5)
HEALTH_EVERY = timedelta(minutes=1)
HEALTH_SWITCH = datetime(2026, 11, 5, tzinfo=UTC)

StatusProbe = Callable[[], Awaitable[str]]


class CodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=64)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=64)
    file_name: str = Field(min_length=1, max_length=255)


def hero_job_id(hero_id: str) -> str:
    """The pinned job behind ``/v1/demo/{hero_id}``: a fixed ID per hero, so restarts reuse it."""
    digest = hashlib.sha256(f"hero:{hero_id}".encode()).digest()
    return "j_" + base64.urlsafe_b64encode(digest).decode()[:22]


def clip_duration(path: Path) -> float | None:
    """The container's duration from ffmpeg's header line (imageio-ffmpeg ships no ffprobe)."""
    proc = subprocess.run(  # noqa: S603 -- fixed argv, our own ffmpeg
        [get_ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30, check=False
    )
    match = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", proc.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def safe_name(name: str, content_type: str) -> str:
    """The upload's own name, reduced to a safe basename with the extension its type implies."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name.replace("\\", "/")).name).strip("._") or "clip"
    ext = ".mov" if content_type == "video/quicktime" else ".mp4"
    stem = re.sub(r"\.(mp4|mov)$", "", stem, flags=re.IGNORECASE)[:100] or "clip"
    return stem + ext


class Service:
    """Everything a request handler needs, built once per app."""

    def __init__(
        self,
        settings: Settings,
        *,
        store: JobStore | None = None,
        worker: Worker | None = None,
        status_probe: StatusProbe | None = None,
        fixtures: Path = pipeline.FIXTURE_JOBS,
    ) -> None:
        self.settings = settings
        self.store = store or JobStore(
            Path(settings.jobs_dir),
            ttl=timedelta(hours=settings.job_ttl_hours),
            cleanup_every=timedelta(minutes=settings.cleanup_interval_min),
        )
        self.worker = worker or Worker(self.store, settings)
        self.access = Access(settings)
        self.limiter = RateLimiter()
        self.ledger = pipeline.job_ledger(settings)
        secret = settings.url_secret.get_secret_value().encode() if settings.url_secret else None
        self.signer = Signer(secret, settings.public_url)
        self.views = Views(settings, self.signer)
        self.status_probe = status_probe or self._meta_status
        self.fixtures = fixtures
        self._health: tuple[datetime, str] | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()
        self.worker.shutdown()

    @property
    def mode(self) -> Literal["live", "replay"]:
        return "replay" if self.settings.replay else "live"

    # -- background jobs -----------------------------------------------------

    def cleanup_loop(self) -> None:
        """The in-process 24 h deletion job (the Modal cron runs the same sweep on the Volume)."""
        while not self._stop.wait(self.settings.cleanup_interval_min * 60):
            try:
                removed = self.store.sweep()
                if removed:
                    log.info("deleted %d expired job(s)", len(removed))
            except Exception:
                log.exception("cleanup sweep failed")

    def build_demo_jobs(self) -> list[str]:
        """Precompute each recorded hero job (``raw/manifest.json`` with ``demo`` or ``pinned``) as a pinned replay
        job, so ``/v1/demo/{hero_id}`` serves it. A hero whose stages can't run yet is logged and skipped."""
        built: list[str] = []
        for manifest in sorted(self.fixtures.glob(f"*/{RAW_DIR}/manifest.json")):
            recording = manifest.parent.parent
            try:
                data = load(manifest, _Manifest)
            except Exception:
                log.warning("unreadable manifest %s", manifest)
                continue
            if not (data.demo or data.pinned) or data.source is None:
                continue
            job_id = hero_job_id(recording.name)
            try:
                if self.store.get(job_id).status == "done":
                    built.append(recording.name)
                    continue
                self.store.delete(job_id)
            except JobNotFound:
                pass
            try:
                self._precompute(job_id, recording, Path(self.fixtures.parent.parent / data.source))
                built.append(recording.name)
            except Exception as exc:
                log.warning("demo job %s not built: %s", recording.name, exc)
                self.store.delete(job_id)
        return built

    def _precompute(self, job_id: str, recording: Path, clip: Path) -> None:
        """Run the hero job with ``safecut run --replay`` in a child process: the child blocks the network for
        its whole life, and a live API's own threads are never blocked by it."""
        self.store.create(mode="replay", job_id=job_id, pinned=True)
        job_dir = self.store.path(job_id)
        proc = subprocess.run(  # noqa: S603 -- fixed argv: this interpreter, our own CLI, our own paths
            [
                sys.executable,
                "-m",
                "safecut.cli",
                "run",
                str(clip),
                "--out",
                str(job_dir),
                "--replay",
                "--replay-from",
                str(recording),
                "--auto-approve-policy",
            ],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if proc.returncode != 0:
            raise pipeline.PipelineError(f"safecut run exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
        with self.store.update(job_id) as state:
            state.status, state.stage = "done", "done"

    # -- health ----------------------------------------------------------------

    async def _meta_status(self) -> str:
        async with httpx.AsyncClient() as http:
            try:
                status = await fetch_status(http, self.settings.meta_base_url)
            except StatusUnavailableError:
                return "unreachable"
        return "ok" if status.healthy else status.service_status

    async def meta_health(self, now: datetime) -> str:
        if self.settings.replay:
            return "replay"
        every = HEALTH_EVERY_EARLY if now < HEALTH_SWITCH else HEALTH_EVERY
        if self._health is None or now - self._health[0] >= every:
            self._health = (now, await self.status_probe())
        return self._health[1]

    # -- request helpers -----------------------------------------------------

    def client_ip(self, request: Request) -> str:
        if self.settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if hops:
                return hops[-1]
        return request.client.host if request.client else "unknown"

    def job(self, job_id: str) -> JobState:
        try:
            return self.store.get(job_id)
        except JobNotFound as exc:
            if exc.expired:
                raise ApiRefusal(404, "expired", "This clip has been deleted.") from None
            raise ApiRefusal(404, "not_found", "We couldn't find that clip.") from None

    def paid_grant(self, state: JobState) -> Grant | None:
        """Re-check the job's bound code before paid work: ``401`` when revoked, ``code_not_active`` outside its
        window. Local jobs with no code (the CLI, the precomputed heroes) have no grant."""
        if state.code_kind is None and state.service is None:
            return None
        grant = self.access.job_grant(code_kind=state.code_kind, cid=state.code_id, service=state.service)
        self.access.require_active(grant)
        return grant


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_sha256: str
    source: str | None = None
    synthetic: bool = False
    demo: bool = False
    pinned: bool = False
    truth: str | None = None


def get_service(request: Request) -> Service:
    service: Service = request.app.state.service
    return service


Svc = Annotated[Service, Depends(get_service)]
router = APIRouter()


def _limit(request: Request, svc: Service, *, paid: bool) -> None:
    client = svc.client_ip(request)
    svc.limiter.hit("api", client, limit=svc.settings.rate_limit_per_min, window_s=60)
    if paid:
        svc.limiter.hit("paid", client, limit=svc.settings.paid_actions_per_hour, window_s=3600)


def _api_limit(request: Request, svc: Svc) -> None:
    _limit(request, svc, paid=False)


def _paid_limit(request: Request, svc: Svc) -> None:
    _limit(request, svc, paid=True)


api_limit = Depends(_api_limit)
paid_limit = Depends(_paid_limit)


def ack(state: JobState, status: int = 202) -> JSONResponse:
    return JSONResponse(
        {"job_id": state.job_id, "status": state.status, "stage": state.stage, "mode": state.mode},
        status_code=status,
    )


# -- codes and jobs --------------------------------------------------------


@router.post("/v1/codes/check", dependencies=[api_limit])
def check_code(svc: Svc, body: CodeBody) -> dict[str, Any]:
    grant = svc.access.check_code(body.code.strip())
    svc.access.require_active(grant)
    s = svc.settings
    return {
        "kind": grant.kind,
        "valid_from": iso(grant.valid_from),
        "valid_until": iso(grant.valid_until),
        "open_weight": s.open_weight_audit == "on" and grant.kind in s.open_weight_code_kinds,
    }


@router.post("/v1/jobs", status_code=201, dependencies=[paid_limit])
def create_job(svc: Svc, body: CreateBody, authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
    grant = svc.access.check_service_key(authorization)
    if grant is None:
        if body.code is None:
            raise ApiRefusal(401, "unauthorized", "An access code or a service key is required.")
        grant = svc.access.check_code(body.code.strip())
    svc.access.require_active(grant)
    if body.size_bytes > MAX_UPLOAD_BYTES:
        raise ApiRefusal(413, "too_large", "The limit is 150 MB.", size_bytes=body.size_bytes)
    if body.content_type not in ("video/mp4", "video/quicktime"):
        raise ApiRefusal(415, "unsupported_media", "Safe Cut takes MP4 or MOV video files.")
    if grant.kind in ("pilot", "recording", "owner"):
        check_caps(svc.settings, svc.ledger, grant, estimate=estimate_usd(None))
    now = datetime.now(UTC)
    upload_expires = now + timedelta(seconds=UPLOAD_TTL_S)
    state = svc.store.create(
        mode=svc.mode,
        now=now,
        code_id=grant.code_id,
        code_kind=grant.kind,
        service=grant.service,
        upload=UploadSpec(
            size_bytes=body.size_bytes,
            content_type=body.content_type,  # type: ignore[arg-type] -- checked above
            file_name=safe_name(body.file_name, body.content_type),
            expires_at=upload_expires,
        ),
    )
    url = svc.signer.sign(
        f"/v1/uploads/{state.job_id}", now=now, ttl_s=UPLOAD_TTL_S, extra=f"{body.size_bytes}:{body.content_type}"
    )
    return JSONResponse(
        {"job_id": state.job_id, "mode": state.mode, "upload_url": url, "upload_expires_at": iso(expiry(url))},
        status_code=201,
    )


@router.put("/v1/uploads/{job_id}")
async def upload(svc: Svc, job_id: str, request: Request, exp: str | None = None, sig: str | None = None) -> Response:
    state = svc.job(job_id)
    spec = state.upload
    if spec is None or not svc.signer.verify(
        f"/v1/uploads/{job_id}", exp, sig, extra=f"{spec.size_bytes}:{spec.content_type}"
    ):
        raise ApiRefusal(403, "bad_signature", "This upload link is invalid or has expired.")
    if spec.received:
        raise ApiRefusal(409, "already_uploaded", "This clip was already uploaded.")
    if request.headers.get("content-type", "").split(";")[0].strip() != spec.content_type:
        raise ApiRefusal(403, "bad_signature", "The upload's Content-Type isn't the one this link was made for.")
    length = request.headers.get("content-length")
    if length is None or not length.isdigit() or int(length) != spec.size_bytes:
        raise ApiRefusal(403, "bad_signature", "The upload's Content-Length isn't the one this link was made for.")
    folder = svc.store.path(job_id) / SOURCE_DIR
    folder.mkdir(exist_ok=True)
    partial = folder / f".{spec.file_name}.part"
    received = 0
    with partial.open("wb") as handle:
        async for chunk in request.stream():
            received += len(chunk)
            if received > spec.size_bytes:
                handle.close()
                partial.unlink(missing_ok=True)
                raise ApiRefusal(413, "too_large", "The upload is larger than declared.", size_bytes=received)
            handle.write(chunk)
    if received != spec.size_bytes:
        partial.unlink(missing_ok=True)
        raise ApiRefusal(400, "upload_incomplete", "The upload ended before the declared size.")
    partial.replace(folder / spec.file_name)
    with svc.store.update(job_id) as current:
        if current.upload is not None:
            current.upload.received = True
    return Response(status_code=200)


@router.post("/v1/jobs/{job_id}/start", status_code=202, dependencies=[paid_limit])
def start(svc: Svc, job_id: str) -> JSONResponse:
    state = svc.job(job_id)
    grant = svc.paid_grant(state)
    if svc.worker.busy(job_id) or state.status in ("processing", "rendering", "retry_later"):
        raise ApiRefusal(409, "already_running", "This clip is already being processed.")
    if state.status not in ("created", "failed"):
        raise ApiRefusal(409, "already_started", "This clip has already been processed.")
    job_dir = svc.store.path(job_id)
    spec = state.upload
    clip = job_dir / SOURCE_DIR / spec.file_name if spec else None
    if (
        spec is None
        or clip is None
        or not spec.received
        or not clip.is_file()
        or clip.stat().st_size != spec.size_bytes
    ):
        raise ApiRefusal(409, "upload_incomplete", "The upload didn't finish, so nothing was processed.")
    duration = state.duration_s or clip_duration(clip)
    if state.mode == "live":
        if svc.settings.model_api_key is None:
            raise ApiRefusal(503, "config", "Safe Cut isn't configured to process clips right now.")
        if grant is not None:
            check_caps(svc.settings, svc.ledger, grant, estimate=estimate_usd(duration))
    if not (job_dir / INTAKE).is_file():
        dump(
            Intake(
                source=spec.file_name,
                created_at=state.created_at,
                consented=state.code_kind in ("owner", "recording"),
                mode=state.mode,
                code_kind=state.code_kind,
                code_id=state.code_id,
            ),
            job_dir / INTAKE,
        )
    if state.mode == "replay" and not (job_dir / RAW_DIR).is_dir():
        recording = pipeline.find_recording(pipeline.sha256_file(clip), svc.fixtures)
        if recording is None:
            raise ApiRefusal(422, "no_recording", "Demo mode can only replay the recorded demo clips.")
        pipeline.attach_recording(job_dir, recording)
    with svc.store.update(job_id) as current:
        current.status, current.stage, current.failure = "processing", "queued", None
        current.duration_s = duration
        current.requeues = 0
        updated = current.model_copy()
    svc.worker.submit(job_id, "analyse")
    return ack(updated)


@router.get("/v1/jobs/{job_id}", dependencies=[api_limit])
def get_job(svc: Svc, job_id: str) -> dict[str, Any]:
    state = svc.job(job_id)
    return svc.views.job(state, svc.store.path(job_id))


@router.post("/v1/jobs/{job_id}/review", dependencies=[api_limit])
async def review(svc: Svc, job_id: str, request: Request) -> dict[str, Any]:
    try:
        edit = EDIT.validate_json(await request.body())
    except ValidationError as exc:
        raise ApiRefusal(422, "bad_request", f"not a review edit: {exc.error_count()} error(s)") from None
    return _review(svc, job_id, edit)


def _review(svc: Service, job_id: str, edit: ReviewEdit) -> dict[str, Any]:
    state = svc.job(job_id)
    if state.status == "needs_you":
        raise ApiRefusal(409, "read_only", "This clip can't be edited until the audit runs again.")
    if state.status not in ("review", "done") or svc.worker.busy(job_id):
        raise ApiRefusal(409, "not_reviewable", "This clip isn't ready for review.")
    job_dir = svc.store.path(job_id)
    with svc.store.update(job_id) as current:
        log_path = job_dir / REVIEW
        edits = list(load(log_path, ReviewLog).root) if log_path.is_file() else []
        if all(e.edit_id != edit.edit_id for e in edits):
            job = load(job_dir / "job.json", Job)
            plan = load(job_dir / "plan.json", Plan)
            audit = load(job_dir / "audit.json", Audit) if (job_dir / "audit.json").is_file() else None
            try:
                result = apply_review(
                    policy_decisions(job_dir),
                    [*edits, edit],
                    audit=audit,
                    frames=job.frames,
                    extend=plan.temporal.extend,
                )
            except ReviewError as exc:
                raise ApiRefusal(409, exc.code, str(exc)) from None
            dump(ReviewLog([*edits, edit]), log_path)
            dump(result.decisions, job_dir / "decisions.json")
            if result.audit is not None:
                dump(result.audit, job_dir / "audit.json")
            pipeline.run_stage(
                job_dir, stage("guard"), replay=current.mode == "replay", settings=svc.settings, force=True
            )
            if current.status == "done":
                current.status, current.stage = "review", "review"
        status = current.status
    decisions = load(job_dir / "decisions.json", Decisions)
    plan_now = load(job_dir / "plan.json", Plan)
    audit_now = load(job_dir / "audit.json", Audit) if (job_dir / "audit.json").is_file() else None
    return {
        "edit_id": edit.edit_id,
        "mode": state.mode,
        "status": status,
        "has_render": (job_dir / "redacted.mp4").is_file(),
        "items": [i.model_dump(mode="json") | {"removed_by_creator": i.removed_by_creator} for i in decisions.items],
        "plan": plan_now.model_dump(mode="json"),
        "audit": {"spots": [s.model_dump(mode="json") for s in audit_now.spots]} if audit_now else None,
    }


@router.post("/v1/jobs/{job_id}/render", status_code=202, dependencies=[paid_limit])
def render(svc: Svc, job_id: str) -> JSONResponse:
    state = svc.job(job_id)
    grant = svc.paid_grant(state)
    if svc.worker.busy(job_id) or state.status in ("rendering", "processing", "retry_later"):
        raise ApiRefusal(409, "already_running", "A render is already running.")
    retry = (
        state.status == "failed" and state.failure is not None and state.failure.stage in ("render", "audit", "receipt")
    )
    if state.status != "review" and not retry:
        raise ApiRefusal(409, "not_reviewable", "This clip isn't waiting for a render.")
    if state.mode == "live" and grant is not None:
        check_caps(svc.settings, svc.ledger, grant, estimate=0.01)
    job_dir = svc.store.path(job_id)
    pipeline.approve(job_dir, how="review")
    with svc.store.update(job_id) as current:
        current.status, current.stage, current.failure = "rendering", "render", None
        updated = current.model_copy()
    svc.worker.submit(job_id, "publish")
    return ack(updated)


@router.post("/v1/jobs/{job_id}/audit", status_code=202, dependencies=[paid_limit])
def audit(svc: Svc, job_id: str) -> JSONResponse:
    state = svc.job(job_id)
    grant = svc.paid_grant(state)
    if svc.worker.busy(job_id) or state.status == "rendering":
        raise ApiRefusal(409, "already_running", "The audit is already running.")
    if state.status != "needs_you":
        raise ApiRefusal(409, "not_needed", "This clip's audit doesn't need to run again.")
    if state.mode == "live" and grant is not None:
        check_caps(svc.settings, svc.ledger, grant, estimate=0.01)
    with svc.store.update(job_id) as current:
        current.status, current.stage, current.failure = "rendering", "audit", None
        updated = current.model_copy()
    svc.worker.submit(job_id, "audit")
    return ack(updated)


@router.get("/v1/jobs/{job_id}/result", dependencies=[api_limit])
def result(svc: Svc, job_id: str) -> dict[str, Any]:
    state = svc.job(job_id)
    job_dir = svc.store.path(job_id)
    if not (job_dir / "receipt.json").is_file() or not (job_dir / "redacted.mp4").is_file():
        raise ApiRefusal(409, "not_ready", "The result isn't ready yet.")
    return svc.views.result(state, job_dir)


@router.delete("/v1/jobs/{job_id}", status_code=204, dependencies=[api_limit])
def delete(svc: Svc, job_id: str) -> Response:
    svc.worker.cancel(job_id)
    if not svc.store.delete(job_id):
        raise ApiRefusal(404, "not_found", "We couldn't find that clip.")
    return Response(status_code=204)


@router.get("/v1/demo/{hero_id}", dependencies=[api_limit])
def demo(svc: Svc, hero_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", hero_id):
        raise ApiRefusal(404, "not_found", "No such demo.")
    try:
        state = svc.store.get(hero_job_id(hero_id))
    except JobNotFound:
        raise ApiRefusal(404, "not_found", "No such demo.") from None
    if not state.pinned or state.status != "done":
        raise ApiRefusal(404, "not_found", "No such demo.")
    return svc.views.demo(state, svc.store.path(state.job_id))


@router.get("/v1/jobs/{job_id}/media/{name:path}")
def media(svc: Svc, job_id: str, name: str, exp: str | None = None, sig: str | None = None) -> Response:
    if not svc.signer.verify(f"/v1/jobs/{job_id}/media/{name}", exp, sig):
        raise ApiRefusal(403, "bad_signature", "This link is invalid or has expired.")
    svc.job(job_id)
    job_dir = svc.store.path(job_id)
    if not svc.views.media_allowed(job_dir, name):
        raise ApiRefusal(404, "not_found", "No such file.")
    headers = {"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"}
    if name == "captions.vtt":
        if not svc.views.has_captions(job_dir):
            raise ApiRefusal(404, "not_found", "No captions for this clip.")
        return PlainTextResponse(svc.views.captions(job_dir), media_type="text/vtt", headers=headers)
    path = job_dir / name
    if not path.is_file():
        raise ApiRefusal(404, "not_found", "No such file.")
    if name.endswith(".html"):
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
    return FileResponse(path, headers=headers)


@router.get("/healthz")
async def healthz(svc: Svc) -> JSONResponse:
    now = datetime.now(UTC)
    meta = await svc.meta_health(now)
    writable = svc.store.root.is_dir()
    body = {
        "status": "ok" if writable else "degraded",
        "mode": svc.mode,
        "time": iso(now),
        "meta": meta,
        "jobs_dir": "ok" if writable else "missing",
        "key": svc.settings.model_api_key is not None,
    }
    return JSONResponse(body, status_code=200 if writable else 503)


def create_app(settings: Settings | None = None, *, service: Service | None = None, background: bool = True) -> FastAPI:
    """``background`` starts the deletion loop and builds the demo jobs at startup (off in unit tests)."""
    svc = service or Service(settings or load_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        threads: list[threading.Thread] = []
        blocking = svc.settings.replay and not netguard.active()
        if blocking:
            netguard.block()  # a replay deployment never reaches the network, in any thread
        if background:
            threads.append(threading.Thread(target=svc.cleanup_loop, name="cleanup", daemon=True))
            threads.append(threading.Thread(target=svc.build_demo_jobs, name="demo", daemon=True))
            for thread in threads:
                thread.start()
        try:
            yield
        finally:
            svc.stop()
            if blocking:
                netguard.unblock()

    app = FastAPI(title="Sigmora Safe Cut API", version="0.1.0", lifespan=lifespan, docs_url="/docs", redoc_url=None)
    app.state.service = svc
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(svc.settings.cors_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
        expose_headers=["Retry-After"],
        allow_credentials=False,
        max_age=600,
    )

    @app.exception_handler(ApiRefusal)
    async def refusal(_: Request, exc: ApiRefusal) -> JSONResponse:
        headers = {"Retry-After": str(int(exc.retry_after_s))} if exc.retry_after_s is not None else None
        return JSONResponse(exc.body(), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        where = "; ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors()[:3])
        return JSONResponse({"error": {"code": "bad_request", "message": f"invalid request: {where}"}}, status_code=422)

    app.include_router(router)
    return app


__all__ = ["Service", "create_app", "hero_job_id"]
