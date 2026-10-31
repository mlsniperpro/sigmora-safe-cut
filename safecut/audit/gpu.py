"""EgoBlur Gen 2 on a Modal GPU (WP4 step 2: "if a 30 s clip at 1280 px takes over 3 minutes on CPU, add a Modal
GPU function"; lane SAFECUT-MODAL).

EgoBlur Gen 2 runs about 1.5 s per frame per model on CPU (``egoblur-gen2.md``), so a 30 s, 900-frame clip takes
~45 min on CPU (face + plate); Meta quotes about 21 ms per frame on a GPU (an unnamed one; not measured here). The
API container stays slim (no torch): with ``SAFECUT_AUDIT_GPU=1`` each detector scan is one call to the GPU function.
The render reaches it through a handoff Volume (``safecut-audit``) that the API holds no file open on: the API copies
the render there and commits, the function reloads and reads it, so only frame numbers go out and boxes come back.
(Committing the jobs Volume itself would also reload it, which Modal refuses while the API holds the spend ledger's
SQLite files open on it.)

* :class:`Handoff` puts a render where the GPU function reads it.
* :class:`GpuServer` is what the Modal GPU function wraps (``deploy/modal_app.py`` owns the decorators, the Volumes
  and the GPU type): it checks the request, verifies the weights' SHA-256, builds EgoBlur once per container, runs it
  on the wanted frames of ``redacted.mp4`` and answers with the video's hash, so a stale Volume view is caught.
* :class:`GpuDetector` is the audit's side: a batch :class:`~safecut.audit.detectors.Detector`. Every call is
  bounded (``SAFECUT_AUDIT_GPU_TIMEOUT_S``), priced into the ledger and ``cost.jsonl`` (``provider: "modal"``,
  estimated), and schema-checked. Any failure (timeout, error, missing or altered weights, no GPU, a cap) is typed
  as :class:`GpuUnavailable`; the audit stage then runs YuNet and records that YuNet ran (``audit/__init__.py``).
"""

from __future__ import annotations

import fcntl
import importlib
import importlib.util
import logging
import os
import re
import shutil
import site
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from safecut import netguard
from safecut.audit.detectors import (
    AuditorModel,
    AuditorUnavailable,
    Detection,
    Detector,
    EgoBlur,
    egoblur_weights,
    to_box,
    verify_egoblur,
)
from safecut.config import Settings
from safecut.contracts import ContractError, CostLine, Job, append_cost_line, load, now_utc
from safecut.meta.budget import Caller, CapLimit, LocalLedger, job_limit
from safecut.meta.errors import BudgetExceeded
from safecut.render import REDACTED, file_sha256
from safecut.render.video import RenderError, read_frames

log = logging.getLogger(__name__)

#: A job folder's name on the Volume: one path component, never ``..``.
_JOB_NAME = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")
#: A transient failure (not a timeout, a refusal or a cap) is retried once, after this pause.
RETRY_DELAY_S = 2.0
RETRYABLE = frozenset({"error", "stale_volume"})
GpuRefusal = Literal["no_weights", "altered_weights", "no_gpu", "bad_request", "no_render"]


class NotSubmitted(RuntimeError):
    """The GPU call failed before Modal accepted it (the control plane unreachable, the function not deployed): no
    GPU ran, so nothing is priced or claimed."""


