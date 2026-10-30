"""Stage orchestration over one job directory (WP5 step 1).

``analyse`` runs prepare → track → transcribe → scene → roles → decide → guard and stops for review. The creator
(or ``--auto-approve-policy``) writes ``approval.json`` with :func:`approve`, and ``publish`` runs render → audit →
receipt. Every stage is idempotent: a stage whose output and inputs match its last ``done`` line in
``job_log.jsonl`` is skipped, so a crashed or restarted job resumes where it stopped. Before each paid stage the
job's Meta spend in ``cost.jsonl`` is checked against ``SAFECUT_JOB_USD_CAP``; in replay the network is blocked.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from safecut import netguard
from safecut.config import CodeKind, Settings, load_settings
from safecut.contracts import (
    JOB_FILES,
    Approval,
    ContractError,
    Intake,
    dump,
    load,
    measured_usd,
    read_cost_lines,
)
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.stages import (
    APPROVAL,
    INTAKE,
    JOB_LOG,
    RAW_DIR,
    REDACTED,
    SOURCE_DIR,
    STAGES,
    Phase,
    Stage,
    StageError,
    phase,
)

#: Where recorded jobs live (``fixtures/jobs/<id>/raw/``, PRE-A §12; written by ``scripts/go-live.sh``).
FIXTURE_JOBS = Path(__file__).resolve().parent.parent / "fixtures" / "jobs"
#: A recorded job's manifest: ``{"source_sha256": "…", "synthetic": bool}``.
RAW_MANIFEST = "manifest.json"

Event = Literal["start", "done", "skipped", "failed"]


class PipelineError(RuntimeError):
    """The job can't continue; the message says why and what to do."""


class JobCapReached(PipelineError):
    """The job's measured Meta spend reached ``SAFECUT_JOB_USD_CAP`` before a paid stage."""


class NotApproved(PipelineError):
    """``publish`` was asked for before the creator approved the current ``decisions.json``."""


class StageOutputInvalid(PipelineError):
    """A stage returned, but the file it wrote doesn't validate against its contract."""


@dataclass(frozen=True)
class StageResult:
    stage: str
    event: Literal["done", "skipped"]
    output: Path
    elapsed_s: float


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_clip(job_dir: Path) -> Path:
    """The uploaded clip: the single file in ``source/``."""
    folder = job_dir / SOURCE_DIR
    files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    if len(files) != 1:
        raise PipelineError(f"{folder}: expected exactly one source clip, found {len(files)}")
    return files[0]


def create_job(
    clip: Path,
    job_dir: Path,
    *,
    mode: Literal["live", "replay"] = "live",
    consented: bool = False,
    code_kind: CodeKind | None = None,
    created_at: datetime | None = None,
) -> Intake:
    """Make ``job_dir`` (it must not hold a job already), copy the clip into ``source/`` and write ``intake.json``."""
    if not clip.is_file():
        raise PipelineError(f"{clip}: no such clip")
    if (job_dir / INTAKE).exists():
        raise PipelineError(f"{job_dir} already holds a job; pick a new --out directory")
    (job_dir / SOURCE_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, job_dir / SOURCE_DIR / clip.name)
    intake = Intake(
        source=clip.name,
        created_at=created_at or datetime.now(UTC),
        consented=consented,
        mode=mode,
        code_kind=code_kind,
    )
    dump(intake, job_dir / INTAKE)
    return intake


