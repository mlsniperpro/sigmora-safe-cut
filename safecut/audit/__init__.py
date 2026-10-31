"""audit: ``redacted.mp4`` → ``audit.json`` (detector on every frame + red-team + auto-patch; WP4 step 2).

``run(job_dir, replay=…)`` picks what answers each question:

* the detector: EgoBlur Gen 2 when its weights are installed, else the bundled YuNet (``detectors.load_detector``);
  it runs locally in both modes;
* the red-team: live Muse Spark, or in replay the answers recorded from a live run (``raw/redteam/frames.json``), or
  for a **synthetic** job the ground-truth oracle (``raw/redteam/synthetic_truth.json``, or the label file a
  synthetic recording's ``raw/manifest.json`` names). A replay with none of these has
  no red-team answer at all: every sampled frame is unresolved (``audit_failed``), never clean.

Per-frame CPU timings and the models that answered go to ``raw/audit/run.json`` (WP4: if a 30 s clip at
1280 px takes over 3 minutes on CPU, the detector belongs on a GPU; ``gpu.py``).
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from collections.abc import Callable, Sequence
from contextlib import AsyncExitStack
from pathlib import Path

from safecut import open_weight, pipeline
from safecut.audit import gpu
from safecut.audit.detectors import AuditorUnavailable, Detector, device_of, load_detector
from safecut.audit.gpu import GpuDetector, GpuMeter, GpuUnavailable, Handoff, RemoteCall
from safecut.audit.loop import audit_job
from safecut.audit.opinion import Ask
from safecut.audit.opinion import attempted as opinion_attempted
from safecut.audit.redteam import Answer, LiveRedTeam, RedTeam, ReplayRedTeam, SyntheticRedTeam
from safecut.audit.truth import load_labels, manifest_truth
from safecut.config import Settings, load_settings
from safecut.contracts import Audit, Job, Plan, load
from safecut.meta.budget import Caller
from safecut.meta.client import MetaClient
from safecut.render import write_atomic
from safecut.render.draw import Frame

AUDIT = "audit.json"
RECORDED = Path("raw/redteam/frames.json")
SYNTHETIC_TRUTH = Path("raw/redteam/synthetic_truth.json")
GPU_RECORD = Path("raw/audit/gpu.json")

log = logging.getLogger(__name__)


class NoRedTeam:
    """A replay with nothing recorded: no frame is answered, so every one counts as unresolved."""

    async def ask(self, frames: Sequence[tuple[int, Frame]], approved: Sequence[str], *, bar: int) -> Answer:
        del approved, bar
        return Answer(missing=[f for f, _ in frames])


def replay_redteam(job_dir: Path) -> RedTeam:
    if (job_dir / RECORDED).exists():
        return ReplayRedTeam.load(job_dir / RECORDED)
    job = load(job_dir / "job.json", Job)
    plan_of = lambda: load(job_dir / "plan.json", Plan)  # noqa: E731 -- the oracle re-reads the current plan
    if (job_dir / SYNTHETIC_TRUTH).exists():
        return SyntheticRedTeam.load(job_dir / SYNTHETIC_TRUTH, plan_of, job.width, job.height)
    labels = manifest_truth(job_dir)
    if labels is not None:
        truth = load_labels(labels, width=job.width, height=job.height, frames=job.frames)
        return SyntheticRedTeam(truth.frames, plan_of, job.width, job.height)
    return NoRedTeam()


async def _live(job_dir: Path, settings: Settings, detector: Detector, client: MetaClient | None) -> Audit:
    job = load(job_dir / "job.json", Job)
    # The job's own caller (judge, pilot, owner …): its caps hold, and the open-weight gate reads its code kind.
    caller = pipeline.job_caller(job_dir, settings) if (job_dir / pipeline.INTAKE).exists() else Caller.local()
    # Eligible, and actually able to run: a missing Baseten key or price would fail every batch.
    eligible = (
        not opinion_attempted(job_dir, job)
        and open_weight.enabled_for(settings, consented=job.consented, code_kind=caller.code_kind)
        and settings.baseten_api_key is not None
        and settings.open_weight_price is not None
    )
    # The service's one spend ledger: the daily, code and pilot-pool caps count every job's calls, not just this one.
    ledger = pipeline.job_ledger(settings)
    async with AsyncExitStack() as stack:
        if client is None:
            client = await stack.enter_async_context(
                MetaClient(settings, job_id=job.job_id, caller=caller, ledger=ledger, cost_path=job_dir / "cost.jsonl")
            )
        meta = client
        opinion: Ask | None = None
        if eligible:
            baseten = open_weight.open_weight_client(settings, job_id=job.job_id, caller=caller, ledger=ledger,
                                                     cost_path=job_dir / "cost.jsonl")  # fmt: skip
            stack.push_async_callback(baseten.aclose)

            async def ask(frames: Sequence[tuple[int, str]], words: str) -> open_weight.SecondOpinion:
                return await open_weight.second_opinion(baseten, settings, consented=job.consented, frames=frames,
                                                        kept_clear=words)  # fmt: skip

            opinion = ask

        audit, _ = await audit_job(job_dir, detector=detector, redteam=LiveRedTeam(meta, settings, job_dir),
                                   opinion=opinion, opinion_grid_ok=settings.open_weight_grid_ok,
                                   opinion_model=settings.open_weight_model)  # fmt: skip
        return audit


def auditor_available(settings: Settings) -> bool:
    """Whether the audit can run here (WP5 answers ``POST /start`` with 503 ``auditor_unavailable`` when it can't):
    EgoBlur when its weights are installed (and torch is), else the bundled YuNet, whose weights must be present and
    unaltered. Answered once per detector setup and weights folder state, not by loading models on every request."""
    weights = Path(settings.egoblur_weights_dir)
    stamp = weights.stat().st_mtime_ns if weights.exists() else None
    return _available(settings.egoblur_model, str(weights), stamp, settings.egoblur_face_threshold,
                      settings.egoblur_plate_threshold)  # fmt: skip


@functools.lru_cache(maxsize=8)
def _available(model: str, weights: str, stamp: int | None, face: float, plate: float) -> bool:
    del stamp  # part of the cache key only: new or removed weights are seen
    update = {"egoblur_model": model, "egoblur_weights_dir": weights, "egoblur_face_threshold": face,
              "egoblur_plate_threshold": plate}  # fmt: skip
    settings = load_settings().model_copy(update=update)
    try:
        load_detector(settings)
    except AuditorUnavailable:
        return False
    return True


def choose_detector(
    job_dir: Path,
    settings: Settings,
    *,
    call: RemoteCall | None = None,
    commit: Callable[[], None] | None = None,
    tried: list[GpuDetector] | None = None,
) -> tuple[Detector, str | None]:
    """EgoBlur on the Modal GPU when ``SAFECUT_AUDIT_GPU=1`` and it answers pass 1 (fetched here, before the red
    team spends anything); otherwise the local detector (YuNet in the slim API container). Returns the detector and,
    when the GPU was wanted but didn't answer, why (logged, and written to ``raw/audit/gpu.json``)."""
    if not settings.audit_gpu or settings.egoblur_model == "yunet-face":
        return load_detector(settings), None
    try:
        job = load(job_dir / "job.json", Job)
        caller = pipeline.job_caller(job_dir, settings) if (job_dir / pipeline.INTAKE).exists() else Caller.local()
        meter = GpuMeter(settings, pipeline.job_ledger(settings), caller, job.job_id, job_dir / "cost.jsonl")
        handoff = Handoff(Path(settings.audit_gpu_handoff_dir), commit or gpu.modal_commit(settings))
        detector = GpuDetector(job_dir, settings, call or gpu.modal_call(settings), meter, handoff=handoff)
        if tried is not None:
            tried.append(detector)  # its calls are on record even if YuNet ends up auditing
    except ImportError as exc:  # no Modal client here (a local run with SAFECUT_AUDIT_GPU=1)
        return _local(settings, f"no_modal: {exc}")
    except Exception as exc:  # anything else that stops the GPU path being set up: the audit still runs
        return _local(settings, f"setup: {type(exc).__name__}: {exc}"[:300])
    try:
        detector.prefetch()
    except Exception as exc:
        handoff.close()
        reason = str(exc) if isinstance(exc, GpuUnavailable) else f"error: {type(exc).__name__}: {exc}"[:300]
        return _local(settings, reason)
    return detector, None


def _local(settings: Settings, reason: str) -> tuple[Detector, str]:
    fallback = load_detector(settings)
    log.warning("GPU auditor unavailable (%s): auditing with %s on this machine", reason, fallback.model)
    return fallback, reason


def _audit(job_dir: Path, settings: Settings, detector: Detector, redteam: RedTeam | None, client: MetaClient | None,
           *, replay: bool) -> None:  # fmt: skip
    if redteam is None and not replay:
        asyncio.run(_live(job_dir, settings, detector, client))
    else:
        asyncio.run(audit_job(job_dir, detector=detector, redteam=redteam or replay_redteam(job_dir)))


def _record(job_dir: Path, detector: Detector, wanted: bool, fallback: str | None, tried: list[GpuDetector]) -> None:
    """``raw/audit/gpu.json``: whether the GPU auditor was asked for, what ran, why not when it didn't, and every
    GPU call this audit made (priced in ``cost.jsonl``), including those before a fallback."""
    if not wanted:
        return
    record = {"requested": True, "ran": detector.model, "device": device_of(detector), "fallback": fallback,
              "gpu_calls": sum(g.calls for g in tried),
              "gpu_wall_s": round(sum(g.wall_s for g in tried), 3)}  # fmt: skip
    write_atomic(job_dir / GPU_RECORD, json.dumps(record, indent=1))


def run(
    job_dir: Path,
    *,
    replay: bool = False,
    settings: Settings | None = None,
    detector: Detector | None = None,
    redteam: RedTeam | None = None,
    client: MetaClient | None = None,
    gpu_call: RemoteCall | None = None,
    gpu_commit: Callable[[], None] | None = None,
) -> Path:
    """Write ``audit.json`` (and, after patches, ``decisions.json``, ``plan.json`` and the re-rendered video)."""
    settings = settings or load_settings()
    replay = replay or settings.replay
    fallback: str | None = None
    tried: list[GpuDetector] = []
    if detector is None:
        detector, fallback = choose_detector(job_dir, settings, call=gpu_call, commit=gpu_commit, tried=tried)
    try:
        _audit(job_dir, settings, detector, redteam, client, replay=replay)
    finally:
        if isinstance(detector, GpuDetector):
            detector.handoff.close()
    if isinstance(detector, GpuDetector) and detector.failure is not None:
        # The GPU answered pass 1 but not a re-check: those frames are unscanned, so the audit can't pass. It runs
        # again, whole, on the local detector, which is then the one audit.json and the receipt name.
        fallback = str(detector.failure)
        detector = load_detector(settings)
        log.warning("GPU auditor stopped mid-audit (%s): auditing again with %s", fallback, detector.model)
        _audit(job_dir, settings, detector, redteam, client, replay=replay)
    _record(job_dir, detector, settings.audit_gpu and settings.egoblur_model != "yunet-face", fallback, tried)
    return job_dir / AUDIT


__all__ = [
    "AUDIT",
    "GPU_RECORD",
    "RECORDED",
    "SYNTHETIC_TRUTH",
    "NoRedTeam",
    "auditor_available",
    "choose_detector",
    "replay_redteam",
    "run",
]