class GpuUnavailable(RuntimeError):
    """The GPU auditor didn't answer this scan; the audit runs YuNet instead."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


# -- the wire ------------------------------------------------------------------------------------------------


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GpuRequest(_Wire):
    job: str = Field(pattern=_JOB_NAME.pattern)
    frames: list[int] = Field(min_length=1)
    model: Literal["egoblur-gen2", "egoblur-gen1"]
    face_threshold: float = Field(gt=0, lt=1)
    plate_threshold: float = Field(gt=0, lt=1)


class WireDetection(_Wire):
    kind: Literal["face", "plate"]
    box: tuple[float, float, float, float]
    score: float = Field(ge=0, le=1)


class GpuAnswer(_Wire):
    model: Literal["egoblur-gen2", "egoblur-gen1"]
    #: ``torch.cuda.get_device_name``, e.g. ``Tesla T4``.
    gpu: str = Field(min_length=1, max_length=120)
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seconds: float = Field(ge=0)
    frames: dict[int, list[WireDetection]]


class GpuRefused(_Wire):
    refused: GpuRefusal
    detail: str = Field(max_length=500)


# -- the GPU side --------------------------------------------------------------------------------------------


class GpuServer:
    """One per GPU container: the detectors load once, then every request reuses them."""

    def __init__(
        self,
        root: Path,
        weights_dir: Path,
        *,
        load: Callable[[AuditorModel, Path, Path, float, float], Detector] | None = None,
        gpu_name: Callable[[], str | None] | None = None,
    ) -> None:
        self.root = root
        self.weights_dir = weights_dir
        self._load = load or _load_egoblur
        self._gpu_name = gpu_name or _cuda_name
        self._detectors: dict[tuple[str, float, float], Detector] = {}
        self._lock = threading.Lock()

    def serve(self, raw: dict[str, Any]) -> dict[str, Any]:
        """One scan: a :class:`GpuAnswer`, or a :class:`GpuRefused` saying exactly why not (as plain JSON)."""
        try:
            request = GpuRequest.model_validate(raw)
        except ValidationError as exc:
            return _refused("bad_request", str(exc.errors(include_input=False))[:500])
        gpu = self._gpu_name()
        if gpu is None:
            return _refused("no_gpu", "no CUDA device in this container: EgoBlur on CPU takes ~1.5 s per frame")
        job_dir = self.root / request.job
        video = job_dir / REDACTED
        if not (job_dir / "job.json").is_file() or not video.is_file():
            return _refused("no_render", f"{request.job} has no job.json or {REDACTED} on the handoff Volume")
        try:
            job = load(job_dir / "job.json", Job)
        except ContractError as exc:
            return _refused("no_render", f"{request.job}/job.json doesn't validate: {exc}")
        wanted = set(request.frames)
        if min(wanted) < 0 or max(wanted) >= job.frames:
            return _refused("bad_request", f"frames outside 0..{job.frames - 1}")
        try:
            detector = self._detector(request)
        except AuditorUnavailable as exc:
            return _refused("altered_weights" if "SHA-256" in str(exc) else "no_weights", str(exc))
        started = time.perf_counter()
        found: dict[int, list[WireDetection]] = {}
        try:
            sha = file_sha256(video)
            for index, frame in enumerate(read_frames(video, job)):
                if index in wanted:
                    found[index] = [
                        WireDetection(kind=d.kind, box=d.box, score=d.score) for d in detector.detect(frame)
                    ]
        except (RenderError, OSError) as exc:  # the same render fails the same way: refused, never retried
            return _refused("no_render", f"{request.job}/{REDACTED} can't be read: {exc}"[:500])
        answer = GpuAnswer(
            model=request.model, gpu=gpu, video_sha256=sha, seconds=time.perf_counter() - started, frames=found
        )
        return answer.model_dump(mode="json")

    def _detector(self, request: GpuRequest) -> Detector:
        key = (request.model, request.face_threshold, request.plate_threshold)
        with self._lock:
            if key not in self._detectors:
                files = egoblur_weights(self.weights_dir, request.model)
                if files is None:
                    raise AuditorUnavailable(f"no {request.model} weights in {self.weights_dir}")
                verify_egoblur(*files, request.model)
                self._detectors[key] = self._load(request.model, *files, request.face_threshold,
                                                  request.plate_threshold)  # fmt: skip
            return self._detectors[key]


def _refused(reason: GpuRefusal, detail: str) -> dict[str, Any]:
    return GpuRefused(refused=reason, detail=detail[:500]).model_dump(mode="json")


def _load_egoblur(model: AuditorModel, face: Path, plate: Path, face_t: float, plate_t: float) -> Detector:
    return EgoBlur(model, face, plate, face_threshold=face_t, plate_threshold=plate_t)


def _cuda_name() -> str | None:
    import torch  # noqa: PLC0415 -- the GPU image's audit group; never imported by the API

    return str(torch.cuda.get_device_name(0)) if torch.cuda.is_available() else None


# -- the API side --------------------------------------------------------------------------------------------

#: ``(request, timeout_s) -> (raw answer, call id)``; raises :class:`TimeoutError` past ``timeout_s``.
RemoteCall = Callable[[GpuRequest, float], tuple[dict[str, Any], str | None]]


class GpuMeter:
    """Prices GPU seconds into the service's ledger (the caller's caps and the job cap) and ``cost.jsonl``.

    Modal bills the GPU container by the second, cold start and the idle ``scaledown_window`` included, so each call
    is reserved at its timeout plus that idle tail (first call only) and settled at its wall time plus the tail:
    an estimate that errs high, logged ``estimated: true``."""

    def __init__(self, settings: Settings, ledger: LocalLedger, caller: Caller, job_id: str, cost_path: Path) -> None:
        self.settings = settings
        self.ledger = ledger
        self.caller = caller
        self.job_id = job_id
        self.cost_path = cost_path
        self._tail = settings.audit_gpu_idle_s

    def usd(self, seconds: float) -> float:
        return seconds * self.settings.audit_gpu_usd_per_hour / 3600

    def _limits(self) -> list[CapLimit]:
        return [job_limit(self.settings, self.job_id), *self.caller.limits_at(now_utc())]

    def reserve(self, call_id: str) -> None:
        """Raises :class:`BudgetExceeded` (and logs the stop) when a cap can't cover this call's worst case."""
        try:
            self.ledger.reserve(call_id, self.job_id, self.usd(self.settings.audit_gpu_timeout_s + self._tail),
                                self._limits())  # fmt: skip
        except BudgetExceeded as exc:
            self._line(stage="budget:audit", usd=0, units={}, estimated=False, rid=None, cap=exc.cap)
            raise

    def settle(self, call_id: str, wall_s: float, model: str, rid: str | None) -> None:
        """Record what the call cost. Never raises: a failed write must not lose the scan's answer (an open
        reservation expires as a charge, failing closed, as the Meta client's do)."""
        usd = self.usd(wall_s + self._tail)
        try:
            self._line(stage="audit", usd=usd, units={"gpu_s": round(wall_s, 3), "idle_s": self._tail},
                       estimated=True, rid=rid, model=model)  # fmt: skip
        except (OSError, ValidationError):
            log.exception("cost.jsonl write failed for a GPU audit call")
        self._tail = 0.0  # the idle tail is billed once per audit, after its last call
        try:
            self.ledger.settle(call_id, usd)
        except Exception:
            log.exception("ledger settle failed for a GPU audit call; the reservation will expire as a charge")

    def release(self, call_id: str) -> None:
        """A reserved call that never reached Modal: released, never priced. Never raises (as ``settle``)."""
        try:
            self.ledger.release(call_id)
        except Exception:
            log.exception("ledger release failed for an unsubmitted GPU call; the reservation will expire as a charge")

    def _line(self, *, stage: str, usd: float, units: dict[str, float], estimated: bool, rid: str | None,
              cap: Any = None, model: str | None = None) -> None:  # fmt: skip
        line = CostLine(ts=now_utc(), provider="modal", job_id=self.job_id, stage=stage, model=model, attempt=0,
                        units=units, usd=usd, estimated=estimated, request_id=rid, cap=cap,
                        code_kind=self.caller.code_kind, code_id=self.caller.code_id)  # fmt: skip
        append_cost_line(line, self.cost_path)


