"""The Python half of ``scripts/entry-check.sh``: one function per E-line that needs more than a shell command.

``uv run python -m scripts.entry_check <E-line>`` prints progress, then a last line ``OK`` or ``FAIL <reason>``,
and exits 0 or 1. The E-lines and their wording are in ``.agent/ENTRY-DONE.md``; checks may be added or made
stricter, never removed or weakened.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from imageio_ffmpeg import get_ffmpeg_exe

from safecut import pipeline
from safecut.contracts import Audit, Receipt, load, validate_job_dir
from safecut.stages import REDACTED, STAGES

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / ".venv" / "bin"
FIXTURE_JOBS = ROOT / "fixtures" / "jobs"


class CheckFailed(Exception):
    """One E-line failed; the message is the reason printed after ``FAIL``."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def sh(
    args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, timeout: float = 600, check: bool = False
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(  # noqa: S603 -- fixed argv lists built in this file, no shell
        args,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["(no output)"]
        raise CheckFailed(f"`{' '.join(args[:4])}` exited {proc.returncode}: {tail[0][:200]}")
    return proc


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:240] if lines else "(no output)"


def demo_recording() -> tuple[Path, dict[str, Any]]:
    """The recorded demo job: ``fixtures/jobs/<id>/raw/manifest.json`` with ``"demo": true``."""
    found: list[tuple[Path, dict[str, Any]]] = []
    for manifest in sorted(FIXTURE_JOBS.glob("*/raw/manifest.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("demo") is True:  # pyright: ignore[reportUnknownMemberType] -- untyped JSON
            found.append((manifest.parent.parent, dict(data)))  # pyright: ignore[reportUnknownArgumentType] -- untyped JSON
    if not found:
        raise CheckFailed(
            'no demo job recorded: fixtures/jobs/<id>/raw/manifest.json with "demo": true '
            "(lane SAFECUT-SENSE's synthetic demo job)"
        )
    if len(found) > 1:
        raise CheckFailed(f'{len(found)} recorded jobs claim "demo": true; exactly one may')
    return found[0]


def demo_clip(recording: Path, manifest: dict[str, Any]) -> Path:
    source = manifest.get("source")
    if not isinstance(source, str):
        raise CheckFailed(f'{recording.name}/raw/manifest.json has no "source" (the repo-relative clip path)')
    clip = (ROOT / source).resolve()
    if not clip.is_file() or ROOT not in clip.parents:
        raise CheckFailed(f"demo clip {source} is missing or outside the repo")
    return clip


def is_h264(path: Path) -> tuple[bool, bool]:
    """``(video is H.264, has an audio stream)``, from ffmpeg's stream listing (imageio-ffmpeg ships no ffprobe)."""
    proc = sh([get_ffmpeg_exe(), "-hide_banner", "-i", str(path)], timeout=60)
    streams = [line for line in proc.stderr.splitlines() if line.strip().startswith("Stream #")]
    video = [s for s in streams if " Video: " in s]
    return bool(video) and all(" Video: h264" in s for s in video), any(" Audio: " in s for s in streams)


# ---------------------------------------------------------------------------
# E2: every stage, replay
# ---------------------------------------------------------------------------


def check_stage_output(out: Path) -> None:
    if out.name == REDACTED:
        h264, _ = is_h264(out)
        if not h264:
            raise CheckFailed(f"{REDACTED} is not an H.264 video")
    else:
        load(out)


def e2() -> None:
    recording, manifest = demo_recording()
    clip = demo_clip(recording, manifest)
    work = Path(tempfile.mkdtemp(prefix="entry-e2-"))
    job = work / recording.name
    try:
        pipeline.create_job(clip, job, mode="replay")
        pipeline.attach_recording(job, recording)
        failures: list[str] = []
        for stage in STAGES:
            if failures:
                failures.append(f"{stage.name}: not run")
                continue
            if stage.name == "render":
                sh([str(BIN / "safecut"), "approve", "--job", str(job)], check=True)
            proc = sh([str(BIN / "safecut"), stage.name, "--job", str(job), "--replay"], timeout=900)
            if proc.returncode != 0:
                failures.append(f"{stage.name}: exit {proc.returncode}: {last_line(proc.stderr or proc.stdout)}")
                continue
            try:
                check_stage_output(job / stage.output)
            except Exception as exc:  # any failure is this stage's reason
                failures.append(f"{stage.name}: {exc}")
            print(f"  {stage.name}: ok", flush=True)
        if failures:
            first = failures[0]
            raise CheckFailed(f"{first} (+{len(failures) - 1} later stage(s) not run)" if len(failures) > 1 else first)
        validate_job_dir(job)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# E3: end to end, offline, scored against ground truth
# ---------------------------------------------------------------------------


def offline_prefix() -> list[str]:
    """Run the child in a fresh network namespace when the kernel allows it (no interfaces but loopback)."""
    unshare = shutil.which("unshare")
    if unshare and sh([unshare, "-rn", "true"], timeout=20).returncode == 0:
        return [unshare, "-rn"]
    return []


def e3() -> None:
    recording, manifest = demo_recording()
    clip = demo_clip(recording, manifest)
    truth = manifest.get("truth")
    if not isinstance(truth, str) or not (ROOT / truth).is_file():
        raise CheckFailed(f'{recording.name}/raw/manifest.json has no "truth" (an EVAL §1 label file)')
    work = Path(tempfile.mkdtemp(prefix="entry-e3-"))
    job = work / recording.name
    try:
        prefix = offline_prefix()
        # Without a namespace, proxies point at a closed port as well as the in-process guard (safecut.netguard).
        env = (
            {} if prefix else {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
        )
        print(f"  network: {'blocked by a network namespace' if prefix else 'blocked in process and by proxy'}")
        proc = sh(
            [*prefix, str(BIN / "safecut"), "run", str(clip), "--out", str(job), "--replay", "--auto-approve-policy"],
            env=env,
            timeout=1500,
        )
        if proc.returncode != 0:
            raise CheckFailed(f"safecut run exited {proc.returncode}: {last_line(proc.stderr or proc.stdout)}")
        redacted = job / "redacted.mp4"
        if not redacted.is_file():
            raise CheckFailed("no redacted.mp4")
        h264, audio = is_h264(redacted)
        _, source_audio = is_h264(clip)
        if not h264:
            raise CheckFailed("redacted.mp4 is not H.264")
        if source_audio and not audio:
            raise CheckFailed("redacted.mp4 has no audio stream, but the source has one")
        audit = load(job / "audit.json", Audit)
        if audit.unresolved != 0:
            raise CheckFailed(f"audit.json unresolved = {audit.unresolved}")
        load(job / "receipt.json", Receipt)  # the model validator verifies the hash chain link
        if not (job / "receipt.html").is_file():
            raise CheckFailed("no receipt.html")
        validate_job_dir(job)
        score_against_truth(job, ROOT / truth)
    finally:
        shutil.rmtree(work, ignore_errors=True)


#: A pixel is the entity's content (a face's features, a plate's characters, a screen's text) when it differs from
#: the box's median colour by more than this (0–255, any channel) in the prepared clip.
CONTENT_DELTA = 25
#: Hidden means the content can no longer be told from its background in ``redacted.mp4``: the content-vs-background
#: contrast left over, as a share of the source's. The demo's covers leave 0.00; a tint or a sliver of a cover
#: leaves almost all of it (a +10 tint: 1.00).
RESIDUAL_CONTRAST = 0.25
#: A kept entity's box changes by less than this mean (0–255) on most of its frames: the codec moves a kept face by
#: about 2.5; a renderer that tints or blurs the whole frame moves every box.
KEPT_CHANGE = 8.0


def _box(box: Any, sx: float, sy: float, width: int, height: int) -> tuple[int, int, int, int] | None:
    import math  # noqa: PLC0415

    x1, y1 = max(int(box[0] * sx), 0), max(int(box[1] * sy), 0)
    x2, y2 = min(math.ceil(box[2] * sx), width), min(math.ceil(box[3] * sy), height)
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def render_hides(job: Path, clip_labels: Any) -> list[str]:
    """The plan is scored above; this checks the **pixels** of ``redacted.mp4`` against the prepared clip:

    - every should-hide entity's content (pixels that stand out from its box's background) can't be told from that
      background any more on at least 99 % of its visible frames (a renderer that draws nothing, a tint, or a cover
      over a sliver of the box fails);
    - every kept entity's box is left as it was (mean change below :data:`KEPT_CHANGE`) on at least 75 % of its
      frames (a renderer that alters the whole frame fails; a short legitimate hide, like the guest's re-entry
      before a creator merges it, is under the plan's own over-blur rule above).
    """
    import numpy as np  # noqa: PLC0415 -- the check's own dependencies, loaded only when E3 runs

    video = importlib.import_module("safecut.render.video")
    contracts = importlib.import_module("safecut.contracts")
    meta = contracts.load(job / "job.json", contracts.Job)
    sx, sy = meta.width / clip_labels.width, meta.height / clip_labels.height
    entities = [e for e in clip_labels.entities if e.dense]
    good = dict.fromkeys((e.id for e in entities), 0)
    seen = dict.fromkeys((e.id for e in entities), 0)
    rendered_frames = video.read_frames(job / "redacted.mp4", meta)
    frames = zip(video.read_frames(job / meta.prepared, meta), rendered_frames, strict=True)
    for f, (source, rendered) in enumerate(frames):
        for entity in entities:
            box = entity.dense.get(f)
            region = None if box is None else _box(box, sx, sy, meta.width, meta.height)
            if region is None:
                continue
            x1, y1, x2, y2 = region
            a = source[y1:y2, x1:x2].astype(np.float32)
            b = rendered[y1:y2, x1:x2].astype(np.float32)
            seen[entity.id] += 1
            if not entity.should_hide:
                good[entity.id] += float(np.abs(a - b).mean()) < KEPT_CHANGE
                continue
            content = np.abs(a - np.median(a.reshape(-1, 3), axis=0)).max(axis=2) > CONTENT_DELTA
            if not content.any() or content.all():
                good[entity.id] += float(np.abs(a - b).mean()) >= KEPT_CHANGE  # a flat box: it must at least change
                continue
            before = float(np.abs(a[content].mean(axis=0) - a[~content].mean(axis=0)).max())
            after = float(np.abs(b[content].mean(axis=0) - b[~content].mean(axis=0)).max())
            good[entity.id] += after <= RESIDUAL_CONTRAST * max(before, 1.0)
    hidden = {e.id for e in entities if e.should_hide}
    if not any(seen[i] for i in hidden):
        return ["the rendered video shows none of the should-hide entities' frames"]
    problems = [
        f"{eid}: still legible in redacted.mp4 on {n - good[eid]}/{n} visible frames"
        for eid, n in seen.items()
        if eid in hidden and n and good[eid] / n < 0.99
    ]
    problems += [
        f"{eid} (keep): altered in redacted.mp4 on {n - good[eid]}/{n} visible frames"
        for eid, n in seen.items()
        if eid not in hidden and n and good[eid] / n < 0.75
    ]
    return problems


def score_against_truth(job: Path, truth: Path) -> None:
    sys.path.insert(0, str(ROOT))
    try:
        labels = importlib.import_module("eval.labels")
        metrics = importlib.import_module("eval.metrics")
    except ImportError as exc:
        raise CheckFailed(f"eval metrics not importable ({exc}); WP7 eval/metrics.py") from exc
    clip_labels = labels.load_labels(truth)
    score = metrics.score_job(job, clip_labels)
    problems: list[str] = []
    for entity in score.entities:
        if entity.should_hide:
            if entity.visible_frames and entity.frames_covered_95 / entity.visible_frames < 0.99:
                problems.append(
                    f"{entity.id}: ≥95% covered on only {entity.frames_covered_95}/"
                    f"{entity.visible_frames} visible frames"
                )
            if entity.leak_bursts:
                problems.append(f"{entity.id}: {entity.leak_bursts} leak burst(s)")
        elif entity.visible_frames and entity.frames_hidden / entity.visible_frames > 0.10:
            problems.append(f"{entity.id} (keep): hidden on {entity.frames_hidden}/{entity.visible_frames} frames")
    print(f"  scored {len(score.entities)} entities against {truth.name}")
    # Never a vacuous pass: the truth must hold something to hide that is actually on screen, and someone to keep.
    if not any(e.should_hide and e.visible_frames for e in score.entities):
        problems.insert(0, "the truth file has no visible entity that should be hidden")
    else:
        problems += render_hides(job, clip_labels)
    if not any(not e.should_hide and e.visible_frames for e in score.entities):
        problems.append("the truth file has no visible entity that should be kept clear")
    if problems:
        raise CheckFailed(
            f"ground truth: {problems[0]}" + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else "")
        )


# ---------------------------------------------------------------------------
# E4, E5, E8: required tests, by entry key
# ---------------------------------------------------------------------------

E4_KEYS = (
    "non_participant_never_kept",
    "child_never_kept",
    "hidden_frames_covered",
    "backfill_gap_hold",
    "locked_grid_fixed",
    "injected_leak_patched",
)
E4_PROPERTIES = E4_KEYS[:5]
E5_KEYS = (
    "flow",
    "auth_access_code",
    "auth_service_key",
    "rate_limit",
    "daily_cap",
    "upload_limits",
    "cors",
    "deletion_job",
    "healthz",
)
E8_KEYS = (
    "files",
    "sam",
    "muse_scene",
    "muse_role",
    "muse_escalate",
    "muse_redteam",
    "voice_transcribe",
    "open_weight",
)


def run_entry_tests(
    line: str, *, extra: Iterable[str] = (), env: dict[str, str] | None = None, collect_only: bool = False
) -> list[dict[str, Any]]:
    """Run (or collect) the tests marked ``entry("<line>:…")`` and return the plugin's report lines."""
    report = Path(tempfile.mkstemp(prefix=f"entry-{line}-", suffix=".jsonl")[1])
    try:
        args = [str(BIN / "pytest"), "-q", "-p", "no:cacheprovider", f"--entry-only={line}", *extra]
        if collect_only:
            args.append("--collect-only")
        proc = sh(args, env={**(env or {}), "SAFECUT_ENTRY_REPORT": str(report)}, timeout=1800)
        lines = [json.loads(raw) for raw in report.read_text(encoding="utf-8").splitlines() if raw.strip()]
        # 5 = no tests collected: reported below as missing keys, with the names.
        if proc.returncode not in (0, 5):
            failed = sorted({e["nodeid"] for e in lines if e.get("event") == "result" and e["outcome"] != "passed"})
            raise CheckFailed(f"{line} tests failed: {', '.join(failed[:3]) or last_line(proc.stdout)}")
        return lines
    finally:
        report.unlink(missing_ok=True)


def require_passed(lines: list[dict[str, Any]], line: str) -> None:
    """Every collected keyed test ran and passed: a skipped, xfailed or erroring one is a failure, whatever pytest's
    exit code says."""
    collected = {e["nodeid"] for e in lines if e.get("event") == "collected"}
    passed = {
        e["nodeid"]
        for e in lines
        if e.get("event") == "result" and e.get("when") == "call" and e.get("outcome") == "passed"
    }
    other = sorted({e["nodeid"] for e in lines if e.get("event") == "result" and e.get("outcome") != "passed"})
    if other or collected - passed:
        bad = other or sorted(collected - passed)
        raise CheckFailed(f"{line} test(s) didn't pass: {', '.join(bad[:3])}")


def keys_present(lines: list[dict[str, Any]], line: str, required: Iterable[str]) -> dict[str, list[str]]:
    by_key: dict[str, list[str]] = {}
    for entry in lines:
        if entry.get("event") != "collected":
            continue
        for key in entry["keys"]:
            by_key.setdefault(key, []).append(entry["nodeid"])
    missing = [k for k in required if f"{line}:{k}" not in by_key]
    if missing:
        raise CheckFailed(f'no test marked entry("{line}:…") for: {", ".join(missing)}')
    return by_key


def e4() -> None:
    lines = run_entry_tests("E4", extra=["--hypothesis-show-statistics"], env={"HYPOTHESIS_PROFILE": "entry"})
    by_key = keys_present(lines, "E4", E4_KEYS)
    require_passed(lines, "E4")
    examples = {e["nodeid"]: e.get("examples") for e in lines if e.get("event") == "teardown"}
    for key in E4_PROPERTIES:
        for nodeid in by_key[f"E4:{key}"]:
            count = examples.get(nodeid)
            if count is None or count < 2000:
                raise CheckFailed(f"{nodeid} ({key}) ran {count or 0} hypothesis examples; needs ≥ 2000")
    cov = sh(
        [
            str(BIN / "pytest"),
            "-q",
            "-p",
            "no:cacheprovider",
            "--cov=safecut.decide.policy",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-fail-under=100",
        ],
        timeout=1800,
    )
    if cov.returncode != 0:
        total = [ln for ln in cov.stdout.splitlines() if "policy" in ln or "TOTAL" in ln or "Required" in ln]
        raise CheckFailed(f"safecut/decide/policy.py branch coverage below 100%: {(total or ['no data'])[-1][:160]}")


def e5() -> None:
    lines = run_entry_tests("E5")
    keys_present(lines, "E5", E5_KEYS)
    require_passed(lines, "E5")


def e8() -> None:
    lines = run_entry_tests("E8", extra=["-m", "live"], collect_only=True)
    by_key = keys_present(lines, "E8", E8_KEYS)
    markers = {e["nodeid"]: e.get("markers", []) for e in lines if e.get("event") == "collected"}
    unmarked = sorted(n for ids in by_key.values() for n in ids if "live" not in markers.get(n, []))
    if unmarked:
        raise CheckFailed(f"E8 tests without the live marker: {', '.join(unmarked[:3])}")
    script = ROOT / "scripts" / "go-live.sh"
    if not script.is_file():
        raise CheckFailed("scripts/go-live.sh is missing (lane SAFECUT-SENSE)")
    env = {k: v for k, v in os.environ.items() if k != "MODEL_API_KEY"}
    proc = subprocess.run(  # noqa: S603 -- fixed argv
        ["bash", str(script), str(ROOT / "fixtures" / "clips" / "counter_30fps_audio.mp4")],  # noqa: S607
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    message = (proc.stderr or proc.stdout).strip()
    if proc.returncode != 2 or "MODEL_API_KEY" not in message or len(message.splitlines()) != 1:
        raise CheckFailed(
            f"go-live.sh without MODEL_API_KEY must exit 2 with one line naming it; got exit "
            f"{proc.returncode}: {last_line(message)}"
        )


# ---------------------------------------------------------------------------
# E6, E7: web on the API, deploy-ready
# ---------------------------------------------------------------------------

TEST_FILE = re.compile(r"(\.test\.[cm]?[jt]sx?$)|(/__tests__/)|(/__fixtures__/)|(^web/src/test/)")


def e6() -> None:
    """The web app's Playwright run against a locally started API in replay (``pnpm e2e:api`` starts both and
    runs axe), and ``MockBackend`` only in unit tests and the test-support folder ``web/src/test/``."""
    proc = sh(["git", "grep", "-l", "MockBackend", "--", "web/src", "web/app"])
    leaks = [f for f in proc.stdout.split() if not TEST_FILE.search(f)]
    if leaks:
        raise CheckFailed(f"MockBackend outside unit tests: {', '.join(leaks[:4])}")
    proc = sh(["git", "grep", "-lE", r"from ['\"](@/test/|\.\./test/|\./test/)", "--", "web/src"])
    leaks = [f for f in proc.stdout.split() if not TEST_FILE.search(f)]
    if leaks:
        raise CheckFailed(f"app code imports the test-support folder: {', '.join(leaks[:4])}")
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    if "e2e:api" not in package.get("scripts", {}):
        raise CheckFailed("web/package.json has no e2e:api script (Playwright against the local replay API)")
    proc = sh(["pnpm", "--dir", "web", "run", "e2e:api"], timeout=1800)
    if proc.returncode != 0:
        raise CheckFailed(f"pnpm e2e:api exited {proc.returncode}: {last_line(proc.stderr or proc.stdout)}")


def e7() -> None:
    modal_app = ROOT / "deploy" / "modal_app.py"
    if not modal_app.is_file():
        raise CheckFailed("deploy/modal_app.py is missing")
    text = modal_app.read_text(encoding="utf-8")
    needs = {
        "the ASGI app": r"@[\w.]*asgi_app",
        "a Volume": r"Volume\.from_name",
        "the 24 h deletion cron": r"schedule\s*=\s*modal\.(Cron|Period)",
        # The pipeline's workers are threads in the API container (one container, one ledger writer): the ASGI
        # function must build the real app, whose Service starts them, and a worker smoke must run the pipeline.
        "the API app that runs the pipeline workers": r"return create_app\(",
        "a pipeline worker smoke run": r"def pipeline_worker_smoke\(",
    }
    missing = [what for what, pattern in needs.items() if not re.search(pattern, text)]
    if not re.search(r"self\.worker = worker or Worker\(", (ROOT / "safecut" / "api" / "app.py").read_text("utf-8")):
        missing.append("the Service's pipeline Worker (safecut/api/app.py)")
    if missing:
        raise CheckFailed(f"deploy/modal_app.py lacks {', '.join(missing)}")
    imp = sh([str(BIN / "python"), "-c", "import deploy.modal_app"], timeout=120)
    if imp.returncode != 0:
        raise CheckFailed(f"deploy/modal_app.py doesn't import: {last_line(imp.stderr)}")
    workflow = ROOT / ".github" / "workflows" / "deploy.yml"
    if not workflow.is_file():
        raise CheckFailed(".github/workflows/deploy.yml is missing")
    wf = workflow.read_text(encoding="utf-8")
    if "MODAL_TOKEN_ID" not in wf or "::notice" not in wf:
        raise CheckFailed("deploy.yml must read MODAL_TOKEN_ID and skip with a ::notice when it's missing")
    web_readme = ROOT / "web" / "README.md"
    if not web_readme.is_file() or "Vercel" not in web_readme.read_text(encoding="utf-8"):
        raise CheckFailed("web/README.md doesn't document the Vercel settings")
    check = ROOT / "scripts" / "deploy-check.sh"
    if not check.is_file() or sh(["bash", "-n", str(check)]).returncode != 0:
        raise CheckFailed("scripts/deploy-check.sh is missing or not valid bash")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    blocked = (ROOT / "BLOCKED.md").read_text(encoding="utf-8") if (ROOT / "BLOCKED.md").is_file() else ""
    urls = re.findall(r"https://([\w.-]+)\.modal\.run", readme)
    # A placeholder (`your-app.modal.run`, `example`) never counts as deployed.
    real = [u for u in urls if not re.search(r"your|example|placeholder|xxx|<|changeme", u, re.IGNORECASE)]
    deployed = bool(real) and "safecut.sigmora.org" in readme
    if not deployed and not re.search(r"^- \[ \].*Modal", blocked, re.MULTILINE):
        raise CheckFailed("no deployed URLs in README.md and no open Modal line in BLOCKED.md")


# ---------------------------------------------------------------------------
# E9, E10: eval and the submission package
# ---------------------------------------------------------------------------

VARIANTS = ("blur_all", "egoblur", "detector_only", "muse_no_track", "full", "no_audit")


def e9() -> None:
    run_py = ROOT / "eval" / "run.py"
    if not run_py.is_file():
        raise CheckFailed("eval/run.py is missing")
    helptext = sh([str(BIN / "python"), str(run_py), "--help"], timeout=120)
    if helptext.returncode != 0:
        raise CheckFailed(f"eval/run.py --help exited {helptext.returncode}: {last_line(helptext.stderr)}")
    for word in ("hero", "dev", "public", *VARIANTS, "--replay"):
        if word not in helptext.stdout:
            raise CheckFailed(f"eval/run.py --help doesn't offer {word}")
    seen: set[str] = set()
    for config in sorted((ROOT / "eval" / "results").glob("*/config.json")):
        data = json.loads(config.read_text(encoding="utf-8"))
        if (config.parent / "metrics.json").is_file() and isinstance(data, dict):
            seen.add(str(data.get("variant")))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType] -- untyped JSON
    missing = [v for v in VARIANTS if v not in seen]
    if missing:
        raise CheckFailed(f"no committed eval run (config.json + metrics.json) for variant(s): {', '.join(missing)}")
    report = sh([str(BIN / "python"), str(ROOT / "eval" / "report.py"), "--check"], timeout=300)
    if report.returncode != 0:
        raise CheckFailed(
            f"eval/RESULTS.md is not what eval/report.py generates from committed runs: "
            f"{last_line(report.stderr or report.stdout)}"
        )
    tests = sorted((ROOT / "tests").glob("test_metrics*.py"))
    if not tests:
        raise CheckFailed("no WP7 metric unit tests (tests/test_metrics*.py)")
    sh([str(BIN / "pytest"), "-q", "-p", "no:cacheprovider", *map(str, tests)], check=True, timeout=600)


SUBMISSION_DOCS = ("README.md", "docs/SUBMISSION.md", "docs/VIDEO-SCRIPT.md", "docs/AGENTIC-LOOP.md", "docs/LAUNCH.md")
#: A reported figure: a percentage, a dollar amount, or a decimal fraction standing alone (not a version like 3.1 in
#: ``sam-3.1``, which sits in code spans anyway).
FIGURE = re.compile(r"(?<![\w.\-/])(\$?\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?|\d+\.\d+)(?![\w\-/%]|\.\d)")


#: A count reported as a result ("47 leaks", "20 clips"): checked like a figure, whatever its size.
COUNT = re.compile(
    r"(?<![\w.\-/])(\d+)(?=\s+(?:leaks?|leak bursts?|bursts?|clips|entities|labelled clips|missed|over-blurred)\b)"
)
#: Fences that hold commands or data a reader runs, not results; any other fence is read like prose.
CODE_FENCE = re.compile(
    r"```(?:bash|sh|shell|console|json|jsonc|python|py|ts|tsx|js|yaml|yml|toml|text|diff)\b.*?```", re.DOTALL
)


def prose(text: str) -> str:
    """The text a reader sees: command and data fences, link targets and HTML comments removed. Inline code and
    untagged fences are kept, so a figure can't hide in backticks or a bare fence (model IDs like ``sam-3.1``
    never match :data:`FIGURE`)."""
    text = CODE_FENCE.sub(" ", text)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    return re.sub(r"\]\([^)]*\)", "]", text)


def e10() -> None:
    missing = [d for d in SUBMISSION_DOCS if not (ROOT / d).is_file()]
    if missing:
        raise CheckFailed(f"missing: {', '.join(missing)}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("What each Meta model does here", "What existed before Oct 26"):
        if not re.search(rf"^#+ .*{re.escape(heading)}", readme, re.MULTILINE):
            raise CheckFailed(f'README.md has no "{heading}" section')
    script = (ROOT / "docs" / "VIDEO-SCRIPT.md").read_text(encoding="utf-8")
    stamps = [int(m) * 60 + int(s) for m, s in re.findall(r"\b(\d{1,2}):([0-5]\d)\b", script)]
    if not stamps:
        raise CheckFailed("docs/VIDEO-SCRIPT.md has no m:ss timings")
    if max(stamps) > 180:
        raise CheckFailed(f"docs/VIDEO-SCRIPT.md runs to {max(stamps) // 60}:{max(stamps) % 60:02d} (> 3:00)")
    results_path = ROOT / "eval" / "RESULTS.md"
    if not results_path.is_file():
        raise CheckFailed("eval/RESULTS.md is missing")
    results = results_path.read_text(encoding="utf-8")
    for doc in SUBMISSION_DOCS:
        seen = prose((ROOT / doc).read_text(encoding="utf-8"))
        for figure in [*FIGURE.findall(seen), *COUNT.findall(seen)]:
            if not re.search(rf"(?<![\w.]){re.escape(figure)}(?![\w%]|\.\d)", results):
                raise CheckFailed(f"{doc}: the figure {figure} is not in eval/RESULTS.md")


# ---------------------------------------------------------------------------
# E11, E12: hygiene and the owner list
# ---------------------------------------------------------------------------

SECRET = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9]{16,}|rk_live_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"
    r"|-----BEGIN ([A-Z]+ )?PRIVATE KEY-----|\"private_key\":\s*\"-----BEGIN"
    r"|[\"']?(MODEL_API_KEY|BASETEN_API_KEY|MODAL_TOKEN_SECRET|MODAL_TOKEN_ID)[\"']?\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}"
)
SHIPPED = ("safecut", "eval", "deploy", "scripts", "web/src", "web/e2e", "web/scripts", ".github")
#: The three unfinished-work markers, spelt in pieces so this file doesn't match its own check.
MARKER = re.compile(r"\b(" + "|".join(("TO" + "DO", "FIX" + "ME", "X" + "XX")) + r")\b")


def e11() -> None:
    # --cc adds what a merge commit itself introduced (a conflict resolution), which plain -p never shows.
    history = sh(["git", "log", "-p", "--cc", "--all", "--no-color", "--format=commit %H"], timeout=600)
    hits = [
        line
        for line in history.stdout.splitlines()
        if line.startswith("+")
        and SECRET.search(line)
        and "SECRET_RE" not in line
        and "SECRET = re.compile" not in line
        and "SECRET.search(" not in line  # the scanner's own tests feed it key-shaped strings
    ]
    if hits:
        raise CheckFailed(f"secret-shaped text in git history: {hits[0][:80]}…")
    # And the tree as it stands, every tracked text file; only the scanner and its own tests may hold key shapes.
    scanner = {"scripts/entry_check.py", "tests/test_entry_check.py"}
    for name in sh(["git", "ls-files"]).stdout.split():
        path = ROOT / name
        if name in scanner or not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if SECRET.search(line):
                raise CheckFailed(f"{name}:{number}: secret-shaped text in the tree")
    tracked = sh(["git", "ls-files", "--", *SHIPPED]).stdout.split()
    for name in tracked:
        path = ROOT / name
        if (
            TEST_FILE.search(name)
            or "/tests/" in name
            or not path.is_file()
            or path.suffix in {".png", ".jpg", ".mp4", ".gif"}
        ):
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue  # binary (an icon, model weights): no source lines to mark
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if MARKER.search(line):
                raise CheckFailed(f"{name}:{number}: unfinished marker in shipped code")
    skips = sh(
        [
            "git",
            "grep",
            "-nE",
            r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail|importorskip)\(|\b(it|test|describe)\.(skip|skipIf|runIf|only|fixme|todo|fails)\b"
            r"|\bx(it|test|describe)\(",
            "--",
            "tests",
            "web/src",
            "web/e2e",
        ]
    ).stdout.splitlines()
    skips = [s for s in skips if not LIVE_SKIP.match(s)]
    if skips:
        raise CheckFailed(f"skipped test outside the live suite: {skips[0][:120]}")
    fresh_clone_readme()


#: The one allowed skip: a live test (tests/test_live*.py) skipping because its owner key isn't set.
LIVE_SKIP = re.compile(
    r"^tests/test_live[\w]*\.py:\d+:.*pytest\.mark\.skipif\(not os\.environ\.get\(\"(MODEL_API_KEY|BASETEN_API_KEY)\"\)"
)


def fresh_clone_readme() -> None:
    """Run the README's fresh-clone block (between ``<!-- fresh-clone:start -->`` and ``:end``) in a clone."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"<!-- fresh-clone:start -->(.*?)<!-- fresh-clone:end -->", readme, re.DOTALL)
    if not match:
        raise CheckFailed("README.md has no fresh-clone block (<!-- fresh-clone:start --> … :end)")
    commands = [
        line.strip()
        for block in re.findall(r"```(?:bash|sh)\n(.*?)```", match.group(1), re.DOTALL)
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not commands:
        raise CheckFailed("README.md's fresh-clone block has no bash commands")
    work = Path(tempfile.mkdtemp(prefix="entry-readme-"))
    try:
        sh(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(work / "repo")], check=True, timeout=300)
        script = "set -euo pipefail\n" + "\n".join(c for c in commands if not c.startswith("git clone"))
        cd_line = [c for c in commands if c.startswith("cd ")]
        if cd_line:
            script = script.replace(cd_line[0], "", 1)
        proc = sh(["bash", "-c", script], cwd=work / "repo", timeout=2400)
        if proc.returncode != 0:
            raise CheckFailed(
                f"README fresh-clone steps failed (exit {proc.returncode}): {last_line(proc.stderr or proc.stdout)}"
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)


OWNER_INPUTS = {
    "MODEL_API_KEY": r"MODEL_API_KEY",
    "hero footage": r"hero (footage|clips?)",
    "Modal tokens": r"MODAL_TOKEN_ID",
    "the domain and Vercel project": r"Vercel",
    "making the repo public": r"[Mm]ak(e|ing) `?[\w/-]*`? ?(the )?(repo|repository)?\s*`?[\w/-]*`?\s*public",
    "EgoBlur weights": r"EgoBlur Gen ?2 weights",
    "BASETEN_API_KEY": r"BASETEN_API_KEY",
    "the voice-over and the submit click": r"voice-?over",
}


def e12() -> None:
    path = ROOT / "BLOCKED.md"
    if not path.is_file():
        raise CheckFailed("root BLOCKED.md is missing")
    text = path.read_text(encoding="utf-8")
    items = re.findall(r"^\s*- \[([ xX])\] (.+)$", text, re.MULTILINE)
    if not items:
        raise CheckFailed("BLOCKED.md has no checklist items")
    open_text = "\n".join(body for mark, body in items if mark == " ")
    done_text = "\n".join(body for mark, body in items if mark != " ")
    missing = [
        what
        for what, pattern in OWNER_INPUTS.items()
        if not re.search(pattern, open_text + "\n" + done_text, re.IGNORECASE)
    ]
    if missing:
        raise CheckFailed(f"BLOCKED.md doesn't list: {', '.join(missing)}")
    if done_text.strip():
        raise CheckFailed("BLOCKED.md still lists inputs already done; drop them")
    vague = [body for mark, body in items if mark == " " and len(body) < 40]
    if vague:
        raise CheckFailed(f"BLOCKED.md item without exact steps: {vague[0][:80]}")
    lane_env = set[str]()
    for lane_file in sorted((ROOT / ".agent" / "win").glob("SAFECUT-*/BLOCKED.md")):
        if lane_file.parent.name in {"SAFECUT-WP0", "SAFECUT-WP6", "SAFECUT-PRE-A", "SAFECUT-PRE-B"}:
            continue  # Wave A's lists, already merged into the root list by hand
        for mark, body in re.findall(r"^\s*- \[([ pP])\] (.+)$", lane_file.read_text(encoding="utf-8"), re.MULTILINE):
            del mark
            lane_env.update(re.findall(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}\b", body))
    absent = sorted(env for env in lane_env if env not in text)
    if absent:
        raise CheckFailed(f"lane BLOCKED lists name inputs the root BLOCKED.md lacks: {', '.join(absent[:5])}")


CHECKS: dict[str, Callable[[], None]] = {
    "E2": e2,
    "E3": e3,
    "E4": e4,
    "E5": e5,
    "E6": e6,
    "E7": e7,
    "E8": e8,
    "E9": e9,
    "E10": e10,
    "E11": e11,
    "E12": e12,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in CHECKS:
        print(f"usage: python -m scripts.entry_check {{{'|'.join(CHECKS)}}}", file=sys.stderr)
        return 2
    try:
        CHECKS[argv[0]]()
    except CheckFailed as exc:
        print(f"FAIL {exc}", flush=True)
        return 1
    except Exception as exc:  # a crash is a failure with its own reason, never a pass
        print(f"FAIL {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        return 1
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
