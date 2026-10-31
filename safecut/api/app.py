"""The Safe Cut API (WP5 step 2): upload a clip, follow it, review it, render it, fetch the result, delete it.

Routes and shapes follow UI-SPEC §8 and §10 (``web/src/lib/contracts.ts`` parses every response). Run it with
``uvicorn --factory safecut.api.app:create_app`` (settings from the environment), or build one with
:func:`create_app` in tests.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib
import ipaddress
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Body, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from imageio_ffmpeg import get_ffmpeg_exe
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from safecut import netguard, pipeline, receipt
from safecut.api.access import (
    MAX_DURATION_S,
    MAX_UPLOAD_BYTES,
    Access,
    ApiRefusal,
    Grant,
    RateLimiter,
    StoredRateLimiter,
    check_caps,
    estimate_usd,
)
from safecut.api.store import ACTIVE, BUILDING, Failure, JobNotFound, JobState, JobStore, UploadSpec
from safecut.api.urls import UPLOAD_TTL_S, Signer, expiry
from safecut.api.views import Views, iso
from safecut.api.worker import Worker
from safecut.audit.gpu import child_env
from safecut.config import Settings, load_settings
from safecut.contracts import Audit, ContractError, Decisions, Intake, Job, Plan, Tracks, dump, load
from safecut.decide import REVIEW, policy_decisions
from safecut.decide.review import ReviewEdit, ReviewError, ReviewLog, apply_review
from safecut.meta.status import StatusUnavailableError, fetch_status
from safecut.stages import INTAKE, RAW_DIR, SOURCE_DIR, stage
from safecut.track.media import SAFE_INPUT

log = logging.getLogger("safecut.api")

#: /healthz asks Meta's status endpoint at most this often (PRE-A §10.7: every 5 min before Nov 5, then 1 min).
HEALTH_EVERY_EARLY = timedelta(minutes=5)
HEALTH_EVERY = timedelta(minutes=1)
HEALTH_SWITCH = datetime(2026, 11, 5, tzinfo=UTC)
#: One action runs a few minutes (a 60 s clip, live); one past this is stuck, not slow, and fails.
STALL_LIMIT = timedelta(minutes=45)
#: How often a demo job the GPU couldn't audit is built again (each rebuild takes the demo away for a minute).
DEMO_GPU_RETRY = timedelta(hours=6)
#: ``hold``'s name for the demo build: the container stays up while it runs (it isn't a job action).
DEMO_HOLD = "demo-build"
#: Restarts a job may need (a redeploy, a preemption): one more and it is the job taking its container down.
MAX_RESUMES = 3
#: How long one ``hold`` input waits: under the API function's 60-minute timeout (deploy/modal_app.py).
HOLD_LIMIT_S = 55 * 60.0
#: The paid-action rate limit's SQLite file, beside the spend ledger on the jobs Volume.
RATE_DB = "ratelimit.sqlite"

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
        [get_ffmpeg_exe(), "-hide_banner", *SAFE_INPUT, "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    match = re.search(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", proc.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def auditor_available(settings: Settings) -> bool:
    """PRE-A §12: a live job never starts without its audit. The audit stage may say its detector can't load
    (``safecut.audit.auditor_available``); a build without the audit stage can't audit at all."""
    try:
        module = importlib.import_module("safecut.audit")
    except ModuleNotFoundError as exc:
        if exc.name in ("safecut.audit", "safecut"):
            return False
        raise
    check = getattr(module, "auditor_available", None)
    return bool(check(settings)) if callable(check) else True


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
        keepalive: Callable[[str], None] | None = None,
        wait_on_stop: bool = True,
    ) -> None:
        self.settings = settings
        #: Whether shutting down waits for running jobs. Modal's container sets False: its ASGI lifespan ends (and
        #: stops this service) before ``@modal.exit``, and a container being replaced must go at once.
        self.wait_on_stop = wait_on_stop
        self.store = store or JobStore(
            Path(settings.jobs_dir),
            ttl=timedelta(hours=settings.job_ttl_hours),
            cleanup_every=timedelta(minutes=settings.cleanup_interval_min),
        )
        self.worker = worker or Worker(self.store, settings, keepalive=keepalive)
        #: Jobs whose upload is streaming right now (one PUT per job at a time).
        self.uploading: set[str] = set()
        self.uploads_lock = threading.Lock()
        self.access = Access(settings)
        #: Per-minute limits live in memory (a container only restarts after a quiet spell longer than their
        #: window); the per-hour paid-action limit is on the jobs Volume, so a scale-to-zero restart can't reset it.
        self.limiter = RateLimiter()
        self.paid_limiter = StoredRateLimiter(Path(settings.jobs_dir) / RATE_DB)
        self.ledger = pipeline.job_ledger(settings)
        secret = settings.url_secret.get_secret_value().encode() if settings.url_secret else None
        self.signer = Signer(secret, settings.public_url)
        self.views = Views(settings, self.signer)
        self.status_probe = status_probe or self._meta_status
        self.fixtures = fixtures
        self._health: tuple[datetime, str] | None = None
        self._stop = threading.Event()
        self._started = False
        self._start_lock = threading.Lock()
        self.started_monotonic = time.monotonic()
        self._demo_built = threading.Event()
        #: Heroes whose served demo was built from this process's code and recordings (``/healthz``, deploy checks).
        self.demos_current: set[str] = set()

    def start(self) -> bool:
        """Once per process, whichever comes first (the ASGI lifespan, or Modal's container start): resume the
        jobs a previous container left mid-action, and start the deletion loop and the demo-job build. Returns
        whether this call did it."""
        with self._start_lock:
            if self._started:
                return False
            self._started = True
        self.recover()
        threading.Thread(target=self.cleanup_loop, name="cleanup", daemon=True).start()
        threading.Thread(target=self._build_demos, name="demo", daemon=True).start()
        self.worker.keep_up(DEMO_HOLD)  # building the demo isn't a job action: hold the container up for it too
        return True

    @property
    def demo_built(self) -> bool:
        return self._demo_built.is_set()

    def _build_demos(self) -> None:
        try:
            self.build_demo_jobs()
        finally:
            self._demo_built.set()

    def stop(self, *, wait: bool = True) -> None:
        """Stop the loops and the workers. ``wait=False`` (a container being replaced) doesn't wait for running jobs:
        the next container resumes them from their last finished stage, and a quick exit keeps the two apart."""
        self._stop.set()
        self.worker.shutdown(wait=wait)
        self.paid_limiter.close()
        self.ledger.close()

    def hold(self, job_id: str, *, poll_s: float = 2.0, limit_s: float = HOLD_LIMIT_S) -> str:
        """Block while this process is working on the job, then return its status (``gone`` once deleted).

        On Modal this runs as an input of the API container itself (``SafeCutApi.hold``): a container with an
        input in flight isn't scaled down, and a worker thread alone isn't an input. A job active on disk that
        nothing here is moving (stranded by a container that went away) is resumed; one active past
        :data:`STALL_LIMIT` is failed, so no job, and no container, waits forever."""
        deadline = time.monotonic() + limit_s
        if job_id == DEMO_HOLD:
            self._demo_built.wait(limit_s)
            return "built" if self._demo_built.is_set() else "building"
        idle_polls = 0
        while True:
            try:
                state = self.store.get(job_id)
            except JobNotFound:
                return "gone"
            if state.status not in ACTIVE:
                return state.status
            idle_polls = 0 if self.worker.tracking(job_id) else idle_polls + 1
            if idle_polls >= 2:  # two polls apart, so an action between its timer and its thread isn't caught
                self.recover(only=job_id)
                idle_polls = 0
            if self._stop.wait(poll_s) or time.monotonic() > deadline:
                return state.status

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

    def recover(self, *, only: str | None = None) -> list[str]:
        """After a restart (a redeploy, a crash, a scale-to-zero sleep) no thread is working on any job: re-queue
        every job that was mid-action, from where its files say it stopped (stages are idempotent and resume from
        ``job_log.jsonl``, so a stage that finished is never paid for twice), so a poller never waits forever on a
        status nothing will change. A job this process is still moving is left alone, and one active past
        :data:`STALL_LIMIT` fails as ``internal`` instead. Returns the re-queued IDs."""
        resumed: list[str] = []
        now = datetime.now(UTC)
        for job_id in [only] if only is not None else self.store.ids():
            try:
                with self.store.update(job_id) as state:
                    if state.pinned or state.status not in ACTIVE or self.worker.tracking(job_id):
                        continue
                    stalled = state.started_at is not None and now - state.started_at > STALL_LIMIT
                    if stalled or state.resumes >= MAX_RESUMES:
                        state.status, state.retry_at = "failed", None
                        detail = (
                            f"stalled: still at {state.stage} {STALL_LIMIT} after it started"
                            if stalled
                            else f"stopped {state.resumes + 1} times at {state.stage} (its container went away)"
                        )
                        state.failure = Failure(stage=state.stage, reason="internal", detail=detail)
                        log.warning("job %s failed at %s: %s", job_id, state.stage, detail)
                        continue
                    state.resumes += 1
                    analysing = state.status == "processing" or (
                        state.status == "retry_later" and state.stage not in ("render", "audit", "receipt")
                    )
                    action: Literal["analyse", "publish", "audit"] = (
                        "analyse"
                        if analysing
                        else "audit"
                        if state.stage == "audit" and (self.store.path(job_id) / "redacted.mp4").is_file()
                        else "publish"
                    )
                    try:
                        self.paid_grant(state)  # a code revoked or expired over the restart stops paid work here
                    except ApiRefusal:
                        state.status = "failed"
                        state.failure = Failure(stage=state.stage, reason="code_not_active")
                        state.retry_at = None
                        continue
                    wait = (state.retry_at - datetime.now(UTC)).total_seconds() if state.retry_at else 0.0
                    if state.status == "retry_later" and wait > 0:
                        # The one re-queue keeps its delay (and re-checks the code when it fires).
                        self.worker.submit_later(job_id, action, wait)
                    else:
                        state.status = "processing" if analysing else "rendering"
                        state.started_at = now  # re-queued: its stall clock starts again
                        state.retry_at = None
                        self.worker.submit(job_id, action)
                    resumed.append(job_id)
            except (JobNotFound, ContractError):
                continue
        if resumed:
            log.info("re-queued %d job(s) interrupted by a restart", len(resumed))
        return resumed

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
            clip = Path(self.fixtures.parent.parent / data.source)
            stamp = demo_stamp(recording, clip, audit_gpu=self.settings.audit_gpu)
            try:
                existing = self.store.get(job_id)
                if existing.status == "done" and existing.demo_stamp == stamp and not self._retry_gpu(job_id, existing):
                    built.append(recording.name)
                    self.demos_current.add(recording.name)
                    continue
            except JobNotFound:
                pass
            # A re-recorded hero, a new clip, new code, or a demo the GPU couldn't audit: built again, beside the one
            # being served, which keeps serving until the new one is done (and stays if the build fails).
            try:
                self._precompute(job_id, recording, clip, stamp)
                built.append(recording.name)
                self.demos_current.add(recording.name)
            except Exception as exc:
                log.warning("demo job %s not built (any earlier build is still served): %s", recording.name, exc)
        return built

    def _retry_gpu(self, job_id: str, state: JobState) -> bool:
        """A demo job built while the GPU auditor couldn't answer (its audit names YuNet) is built again, at most every
        :data:`DEMO_GPU_RETRY` so a GPU outage can't take the demo away on every wake."""
        if not self.settings.audit_gpu or datetime.now(UTC) - state.created_at < DEMO_GPU_RETRY:
            return False
        try:
            device = load(self.store.path(job_id) / "audit.json", Audit).egoblur.device
        except (OSError, ContractError):
            return True
        return not (device or "").startswith("cuda:")

    def _precompute(self, job_id: str, recording: Path, clip: Path, stamp: str) -> None:
        """Run the hero job with ``safecut run --replay`` in a child process (the child blocks the network for its
        whole life, and a live API's own threads are never blocked by it), into a scratch folder beside the store;
        only a finished build replaces the served demo, in one quick swap. The child keeps a ledger of its own: the
        demo is the owner's spend under the job cap alone, and the service's ledger keeps one writer."""
        scratch = self.store.root / BUILDING / job_id
        shutil.rmtree(scratch, ignore_errors=True)  # a build a dead container left half done
        scratch.mkdir(parents=True)
        try:
            with tempfile.TemporaryDirectory(prefix="demo-ledger-") as ledger:
                env = child_env({**os.environ, "SAFECUT_JOBS_DIR": ledger})  # the GPU path reaches Modal from it too
                proc = subprocess.run(  # noqa: S603 -- fixed argv: this interpreter, our own CLI, our own paths
                    [sys.executable, "-m", "safecut.cli", "run", str(clip), "--out", str(scratch), "--replay",
                     "--replay-from", str(recording), "--auto-approve-policy"],
                    capture_output=True, text=True, timeout=900, check=False, env=env,
                )  # fmt: skip
            if proc.returncode != 0:
                raise pipeline.PipelineError(f"safecut run exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
            synthetic = pipeline.recording_is_synthetic(scratch)
            # One swap: readers see the old demo or the new one, never neither (JobStore.replace_pinned).
            self.store.replace_pinned(job_id, scratch, synthetic=synthetic, demo_stamp=stamp)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

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
        """The rate limits' key: the client address (the proxy's last hop when it's trusted); an IPv6 client is
        keyed by its /64, which one subscriber controls whole, so rotating addresses doesn't reset the limits."""
        host = request.client.host if request.client else "unknown"
        if self.settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if hops:
                host = hops[-1]
        address = _parse_ip(host)
        if address is None:
            return host
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)  # an IPv4 client on a dual-stack socket or proxy hop
        return str(ipaddress.ip_network(f"{address}/64", strict=False)) if address.version == 6 else str(address)

    def job(self, job_id: str) -> JobState:
        try:
            return self.store.get(job_id)
        except JobNotFound as exc:
            if exc.expired:
                raise ApiRefusal(404, "expired", "This clip has been deleted.") from None
            raise ApiRefusal(404, "not_found", "We couldn't find that clip.") from None

    def refuse_when_busy(self, job_id: str) -> None:
        """``429`` once ``SAFECUT_MAX_ACTIVE_JOBS`` other jobs are processing, rendering or waiting to retry (the demo
        excluded). Checked after the job's own status checks, so a retried start of a finished job still gets its
        idempotent 409. A best-effort ceiling: two starts of different jobs racing can overshoot it by one each, and
        the spend caps (reserved per call in the ledger) are what bound money."""
        active = 0
        for other in self.store.ids():
            if other == job_id:
                continue
            try:
                state = load(self.store.path(other) / "state.json", JobState)
            except ContractError:
                continue
            active += not state.pinned and state.status in ("processing", "rendering", "retry_later")
        if active >= self.settings.max_active_jobs:
            raise ApiRefusal(
                429, "rate_limited", "Safe Cut is busy right now. Try again in a minute.", retry_after_s=60
            )

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
        svc.paid_limiter.hit("paid", client, limit=svc.settings.paid_actions_per_hour, window_s=3600)


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
        check_caps(svc.settings, svc.ledger, grant, estimate=estimate_usd(None, svc.settings))
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
    if length is None or not (length.isascii() and length.isdigit()) or int(length) != spec.size_bytes:
        raise ApiRefusal(403, "bad_signature", "The upload's Content-Length isn't the one this link was made for.")
    with svc.uploads_lock:
        if job_id in svc.uploading:  # two PUTs on one link would interleave in the same .part file
            raise ApiRefusal(409, "already_uploading", "This clip is already being uploaded.")
        current = svc.job(job_id).upload
        if current is not None and current.received:  # a PUT that finished while this one waited for the lock
            raise ApiRefusal(409, "already_uploaded", "This clip was already uploaded.")
        svc.uploading.add(job_id)
    try:
        return await _receive(svc, job_id, spec, request)
    finally:
        with svc.uploads_lock:
            svc.uploading.discard(job_id)