#: How long a handoff commit may take before the scan gives up on the GPU (Modal retries a commit internally).
HANDOFF_COMMIT_TIMEOUT_S = 120.0
#: One file lock per container: the API and its demo-build child process write the same handoff mount.
HANDOFF_LOCK = Path(tempfile.gettempdir()) / "safecut-handoff.lock"


class Handoff:
    """Where the GPU function reads a render: ``<root>/<job>-<render sha>/`` (``job.json`` and ``redacted.mp4``) on
    a Volume of its own. Writes and commits hold one lock across threads and processes of this container, so a
    commit (and the reload Modal does after it) never meets a file open there; a commit that hangs is abandoned after
    ``commit_timeout_s`` as a :class:`TimeoutError`, so no scan waits on it forever."""

    _lock = threading.Lock()

    def __init__(
        self,
        root: Path,
        commit: Callable[[], None],
        *,
        commit_timeout_s: float = HANDOFF_COMMIT_TIMEOUT_S,
        lock_file: Path = HANDOFF_LOCK,
    ) -> None:
        self.root = root
        self._commit = commit
        self._commit_timeout_s = commit_timeout_s
        self._lock_file = lock_file
        self._put: set[str] = set()

    @staticmethod
    def name(job_dir: Path, sha: str) -> str:
        return f"{re.sub(r'[^A-Za-z0-9_-]', '_', job_dir.name)[:100]}-{sha[:16]}"

    @contextmanager
    def _exclusive(self) -> Generator[None]:
        with self._lock, self._lock_file.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def put(self, job_dir: Path, sha: str) -> str:
        """Copy the render (once per render) and commit; returns the folder name the GPU request names."""
        name = self.name(job_dir, sha)
        target = self.root / name
        with self._exclusive():
            if not (target / REDACTED).is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(job_dir / "job.json", target / "job.json")
                partial = target / f".{REDACTED}.partial"
                shutil.copyfile(job_dir / REDACTED, partial)
                partial.replace(target / REDACTED)
            self._put.add(name)
            self._bounded_commit()
        return name

    def _bounded_commit(self) -> None:
        try:
            on_daemon(self._commit, timeout_s=self._commit_timeout_s)
        except TimeoutError as exc:
            raise TimeoutError(f"the handoff commit took over {self._commit_timeout_s:.0f} s") from exc

    def discard(self, name: str) -> None:
        """Remove one render, so the next ``put`` copies it afresh."""
        with self._exclusive():
            shutil.rmtree(self.root / name, ignore_errors=True)

    def close(self) -> None:
        """Remove every render this audit put there, and commit the removal (best effort: a commit that fails is
        logged, and Modal's background commit or the cron's hourly sweep removes the copy instead)."""
        with self._exclusive():
            if not self._put:
                return
            for name in self._put:
                shutil.rmtree(self.root / name, ignore_errors=True)
            self._put.clear()
            try:
                self._bounded_commit()
            except Exception:
                log.warning("couldn't commit the handoff cleanup; the cron's sweep removes it", exc_info=True)


