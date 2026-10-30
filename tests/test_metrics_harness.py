"""WP7 harness: eval/run.py (variants, the test split's freeze, hash check and 3-run cap) and eval/report.py, on
stand-in stages (``tests/fake_stages.py``), so they test the harness, not the model stages."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from eval import report
from eval import run as runner
from eval.metrics import Region
from eval.variants import VARIANTS, Variant, VariantUnavailable, held_boxes, run_variant
from safecut import pipeline
from safecut.stages import Stage
from tests.fake_stages import CLIP, EXAMPLE, fake_runner


@pytest.fixture(autouse=True)
def fake_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Stage, "runner", fake_runner)
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef")


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """A repo-like root with one clip, its labels (inside the example job's planned region) and a recording."""
    root = tmp_path / "repo"
    (root / "clips").mkdir(parents=True)
    shutil.copyfile(CLIP, root / "clips" / "a.mp4")
    plan = json.loads((EXAMPLE / "plan.json").read_text())
    frame, entries = next(iter(sorted(plan["frames"].items(), key=lambda kv: int(kv[0]))))
    x1, y1, x2, y2 = entries[0]["box"]
    labels = {
        "clip": "a.mp4",
        "fps": 30,
        "frames": 12,
        "width": 1280,
        "height": 720,
        "split": "dev",
        "entities": [
            {
                "id": "e1",
                "category": "bystander",
                "should_hide": True,
                "frames": {"first": int(frame), "last": int(frame)},
                "boxes": {frame: [x1 + 2, y1 + 2, x2 - 2, y2 - 2]},
            },
            {
                "id": "e2",
                "category": "participant",
                "should_hide": False,
                "frames": {"first": 0, "last": 0},
                "boxes": {"0": [1200, 650, 1210, 660]},
            },
        ],
    }
    (root / "labels").mkdir()
    (root / "labels" / "a.json").write_text(json.dumps(labels))
    raw = root / "recordings" / "demo" / "raw"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text(json.dumps({"source_sha256": pipeline.sha256_file(CLIP), "synthetic": True}))
    splits = root / "splits"
    splits.mkdir()
    for split in ("dev", "test"):
        (splits / f"{split}.json").write_text(
            json.dumps(
                {
                    "split": split,
                    "clips": [{"clip": "clips/a.mp4", "labels": "labels/a.json", "recording": "recordings/demo"}],
                }
            )
        )
    return root


def test_a_replay_run_writes_every_result_file(base: Path) -> None:
    now = datetime(2026, 10, 30, 12, tzinfo=UTC)
    run_dir = runner.run("dev", "full", replay=True, out=base / "results", now=now, splits=base / "splits", base=base)
    assert run_dir.name == "20261030T120000Z-dev-full-0123456"
    assert {p.name for p in run_dir.iterdir()} == {
        "config.json",
        "metrics.json",
        "per_clip.csv",
        "cost.json",
        "worst.json",
    }
    config = json.loads((run_dir / "config.json").read_text())
    assert config["synthetic"] is True
    assert config["variant"] == "full"
    assert config["models"]["tracks"] == "sam-3.1"  # the model the tracks themselves name
    # The detector the job's own audit.json names, never the configured default; a synthetic replay says no model ran.
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    assert config["models"]["auditor"] == audit["egoblur"]["model"]
    assert config["models_note"] == "synthetic recordings replayed: no Meta model was called"
    assert config["detail"] == {}
    assert len(config["split_hash"]) == 64
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["entity_recall"] == 1.0
    assert metrics["over_blur"] == 0.0
    assert metrics["leak_bursts"] == 0
    assert (run_dir / "per_clip.csv").read_text().count("\n") == 3


@pytest.mark.parametrize("variant", ["no_audit", "blur_all", "detector_only"])
def test_the_built_in_variants_run(base: Path, variant: str) -> None:
    run_dir = runner.run(
        "dev",
        cast(Variant, variant),
        replay=True,
        out=base / "results",
        splits=base / "splits",
        base=base,
    )
    assert json.loads((run_dir / "config.json").read_text())["variant"] == variant


def test_blur_all_hides_every_face_track_only(tmp_path: Path) -> None:
    job = tmp_path / "j"
    pipeline.create_job(CLIP, job, mode="replay")
    run_variant("blur_all", job, replay=True)
    tracks = json.loads((job / "tracks.json").read_text())
    decisions = json.loads((job / "decisions.json").read_text())
    assert {t["concept"] for t in tracks["tracks"]} <= {"face"}
    assert all(i["decision"] == "hide" for i in decisions["items"])
    assert len(decisions["items"]) == len(tracks["tracks"])


def test_muse_no_track_says_which_lane_hook_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys  # noqa: PLC0415

    monkeypatch.setitem(sys.modules, "safecut.scout.baselines", None)  # whatever the scout lane has merged
    job = tmp_path / "j"
    pipeline.create_job(CLIP, job, mode="replay")
    with pytest.raises((VariantUnavailable, ModuleNotFoundError)):
        run_variant("muse_no_track", job, replay=True)


def test_egoblur_runs_the_audit_detector_on_every_frame_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real prepare stage, on the real demo clip
    demo = Path(__file__).resolve().parent.parent / "fixtures" / "jobs" / "demo"
    manifest = json.loads((demo / "raw" / "manifest.json").read_text())
    job = tmp_path / "j"
    pipeline.create_job(Path(__file__).resolve().parent.parent / manifest["source"], job, mode="replay")
    pipeline.attach_recording(job, demo)
    result = run_variant("egoblur", job, replay=True)
    assert result.detail["detector"] in ("egoblur-gen2", "yunet-face")
    assert all(0 <= f < 360 for f in result.regions)


def test_held_boxes() -> None:
    boxes = {2: [(0, 0, 1, 1)], 5: [(5, 5, 6, 6)]}
    held = held_boxes(boxes, 8, hold=True)
    assert sorted(held) == [2, 3, 4, 5, 6, 7]
    assert held[4] == [Region((0, 0, 1, 1))]
    assert held[7] == [Region((5, 5, 6, 6))]
    assert sorted(held_boxes(boxes, 8, hold=False)) == [2, 5]


def test_the_test_split_is_frozen_hash_checked_live_only_and_capped(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    splits = base / "splits"
    with pytest.raises(runner.EvalError, match="live runs only"):
        runner.run("test", "full", replay=True, out=base / "results", splits=splits, base=base)
    with pytest.raises(runner.EvalError, match="isn't frozen"):
        runner.check_test_split(runner.load_split("test", splits), splits, base)
    runner.freeze("test", splits, base)
    assert runner.check_test_split(runner.load_split("test", splits), splits, base) == 0
    (splits / "test.runs.json").write_text(json.dumps({"runs": ["r1", "r2", "r3"]}))
    with pytest.raises(runner.EvalError, match="had its 3 runs"):
        runner.check_test_split(runner.load_split("test", splits), splits, base)
    (splits / "test.runs.json").unlink()
    labels = base / "labels" / "a.json"
    labels.write_text(labels.read_text().replace('"bystander"', '"other"'))
    with pytest.raises(runner.EvalError, match="changed since it was frozen"):
        runner.check_test_split(runner.load_split("test", splits), splits, base)


def test_a_test_run_counts_toward_the_cap(base: Path) -> None:
    splits = base / "splits"
    runner.freeze("test", splits, base)
    for n in range(3):
        runner.run(
            "test",
            "full",
            replay=False,
            out=base / "results",
            splits=splits,
            base=base,
            now=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=n),
        )
    assert len(json.loads((splits / "test.runs.json").read_text())["runs"]) == 3
    with pytest.raises(runner.EvalError, match="had its 3 runs"):
        runner.run("test", "full", replay=False, out=base / "results", splits=splits, base=base)


def test_split_errors(base: Path) -> None:
    with pytest.raises(runner.EvalError, match="no clips yet"):
        runner.load_split("hero", base / "splits")
    (base / "splits" / "public.json").write_text(json.dumps({"split": "public", "clips": []}))
    with pytest.raises(runner.EvalError, match="lists no clips"):
        runner.load_split("public", base / "splits")
    (base / "splits" / "hero.json").write_text(json.dumps({"split": "dev", "clips": []}))
    with pytest.raises(runner.EvalError, match="says split"):
        runner.load_split("hero", base / "splits")


def test_cli_help_lists_splits_variants_and_replay(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        runner.main(["--help"])
    out = capsys.readouterr().out
    for word in ("hero", "dev", "public", "--replay", *VARIANTS):
        assert word in out
    assert runner.main(["--split", "hero", "--variant", "full", "--replay"]) == 1


def test_report_tables_link_every_number_and_label_synthetic_runs(base: Path) -> None:
    results = base / "results"
    for n, variant in enumerate(("full", "blur_all")):
        runner.run(
            "dev",
            variant,
            replay=True,
            out=results,
            splits=base / "splits",
            base=base,
            now=datetime(2026, 10, 30, 12, n, tzinfo=UTC),
        )
    runs = report.load_runs(results)
    text = report.render(runs)
    assert "## Split `dev` (synthetic recordings)" in text
    assert "> **Synthetic.**" in text
    full_row = next(line for line in text.splitlines() if line.startswith("| **Safe Cut (full)**"))
    assert "100.0%" in full_row
    assert "(results/20261030T120000Z-dev-full-0123456/metrics.json)" in full_row
    assert "| EgoBlur Gen 2 on every frame | not run |" in text
    assert "$3.00" in text  # the service limits come from config defaults
    assert "Cost: none measured; replay runs make no API calls." in text  # never a $0.00 "measured" claim
    assert report.render(runs) == text  # deterministic
    charts = report.charts(runs, base / "charts")
    assert [c.name for c in charts] == ["dev-synthetic.png"]


def test_report_check_compares_with_the_committed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(report, "OUT", tmp_path / "RESULTS.md")
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n{report.README_START}\nstale\n{report.README_END}\n")
    monkeypatch.setattr(report, "README", readme)
    assert report.main(["--check"]) == 1
    (tmp_path / "RESULTS.md").write_text(report.render([]))
    assert report.main(["--check"]) == 1  # the README's table is still stale
    assert report.main([]) == 0
    assert "No committed runs yet." in readme.read_text()
    assert report.main(["--check"]) == 0


def test_an_egoblur_run_records_the_detector_that_ran_and_the_report_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real prepare stage and the real audit detector, on the committed dev split
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef")  # the report refuses a dirty tree's runs
    root = Path(__file__).resolve().parent.parent
    run_dir = runner.run("dev", "egoblur", replay=True, out=tmp_path / "results")
    config = json.loads((run_dir / "config.json").read_text())
    assert config["detail"]["detector"] in ("egoblur-gen2", "yunet-face")
    text = report.render(report.load_runs(tmp_path / "results"))
    if config["detail"]["detector"] == "yunet-face":
        assert "OpenCV YuNet face detector on every frame (EgoBlur weights not installed)" in text
        assert "| EgoBlur Gen 2 on every frame |" not in text
    assert (root / "eval" / "splits" / "dev.json").is_file()


def test_a_test_run_that_crashes_still_counts(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    splits = base / "splits"
    runner.freeze("test", splits, base)

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Meta went away halfway")

    monkeypatch.setattr(runner, "run_variant", crash)
    with pytest.raises(RuntimeError):
        runner.run("test", "full", replay=False, out=base / "results", splits=splits, base=base)
    assert len(runner.runs_made(splits)) == 1


def test_a_live_run_needs_committed_code_and_stops_at_its_ceiling(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef-dirty")
    with pytest.raises(runner.EvalError, match="uncommitted"):
        runner.run("dev", "full", replay=False, out=base / "results", splits=base / "splits", base=base)
    runner.run("dev", "full", replay=True, out=base / "results", splits=base / "splits", base=base)  # replay may
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef")
    split = json.loads((base / "splits" / "dev.json").read_text())
    split["clips"] *= 2
    (base / "splits" / "dev.json").write_text(json.dumps(split))
    monkeypatch.setattr(pipeline, "job_spend", lambda job_dir: 2.0)
    with pytest.raises(runner.EvalError, match=r"reached --max-usd \$1\.50 after 1 clip"):
        runner.run("dev", "full", replay=False, out=base / "results2", splits=base / "splits", base=base, max_usd=1.5)


def test_the_report_refuses_a_run_made_from_uncommitted_code(base: Path) -> None:
    run_dir = runner.run("dev", "full", replay=True, out=base / "results", splits=base / "splits", base=base)
    config = json.loads((run_dir / "config.json").read_text())
    config["git_sha"] += "-dirty"
    (run_dir / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="uncommitted code"):
        report.load_runs(base / "results")


def test_a_refused_test_run_is_never_counted(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a run that starts paid work uses one of the test split's 3: a dirty tree or a missing hook refuses
    before the counter is written."""
    splits = base / "splits"
    runner.freeze("test", splits, base)
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef-dirty")
    with pytest.raises(runner.EvalError, match="uncommitted"):
        runner.run("test", "full", replay=False, out=base / "results", splits=splits, base=base)
    monkeypatch.setattr(runner, "git_sha", lambda: "0123456789abcdef")

    def missing(variant: str) -> None:
        raise VariantUnavailable("safecut.scout.baselines.muse_keyframe_boxes isn't in this build")

    monkeypatch.setattr(runner, "preflight", missing)
    with pytest.raises(VariantUnavailable):
        runner.run("test", "muse_no_track", replay=False, out=base / "results", splits=splits, base=base)
    assert runner.runs_made(splits) == []


@pytest.mark.parametrize(
    ("variant", "absent"),
    [
        ("full", set()),
        ("no_audit", {"auditor", "redteam"}),
        ("blur_all", {"auditor", "redteam", "roles", "scene", "asr", "escalate"}),
        ("detector_only", {"auditor", "redteam", "roles", "scene", "asr", "escalate"}),
    ],
)
def test_a_run_config_names_only_the_models_that_ran(base: Path, variant: str, absent: set[str]) -> None:
    """AGENTS rule 9: a baseline that skips a stage never claims that stage's model."""
    run_dir = runner.run(
        "dev", cast(Variant, variant), replay=True, out=base / "results", splits=base / "splits", base=base
    )
    models = json.loads((run_dir / "config.json").read_text())["models"]
    assert not absent & set(models), models
    assert "tracks" in models


def test_muse_no_track_never_runs_the_tracker(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The keyframe-boxes baseline needs only prepare: SAM (paid, live) is never called, and the config says so."""
    from eval import variants  # noqa: PLC0415 -- the module whose hook loader is stubbed

    monkeypatch.setattr(variants, "_hook", lambda module, name: lambda job_dir, *, replay: {0: [(0, 0, 4, 4)]})
    run_dir = runner.run("dev", "muse_no_track", replay=True, out=base / "results", splits=base / "splits", base=base)
    models = json.loads((run_dir / "config.json").read_text())["models"]
    assert models == {"keyframe_boxes": "muse-spark-1.3"}
