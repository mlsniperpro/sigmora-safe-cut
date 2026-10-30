"""``scripts/go-live.sh``: run one clip through the live pipeline and keep every raw response as a fixture.

The job runs in ``jobs/live/<id>/`` (git-ignored) with ``SAFECUT_JOB_USD_CAP`` set to ``--usd-cap``: the client
reserves each call's worst case against it before sending, so the recording can't overspend. When it ends (or
stops at the cap), ``raw/`` and ``cost.jsonl`` are copied to ``fixtures/jobs/<id>/`` with a ``manifest.json`` that
lets ``safecut run <clip> --replay`` find it by the clip's sha256. Every recording made here is ``synthetic: false``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_CLIPS = ROOT / "fixtures" / "clips"
DEFAULT_CAP = 3.00


def clip_id(clip: Path) -> str:
    """A fixture directory name: lowercase ``[a-z0-9_-]`` only, never empty, ``.`` or ``..``."""
    return re.sub(r"[^a-z0-9_-]+", "-", clip.name.removesuffix(clip.suffix).lower()).strip("-")[:60] or "clip"


def fixture_id(given: str) -> str:
    """An ``--id`` as a fixture directory name: like :func:`clip_id`, but a dot is part of the id (``v1.5``)."""
    return re.sub(r"[^a-z0-9_-]+", "-", given.lower()).strip("-")[:60] or "clip"


def allowed(clip: Path, consented: bool) -> bool:
    """Synthetic clips from ``fixtures/clips/``, or a clip the owner marks consented (AGENTS rules 4–5)."""
    return consented or clip.resolve().parent == SYNTHETIC_CLIPS.resolve()


def manifest(clip: Path, cost_path: Path, *, sha256: str) -> dict[str, object]:
    from safecut.contracts import measured_usd, read_cost_lines  # noqa: PLC0415 -- after the env is set

    lines = list(read_cost_lines(cost_path)) if cost_path.exists() else []
    usd, estimated = measured_usd(lines)
    try:
        source = str(clip.resolve().relative_to(ROOT))
    except ValueError:
        source = clip.name
    return {
        "demo": False,
        "synthetic": False,
        "source": source,
        "source_sha256": sha256,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "usd": round(usd, 6),
        "usd_estimated": round(estimated, 6),
        "calls": len(lines),
    }


def keep(job_dir: Path, out: Path, clip: Path) -> Path:
    """Copy the job's recordings and spend to ``out``: built beside it first, then swapped in, so a failure never
    leaves a half-written or emptied fixture."""
    from safecut import pipeline  # noqa: PLC0415

    # Staging and the old copy live outside fixtures/jobs/, so a crash mid-swap never leaves a second manifest
    # there for find_recording to match.
    work = out.parent.parent / ".go-live"
    staging, old = work / f"{out.name}.staging", work / f"{out.name}.old"
    out.parent.mkdir(parents=True, exist_ok=True)
    if old.exists():  # a run killed mid-swap: put the earlier recording back first
        if out.exists():
            shutil.rmtree(old)
        else:
            old.replace(out)
    if staging.exists():
        shutil.rmtree(staging)
    raw = job_dir / "raw"
    if raw.is_dir():
        shutil.copytree(raw, staging / "raw")
    else:
        (staging / "raw").mkdir(parents=True)
    if (job_dir / "cost.jsonl").exists():
        shutil.copyfile(job_dir / "cost.jsonl", staging / "cost.jsonl")
    data = manifest(clip, job_dir / "cost.jsonl", sha256=pipeline.sha256_file(clip))
    (staging / "raw" / "manifest.json").write_text(json.dumps(data, indent=1) + "\n")
    if out.exists():
        out.replace(old)  # a rename: the earlier recording is never deleted before the new one is in place
    staging.replace(out)
    if old.exists():
        shutil.rmtree(old)
    with contextlib.suppress(OSError):  # another id's run may still have files there
        work.rmdir()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="go-live.sh", description="Record a live job's raw responses.")
    parser.add_argument("clip", type=Path)
    parser.add_argument("--id", default=None, help="fixtures/jobs/<id>/ (default: from the clip's name)")
    parser.add_argument("--usd-cap", type=float, default=DEFAULT_CAP, help="the job's USD cap (default 3.00)")
    parser.add_argument("--consented", action="store_true", help="a consented hero/dev clip (AGENTS rules 4-5)")
    parser.add_argument("--analyse-only", action="store_true", help="stop after the analysis (prepare … guard)")
    parser.add_argument("--replace", action="store_true", help="replace an earlier recording with the same id")
    parser.add_argument("--out-root", type=Path, default=ROOT, help="where jobs/ and fixtures/ are (default: repo)")
    args = parser.parse_args(argv)
    # go-live.sh runs from the repo root; relative paths are the caller's, from where they ran it.
    caller = Path(os.environ.get("GO_LIVE_CWD") or Path.cwd())
    root: Path = caller / args.out_root
    clip: Path = caller / args.clip
    if not clip.is_file():
        print(f"go-live: no such clip: {clip}", file=sys.stderr)
        return 2
    if not allowed(clip, args.consented):
        print("go-live: only synthetic clips (fixtures/clips/) or consented clips (--consented) may be recorded",
              file=sys.stderr)  # fmt: skip
        return 2
    if not 0 < args.usd_cap <= 15:
        print("go-live: --usd-cap must be between 0 and 15 USD", file=sys.stderr)
        return 2
    os.environ["SAFECUT_JOB_USD_CAP"] = f"{args.usd_cap:.2f}"
    os.environ["SAFECUT_REPLAY"] = "false"
    from safecut import pipeline  # noqa: PLC0415 -- settings read the env set above
    from safecut.stages import StageUnavailable  # noqa: PLC0415

    name = fixture_id(args.id) if args.id else clip_id(clip)  # never a path: only [a-z0-9_-]
    # A run killed mid-swap leaves the earlier recording aside in fixtures/.go-live/: it still counts as one.
    aside = root / "fixtures" / ".go-live" / f"{name}.old"
    if ((root / "fixtures" / "jobs" / name).exists() or aside.exists()) and not args.replace:
        print(f"go-live: fixtures/jobs/{name} already holds a recording; pass --replace or another --id",
              file=sys.stderr)  # fmt: skip
        return 2
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    job_dir = root / "jobs" / "live" / f"{name}-{stamp}"
    pipeline.create_job(clip, job_dir, mode="live", consented=args.consented)
    status, stopped = 0, False
    try:
        pipeline.analyse(job_dir, replay=False)
        if not args.analyse_only:
            pipeline.approve(job_dir, how="auto_policy")
            pipeline.publish(job_dir, replay=False)
    except StageUnavailable as exc:
        print(f"go-live: stopped: {exc}", file=sys.stderr)
        stopped = True
    except Exception as exc:  # report and keep what was recorded: every response so far is evidence
        print(f"go-live: the job failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        status = 1
    out = root / "fixtures" / "jobs" / name
    recorded = (job_dir / "raw").is_dir() and any((job_dir / "raw").rglob("*.json"))
    if not recorded or ((out.exists() or aside.exists()) and (status or stopped)):
        # A run that recorded nothing, or an unfinished one, never replaces an earlier (paid-for) recording.
        kept = out if out.exists() else aside if aside.exists() else "nothing"
        print(f"go-live: kept {kept}; this run's responses stay in {job_dir}",
              file=sys.stderr)  # fmt: skip
        return status or 1
    out = keep(job_dir, out, clip)
    data = json.loads((out / "raw" / "manifest.json").read_text())
    print(f"go-live: recorded {data['calls']} call(s), ${data['usd']:.4f} measured "
          f"(+${data['usd_estimated']:.4f} possibly billed) into {out}")  # fmt: skip
    return status or (1 if stopped else 0)  # a stopped run is unfinished: never reported as success


if __name__ == "__main__":
    raise SystemExit(main())
