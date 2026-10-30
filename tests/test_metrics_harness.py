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
    assert config["models"]["sam"] == "sam-3.1"
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


@pytest.mark.parametrize("variant", ["egoblur", "muse_no_track"])
def test_hook_variants_say_which_lane_hook_is_missing(tmp_path: Path, variant: str) -> None:
    job = tmp_path / "j"
    pipeline.create_job(CLIP, job, mode="replay")
    with pytest.raises(VariantUnavailable, match="baselines"):
        run_variant(cast(Variant, variant), job, replay=True)


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
    assert report.render(runs) == text  # deterministic
    charts = report.charts(runs, base / "charts")
    assert [c.name for c in charts] == ["dev-synthetic.png"]


def test_report_check_compares_with_the_committed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(report, "OUT", tmp_path / "RESULTS.md")
    assert report.main(["--check"]) == 1
    (tmp_path / "RESULTS.md").write_text(report.render([]))
    assert report.main(["--check"]) == 0