async def _receive(svc: Service, job_id: str, spec: UploadSpec, request: Request) -> Response:
    folder = svc.store.path(job_id) / SOURCE_DIR
    try:
        folder.mkdir(exist_ok=True)
    except FileNotFoundError:
        raise JobNotFound(job_id) from None  # deleted between the signature check and the first write
    partial = folder / f".{spec.file_name}.part"
    received = 0
    with partial.open("wb") as handle:
        async for chunk in request.stream():
            received += len(chunk)
            if received > spec.size_bytes:
                handle.close()
                partial.unlink(missing_ok=True)
                raise ApiRefusal(413, "too_large", "The upload is larger than declared.", size_bytes=received)
            await run_in_threadpool(handle.write, chunk)  # disk writes never stall the event loop
    if received != spec.size_bytes:
        partial.unlink(missing_ok=True)
        raise ApiRefusal(400, "upload_incomplete", "The upload ended before the declared size.")
    try:
        partial.replace(folder / spec.file_name)
    except FileNotFoundError:
        raise JobNotFound(job_id) from None  # the job was deleted during the upload
    with svc.store.update(job_id) as current:
        if current.upload is not None:
            current.upload.received = True
    return Response(status_code=200)


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """An address from a peer or proxy hop, with any port dropped (``1.2.3.4:5000``, ``[::1]:80``)."""
    candidates = [host]
    if host.startswith("[") and "]" in host:
        candidates.append(host[1 : host.index("]")])
    elif host.count(":") == 1:
        candidates.append(host.split(":", 1)[0])
    for candidate in candidates:
        try:
            return ipaddress.ip_address(candidate)
        except ValueError:
            continue
    return None


