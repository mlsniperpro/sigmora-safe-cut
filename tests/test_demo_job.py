"""The synthetic demo job: its recordings are labelled synthetic and valid, rebuild byte for byte, and replay through
every SENSE stage to the roles the scene was written to have."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from safecut import pipeline, prepare
from safecut.config import Settings
from safecut.contracts import Roles, Scene, Tracks, Transcript, load, validate_job_dir
from safecut.meta import replay, sam
from safecut.scout import roles, scene
from safecut.speech import stage as speech
from safecut.track import stage as track_stage
from safecut.track.axes import backfill_frames
from scripts import make_demo_job as demo

DEMO = Path("fixtures/jobs/demo")
RAW = DEMO / replay.RAW
MANIFEST = json.loads((RAW / "manifest.json").read_text())


def test_manifest_names_the_clip_and_its_truth() -> None:
    assert MANIFEST["demo"] is True
    assert MANIFEST["synthetic"] is True
    clip = Path(MANIFEST["source"])
    assert clip.is_file()
    assert MANIFEST["source_sha256"] == prepare.sha256_file(clip)
    truth = json.loads(Path(MANIFEST["truth"]).read_text())
    assert truth["clip"] == clip.name
    assert {e["id"]: e["should_hide"] for e in truth["entities"]} == {
        "e1": False, "e2": False, "e3": True, "e4": True, "e5": True, "e6": True, "e7": True,
    }  # fmt: skip
    for entity in truth["entities"]:
        rows = (Path(MANIFEST["truth"]).parent / entity["boxes"]).read_text().splitlines()
        assert int(rows[0].split(",")[0]) - 1 == entity["frames"]["first"]
        assert int(rows[-1].split(",")[0]) - 1 == entity["frames"]["last"]


def test_every_recording_is_synthetic_and_parses() -> None:
    recordings = sorted(p for p in RAW.rglob("*.json") if p.name != "manifest.json")
    assert len(recordings) >= 15
    for path in recordings:
        call = load(path, replay.RawCall)
        assert call.synthetic, path
        assert call.usd == 0
        if path.parent.name == "sam":
            assert call.events is not None
            asyncio.run(sam.parse_video_events(call.events))  # the same parser live responses go through


def test_pipeline_finds_the_recording_by_sha256() -> None:
    found = pipeline.find_recording(MANIFEST["source_sha256"])
    assert found is not None
    assert found.resolve() == DEMO.resolve()


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    job = tmp_path_factory.mktemp("demo") / "demo"
    pipeline.create_job(Path(MANIFEST["source"]), job, mode="replay")
    pipeline.attach_recording(job, DEMO)
    settings = Settings(replay=True)
    prepare.run(job)
    asyncio.run(track_stage.run_async(job, replay_mode=True, settings=settings))
    asyncio.run(speech.run_async(job, replay_mode=True, settings=settings))
    asyncio.run(scene.run_async(job, replay_mode=True, settings=settings))
    asyncio.run(roles.run_async(job, replay_mode=True, settings=settings))
    return job


def test_replay_writes_valid_contracts(replayed: Path) -> None:
    loaded = validate_job_dir(replayed)
    assert {"job.json", "tracks.json", "transcript.json", "scene.json", "roles.json"} <= set(loaded)
    transcript = load(replayed / "transcript.json", Transcript)
    assert transcript.source_kind == "primary"
    assert [t.speaker for t in transcript.turns] == ["S1", "S1", "S2", "S1"]
    found = load(replayed / "scene.json", Scene)
    assert [p.introduced_in_turn for p in found.participants] == [0, 1]


def _entity(track_id: str, replayed: Path) -> str | None:
    tracks = {t.track_id: t for t in load(replayed / "tracks.json", Tracks).tracks}
    return demo.entity_of(tracks[track_id])


def test_roles_match_the_scene(replayed: Path) -> None:
    result = load(replayed / "roles.json", Roles)
    assert result.status == "ok"
    by_entity: dict[str | None, set[str]] = {}
    for t in result.tracks:
        by_entity.setdefault(_entity(t.track_id, replayed), set()).add(t.role)
    assert by_entity["e1"] == {"participant"}
    assert by_entity["e2"] == {"participant"}
    assert by_entity["e3"] == {"bystander", "unsure"}  # the re-entry is a new ID, disputed and escalated
    assert by_entity["e4"] == {"child"}
    reentered = [t for t in result.tracks if t.role == "unsure"]
    assert reentered
    assert all(t.escalated and t.suggested_role == "bystander" for t in reentered)
    tracks = {t.track_id: t for t in load(replayed / "tracks.json", Tracks).tracks}
    assert all(tracks[t.track_id].reentry_of is not None for t in reentered)
    assert {o.track_id: o.sensitive for o in result.objects} == {
        "license plate:1": True, "screen:1": True, "envelope:1": True,
    }  # fmt: skip
    assert [m.track_ids for m in result.missed] == [["envelope:1"]]  # found by the miss loop, not the base sweep


def test_tracks_follow_the_truth(replayed: Path) -> None:
    tracks = load(replayed / "tracks.json", Tracks)
    for track in tracks.tracks:
        entity = _entity(track.track_id, replayed)
        assert entity is not None, track.track_id
        for frame, box in track.boxes.items():
            truth = (demo.face_box if track.concept == "face" else
                     demo.person_box if track.concept == "person" else demo.object_box)(entity, frame)  # fmt: skip
            if truth is not None:
                assert demo.iou(box, truth) >= 0.8, (track.track_id, frame)


def test_rebuild_is_byte_identical(tmp_path: Path) -> None:
    demo.main(tmp_path)
    for path in [Path(MANIFEST["source"]), *sorted(p for p in DEMO.rglob("*") if p.is_file())]:
        rebuilt = tmp_path / path
        assert rebuilt.is_file(), path
        assert rebuilt.read_bytes() == path.read_bytes(), path


def test_every_hidden_entity_is_covered_on_every_visible_frame(replayed: Path) -> None:
    """E3, perception side: a track box covers ≥ 95% of each should-hide entity's labelled box on each visible
    frame, or the frame is inside the back-fill before the track or the extension after it (which the guard holds)."""
    tracks = load(replayed / "tracks.json", Tracks).tracks
    backfill = backfill_frames(30, 8)
    by_entity: dict[str, list[Any]] = {}
    for track in tracks:
        entity = demo.entity_of(track)
        assert entity is not None
        by_entity.setdefault(entity, []).append(track)
    for entity in ("e3", "e4", "e5", "e6", "e7"):
        for frame in range(demo.FRAMES):
            truth = demo.truth_box(entity, frame)
            if truth is None:
                continue
            area = (truth[2] - truth[0]) * (truth[3] - truth[1])
            held = any(t.first - backfill <= frame < t.first or t.last < frame <= t.last + 8 for t in by_entity[entity])
            covered = any(
                (b := t.boxes.get(frame)) is not None and overlap(b, truth) >= 0.95 * area for t in by_entity[entity]
            )
            assert covered or held, (entity, frame)


def overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