class GpuDetector:
    """The audit's detector when ``SAFECUT_AUDIT_GPU=1``: whole scans go to the GPU function (``detect_frames``).

    Answers are cached per render (keyed by its SHA-256), so pass 1 can be fetched before the audit starts
    (:meth:`prefetch`): a GPU that can't answer is known before a single red-team frame is paid for."""

    def __init__(
        self,
        job_dir: Path,
        settings: Settings,
        call: RemoteCall,
        meter: GpuMeter,
        *,
        handoff: Handoff,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if settings.egoblur_model == "yunet-face":
            raise ValueError("the GPU auditor runs EgoBlur; SAFECUT_EGOBLUR_MODEL is yunet-face")
        self.job_dir = job_dir
        self.settings = settings
        self._call = call
        self._meter = meter
        self.handoff = handoff
        self._sleep = sleep
        self._model: Literal["egoblur-gen2", "egoblur-gen1"] = settings.egoblur_model
        self._job = load(job_dir / "job.json", Job)
        self._cache: dict[str, dict[int, list[Detection]]] = {}
        #: Set by the first scan the GPU couldn't answer (the audit stage then re-runs on YuNet).
        self.failure: GpuUnavailable | None = None
        #: Every GPU that answered (Modal may give a pass a T4 when no L4 is free).
        self.gpus: set[str] = set()
        self.calls = 0
        #: Wall seconds spent in GPU calls (cold starts and the wire included): run.json's GPU timing.
        self.wall_s = 0.0

    @property
    def model(self) -> AuditorModel:
        return self._model

    @property
    def detects_plates(self) -> bool:
        return True

    @property
    def device(self) -> str | None:
        return f"cuda:{'+'.join(sorted(self.gpus))}" if self.gpus else None

    def detect(self, frame: Any) -> list[Detection]:
        raise TypeError("the GPU auditor scans whole renders: use detect_frames")

    def prefetch(self) -> None:
        """Pass 1's scan (every frame) before the audit starts; raises :class:`GpuUnavailable`."""
        self.detect_frames(self.job_dir, set(range(self._job.frames)))

    def detect_frames(self, job_dir: Path, wanted: set[int]) -> dict[int, list[Detection]]:
        """Detections for every frame in ``wanted`` of the current render, or :class:`GpuUnavailable`."""
        if job_dir != self.job_dir:
            raise ValueError(f"this GPU detector audits {self.job_dir}, not {job_dir}")
        if not wanted:
            return {}
        if self.failure is not None:  # once the GPU has failed this audit, it's re-run on YuNet: no more GPU calls
            raise self.failure
        try:
            sha = file_sha256(job_dir / REDACTED)
            cached = self._cache.get(sha, {})
            missing = sorted(wanted - cached.keys())
            if missing:
                cached = {**cached, **self._fetch(sha, missing)}
                self._cache = {sha: cached}  # a new render retires the old one's answers
            return {i: cached[i] for i in wanted}
        except Exception as exc:  # every way a scan can fail is the GPU path failing: recorded, then re-raised
            failure = (
                exc
                if isinstance(exc, GpuUnavailable)
                else GpuUnavailable("error", f"{type(exc).__name__}: {exc}"[:300])
            )
            self.failure = self.failure or failure
            raise failure from exc

    def _fetch(self, sha: str, frames: list[int]) -> dict[int, list[Detection]]:
        try:
            return self._attempt(sha, frames)
        except GpuUnavailable as exc:
            if exc.reason not in RETRYABLE:
                raise  # a timeout, a refusal or a cap won't change on a retry
            log.warning("GPU auditor: %s; retrying once in %.0f s", exc, RETRY_DELAY_S)
        self._sleep(RETRY_DELAY_S)
        return self._attempt(sha, frames)

    def _attempt(self, sha: str, frames: list[int]) -> dict[int, list[Detection]]:
        # The render must be on the handoff Volume, committed, before the GPU reads it. Free: nothing is reserved,
        # priced or claimed until a call is actually made.
        try:
            name = self.handoff.put(self.job_dir, sha)
        except TimeoutError as exc:
            raise GpuUnavailable("timeout", str(exc)) from exc
        except Exception as exc:
            raise GpuUnavailable("error", f"handoff: {type(exc).__name__}: {exc}"[:300]) from exc
        request = GpuRequest(job=name, frames=frames, model=self._model,
                             face_threshold=self.settings.egoblur_face_threshold,
                             plate_threshold=self.settings.egoblur_plate_threshold)  # fmt: skip
        call_id = f"gpu-{self._meter.job_id}-{uuid.uuid4().hex}"
        try:
            self._meter.reserve(call_id)
        except BudgetExceeded as exc:
            raise GpuUnavailable("over_budget", str(exc)) from exc
        except Exception as exc:  # a ledger it can't write: no unpriced GPU call
            raise GpuUnavailable("ledger", f"{type(exc).__name__}: {exc}"[:300]) from exc
        started = time.monotonic()
        rid: str | None = None
        submitted = True
        try:
            raw, rid = self._call(request, self.settings.audit_gpu_timeout_s)
        except NotSubmitted as exc:
            submitted = False
            raise GpuUnavailable("error", f"not submitted: {exc}"[:300]) from exc
        except TimeoutError as exc:
            raise GpuUnavailable(
                "timeout", str(exc) or f"no answer in {self.settings.audit_gpu_timeout_s:.0f} s"
            ) from exc
        except Exception as exc:
            raise GpuUnavailable("error", f"{type(exc).__name__}: {exc}"[:300]) from exc
        finally:
            if submitted:
                self.calls += 1
                self.wall_s += time.monotonic() - started
                self._meter.settle(call_id, time.monotonic() - started, self._model, rid)
            else:  # no GPU ran: the reservation goes, and nothing is priced or claimed
                self._meter.release(call_id)
        return self._read(raw, request, sha)

    def _read(self, raw: dict[str, Any], request: GpuRequest, sha: str) -> dict[int, list[Detection]]:
        try:
            if "refused" in raw:
                refused = GpuRefused.model_validate(raw)
                raise GpuUnavailable(refused.refused, refused.detail)
            answer = GpuAnswer.model_validate(raw)
        except ValidationError as exc:
            raise GpuUnavailable("bad_answer", str(exc.errors(include_input=False))[:300]) from exc
        if answer.model != request.model:
            raise GpuUnavailable("bad_answer", f"asked for {request.model}, {answer.model} answered")
        if answer.video_sha256 != sha:
            self.handoff.discard(request.job)  # copied again on the retry, never trusted twice
            raise GpuUnavailable("stale_volume", "the GPU read another version of the render (Volume not reloaded)")
        if set(answer.frames) != set(request.frames):
            raise GpuUnavailable("bad_answer", "the GPU didn't answer exactly the frames it was asked for")
        self.gpus.add(answer.gpu)
        width, height = self._job.width, self._job.height
        out: dict[int, list[Detection]] = {}
        for index, found in answer.frames.items():
            boxes = ((d, to_box(d.box, width, height)) for d in found)
            out[index] = [Detection(d.kind, box, d.score) for d, box in boxes if box is not None]
        return out


# -- Modal ---------------------------------------------------------------------------------------------------


def _modal() -> Any:
    """The Modal client (the ``deploy`` group; present in every Modal container), imported only when used; a child
    process finds it through ``SAFECUT_MODAL_PATH`` (``child_env``), appended last to ``sys.path``."""
    try:
        return importlib.import_module("modal")
    except ModuleNotFoundError:
        folder = os.environ.get(MODAL_PATH_ENV)
        if not folder or folder in sys.path:
            raise
        sys.path.append(folder)
        return importlib.import_module("modal")


def on_daemon[T](work: Callable[[], T], *, timeout_s: float | None = None) -> T:
    """Run ``work`` on a daemon thread and wait for it (at most ``timeout_s``, else :class:`TimeoutError`, the work left
    running). A daemon, because ``ThreadPoolExecutor``'s threads are joined at interpreter exit: a container being
    replaced mid-scan must exit at once, like its job threads (``safecut.api.worker.DaemonPool``)."""
    result: list[T] = []
    error: list[BaseException] = []
    done = threading.Event()

    def run() -> None:
        try:
            result.append(work())
        except BaseException as exc:
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=run, name="modal-call", daemon=True).start()
    if not done.wait(timeout_s):
        raise TimeoutError(f"no answer in {timeout_s:.0f} s")
    if error:
        raise error[0]
    return result[0]