def demo_stamp(recording: Path, clip: Path, *, audit_gpu: bool = False) -> str:
    """What a pinned demo job was built from: every file of its recording (path and bytes), its clip, the
    ``safecut`` source and whether its audit runs on the GPU. Any change (a retake under the same id, a contract
    change in a new deploy, the GPU auditor switched on or off) rebuilds it."""
    package = Path(__file__).resolve().parent.parent
    labelled = [(f"raw:{p.relative_to(recording)}", p) for p in sorted(recording.rglob("*")) if p.is_file()]
    labelled.append(("clip", clip))
    labelled += [
        (f"code:{p.relative_to(package)}", p) for p in sorted(package.rglob("*.py")) if "__pycache__" not in p.parts
    ]
    digest = hashlib.sha256()
    if audit_gpu:  # off leaves every earlier stamp as it was
        digest.update(b"audit_gpu")
    for label, path in labelled:
        digest.update(label.encode())
        digest.update(path.read_bytes() if path.is_file() else b"missing")
    return digest.hexdigest()


def refuse_pinned(state: JobState) -> None:
    """The precomputed demo jobs are public and read-only: their IDs are derivable from the hero name."""
    if state.pinned:
        raise ApiRefusal(403, "demo_read_only", "The demo clip can't be changed or deleted.")