def find_recording(clip_sha256: str, root: Path = FIXTURE_JOBS) -> Path | None:
    """The recorded job (``<root>/<id>/``) whose ``raw/manifest.json`` names this clip's sha256, if any."""
    if not root.is_dir():
        return None
    for manifest in sorted(root.glob(f"*/{RAW_DIR}/{RAW_MANIFEST}")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("source_sha256") == clip_sha256:  # pyright: ignore[reportUnknownMemberType] -- untyped JSON, compared by value
            return manifest.parent.parent
    return None


def recording_is_synthetic(job_dir: Path) -> bool:
    """Whether the job replays synthetic recordings (``raw/manifest.json`` ``synthetic``; unknown counts as yes,
    so nothing unlabelled is ever presented as a real run)."""
    manifest = job_dir / RAW_DIR / RAW_MANIFEST
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not (isinstance(data, dict) and data.get("synthetic") is False)  # pyright: ignore[reportUnknownMemberType] -- untyped JSON


def attach_recording(job_dir: Path, recording: Path) -> None:
    """Copy a recorded job's ``raw/`` responses into ``job_dir`` for replay."""
    raw = recording / RAW_DIR
    if not raw.is_dir():
        raise PipelineError(f"{recording}: no {RAW_DIR}/ directory of recorded responses")
    shutil.copytree(raw, job_dir / RAW_DIR, dirs_exist_ok=True)


# ---------------------------------------------------------------------------
# job_log.jsonl
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _log(job_dir: Path, **fields: Any) -> None:
    line = json.dumps({"ts": _now(), "job_id": job_dir.name, **fields}, sort_keys=True)
    with (job_dir / JOB_LOG).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_log(job_dir: Path) -> Iterator[dict[str, Any]]:
    path = job_dir / JOB_LOG
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue  # a torn last line from a crash: the stage reruns, which is the safe reading
        if isinstance(entry, dict):
            yield entry  # pyright: ignore[reportUnknownArgumentType] -- json objects are dict[str, Any]


def _digests(job_dir: Path, names: Iterable[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        path = job_dir / name
        out[name] = sha256_file(path) if path.is_file() else None
    return out


def _inputs(job_dir: Path, stage: Stage) -> dict[str, str | None]:
    digests = _digests(job_dir, stage.inputs)
    if stage.name == "prepare" and (job_dir / SOURCE_DIR).is_dir():
        clip = source_clip(job_dir)
        digests[f"{SOURCE_DIR}/{clip.name}"] = sha256_file(clip)
    return digests


def is_fresh(job_dir: Path, stage: Stage) -> bool:
    """The stage's last ``done`` line still describes its output and inputs on disk."""
    last: dict[str, Any] | None = None
    for entry in read_log(job_dir):
        if entry.get("stage") == stage.name and entry.get("event") in ("done", "failed", "start"):
            last = entry
    if last is None or last.get("event") != "done":
        return False
    output = job_dir / stage.output
    if not output.is_file():
        return False
    return last.get("output_sha256") == sha256_file(output) and last.get("inputs") == _inputs(job_dir, stage)


# ---------------------------------------------------------------------------
# Running stages
# ---------------------------------------------------------------------------


def job_spend(job_dir: Path) -> float:
    """Meta USD this job may have been billed: measured plus estimated lines (the cap counts both)."""
    path = job_dir / "cost.jsonl"
    if not path.exists():
        return 0.0
    measured, estimated = measured_usd(list(read_cost_lines(path)))
    return measured + estimated


def check_output(job_dir: Path, stage: Stage, output: Path) -> None:
    if output.resolve() != (job_dir / stage.output).resolve():
        raise StageOutputInvalid(f"{stage.name} returned {output}, expected {job_dir / stage.output}")
    if not output.is_file():
        raise StageOutputInvalid(f"{stage.name} did not write {stage.output}")
    if stage.output in JOB_FILES:
        try:
            load(output)
        except ContractError as exc:
            raise StageOutputInvalid(f"{stage.name}: {exc}") from exc


def run_stage(
    job_dir: Path, stage: Stage, *, replay: bool, settings: Settings | None = None, force: bool = False
) -> StageResult:
    """Run one stage unless it is already fresh; validate what it wrote and log it."""
    output = job_dir / stage.output
    if not force and is_fresh(job_dir, stage):
        _log(job_dir, stage=stage.name, event="skipped", replay=replay)
        return StageResult(stage.name, "skipped", output, 0.0)
    runner = stage.runner()
    if stage.paid and not replay:
        cap = (settings or load_settings()).job_usd_cap
        spent = job_spend(job_dir)
        if spent >= cap:
            _log(job_dir, stage=stage.name, event="failed", error="job_usd_cap", spent_usd=round(spent, 6))
            raise JobCapReached(f"job spend ${spent:.4f} reached SAFECUT_JOB_USD_CAP ${cap:.2f} before {stage.name}")
    _log(job_dir, stage=stage.name, event="start", replay=replay)
    started = time.monotonic()
    try:
        if replay:
            with netguard.blocked():
                written = runner(job_dir, replay=True)
        else:
            written = runner(job_dir, replay=False)
        check_output(job_dir, stage, Path(written))
    except BaseException as exc:
        _log(
            job_dir,
            stage=stage.name,
            event="failed",
            replay=replay,
            error=f"{type(exc).__name__}: {exc}"[:500],
            elapsed_s=round(time.monotonic() - started, 3),
        )
        raise
    elapsed = round(time.monotonic() - started, 3)
    _log(
        job_dir,
        stage=stage.name,
        event="done",
        replay=replay,
        elapsed_s=elapsed,
        output_sha256=sha256_file(output),
        inputs=_inputs(job_dir, stage),
    )
    return StageResult(stage.name, "done", output, elapsed)


OnStage = Callable[[Stage], None]


def _run_phase(
    job_dir: Path,
    name: Phase,
    *,
    replay: bool,
    settings: Settings | None,
    until: str | None = None,
    on_stage: OnStage | None = None,
) -> list[StageResult]:
    stages = phase(name)
    if until is not None and until not in {s.name for s in stages}:
        raise StageError(f"stage {until!r} is not in the {name} phase")
    results: list[StageResult] = []
    for stage in stages:
        if on_stage is not None and not is_fresh(job_dir, stage):
            on_stage(stage)
        results.append(run_stage(job_dir, stage, replay=replay, settings=settings))
        if stage.name == until:
            break
    return results


def analyse(
    job_dir: Path,
    *,
    replay: bool,
    settings: Settings | None = None,
    until: str | None = None,
    on_stage: OnStage | None = None,
) -> list[StageResult]:
    """prepare … guard (or up to ``until``); then the job waits for review. ``on_stage`` hears each stage that
    is about to run (not the fresh ones it skips)."""
    if not (job_dir / INTAKE).is_file():
        raise PipelineError(f"{job_dir}: no {INTAKE}; create the job first")
    return _run_phase(job_dir, "analyse", replay=replay, settings=settings, until=until, on_stage=on_stage)


def approve(job_dir: Path, *, how: Literal["review", "auto_policy"], at: datetime | None = None) -> Approval:
    """Record the creator's approval of the current ``decisions.json`` (and its plan)."""
    decisions = job_dir / "decisions.json"
    if not (job_dir / "plan.json").is_file() or not decisions.is_file():
        raise PipelineError("nothing to approve yet: run the analysis (prepare … guard) first")
    approval = Approval(approved_at=at or datetime.now(UTC), how=how, decisions_sha256=sha256_file(decisions))
    dump(approval, job_dir / APPROVAL)
    return approval


def check_approval(job_dir: Path) -> Approval:
    path = job_dir / APPROVAL
    if not path.is_file():
        raise NotApproved("the plan has not been approved: review it, or pass --auto-approve-policy")
    approval = load(path, Approval)
    if approval.decisions_sha256 != sha256_file(job_dir / "decisions.json"):
        raise NotApproved("decisions.json changed after approval: approve the current decisions again")
    return approval


def publish(
    job_dir: Path, *, replay: bool, settings: Settings | None = None, on_stage: OnStage | None = None
) -> list[StageResult]:
    """render → audit → receipt, only on an approved plan."""
    check_approval(job_dir)
    return _run_phase(job_dir, "publish", replay=replay, settings=settings, on_stage=on_stage)


def job_ledger(settings: Settings) -> LocalLedger:
    """The service's one spend ledger (``<SAFECUT_JOBS_DIR>/ledger.sqlite``), shared by every job's stages."""
    root = Path(settings.jobs_dir)
    root.mkdir(parents=True, exist_ok=True)
    return LocalLedger(root / "ledger.sqlite")


def job_caller(job_dir: Path, settings: Settings) -> Caller:
    """Whose caps a job's Meta calls count against, from ``intake.json`` (UI-SPEC §8 request 20): judge,
    public and service callers share the daily cap; pilot codes have their own cap plus the pilot pool;
    recording and owner codes their own cap; a local run with no code only the job cap."""
    intake = load(job_dir / INTAKE, Intake)
    kind, cid = intake.code_kind, intake.code_id
    if kind is None:
        return Caller.local("owner")
    if kind in ("judge", "public", "service", "system"):
        return Caller.daily(settings, kind, cid)
    if kind == "eval":
        return Caller.local("eval")
    cap = next((c.cap_usd for c in settings.access_codes if code_id(c.code.get_secret_value()) == cid), None)
    limits: list[CapLimit] = [CapLimit("code", f"code:{cid}", cap or 0.0)]
    if kind == "pilot":
        limits.append(CapLimit("pilot_pool", "pool:pilot", settings.pilot_pool_usd))
    return Caller(code_kind=kind, code_id=cid, limits=tuple(limits))


def code_id(code: str) -> str:
    """A stable, non-secret ID for an access code: job state, intake and cap keys never hold the code itself."""
    return "c_" + hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def status(job_dir: Path) -> Literal["new", "analysing", "review", "publishing", "done"]:
    """Where the job stands, from the files on disk."""
    if (job_dir / "receipt.json").is_file():
        return "done"
    if (job_dir / APPROVAL).is_file() and (job_dir / "plan.json").is_file():
        return "publishing"
    if (job_dir / "plan.json").is_file():
        return "review"
    if any((job_dir / s.output).is_file() for s in STAGES):
        return "analysing"
    return "new"


__all__ = [
    "FIXTURE_JOBS",
    "REDACTED",
    "JobCapReached",
    "NotApproved",
    "PipelineError",
    "StageOutputInvalid",
    "StageResult",
    "analyse",
    "approve",
    "attach_recording",
    "code_id",
    "create_job",
    "find_recording",
    "job_caller",
    "job_ledger",
    "publish",
    "recording_is_synthetic",
    "run_stage",
    "status",
]
