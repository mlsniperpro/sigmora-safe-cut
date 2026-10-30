"""Failure paths of the SENSE stages, against the fake Meta API with injected errors: every failure is written down
(``failed``/``skipped``, ``failed_votes``, no suggestion) and none ever produces evidence to keep someone."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
from pydantic import SecretStr

from safecut import pipeline, prepare
from safecut.config import Settings
from safecut.contracts import FilesIndex, Roles, Scene, Transcript, load, validate_job_dir
from safecut.meta import replay
from safecut.scout import roles, scene
from safecut.speech import stage as speech
from safecut.track import stage as track_stage
from scripts import make_demo_job as demo
from tests.fake_meta import FakeMeta, serving

CLIP = Path("fixtures/clips") / demo.CLIP_NAME
DEMO = Path("fixtures/jobs/demo")


def live(**update: object) -> Settings:
    return Settings(model_api_key=SecretStr("sk-test-not-a-real-key"), sam_fps=8).model_copy(update=update)


@pytest.fixture
def tracked(tmp_path: Path) -> Path:
    """A demo job through ``track`` (replayed: the base sweeps aren't under test here)."""
    job = tmp_path / "demo"
    pipeline.create_job(CLIP, job, mode="live")
    prepare.run(job)
    shutil.copytree(DEMO / replay.RAW / track_stage.RAW_STAGE, job / replay.RAW / track_stage.RAW_STAGE)
    asyncio.run(track_stage.run_async(job, replay_mode=True, settings=Settings(replay=True)))
    return job


def valid(job: Path) -> None:
    """``validate_job_dir`` without ``files.json``: these jobs replay ``track`` (recorded against another upload)
    and run the later stages live, so the SAM requests' file IDs belong to a different upload by construction."""
    copy = job.parent / "copy" / job.name
    shutil.copytree(job, copy, ignore=shutil.ignore_patterns("files.json"))
    validate_job_dir(copy)
    shutil.rmtree(copy.parent)


def run(job: Path, fake: FakeMeta, *stages: str, settings: Settings | None = None) -> None:
    modules = {"transcribe": speech.run_async, "scene": scene.run_async, "roles": roles.run_async}
    with serving(fake):
        for name in stages:
            asyncio.run(modules[name](job, settings=settings or live()))


def test_voice_transcribe_down_falls_back_to_spark_12(tracked: Path) -> None:
    fake = FakeMeta(tracked, fail={"asr"})
    run(tracked, fake, "transcribe")
    transcript = load(tracked / "transcript.json", Transcript)
    assert transcript.status == "ok"
    assert transcript.source_kind == "fallback"
    assert transcript.source == "muse-spark-1.2"
    assert not transcript.degraded
    assert [t.speaker for t in transcript.turns] == ["S1", "S1", "S2", "S1"]
    assert fake.calls.count("asr") == 2  # ASR 500 → retry once (PRE-A §4.2), then the fallback
    assert "speech_fallback" in fake.calls
    assert load(tracked / "files.json", FilesIndex).all_deleted
    assert load(replay.path(tracked, speech.ASR_STAGE, speech.ASR_KEY), replay.RawCall).failure() is not None


def test_spark_12_as_the_configured_source(tracked: Path) -> None:
    fake = FakeMeta(tracked)
    run(tracked, fake, "transcribe", settings=live(speech_source="spark-1.2"))
    assert "asr" not in fake.calls
    assert load(tracked / "transcript.json", Transcript).source_kind == "fallback"


def test_both_speech_paths_fail(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"asr", "speech_fallback"}), "transcribe")
    transcript = load(tracked / "transcript.json", Transcript)
    assert (transcript.status, transcript.degraded, transcript.turns, transcript.source) == ("failed", True, [], None)
    valid(tracked)


def test_a_budget_stop_skips_speech(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked), "transcribe", settings=live(job_usd_cap=0.0001))
    transcript = load(tracked / "transcript.json", Transcript)
    assert (transcript.status, transcript.degraded) == ("skipped", True)
    failure = load(replay.path(tracked, speech.ASR_STAGE, speech.ASR_KEY), replay.RawCall).failure()
    assert failure is not None
    assert failure[0] == "budget"


def test_a_failed_scene_pass_is_written_down(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"scene_pass"}), "transcribe", "scene")
    found = load(tracked / "scene.json", Scene)
    assert (found.status, found.model, found.participants) == ("failed", None, [])
    assert found.summary.startswith("scene pass failed")
    assert load(tracked / "files.json", FilesIndex).all_deleted


def test_one_failed_vote_blocks_every_keep(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"role_pass:3"}), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"  # a partial failure stays ok and shows in failed_votes (vector A8)
    assert result.tracks
    assert all(t.failed_votes == 1 for t in result.tracks)
    assert "participant" not in {t.role for t in result.tracks}
    assert all(t.votes[2] == "unsure" for t in result.tracks)
    valid(tracked)


def test_every_vote_failing_fails_the_role_pass(tracked: Path) -> None:
    fake = FakeMeta(tracked, fail={"role_pass"})
    run(tracked, fake, "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert (result.status, result.model) == ("failed", None)
    assert {t.role for t in result.tracks} == {"unsure"}
    assert all(not t.escalated for t in result.tracks)
    assert "escalation" not in fake.calls  # nothing to dispute without a judgement
    assert "sam" not in fake.calls  # and no miss loop
    valid(tracked)


def test_a_failed_escalation_suggests_nothing(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"escalation"}), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    disputed = [t for t in result.tracks if t.role == "unsure"]
    assert disputed
    assert all((t.escalated, t.suggested_role, t.escalation_evidence) == (False, None, None) for t in disputed)


def test_a_failed_miss_loop_request_leaves_a_static_box(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"sam"}), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert [m.sam_phrase for m in result.missed] == ["envelope"]
    tracks = load(tracked / "tracks.json", demo.Tracks)
    static = [t for t in tracks.tracks if t.origin == "static"]
    assert [t.track_id for t in static] == result.missed[0].track_ids
    assert static[0].boxes[result.missed[0].frame] == result.missed[0].box
    valid(tracked)