@router.post("/v1/jobs/{job_id}/start", status_code=202, dependencies=[paid_limit])
def start(svc: Svc, job_id: str) -> JSONResponse:
    svc.job(job_id)  # a clean 404 before taking the job's lock
    # Everything from the status check to the transition happens under the job's lock, so two concurrent starts
    # can't both pass the check and run the paid analysis twice.
    with svc.store.update(job_id) as state:
        refuse_pinned(state)
        grant = svc.paid_grant(state)
        if svc.worker.busy(job_id) or state.status in ("processing", "rendering", "retry_later"):
            raise ApiRefusal(409, "already_running", "This clip is already being processed.")
        if state.status not in ("created", "failed"):
            raise ApiRefusal(409, "already_started", "This clip has already been processed.")
        svc.refuse_when_busy(job_id)
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
            if not auditor_available(svc.settings):
                raise ApiRefusal(503, "auditor_unavailable", "Safe Cut's final check isn't available right now.")
            if grant is not None:
                check_caps(
                    # Priced at most at the 60 s limit: a longer clip fails in prepare (free) as too_long with its
                    # duration, never as a misleading per-clip cost refusal.
                    svc.settings,
                    svc.ledger,
                    grant,
                    estimate=estimate_usd(
                        min(duration, MAX_DURATION_S) if duration is not None else None, svc.settings
                    ),
                )
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
        state.status, state.stage, state.failure = "processing", "queued", None
        state.started_at = datetime.now(UTC)  # the stall clock runs from queueing, not from the last action
        state.synthetic = pipeline.recording_is_synthetic(job_dir)
        state.duration_s = duration
        state.requeues = 0
        state.resumes = 0
        updated = state.model_copy()
        svc.worker.submit(job_id, "analyse")
    return ack(updated)


