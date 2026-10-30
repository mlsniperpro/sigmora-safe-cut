"""The live code paths of every SENSE stage, against a fake Meta API (respx) that answers like the demo responder.

Proves, without a key, what happens the moment one exists: uploads go to the Files API and are deleted, SAM and Muse
stream over SSE, Voice Transcribe gets its multipart, every call lands in ``cost.jsonl`` and ``raw/`` (not
synthetic), and the stages write the same contracts a replay of those recordings writes.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut import pipeline, prepare
from safecut.config import Settings
from safecut.contracts import FilesIndex, Tracks, load, read_cost_lines
from safecut.meta import replay
from safecut.meta.errors import MetaBadRequest
from safecut.scout import roles, scene
from safecut.speech import stage as speech
from safecut.track import stage as track_stage
from scripts import make_demo_job as demo
from tests.conftest import BASE
from tests.fake_meta import FakeMeta, serving

CLIP = Path("fixtures/clips") / demo.CLIP_NAME


@pytest.fixture
def prepared(tmp_path: Path) -> Path:
    job = tmp_path / "demo"
    pipeline.create_job(CLIP, job, mode="live")
    prepare.run(job)
    return job


@pytest.fixture
def live_job(prepared: Path) -> Iterator[tuple[Path, FakeMeta]]:
    job = prepared
    fake = FakeMeta(job)
    with serving(fake):
        yield job, fake


def test_every_sense_stage_runs_live_and_matches_its_replay(live_job: tuple[Path, FakeMeta], tmp_path: Path) -> None:
    job, fake = live_job
    settings = Settings(model_api_key=SecretStr("sk-test-not-a-real-key"), sam_fps=8)
    asyncio.run(track_stage.run_async(job, settings=settings))
    asyncio.run(speech.run_async(job, settings=settings))
    asyncio.run(scene.run_async(job, settings=settings))
    asyncio.run(roles.run_async(job, settings=settings))

    # Uploads: the proxy for SAM, prepared.mp4 for the scene pass; every one deleted (AGENTS rule 6).
    assert fake.files
    assert not any(fake.files.values())
    assert load(job / "files.json", FilesIndex).all_deleted
    assert fake.calls.count("sam") == len(track_stage.CONCEPTS) + 1  # the base sweep and the miss loop prompt
    assert fake.calls.count("role_pass") == 6  # three votes, then three for the re-pass
    assert {"asr", "scene_pass", "escalation"} <= set(fake.calls)

    # Every call billed and recorded, nothing labelled synthetic.
    stages = {line.stage for line in read_cost_lines(job / "cost.jsonl") if line.usd > 0}
    assert {"track", "speech", "scene", "roles", "escalate", "miss_loop"} <= stages
    recorded = [load(p, replay.RawCall) for p in (job / replay.RAW).rglob("*.json")]
    assert len(recorded) == 17
    assert not any(r.synthetic for r in recorded)
    assert sum(r.usd for r in recorded) > 0

    # A replay of what was just recorded writes the same contracts.
    again = tmp_path / "again" / "demo"
    pipeline.create_job(CLIP, again, mode="replay")
    shutil.copytree(job / replay.RAW, again / replay.RAW)
    prepare.run(again)
    replay_settings = Settings(replay=True, sam_fps=8)
    asyncio.run(track_stage.run_async(again, replay_mode=True, settings=replay_settings))
    asyncio.run(speech.run_async(again, replay_mode=True, settings=replay_settings))
    asyncio.run(scene.run_async(again, replay_mode=True, settings=replay_settings))
    asyncio.run(roles.run_async(again, replay_mode=True, settings=replay_settings))
    for name in ("transcript.json", "scene.json", "roles.json"):
        assert (again / name).read_bytes() == (job / name).read_bytes(), name
    live_tracks, replayed_tracks = load(job / "tracks.json", Tracks), load(again / "tracks.json", Tracks)
    assert live_tracks.tracks == replayed_tracks.tracks
    assert [r.file_id for r in live_tracks.requests] == [r.file_id for r in replayed_tracks.requests]
    assert all(r.usd > 0 for r in live_tracks.requests)
    assert all(r.usd == 0 for r in replayed_tracks.requests)


def test_a_failed_sweep_fails_the_track_stage(prepared: Path) -> None:
    job = prepared
    settings = Settings(model_api_key=SecretStr("sk-test-not-a-real-key"), sam_fps=8)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post("files").mock(return_value=httpx.Response(200, json={"id": "file-9", "object": "file"}))
        router.get("files").mock(return_value=httpx.Response(200, json={"data": [], "has_more": False}))
        router.delete(path__regex=r"/files/file-9$").mock(return_value=httpx.Response(200, json={"deleted": True}))
        router.post("responses").mock(return_value=httpx.Response(400, json={"error": {"message": "bad", "type": "x"}}))
        with pytest.raises(MetaBadRequest):
            asyncio.run(track_stage.run_async(job, settings=settings))
    assert load(job / "files.json", FilesIndex).all_deleted  # deleted even when the stage fails
    assert not (job / "tracks.json").exists()  # never a partial tracks.json


def test_a_rerun_reuses_this_jobs_sam_answers(live_job: tuple[Path, FakeMeta]) -> None:
    job, fake = live_job
    settings = Settings(model_api_key=SecretStr("sk-test-not-a-real-key"), sam_fps=8)
    asyncio.run(track_stage.run_async(job, settings=settings))
    first = fake.calls.count("sam")
    tracks = (job / "tracks.json").read_bytes()
    asyncio.run(track_stage.run_async(job, settings=settings))
    assert fake.calls.count("sam") == first  # nothing re-billed (PRE-A §10.4 checkpoints)
    assert load(job / "tracks.json", Tracks).tracks == Tracks.model_validate_json(tracks).tracks