def off_loop[T](work: Callable[[], T]) -> T:
    """Run a blocking Modal call on a thread of its own: re-check scans run inside the audit's event loop, where
    Modal's blocking API warns (and the loop is blocked either way: the scan waits for its answer)."""
    return on_daemon(work)


def modal_hosts() -> list[str]:
    """The Modal control plane's hosts, which the client must reach even in replay (it's compute, not a model).
    ``server_url`` may list several, comma-separated, and the client falls back across them (modal 1.6.2's default
    is ``https://api.modal.com,https://api.modal2.com``)."""
    modal = _modal()
    urls = str(modal.config.config.get("server_url") or "").split(",")
    return [host for url in urls if (host := urlsplit(url.strip()).hostname)]


@contextmanager
def modal_permitted() -> Generator[None]:
    """Replay's network guard lets every Modal control-plane host through in this scope (``netguard.permitting``)."""
    with ExitStack() as stack:
        for host in modal_hosts():
            stack.enter_context(netguard.permitting(host))
        yield


#: The Modal client's folder, for a child process (``child_env``); appended to ``sys.path`` on first use.
MODAL_PATH_ENV = "SAFECUT_MODAL_PATH"


def child_env(env: Mapping[str, str]) -> dict[str, str]:
    """The environment for a child Python (``safecut run``) that must reach Modal as this process does. In a Modal
    container the client may live outside the interpreter's own site-packages (a mount the runtime adds at
    startup), which a child may not repeat: that folder is named in ``SAFECUT_MODAL_PATH``, and the child appends it
    to ``sys.path`` only when it first needs Modal (``_modal``), after the standard library and its own packages,
    so nothing there can shadow them (``PYTHONPATH`` would put it first). Unchanged where the client is in
    site-packages, or absent."""
    out = dict(env)
    spec = importlib.util.find_spec("modal")
    if spec is None or spec.origin is None:
        return out
    folder = Path(spec.origin).resolve().parent.parent
    standard = {Path(p).resolve() for p in (*site.getsitepackages(), site.getusersitepackages())}
    if folder not in standard:
        out[MODAL_PATH_ENV] = str(folder)
    return out