@router.get("/v1/jobs/{job_id}", dependencies=[api_limit])
def get_job(svc: Svc, job_id: str) -> dict[str, Any]:
    state = svc.job(job_id)
    return svc.views.job(state, svc.store.path(job_id))


@router.post("/v1/jobs/{job_id}/review", dependencies=[api_limit])
def review(svc: Svc, job_id: str, edit: Annotated[ReviewEdit, Body()]) -> dict[str, Any]:
    """A plain (sync) handler: the guard re-plans in FastAPI's threadpool, never on the event loop, so polling and
    media keep flowing while an edit is applied."""
    return _review(svc, job_id, edit)


def _review(svc: Service, job_id: str, edit: ReviewEdit) -> dict[str, Any]:
    svc.job(job_id)
    job_dir = svc.store.path(job_id)
    with svc.store.update(job_id) as current:
        # Checked under the lock: a render that started a moment ago must not have its plan rewritten.
        refuse_pinned(current)
        if current.status == "needs_you":
            raise ApiRefusal(409, "read_only", "This clip can't be edited until the audit runs again.")
        if current.status not in ("review", "done") or svc.worker.busy(job_id):
            raise ApiRefusal(409, "not_reviewable", "This clip isn't ready for review.")
        log_path = job_dir / REVIEW
        edits = list(load(log_path, ReviewLog).root) if log_path.is_file() else []
        if all(e.edit_id != edit.edit_id for e in edits):
            _apply_edit(svc, job_dir, current, edits, edit)
        status = current.status
        mode = current.mode
        decisions = load(job_dir / "decisions.json", Decisions)
        plan_now = load(job_dir / "plan.json", Plan)
        audit_now = load(job_dir / "audit.json", Audit) if (job_dir / "audit.json").is_file() else None
    return {
        "edit_id": edit.edit_id,
        "mode": mode,
        "status": status,
        "has_render": (job_dir / "redacted.mp4").is_file(),
        "items": [i.model_dump(mode="json") | {"removed_by_creator": i.removed_by_creator} for i in decisions.items],
        "plan": plan_now.model_dump(mode="json"),
        "audit": {"spots": [s.model_dump(mode="json") for s in audit_now.spots]} if audit_now else None,
    }


