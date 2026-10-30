"""``scripts/go-live.sh`` (E8): refuses without a key, refuses footage it may not record, and records a whole job
in one command (here against the fake Meta API)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from safecut import pipeline
from safecut.contracts import load
from safecut.meta import replay
from scripts import go_live
from scripts import make_demo_job as demo
from tests.fake_meta import FakeMeta, serving

CLIP = Path("fixtures/clips") / demo.CLIP_NAME


def test_without_a_key_it_exits_2_naming_the_key() -> None:
    env = {k: v for k, v in os.environ.items() if k != "MODEL_API_KEY"}
    argv = ["bash", "scripts/go-live.sh", str(CLIP)]
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=60)  # noqa: S603 -- fixed argv
    message = (proc.stderr or proc.stdout).strip()
    assert proc.returncode == 2
    assert "MODEL_API_KEY" in message
    assert len(message.splitlines()) == 1


def test_refuses_footage_it_may_not_record(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    outside = tmp_path / "street.mp4"
    outside.write_bytes(CLIP.read_bytes())
    assert go_live.main([str(outside), "--out-root", str(tmp_path)]) == 2
    assert "consented" in capsys.readouterr().err
    assert go_live.main([str(tmp_path / "missing.mp4")]) == 2
    assert go_live.main([str(CLIP), "--usd-cap", "40"]) == 2
    assert not (tmp_path / "jobs").exists()


def test_records_a_whole_job_in_one_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("SAFECUT_SAM_FPS", "8")
    with serving(FakeMeta(tmp_path / "jobs" / "live")):
        status = go_live.main([str(CLIP), "--id", "demo-live", "--analyse-only", "--out-root", str(tmp_path)])
    out = tmp_path / "fixtures" / "jobs" / "demo-live"
    manifest = json.loads((out / "raw" / "manifest.json").read_text())
    assert manifest["synthetic"] is False
    assert manifest["demo"] is False
    assert manifest["source_sha256"] == pipeline.sha256_file(CLIP)
    assert manifest["usd"] > 0
    assert manifest["calls"] > 0
    recorded = [load(p, replay.RawCall) for p in (out / "raw").rglob("*.json") if p.name != "manifest.json"]
    assert len(recorded) >= 17
    assert not any(r.synthetic for r in recorded)
    assert (out / "cost.jsonl").is_file()
    assert pipeline.find_recording(manifest["source_sha256"], tmp_path / "fixtures" / "jobs") == out
    assert status in (0, 1)  # 1 only if a later (SAFETY) stage of the analysis failed; SENSE recorded either way


@pytest.mark.parametrize(
    ("given", "want"), [("../..", "clip"), (".", "clip"), ("Hero 1/A", "a"), ("demo-live", "demo-live")]
)
def test_ids_never_escape_fixtures(given: str, want: str) -> None:
    assert go_live.clip_id(Path(given)) == want


def test_an_existing_recording_is_kept_unless_replaced(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "fixtures" / "jobs" / "taken").mkdir(parents=True)
    assert go_live.main([str(CLIP), "--id", "taken", "--out-root", str(tmp_path)]) == 2
    assert "--replace" in capsys.readouterr().err


def test_a_failed_run_never_replaces_an_earlier_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    earlier = tmp_path / "fixtures" / "jobs" / "taken" / "raw"
    earlier.mkdir(parents=True)
    (earlier / "a.json").write_text("{}")
    monkeypatch.setenv("MODEL_API_KEY", "sk-test-not-a-real-key")

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the network went away before any call")

    monkeypatch.setattr(pipeline, "analyse", broken)
    assert go_live.main([str(CLIP), "--id", "taken", "--replace", "--out-root", str(tmp_path)]) == 1
    assert (earlier / "a.json").read_text() == "{}"
    assert not (earlier / "manifest.json").exists()
    assert "kept" in capsys.readouterr().err


def test_relative_paths_are_the_callers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    """go-live.sh changes to the repo root; a clip path relative to where it was run still resolves."""
    repo = Path.cwd()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GO_LIVE_CWD", str(repo))
    assert go_live.main([str(CLIP), "--usd-cap", "40"]) == 2
    err = capsys.readouterr().err
    assert "no such clip" not in err
    assert "--usd-cap" in err


def test_a_swap_killed_halfway_restores_the_earlier_recording(tmp_path: Path) -> None:
    """keep() moves the old recording aside (never deletes it first); a later run puts it back if the swap died."""
    out = tmp_path / "fixtures" / "jobs" / "x"
    old = tmp_path / "fixtures" / ".go-live" / "x.old"
    (old / "raw").mkdir(parents=True)
    (old / "raw" / "a.json").write_text("{}")  # as a crash between the two renames leaves it
    job = tmp_path / "job"
    (job / "raw" / "track").mkdir(parents=True)
    (job / "raw" / "track" / "b.json").write_text("{}")
    go_live.keep(job, out, CLIP)
    assert (out / "raw" / "track" / "b.json").is_file()
    assert not (out / "raw" / "a.json").exists()
    assert not (tmp_path / "fixtures" / ".go-live").exists()
    assert [p.name for p in (tmp_path / "fixtures" / "jobs").iterdir()] == ["x"]  # no stray manifest to match


def test_a_set_aside_recording_still_needs_replace(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "fixtures" / ".go-live" / "taken.old" / "raw").mkdir(parents=True)
    assert go_live.main([str(CLIP), "--id", "taken", "--out-root", str(tmp_path)]) == 2
    assert "--replace" in capsys.readouterr().err


def test_another_ids_leftover_does_not_fail_a_good_swap(tmp_path: Path) -> None:
    (tmp_path / "fixtures" / ".go-live" / "other.staging").mkdir(parents=True)
    job = tmp_path / "job"
    (job / "raw" / "track").mkdir(parents=True)
    (job / "raw" / "track" / "b.json").write_text("{}")
    out = go_live.keep(job, tmp_path / "fixtures" / "jobs" / "x", CLIP)
    assert (out / "raw" / "manifest.json").is_file()


@pytest.mark.parametrize(
    ("given", "want"), [("v1.5", "v1-5"), ("../..", "clip"), ("Hero 1/A", "hero-1-a"), ("a" * 59 + ".b", "a" * 59)]
)
def test_ids_keep_their_dots_as_separators(given: str, want: str) -> None:
    assert go_live.fixture_id(given) == want


def test_a_stopped_run_is_not_reported_as_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from safecut.stages import BY_NAME, StageUnavailable  # noqa: PLC0415 -- only this test stops a run

    monkeypatch.setenv("MODEL_API_KEY", "sk-test-not-a-real-key")

    def stops(job_dir: Path, **_kwargs: object) -> None:
        (job_dir / "raw" / "track").mkdir(parents=True)
        (job_dir / "raw" / "track" / "a.json").write_text("{}")
        raise StageUnavailable(BY_NAME["decide"])

    monkeypatch.setattr(pipeline, "analyse", stops)
    assert go_live.main([str(CLIP), "--id", "stopped", "--out-root", str(tmp_path)]) == 1
    assert (tmp_path / "fixtures" / "jobs" / "stopped" / "raw" / "track" / "a.json").is_file()  # still kept
