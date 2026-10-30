"""The stage registry: every pipeline stage, the module that runs it, and the job-directory layout they share.

Each stage module exposes ``run(job_dir: Path, *, replay: bool = False) -> Path``, which reads the files earlier
stages wrote in ``job_dir`` and returns the contract file it wrote (ARCHITECTURE §3). The CLI (``safecut <stage>``)
and the pipeline both resolve stages here, so a lane adds a stage by creating its module; nothing else needs to be
registered. A stage whose module doesn't exist yet raises :class:`StageUnavailable` naming the lane that owns it.

Job-directory layout (ARCHITECTURE §3.13):

- ``intake.json``: written when the job is created, before ``prepare`` (who uploaded what, and how it may be used);
- ``source/<name>``: the uploaded clip, exactly one file, under its own name;
- ``raw/``: every Meta response a stage received (live) or reads back (replay);
- the §3 contract files, ``redacted.mp4``, ``receipt.html``;
- ``approval.json``: written when the creator approves the plan, before ``render``;
- ``job_log.jsonl``: one line per stage event, with timings (written by :mod:`safecut.pipeline`).
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

INTAKE = "intake.json"
APPROVAL = "approval.json"
SOURCE_DIR = "source"
RAW_DIR = "raw"
JOB_LOG = "job_log.jsonl"
REDACTED = "redacted.mp4"
RECEIPT_HTML = "receipt.html"

Phase = Literal["analyse", "publish"]
Lane = Literal["SAFECUT-SENSE", "SAFECUT-SAFETY"]


class StageRunner(Protocol):
    def __call__(self, job_dir: Path, *, replay: bool = False) -> Path: ...


class StageUnavailable(RuntimeError):
    """The stage's module isn't in this build yet (its lane hasn't merged it)."""

    def __init__(self, stage: Stage) -> None:
        super().__init__(f"stage {stage.name!r} is not in this build yet: {stage.module} (lane {stage.lane})")
        self.stage = stage


class StageError(RuntimeError):
    """A stage module exists but doesn't honour the registry's interface."""


@dataclass(frozen=True)
class Stage:
    name: str
    #: Dotted module path exposing ``run``.
    module: str
    #: The file the stage writes and returns (a §3 contract file, or ``redacted.mp4`` for render).
    output: str
    #: Files the stage reads; a change in any of them makes a finished stage stale.
    inputs: tuple[str, ...]
    lane: Lane
    phase: Phase
    #: Calls a paid API outside replay, so the job's USD cap is checked before it runs.
    paid: bool
    #: Contract files the stage rewrites besides its output (roles appends the miss loop's tracks to
    #: ``tracks.json``, WP2 step 5): their new digests are logged, so the stage that wrote them first stays fresh.
    also_writes: tuple[str, ...] = ()
    #: The stage enforces the job's cap itself and records the stop in its output (the audit ends
    #: ``blocked_reason: "over_budget"``, so [Run the audit again] works), instead of the pipeline refusing first.
    caps_itself: bool = False

    def runner(self) -> StageRunner:
        """Import the stage's ``run``; raise :class:`StageUnavailable` when its module isn't built yet."""
        try:
            module = importlib.import_module(self.module)
        except ModuleNotFoundError as exc:
            missing = exc.name or ""
            if self.module == missing or self.module.startswith(f"{missing}."):
                raise StageUnavailable(self) from None
            raise
        run = getattr(module, "run", None)
        if not callable(run):
            raise StageError(f"{self.module} has no run(job_dir, *, replay=False)")
        params = inspect.signature(run).parameters
        if "replay" not in params or params["replay"].kind is not inspect.Parameter.KEYWORD_ONLY:
            raise StageError(f"{self.module}.run must take replay as a keyword-only argument")
        return cast(StageRunner, cast(Callable[..., Path], run))


STAGES: tuple[Stage, ...] = (
    Stage("prepare", "safecut.prepare", "job.json", (INTAKE,), "SAFECUT-SENSE", "analyse", paid=False),
    Stage("track", "safecut.track", "tracks.json", ("job.json",), "SAFECUT-SENSE", "analyse", paid=True),
    Stage("transcribe", "safecut.speech", "transcript.json", ("job.json",), "SAFECUT-SENSE", "analyse", paid=True),
    Stage(
        "scene",
        "safecut.scout.scene",
        "scene.json",
        ("job.json", "transcript.json"),
        "SAFECUT-SENSE",
        "analyse",
        paid=True,
    ),
    Stage(
        "roles",
        "safecut.scout.roles",
        "roles.json",
        ("job.json", "tracks.json", "transcript.json", "scene.json"),
        "SAFECUT-SENSE",
        "analyse",
        paid=True,
        also_writes=("tracks.json",),
    ),
    Stage(
        "decide",
        "safecut.decide",
        "decisions.json",
        ("job.json", "tracks.json", "roles.json", "transcript.json", "scene.json"),
        "SAFECUT-SAFETY",
        "analyse",
        paid=False,
    ),
    Stage(
        "guard",
        "safecut.guard",
        "plan.json",
        ("job.json", "tracks.json", "decisions.json"),
        "SAFECUT-SAFETY",
        "analyse",
        paid=False,
    ),
    Stage(
        "render",
        "safecut.render",
        REDACTED,
        ("job.json", "plan.json", APPROVAL),
        "SAFECUT-SAFETY",
        "publish",
        paid=False,
    ),
    Stage(
        "audit",
        "safecut.audit",
        "audit.json",
        ("job.json", "decisions.json", "plan.json", REDACTED),
        "SAFECUT-SAFETY",
        "publish",
        paid=True,
        caps_itself=True,
    ),
    Stage(
        "receipt",
        "safecut.receipt",
        "receipt.json",
        ("job.json", "decisions.json", "audit.json", APPROVAL),
        "SAFECUT-SAFETY",
        "publish",
        paid=False,
    ),
)

BY_NAME: dict[str, Stage] = {stage.name: stage for stage in STAGES}


def stage(name: str) -> Stage:
    try:
        return BY_NAME[name]
    except KeyError:
        raise KeyError(f"unknown stage {name!r}; known: {', '.join(BY_NAME)}") from None


def phase(name: Phase) -> tuple[Stage, ...]:
    return tuple(s for s in STAGES if s.phase == name)
