"""The track stage end to end in replay, on the synthetic counter clip with SAM streams written from truth.json."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from safecut import prepare
from safecut.config import Settings
from safecut.contracts import Tracks, load, rle_runs, validate_job_dir
from safecut.meta import replay, sam
from safecut.meta.errors import MetaIncomplete, MetaRefusal
from safecut.track import stage
from safecut.track.axes import from_proxy_table
from safecut.track.synthetic import events, record_sweep, stream_text

CLIP = Path("fixtures/clips/counter_30fps_audio.mp4")
TRUTH = json.loads(Path("fixtures/clips/truth.json").read_text())[CLIP.name]
SIZE = (320, 180)
#: The blue square vanishes for these proxy frames: a gap of 5 > gap_merge_frames, so it comes back as a new ID.
GONE = range(8, 13)


def iou(a: list[int] | tuple[int, ...], b: list[int] | tuple[int, ...]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union


@pytest.fixture(scope="module")
def tracked(tmp_path_factory: pytest.TempPathFactory) -> Path:
    job_dir = tmp_path_factory.mktemp("jobs") / "j_counter"
    prepare.prepare(CLIP, job_dir)
    settings = Settings(replay=True)
    job = load(job_dir / "job.json", prepare.Job)
    proxy = stage.make_proxy(job_dir, job, settings)
    table = from_proxy_table(job.frames, job.fps, proxy.fps, proxy.frames)
    truth = TRUTH["boxes_half_open"]
    red = {j: tuple(truth[str(f)]["red"]) for j, f in enumerate(table)}
    blue = {j: tuple(truth[str(f)]["blue"]) for j, f in enumerate(table) if j not in GONE}
    for concept in stage.CONCEPTS:
        objects: dict[str, Any] = {"3": red, "7": blue} if concept == "face" else {}
        record_sweep(job_dir, text=concept, objects=objects, size=SIZE, proxy_frames=proxy.frames,
                     model=settings.sam_model, shapes={"3": "ellipse"})  # fmt: skip
    asyncio.run(stage.run_async(job_dir, replay_mode=True, settings=settings))
    return job_dir


def test_tracks_validate_and_match_truth(tracked: Path) -> None:
    loaded = validate_job_dir(tracked)
    tracks = loaded["tracks.json"]
    assert isinstance(tracks, Tracks)
    assert tracks.sam_fps == 8
    assert tracks.sam_frames == 24
    assert tracks.concepts == list(stage.CONCEPTS)
    assert [r.kind for r in tracks.requests] == ["phrase"] * 7
    assert [r.matches for r in tracks.requests] == [2, 0, 0, 0, 0, 0, 0]
    by_id = {t.track_id: t for t in tracks.tracks}
    assert sorted(by_id) == ["face:1", "face:2", "face:3"]
    truth = TRUTH["boxes_half_open"]
    colour = {"face:1": "red", "face:2": "blue", "face:3": "blue"}
    for track_id, track in by_id.items():
        assert list(track.boxes) == list(range(track.first, track.last + 1))  # densified, no holes
        for frame, box in track.boxes.items():
            assert iou(box, truth[str(frame)][colour[track_id]]) >= 0.8, (track_id, frame)
        assert set(track.masks) == set(track.conf)
        assert track.masks
        assert all(track.conf[f] == pytest.approx(0.9) for f in track.conf)


def test_reentry_is_a_new_id(tracked: Path) -> None:
    tracks = load(tracked / "tracks.json", Tracks)
    by_id = {t.track_id: t for t in tracks.tracks}
    first, again = by_id["face:2"], by_id["face:3"]
    assert first.reentry_of is None
    assert again.reentry_of == "face:2"
    assert first.last < again.first
    assert first.sam_object == again.sam_object  # one SAM object, split on the gap
    assert by_id["face:1"].reentry_of is None


def test_masks_are_frame_sized_and_inside_their_boxes(tracked: Path) -> None:
    tracks = load(tracked / "tracks.json", Tracks)
    for track in tracks.tracks:
        for frame, rle in track.masks.items():
            assert tuple(rle.size) == (180, 320)
            runs = rle_runs(rle.counts)
            flat = np.repeat(np.arange(len(runs)) % 2, runs).astype(bool)
            img = flat.reshape(320, 180).T
            ys, xs = np.nonzero(img)
            x1, y1, x2, y2 = track.boxes[frame]
            assert xs.min() >= x1
            assert xs.max() < x2
            assert ys.min() >= y1
            assert ys.max() < y2


def test_replay_is_deterministic(tracked: Path, tmp_path: Path) -> None:
    copy = tmp_path / "j_counter"
    shutil.copytree(tracked, copy)
    (copy / "tracks.json").unlink()
    asyncio.run(stage.run_async(copy, replay_mode=True, settings=Settings(replay=True)))
    assert (copy / "tracks.json").read_bytes() == (tracked / "tracks.json").read_bytes()


def test_replay_without_a_recording_fails(tracked: Path, tmp_path: Path) -> None:
    copy = tmp_path / "j_counter"
    shutil.copytree(tracked, copy)
    replay.path(copy, stage.RAW_STAGE, "phrase-screen").unlink()
    with pytest.raises(replay.ReplayMissing):
        asyncio.run(stage.run_async(copy, replay_mode=True, settings=Settings(replay=True)))


def test_extra_concepts_are_swept(tracked: Path, tmp_path: Path) -> None:
    copy = tmp_path / "j_counter"
    shutil.copytree(tracked, copy)
    record_sweep(copy, text="envelope", objects={"0": {2: (5, 5, 30, 20)}}, size=SIZE, proxy_frames=24,
                 model="sam-3.1")  # fmt: skip
    asyncio.run(stage.run_async(copy, replay_mode=True, concepts=(*stage.CONCEPTS, "Envelope"),
                                settings=Settings(replay=True)))  # fmt: skip
    tracks = load(copy / "tracks.json", Tracks)
    assert "envelope" in tracks.concepts
    assert [t.track_id for t in tracks.tracks if t.concept == "envelope"] == ["envelope:1"]


def test_crowded_proxy_frame_marks_its_span(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_crowd"
    prepare.prepare(CLIP, job_dir)
    settings = Settings(replay=True)
    job = load(job_dir / "job.json", prepare.Job)
    proxy = stage.make_proxy(job_dir, job, settings)
    crowd = {str(k): {3: (k * 18, 40, k * 18 + 16, 60)} for k in range(16)}
    for concept in stage.CONCEPTS:
        record_sweep(job_dir, text=concept, objects=crowd if concept == "person" else {}, size=SIZE,
                     proxy_frames=proxy.frames, model=settings.sam_model)  # fmt: skip
    asyncio.run(stage.run_async(job_dir, replay_mode=True, settings=settings))
    tracks = load(job_dir / "tracks.json", Tracks)
    table = from_proxy_table(job.frames, job.fps, proxy.fps, proxy.frames)
    assert tracks.crowded_frames == list(range(table[2] + 1, table[4]))
    assert len(tracks.tracks) == 16


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("<0f>\n", MetaIncomplete),  # S5: a bare header is a dropped line
        ("<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80|>\n", MetaIncomplete),  # no mask
        (
            "<0f>0<|box;x1=90;y1=20;x2=140;y2=24;w=100;h=80|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n",
            MetaIncomplete,
        ),  # box outside the frame
    ],
)
def test_parser_fails_closed(text: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        asyncio.run(sam.parse_video_events(events(text, response_id="resp_bad", frames_billed=10)))


def test_parser_eof_and_refusal() -> None:
    good = events(stream_text({"0": {0: (10, 20, 15, 25)}}, (100, 80)), response_id="resp_ok", frames_billed=10)
    with pytest.raises(MetaIncomplete) as err:
        asyncio.run(sam.parse_video_events(good[:-1]))
    assert err.value.eof
    refusal = [good[0], {"type": "response.refusal.delta", "delta": "no", "item_id": "m", "output_index": 0,
                         "content_index": 0}]  # fmt: skip
    with pytest.raises((MetaRefusal, MetaIncomplete)):
        asyncio.run(sam.parse_video_events(refusal))


def test_zero_matches_is_valid_and_out_of_order_frames_are_fine() -> None:
    empty = asyncio.run(sam.parse_video_events(events("", response_id="resp_e", frames_billed=50)))
    assert empty.detections == ()
    assert empty.frames_billed == 50
    text = stream_text({"0": {9: (10, 20, 15, 25), 7: (10, 20, 15, 25)}}, (100, 80))
    lines = text.splitlines()
    reversed_text = "\n".join(reversed(lines)) + "\n"
    seg = asyncio.run(sam.parse_video_events(events(reversed_text, response_id="resp_r", frames_billed=10)))
    assert [d.frame for d in seg.detections] == [7, 9]


def test_a_mangled_record_line_fails_but_prose_is_ignored() -> None:
    good = stream_text({"0": {0: (10, 20, 15, 25)}}, (100, 80))
    with pytest.raises(MetaIncomplete, match="aren't frame records"):
        asyncio.run(sam.parse_video_events(events(":" + good, response_id="resp_m", frames_billed=10)))
    seg = asyncio.run(
        sam.parse_video_events(events("Found one object.\n" + good, response_id="resp_p", frames_billed=10))
    )
    assert [d.frame for d in seg.detections] == [0]


def test_sam_must_answer_in_the_proxys_space_with_box_sized_masks() -> None:
    good = stream_text({"0": {0: (10, 20, 15, 25)}}, (100, 80))
    assert asyncio.run(sam.parse_video_events(events(good, response_id="r1", frames_billed=10), size=(100, 80)))
    with pytest.raises(MetaIncomplete, match="space"):
        asyncio.run(sam.parse_video_events(events(good, response_id="r2", frames_billed=10), size=(320, 180)))
    small = "<0f>0<|box;x1=10;y1=20;x2=39;y2=59;w=100;h=80|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"
    with pytest.raises(MetaIncomplete, match="box's size"):
        asyncio.run(sam.parse_video_events(events(small, response_id="r3", frames_billed=10)))


def test_a_detection_past_the_proxy_fails_the_stage(tracked: Path, tmp_path: Path) -> None:
    copy = tmp_path / "j_counter"
    shutil.copytree(tracked, copy)
    record_sweep(copy, text="face", objects={"0": {30: (10, 10, 20, 20)}}, size=SIZE, proxy_frames=24,
                 model="sam-3.1")  # fmt: skip
    with pytest.raises(stage.TrackError, match="past the proxy"):
        asyncio.run(stage.run_async(copy, replay_mode=True, settings=Settings(replay=True)))


def test_a_recording_for_another_proxy_is_refused(tracked: Path, tmp_path: Path) -> None:
    copy = tmp_path / "j_counter"
    shutil.copytree(tracked, copy)
    record_sweep(copy, text="face", objects={}, size=SIZE, proxy_frames=30, model="sam-3.1")
    with pytest.raises(replay.ReplayMissing, match="30-frame proxy"):
        asyncio.run(stage.run_async(copy, replay_mode=True, settings=Settings(replay=True)))
    job = load(copy / "job.json", prepare.Job)
    with pytest.raises(stage.TrackError, match=r"tracks\.json was made from"):
        stage.proxy_for(copy, job, Settings(sam_fps=4), load(tracked / "tracks.json", Tracks))