def modal_call(settings: Settings) -> RemoteCall:
    """The deployed GPU function, spawned and awaited with a bound; a timed-out call is cancelled."""
    modal = _modal()

    def call(request: GpuRequest, timeout_s: float) -> tuple[dict[str, Any], str | None]:
        return off_loop(lambda: _call(request, timeout_s))

    def _call(request: GpuRequest, timeout_s: float) -> tuple[dict[str, Any], str | None]:
        with ExitStack() as scope:
            try:  # everything before Modal accepts the call: nothing ran, nothing is priced
                scope.enter_context(modal_permitted())
                function = modal.Function.from_name(settings.audit_gpu_app, settings.audit_gpu_function)
                handle = function.spawn(request.model_dump(mode="json"))
            except Exception as exc:
                raise NotSubmitted(f"{type(exc).__name__}: {exc}") from exc
            try:
                result: Any = handle.get(timeout=timeout_s)
            except (TimeoutError, modal.exception.TimeoutError) as exc:  # waited too long, or the function's own limit
                _cancel(handle)  # a stuck scan must not keep a GPU billing in the background
                raise TimeoutError(str(exc)) from exc
            except BaseException:
                _cancel(handle)  # an error after the spawn: the scan we stop waiting for mustn't run on unpriced
                raise
        if not isinstance(result, dict):
            raise TypeError(f"the GPU function answered a {type(result).__name__}")
        return cast(dict[str, Any], result), str(handle.object_id)

    return call


