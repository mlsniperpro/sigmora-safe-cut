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
