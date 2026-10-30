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


def test_a_failed_proxy_upload_in_the_miss_loop_leaves_a_static_box(tracked: Path) -> None:
    run(tracked, FakeMeta(tracked, fail={"upload"}), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"
    assert [m.sam_phrase for m in result.missed] == ["envelope"]
    tracks = load(tracked / "tracks.json", demo.Tracks)
    assert {t.origin for t in tracks.tracks if t.track_id in result.missed[0].track_ids} == {"static"}


def test_an_unusable_miss_loop_answer_leaves_a_static_box(tracked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A SAM answer the linker rejects (e.g. a frame past the proxy) never crashes ``roles``: static boxes instead."""
    from safecut.scout import missloop  # noqa: PLC0415 -- patched only here

    def reject(*_args: object, **_kwargs: object) -> None:
        raise track_stage.TrackError("SAM answered frame 10064, past the proxy's 96 frames (objects-loop1)")

    monkeypatch.setattr(missloop.track_stage, "build", reject)
    run(tracked, FakeMeta(tracked), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"
    assert [m.sam_phrase for m in result.missed] == ["envelope"]
    tracks = load(tracked / "tracks.json", demo.Tracks)
    assert {t.origin for t in tracks.tracks if t.track_id in result.missed[0].track_ids} == {"static"}
    valid(tracked)


def test_the_role_re_pass_never_spends_the_audit_reserve(tracked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 6: the loop-1 re-pass runs only if its worst case plus the audit reserve fits; else it is skipped and
    loop 1's tracks stay hidden (no role for them), and roles.json is still written."""
    from safecut.scout import missloop  # noqa: PLC0415 -- patched only here

    run(tracked, FakeMeta(tracked), "transcribe", "scene")
    twin = tracked.parent / "twin" / tracked.name
    shutil.copytree(tracked, twin)
    full = FakeMeta(twin)
    run(twin, full, "roles")
    assert full.calls.count("role_pass") == 6  # pass 1 and the loop-1 re-pass, three votes each
    monkeypatch.setattr(missloop, "ROLE_TEXT_BYTES", 10**9)  # a re-pass far over any job cap
    short = FakeMeta(tracked)
    run(tracked, short, "roles")
    assert short.calls.count("role_pass") == 3
    assert "sam" in short.calls  # loop 1's SAM request still fitted
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"
    assert [m.sam_phrase for m in result.missed] == ["envelope"]
    assert result.missed[0].track_ids
    assert not {o.track_id for o in result.objects} & set(result.missed[0].track_ids)  # unjudged: stays hidden
    valid(tracked)


def test_a_proxy_that_cannot_be_rebuilt_leaves_static_boxes(tracked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure outside any Meta call in the miss loop (the proxy can't be rebuilt or doesn't match) never crashes
    ``roles``: the paid votes are kept and every miss gets a static box (re-audit 4, M1)."""
    from safecut.scout import missloop  # noqa: PLC0415 -- patched only here

    def broken(*_args: object, **_kwargs: object) -> None:
        raise track_stage.TrackError("proxy is 97 frames at 8 fps; tracks.json was made from 96 at 8")

    monkeypatch.setattr(missloop.track_stage, "proxy_for", broken)
    run(tracked, FakeMeta(tracked), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"
    tracks = load(tracked / "tracks.json", demo.Tracks)
    assert {t.origin for t in tracks.tracks if t.track_id in result.missed[0].track_ids} == {"static"}
    valid(tracked)


def test_a_ledger_that_cannot_answer_refuses_the_spend(tracked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from safecut.meta.client import MetaClient  # noqa: PLC0415 -- patched only here
    from safecut.meta.errors import MetaUnavailable  # noqa: PLC0415

    async def down(*_args: object, **_kwargs: object) -> None:
        raise MetaUnavailable("ledger unreachable")

    monkeypatch.setattr(MetaClient, "preflight", down)
    fake = FakeMeta(tracked)
    run(tracked, fake, "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    assert result.status == "ok"
    assert "sam" not in fake.calls  # no budget answer, no miss-loop spend
    assert "escalation" not in fake.calls  # nor escalation
    tracks = load(tracked / "tracks.json", demo.Tracks)
    assert {t.origin for t in tracks.tracks if t.track_id in result.missed[0].track_ids} == {"static"}


def test_a_prompt_track_away_from_the_miss_does_not_cover_it(tracked: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An object-prompt answer that doesn't hold the reported point near its frame keeps its SAM track, but the miss
    gets a static box too (re-audit 4, M3)."""
    from safecut.scout import missloop  # noqa: PLC0415 -- patched only here

    monkeypatch.setattr(missloop, "covers", lambda *_a, **_k: False)
    run(tracked, FakeMeta(tracked), "transcribe", "scene", "roles")
    result = load(tracked / "roles.json", Roles)
    tracks = {t.track_id: t for t in load(tracked / "tracks.json", demo.Tracks).tracks}
    assert [tracks[i].origin for i in result.missed[0].track_ids] == ["static"]
    assert any(t.origin == "sam" and t.concept == "envelope" for t in tracks.values())  # SAM's track is kept


def test_a_resumed_roles_stage_re_bills_nothing_and_writes_the_same_files(tracked: Path) -> None:
    """``roles`` appends the miss loop's tracks to tracks.json, so a resumed ``analyse`` re-runs ``track`` and
    ``roles``. Both reuse this job's own live answers: no call is re-billed and every file comes out the same
    (re-audit 4, M2)."""
    fake = FakeMeta(tracked)
    settings = live()
    with serving(fake):
        asyncio.run(track_stage.run_async(tracked, settings=settings))  # live answers (the fixture's are synthetic)
    run(tracked, fake, "transcribe", "scene", "roles")
    first = {name: (tracked / name).read_bytes() for name in ("tracks.json", "roles.json")}
    paid = list(fake.calls)
    with serving(fake):
        asyncio.run(track_stage.run_async(tracked, settings=settings))
        asyncio.run(roles.run_async(tracked, settings=settings))
    assert fake.calls[len(paid) :] == []
    assert {name: (tracked / name).read_bytes() for name in first} == first


def test_only_sweeps_that_ran_count_as_searched(tracked: Path) -> None:
    from safecut.contracts import Job, Tracks  # noqa: PLC0415 -- only this test builds a loop by hand
    from safecut.scout import calls, miss, missloop  # noqa: PLC0415

    job = load(tracked / "job.json", Job)
    ctx = calls.Context(job_dir=tracked, job=job, settings=Settings(replay=True, miss_sam="stub"), replay=True)
    raw = miss.RawMiss(what="a laptop", sam_phrase="laptop", frame=0, point=(500, 500), box=None, recurs=True)
    item = miss.validate(raw, sent=frozenset({0}), width=job.width, height=job.height)
    assert item is not None
    planned = miss.plan([item], swept=[])
    assert planned.sweeps
    tracks = load(tracked / "tracks.json", Tracks)
    out = asyncio.run(missloop.run_loop(ctx, tracks, prompts_=planned.prompts, sweeps=planned.sweeps,
                                        static=planned.static, loop=1))  # fmt: skip
    assert out.swept == []  # stubbed: nothing was searched, so loop 2 may still sweep "laptop"