def _cancel(handle: Any) -> None:
    try:
        handle.cancel(terminate_containers=True)
    except Exception:
        log.warning("couldn't cancel a GPU call; Modal's function timeout ends it", exc_info=True)


def modal_commit(settings: Settings) -> Callable[[], None]:
    """Commit the handoff Volume from this container, so the GPU container's reload sees the render."""
    modal = _modal()

    def commit() -> None:
        def run() -> None:
            with modal_permitted():
                modal.Volume.from_name(settings.audit_gpu_volume).commit()

        off_loop(run)

    return commit


def batches(detector: Detector, job_dir: Path, wanted: set[int]) -> Iterator[tuple[int, list[Detection]]] | None:
    """A batch detector's answers for ``wanted`` in frame order, or None for a per-frame detector."""
    if not isinstance(detector, GpuDetector):
        return None
    found = detector.detect_frames(job_dir, wanted)
    return iter(sorted(found.items()))


__all__ = [
    "MODAL_PATH_ENV",
    "GpuAnswer",
    "GpuDetector",
    "GpuMeter",
    "GpuRefused",
    "GpuRequest",
    "GpuServer",
    "GpuUnavailable",
    "Handoff",
    "NotSubmitted",
    "RemoteCall",
    "batches",
    "child_env",
    "modal_call",
    "modal_commit",
    "modal_hosts",
    "modal_permitted",
]
