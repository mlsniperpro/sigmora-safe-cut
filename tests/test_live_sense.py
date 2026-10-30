"""Live tests for every Meta call the SENSE stages make (E8). Deselected by default; ``uv run pytest -m live``.

Each runs the real stage code on the synthetic counter clip, under a $0.50 job cap, in a temporary job directory,
and checks what was recorded. Spend for the whole module is about $0.10 (SAM's 50-frame minimum, a 3 s clip).
Without ``MODEL_API_KEY`` they're skipped (the only skip E11 allows).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from safecut import prepare
from safecut.config import Settings, load_settings
from safecut.contracts import FilesIndex, Roles, Scene, Tracks, Transcript, load, read_cost_lines
from safecut.meta import replay
from safecut.meta.files import FileStore
from safecut.meta.session import job_client
from safecut.scout import calls, roles, scene, votes
from safecut.speech import stage as speech
from safecut.track import stage as track_stage
from safecut.track.synthetic import record_sweep

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MODEL_API_KEY"), reason="needs MODEL_API_KEY (owner input)"),
]
CLIP = Path("fixtures/clips/counter_30fps_audio.mp4")


def settings() -> Settings:
    return load_settings().model_copy(update={"job_usd_cap": 0.50, "replay": False})


@pytest.fixture
def job(tmp_path: Path) -> Path:
    job_dir = tmp_path / "live_sense"
    prepare.prepare(CLIP, job_dir)
    return job_dir


def billed(job_dir: Path) -> float:
    return sum(line.usd for line in read_cost_lines(job_dir / "cost.jsonl"))


@pytest.mark.entry("E8:files")
async def test_files_upload_and_delete(job: Path) -> None:
    async with job_client(job, settings()) as client:
        store = FileStore(client, job)
        file_id = await store.upload(job / "prepared.mp4", "prepared.mp4")
        assert file_id.startswith(("file-", "file_"))
        assert await store.delete_all()
    assert load(job / "files.json", FilesIndex).all_deleted


@pytest.mark.entry("E8:sam")
async def test_sam_sweep_is_recorded_and_parsed(job: Path) -> None:
    await track_stage.run_async(job, concepts=("face",), settings=settings())
    tracks = load(job / "tracks.json", Tracks)
    assert [r.kind for r in tracks.requests] == ["phrase"]
    assert tracks.requests[0].frames_billed >= 1
    recorded = load(replay.path(job, track_stage.RAW_STAGE, "phrase-face"), replay.RawCall)
    assert not recorded.synthetic
    assert recorded.events
    assert load(job / "files.json", FilesIndex).all_deleted  # AGENTS rule 6
    assert 0 < billed(job) < 0.05


@pytest.mark.entry("E8:voice_transcribe")
async def test_voice_transcribe(job: Path) -> None:
    await speech.run_async(job, settings=settings())
    transcript = load(job / "transcript.json", Transcript)
    assert transcript.status == "ok"
    assert transcript.source_kind == "primary"
    assert replay.exists(job, speech.ASR_STAGE, speech.ASR_KEY)


@pytest.mark.entry("E8:muse_scene")
async def test_scene_pass(job: Path) -> None:
    await scene.run_async(job, settings=settings())
    found = load(job / "scene.json", Scene)
    assert found.status == "ok"
    assert load(job / "files.json", FilesIndex).all_deleted


def _synthetic_tracks(job: Path) -> None:
    """Two face tracks drawn from the counter clip's truth (SAM finds nothing on coloured squares)."""
    job_info = load(job / "job.json", prepare.Job)
    proxy = track_stage.make_proxy(job, job_info, settings())
    import json  # noqa: PLC0415

    from safecut.track.axes import from_proxy_table  # noqa: PLC0415 -- test-only helper import

    truth = json.loads(Path("fixtures/clips/truth.json").read_text())[CLIP.name]["boxes_half_open"]
    table = from_proxy_table(job_info.frames, job_info.fps, proxy.fps, proxy.frames)
    objects = {"0": {j: tuple(truth[str(f)]["red"]) for j, f in enumerate(table)},
               "1": {j: tuple(truth[str(f)]["blue"]) for j, f in enumerate(table)}}  # fmt: skip
    for concept in track_stage.CONCEPTS:
        record_sweep(job, text=concept, objects=objects if concept == "face" else {}, size=(320, 180),
                     proxy_frames=proxy.frames, model="sam-3.1")  # fmt: skip
    asyncio.run(track_stage.run_async(job, replay_mode=True, settings=settings()))
    shutil.rmtree(job / replay.RAW / track_stage.RAW_STAGE)


@pytest.mark.entry("E8:muse_role")
def test_role_pass_three_votes(job: Path) -> None:
    _synthetic_tracks(job)
    asyncio.run(roles.run_async(job, settings=settings()))
    result = load(job / "roles.json", Roles)
    assert result.status == "ok"
    for k in (1, 2, 3):
        recorded = load(replay.path(job, roles.VOTE_STAGE, f"pass1-w0-v{k}"), replay.RawCall)
        assert recorded.failure() is None
    assert all(len(t.votes) == 3 for t in result.tracks)


@pytest.mark.entry("E8:muse_escalate")
def test_escalation_at_max_effort(job: Path) -> None:
    _synthetic_tracks(job)
    tracks = load(job / "tracks.json", Tracks)
    ballot = votes.Vote(tracks={"face:1": votes.TrackVote("participant", "near the creator", (0, 30))})
    split = votes.Vote(tracks={"face:1": votes.TrackVote("bystander", "background", (30,))})

    async def go() -> dict[str, votes.Escalation]:
        async with job_client(job, settings()) as client:
            ctx = calls.Context(job_dir=job, job=load(job / "job.json", prepare.Job), settings=settings(),
                                replay=False, client=client, store=FileStore(client, job))  # fmt: skip
            return await roles.escalate(ctx, tracks=tracks, disputed=["face:1"],
                                        ballots_of={"face:1": [[ballot, ballot, split]]},
                                        context_summary="Two coloured squares move across a grey frame.",
                                        transcript_frames="none (no speech was recognised)")  # fmt: skip

    out = asyncio.run(go())
    assert out["face:1"].role in ("unsure", "child")
    recorded = load(replay.path(job, roles.ESCALATE_STAGE, "w0"), replay.RawCall)
    assert recorded.failure() is None
    assert recorded.request["effort"] == "max"
