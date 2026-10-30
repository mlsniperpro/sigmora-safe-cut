"""Run one eval variant on one split and commit-ready results (WP7 step 4, EVAL.md §4).

    uv run python eval/run.py --split dev --variant full --replay      a run on recorded responses (no spend)
    uv run python eval/run.py --split test --variant full              the owner's Mac only; ≤ 3 runs
    uv run python eval/run.py freeze --split test                      hash the clip list and labels

Splits: hero, dev, public, test (``eval/splits/<split>.json``). Variants: blur_all, egoblur, detector_only,
muse_no_track, full, no_audit. Each run writes ``eval/results/<run-id>/``: ``metrics.json``, ``per_clip.csv``,
``cost.json``, ``config.json`` (model IDs, git SHA, split hash) and ``worst.json`` (the worst five exposures). The
``test`` split runs live only, refuses to run when its labels no longer match ``eval/splits/test.sha256``, and
stops after 3 runs (a run is counted when it starts). No split's results hold frames or images.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # run as a script (`python eval/run.py`): make the repo's packages importable
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, ConfigDict, Field  # noqa: E402 -- after the sys.path line above, on purpose

from eval.labels import ClipLabels, LabelError, load_labels  # noqa: E402 -- after the sys.path line above, on purpose
from eval.metrics import JobScore, score_job, summarize  # noqa: E402 -- after the sys.path line above, on purpose
from eval.variants import VARIANTS, Variant, VariantUnavailable, preflight, run_variant  # noqa: E402 -- as above
from safecut import netguard, pipeline  # noqa: E402 -- after the sys.path line above, on purpose
from safecut.api.views import models_recorded  # noqa: E402 -- after the sys.path line above, on purpose
from safecut.config import ConfigError, load_settings  # noqa: E402 -- after the sys.path line above, on purpose

SPLITS = ("hero", "dev", "public", "test")
Split = Literal["hero", "dev", "public", "test"]
SPLIT_DIR = ROOT / "eval" / "splits"
RESULTS = ROOT / "eval" / "results"
TEST_RUN_LIMIT = 3


#: A live run's ceiling across all its clips (the whole event has $150 of Meta credits, AGENTS rule 10).
DEFAULT_MAX_USD = 15.0


class EvalError(RuntimeError):
    """The run can't go ahead; the message says why."""


class ClipEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip: str = Field(min_length=1)
    labels: str = Field(min_length=1)
    #: A recorded job (``fixtures/jobs/<id>/``) for ``--replay``; repo-relative.
    recording: str | None = None


class SplitFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    split: Split
    clips: list[ClipEntry]


def load_split(split: Split, root: Path = SPLIT_DIR) -> SplitFile:
    path = root / f"{split}.json"
    if not path.is_file():
        raise EvalError(f"split {split!r} has no clips yet (eval/splits/{split}.json is missing; see BLOCKED.md)")
    data = SplitFile.model_validate_json(path.read_bytes())
    if data.split != split:
        raise EvalError(f"{path.name} says split {data.split!r}")
    if not data.clips:
        raise EvalError(f"split {split!r} lists no clips")
    return data


def split_hash(split: SplitFile, base: Path = ROOT) -> str:
    """sha256 over each clip's and labels file's own sha256, in order: changes when any clip or label changes."""
    digest = hashlib.sha256()
    for entry in split.clips:
        for rel in (entry.clip, entry.labels):
            path = base / rel
            if not path.is_file():
                raise EvalError(f"{rel} is missing")
            digest.update(f"{rel}\n{pipeline.sha256_file(path)}\n".encode())
    return digest.hexdigest()


def freeze(split: Split, root: Path = SPLIT_DIR, base: Path = ROOT) -> str:
    value = split_hash(load_split(split, root), base)
    (root / f"{split}.sha256").write_text(value + "\n", encoding="utf-8")
    return value


class RunCounter(BaseModel):
    """``eval/splits/test.runs.json``: the run IDs already made on the test split (committed with each run)."""

    model_config = ConfigDict(extra="forbid")
    runs: list[str] = Field(default_factory=list[str])


def runs_made(root: Path = SPLIT_DIR) -> list[str]:
    counter = root / "test.runs.json"
    return RunCounter.model_validate_json(counter.read_bytes()).runs if counter.is_file() else []


