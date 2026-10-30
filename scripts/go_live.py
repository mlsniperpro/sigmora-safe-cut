"""``scripts/go-live.sh``: run one clip through the live pipeline and keep every raw response as a fixture.

The job runs in ``jobs/live/<id>/`` (git-ignored) with ``SAFECUT_JOB_USD_CAP`` set to ``--usd-cap``: the client
reserves each call's worst case against it before sending, so the recording can't overspend. When it ends (or
stops at the cap), ``raw/`` and ``cost.jsonl`` are copied to ``fixtures/jobs/<id>/`` with a ``manifest.json`` that
lets ``safecut run <clip> --replay`` find it by the clip's sha256. Every recording made here is ``synthetic: false``.
"""

from __future__ import annotations

import argparse
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
    return re.sub(r"[^a-z0-9_-]+", "-", clip.stem.lower()).strip("-")[:60] or "clip"


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
    """Copy the job's recordings and spend to ``out`` (replacing an earlier recording of the same id)."""
    from safecut import pipeline  # noqa: PLC0415

    raw = job_dir / "raw"
    if out.exists():
        shutil.rmtree(out)
    if raw.is_dir():
        shutil.copytree(raw, out / "raw")
    else:
        (out / "raw").mkdir(parents=True)
    if (job_dir / "cost.jsonl").exists():
        shutil.copyfile(job_dir / "cost.jsonl", out / "cost.jsonl")
    data = manifest(clip, job_dir / "cost.jsonl", sha256=pipeline.sha256_file(clip))
    (out / "raw" / "manifest.json").write_text(json.dumps(data, indent=1) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="go-live.sh", description="Record a live job's raw responses.")
    parser.add_argument("clip", type=Path)
    parser.add_argument("--id", default=None, help="fixtures/jobs/<id>/ (default: from the clip's name)")
    parser.add_argument("--usd-cap", type=float, default=DEFAULT_CAP, help="the job's USD cap (default 3.00)")
    parser.add_argument("--consented", action="store_true", help="a consented hero/dev clip (AGENTS rules 4-5)")
    parser.add_argument("--analyse-only", action="store_true", help="stop after the analysis (prepare … guard)")
    parser.add_argument("--out-root", type=Path, default=ROOT, help="where jobs/ and fixtures/ are (default: repo)")
    args = parser.parse_args(argv)
    root: Path = args.out_root
    clip: Path = args.clip
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

    name = args.id or clip_id(clip)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    job_dir = root / "jobs" / "live" / f"{name}-{stamp}"
    pipeline.create_job(clip, job_dir, mode="live", consented=args.consented)
    status = 0
    try:
        pipeline.analyse(job_dir, replay=False)
        if not args.analyse_only:
            pipeline.approve(job_dir, how="auto_policy")
            pipeline.publish(job_dir, replay=False)
    except StageUnavailable as exc:
        print(f"go-live: stopped: {exc}", file=sys.stderr)
    except Exception as exc:  # report and keep what was recorded: every response so far is evidence
        print(f"go-live: the job failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        status = 1
    out = keep(job_dir, root / "fixtures" / "jobs" / name, clip)
    data = json.loads((out / "raw" / "manifest.json").read_text())
    print(f"go-live: recorded {data['calls']} call(s), ${data['usd']:.4f} measured "
          f"(+${data['usd_estimated']:.4f} possibly billed) into {out}")  # fmt: skip
    return status


if __name__ == "__main__":
    raise SystemExit(main())