def _apply_edit(svc: Service, job_dir: Path, current: JobState, edits: list[ReviewEdit], edit: ReviewEdit) -> None:
    """Fold the edit in and re-plan, all or nothing: if the guard fails, the decisions, audit and plan go back to
    what they were and the edit isn't logged, so a retry with the same ``edit_id`` applies it again."""
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
            tracks=load(job_dir / "tracks.json", Tracks),  # a re-hidden person gets exactly the policy's style
            job=job,
        )
    except ReviewError as exc:
        raise ApiRefusal(409, exc.code, str(exc)) from None
    saved = {
        name: (job_dir / name).read_bytes()
        for name in ("decisions.json", "audit.json", "plan.json")
        if (job_dir / name).is_file()
    }
    try:
        dump(result.decisions, job_dir / "decisions.json")
        if result.audit is not None:
            dump(result.audit, job_dir / "audit.json")
        pipeline.run_stage(job_dir, stage("guard"), replay=current.mode == "replay", settings=svc.settings, force=True)
        if current.status == "done":
            # The sealed receipt describes the decisions as they were: it's archived (receipts/, the next one
            # chains from it), never served beside decisions it no longer matches; inside the rollback, so a
            # receipt that can't be archived undoes the edit too. The previous render stays downloadable until a
            # new one replaces it (UI-SPEC §8 request 5).
            receipt.retire(job_dir)
    except BaseException:
        for name, data in saved.items():  # atomically, so a poll never reads a half-restored file
            restoring = job_dir / f".{name}.restore"
            restoring.write_bytes(data)
            restoring.replace(job_dir / name)
        raise
    dump(ReviewLog([*edits, edit]), job_dir / REVIEW)
    if current.status == "done":
        current.status, current.stage = "review", "review"


@router.post("/v1/jobs/{job_id}/render", status_code=202, dependencies=[paid_limit])
def render(svc: Svc, job_id: str) -> JSONResponse:
    svc.job(job_id)
    with svc.store.update(job_id) as state:
        refuse_pinned(state)
        grant = svc.paid_grant(state)
        if svc.worker.busy(job_id) or state.status in ("rendering", "processing", "retry_later"):
            raise ApiRefusal(409, "already_running", "A render is already running.")
        retry = (
            state.status == "failed"
            and state.failure is not None
            and state.failure.stage in ("render", "audit", "receipt")
        )
        if state.status != "review" and not retry:
            raise ApiRefusal(409, "not_reviewable", "This clip isn't waiting for a render.")
        svc.refuse_when_busy(job_id)
        if state.mode == "live" and grant is not None:
            check_caps(svc.settings, svc.ledger, grant, estimate=0.01)
        pipeline.approve(svc.store.path(job_id), how="review")
        state.status, state.stage, state.failure = "rendering", "render", None
        state.started_at = datetime.now(UTC)  # a long review never makes a queued render look stalled
        updated = state.model_copy()
        svc.worker.submit(job_id, "publish")
    return ack(updated)