def check_test_split(split: SplitFile, root: Path = SPLIT_DIR, base: Path = ROOT) -> int:
    """The frozen test split, unchanged, with runs left; returns the number of runs already made."""
    frozen = root / "test.sha256"
    if not frozen.is_file():
        raise EvalError("the test split isn't frozen: run `eval/run.py freeze --split test` first")
    if frozen.read_text(encoding="utf-8").strip() != split_hash(split, base):
        raise EvalError("the test split's clips or labels changed since it was frozen (eval/splits/test.sha256)")
    runs = runs_made(root)
    if len(runs) >= TEST_RUN_LIMIT:
        raise EvalError(f"the test split has had its {TEST_RUN_LIMIT} runs ({', '.join(runs)})")
    return len(runs)


def git_sha() -> str:
    """HEAD's sha, with ``-dirty`` when the code differs from it (a changed or untracked file outside the results
    themselves), so a run says whether the committed code produced it. No git, no sha: ``unknown-dirty``."""
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S607 -- git from PATH
    sha = proc.stdout.strip()
    if proc.returncode != 0 or not sha:
        return "unknown-dirty"
    paths = [".", ":(exclude)eval/results", ":(exclude)eval/RESULTS.md", ":(exclude)eval/splits/test.runs.json"]
    status = subprocess.run(  # noqa: S603 -- a fixed argv of constants
        ["git", "status", "--porcelain", "--untracked-files=normal", "--", *paths],  # noqa: S607 -- git from PATH
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return f"{sha}-dirty" if status.returncode != 0 or status.stdout.strip() else sha


def now_id(now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}"


def refuse_early(split: SplitFile, variant: Variant, *, replay: bool, base: Path) -> tuple[str, dict[str, ClipLabels]]:
    """Everything that can refuse a run, checked before a test run is counted or anything is called: a refusal
    never costs one of the test split's 3 runs, while a run that crashes halfway (after paid calls) still does.
    Returns the commit and every clip's loaded labels."""
    sha = git_sha()
    if not replay and sha.endswith("-dirty"):
        # A live run costs credits (and a test run one of its 3): only committed code can back a reported number.
        raise EvalError("the working tree has uncommitted changes; commit them before a live run")
    preflight(variant)
    if not replay and variant != "egoblur" and load_settings().model_api_key is None:
        # The key is read by the first paid stage; checked here, a forgotten export never costs a test run.
        raise EvalError("MODEL_API_KEY isn't set: a live run needs it (export it in this shell first)")
    return sha, {entry.labels: load_labels(base / entry.labels) for entry in split.clips}


def run(
    split_name: Split,
    variant: Variant,
    *,
    replay: bool,
    out: Path = RESULTS,
    now: datetime | None = None,
    splits: Path = SPLIT_DIR,
    base: Path = ROOT,
    max_usd: float = DEFAULT_MAX_USD,
) -> Path:
    """Run ``variant`` on every clip of the split; return the run directory. A live run stops before the next
    clip once its Meta spend reaches ``max_usd`` (each job also keeps its own ``SAFECUT_JOB_USD_CAP``)."""
    split = load_split(split_name, splits)
    now = now or datetime.now(UTC)
    sha, labels = refuse_early(split, variant, replay=replay, base=base)
    if split_name == "test":
        if replay:
            raise EvalError("the test split is reported from live runs only")
        check_test_split(split, splits, base)
        counter = RunCounter(runs=[*runs_made(splits), f"{now_id(now)}-test-{variant}"])
        (splits / "test.runs.json").write_text(counter.model_dump_json(indent=1) + "\n", encoding="utf-8")
    run_id = f"{now_id(now)}-{split_name}-{variant}-{sha[:7]}"
    scores: list[JobScore] = []
    detail: dict[str, str] = {}
    synthetic = False
    settings = load_settings()
    ran: dict[str, set[str]] = {}
    work = Path(tempfile.mkdtemp(prefix=f"eval-{run_id}-"))
    try:
        spent = 0.0
        for n, entry in enumerate(split.clips):
            if not replay and spent >= max_usd:
                raise EvalError(f"the run's Meta spend ${spent:.2f} reached --max-usd ${max_usd:.2f} after {n} clip(s)")
            clip = base / entry.clip
            job_dir = work / f"j_{n:03d}_{re.sub(r'[^A-Za-z0-9_-]', '_', clip.stem)[:40]}"
            pipeline.create_job(
                clip,
                job_dir,
                mode="replay" if replay else "live",
                consented=split_name in ("hero", "dev"),
                code_kind="eval",
            )
            if replay:
                if entry.recording is None:
                    raise EvalError(f"{entry.clip} has no recording to replay")
                pipeline.attach_recording(job_dir, base / entry.recording)
                synthetic = synthetic or pipeline.recording_is_synthetic(job_dir)
            result = run_variant(variant, job_dir, replay=replay)
            detail.update(result.detail)
            recorded = models_recorded(job_dir, settings)
            if "detector" in result.detail:  # the egoblur baseline's detector, which writes no audit.json
                recorded["auditor"] = result.detail["detector"]
            if "keyframe_boxes" in result.detail:  # muse_no_track: Muse Spark's keyframe boxes, no tracks file
                recorded["keyframe_boxes"] = result.detail["keyframe_boxes"]
            for role, model in recorded.items():
                ran.setdefault(role, set()).add(model)
            scores.append(score_job(job_dir, labels[entry.labels], result.regions))
            spent += pipeline.job_spend(job_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    run_dir = out / run_id
    run_dir.mkdir(parents=True)
    write_run(
        run_dir,
        scores,
        config={
            "run_id": run_id,
            "split": split_name,
            "variant": variant,
            "replay": replay,
            "synthetic": synthetic,
            "git_sha": sha,
            "split_hash": split_hash(split, base),
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "clips": [e.clip for e in split.clips],
            # What each job's own files say ran (the audit's detector, the transcript's source…), never the
            # configured defaults; a synthetic replay ran no model at all and says so.
            "models": {role: " / ".join(sorted(names)) for role, names in sorted(ran.items())},
            "models_note": "synthetic recordings replayed: no Meta model was called" if synthetic else None,
            "detail": detail,
        },
    )
    return run_dir


def write_run(run_dir: Path, scores: list[JobScore], *, config: dict[str, Any]) -> None:
    summary = summarize(scores)
    (run_dir / "config.json").write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8")
    metrics = {
        "run_id": config["run_id"],
        "split": config["split"],
        "variant": config["variant"],
        "synthetic": config["synthetic"],
        **asdict(summary),
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with (run_dir / "per_clip.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "clip",
                "entity",
                "category",
                "should_hide",
                "visible_frames",
                "frames_covered_95",
                "frames_exposed",
                "leak_bursts",
                "frames_hidden",
                "mean_coverage",
            ]
        )
        for score in scores:
            for e in score.entities:
                writer.writerow(
                    [
                        score.clip,
                        e.id,
                        e.category,
                        e.should_hide,
                        e.visible_frames,
                        e.frames_covered_95,
                        e.frames_exposed,
                        e.leak_bursts,
                        e.frames_hidden,
                        e.mean_coverage,
                    ]
                )
    cost = {
        s.clip: {"usd": s.cost_usd, "usd_estimated": s.cost_usd_estimated, "minutes": round(s.minutes, 6)}
        for s in scores
    }
    (run_dir / "cost.json").write_text(json.dumps(cost, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    worst = sorted(
        (
            {
                "clip": s.clip,
                "entity": e.id,
                "category": e.category,
                "frame": frame,
                "time_s": round(frame / s.fps, 3),
                "coverage": round(value, 4),
            }
            for s in scores
            for e in s.entities
            if e.should_hide
            for frame, value in e.worst
            if value < 0.95
        ),
        key=lambda w: (cast(float, w["coverage"]), str(w["clip"]), cast(int, w["frame"])),
    )[:5]
    (run_dir / "worst.json").write_text(json.dumps(worst, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval/run.py",
        description="Run an eval variant on a split (EVAL.md §4).",
        epilog="Splits: hero, dev, public, test. Variants: " + ", ".join(VARIANTS) + ". "
        "`freeze --split test` hashes the test split's clips and labels.",
    )
    parser.add_argument("command", nargs="?", choices=("run", "freeze"), default="run")
    parser.add_argument("--split", choices=SPLITS, required=True, help="hero | dev | public | test")
    parser.add_argument("--variant", choices=VARIANTS, help="which pipeline variant (run only)")
    parser.add_argument("--replay", action="store_true", help="replay recorded responses; nothing is sent to Meta")
    parser.add_argument(
        "--max-usd", type=float, default=DEFAULT_MAX_USD, help="a live run stops once its Meta spend reaches this"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            print(f"froze {args.split}: {freeze(args.split)}")
            return 0
        if args.variant is None:
            parser.error("--variant is required")
        if args.replay:
            netguard.block()  # a replay run never reaches the network, in any thread
        run_dir = run(args.split, args.variant, replay=args.replay, max_usd=args.max_usd)
    except (EvalError, VariantUnavailable, pipeline.PipelineError, LabelError, ConfigError) as exc:
        print(f"eval: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