@router.post("/v1/jobs/{job_id}/audit", status_code=202, dependencies=[paid_limit])
def audit(svc: Svc, job_id: str) -> JSONResponse:
    svc.job(job_id)
    with svc.store.update(job_id) as state:
        refuse_pinned(state)
        grant = svc.paid_grant(state)
        if svc.worker.busy(job_id) or state.status == "rendering":
            raise ApiRefusal(409, "already_running", "The audit is already running.")
        if state.status != "needs_you":
            raise ApiRefusal(409, "not_needed", "This clip's audit doesn't need to run again.")
        if state.mode == "live" and grant is not None:
            check_caps(svc.settings, svc.ledger, grant, estimate=0.01)
        state.status, state.stage, state.failure = "rendering", "audit", None
        state.started_at = datetime.now(UTC)  # a long review never makes a queued audit look stalled
        updated = state.model_copy()
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
    with contextlib.suppress(JobNotFound):  # an unknown job is a 404 below
        refuse_pinned(svc.store.get(job_id))
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
        # The API scales to zero: a small uptime on the first answer after a quiet spell proves a cold wake.
        "uptime_s": round(time.monotonic() - svc.started_monotonic, 1),
        "audit_gpu": svc.settings.audit_gpu,
        # Whether this container's demo build has finished, and which demos match its code: a deploy check judges
        # the demo built by the new code, never one an earlier deploy left on the Volume.
        "demos_building": not svc.demo_built,
        "demos_current": sorted(svc.demos_current),
        # Whether the last keepalive (the container holding itself up for a job) reached Modal; null before any.
        "keepalive": svc.worker.keepalive_ok,
    }
    return JSONResponse(body, status_code=200 if writable else 503)


#: BLOCKED.md's minimums for the deployed service: an access code is guessed across IPs only if it's short.
MIN_CODE_CHARS = 12
MIN_URL_SECRET_CHARS = 32


def production_problems(settings: Settings) -> list[str]:
    """What makes these settings unfit to serve the public (the Modal entry point refuses to start on any)."""
    problems: list[str] = []
    for code in settings.access_codes:
        if len(code.code.get_secret_value()) < MIN_CODE_CHARS:
            problems.append(f"a {code.kind} access code is shorter than {MIN_CODE_CHARS} characters")
    for key in settings.service_keys:
        if len(key.key.get_secret_value()) < MIN_URL_SECRET_CHARS:
            problems.append(f"service key {key.name!r} is shorter than {MIN_URL_SECRET_CHARS} characters")
    secret = settings.url_secret.get_secret_value() if settings.url_secret else ""
    if len(secret) < MIN_URL_SECRET_CHARS:
        problems.append(f"SAFECUT_URL_SECRET is unset or shorter than {MIN_URL_SECRET_CHARS} characters")
    if settings.public_url is None or not settings.public_url.startswith("https://"):
        problems.append("SAFECUT_PUBLIC_URL is not an https URL")
    return problems


def create_app(settings: Settings | None = None, *, service: Service | None = None, background: bool = True) -> FastAPI:
    """``background`` starts the deletion loop and builds the demo jobs at startup (off in unit tests)."""
    svc = service or Service(settings or load_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        blocking = svc.settings.replay and not netguard.active()
        if blocking:
            netguard.block()  # a replay deployment never reaches the network, in any thread
        if background:
            svc.start()
        try:
            yield
        finally:
            svc.stop(wait=svc.wait_on_stop)
            if blocking:
                netguard.unblock()

    # No public /docs or /openapi.json: the API's contract is UI-SPEC §8 and the web app's zod schemas.
    app = FastAPI(
        title="Sigmora Safe Cut API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
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

    @app.exception_handler(JobNotFound)
    async def gone(_: Request, exc: JobNotFound) -> JSONResponse:
        # A job deleted or expired between a handler's first look and its update (``Service.job`` answers the
        # first look itself): the same 404 as an unknown job, never a 500.
        refused = (
            ApiRefusal(404, "expired", "This clip has been deleted.")
            if exc.expired
            else ApiRefusal(404, "not_found", "We couldn't find that clip.")
        )
        return JSONResponse(refused.body(), status_code=404)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        where = "; ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors()[:3])
        return JSONResponse({"error": {"code": "bad_request", "message": f"invalid request: {where}"}}, status_code=422)

    app.include_router(router)
    return app


__all__ = ["Service", "create_app", "hero_job_id"]
