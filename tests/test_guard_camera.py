"""Held boxes follow the camera (DESIGN §2.6): the motion estimate, the guard's moved back-fill / extend / gap holds and
audit patches, and the contract checker that must accept exactly what the guard draws."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from safecut import contracts
from safecut.contracts import ContractError, DecisionItem, Decisions, Plan, Tracks, dump, load
from safecut.guard import camera_for
from safecut.guard import run as guard_run
from safecut.guard.motion import estimate_camera
from safecut.guard.plan import EXTEND, backfill_frames, plan
from safecut.guard.regions import held_box
from tests.safety_factories import FRAMES, H, W, job, track, tracks
from tests.test_guard import JOB, covered, entries, guarded, hide_all

Image = NDArray[np.uint8]

# ------------------------------------------------------------------------------------------ the motion estimate

_RNG = np.random.default_rng(7)
_WORLD = cv2.GaussianBlur((_RNG.random((1400, 2000)) * 255).astype(np.float32), (0, 0), 3).astype(np.uint8)
_ORIGIN = (350, 250)


def close(got: tuple[int, int], want: tuple[int, int], tol: int = 2) -> None:
    assert abs(got[0] - want[0]) <= tol, (got, want)
    assert abs(got[1] - want[1]) <= tol, (got, want)


def pan(offsets: list[tuple[int, int]], *, width: int = 320, height: int = 180) -> Iterator[Image]:
    """Frames of a textured scene whose content sits at ``offsets[f]`` (cumulative) relative to the first frame: the
    camera looks at a world window moved the other way."""
    for dx, dy in offsets:
        x, y = _ORIGIN[0] - dx, _ORIGIN[1] - dy
        grey = _WORLD[y : y + height, x : x + width]
        yield np.asarray(cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR), dtype=np.uint8)


def test_a_pan_of_known_shifts_is_recovered() -> None:
    truth = [(round(5 * f), round(-2 * f)) for f in range(12)]  # the scene moves 5 px right, 2 px up a frame
    got = estimate_camera(pan(truth))
    assert got[0] == (0, 0)
    assert len(got) == len(truth)
    for have, want in zip(got, truth, strict=True):
        close(have, want)


def test_an_uneven_pan_is_recovered_cumulatively() -> None:
    steps = [(0, 0), (3, 1), (7, 0), (7, -3), (-4, 2), (0, 0), (10, 4)]
    truth = [(sum(s[0] for s in steps[: i + 1]), sum(s[1] for s in steps[: i + 1])) for i in range(len(steps))]
    got = estimate_camera(pan(truth))
    for have, want in zip(got, truth, strict=True):
        close(have, want)


def test_a_static_clip_has_no_motion() -> None:
    assert estimate_camera(pan([(0, 0)] * 8)) == [(0, 0)] * 8


def with_walker(frames: Iterator[Image], *, speed: int) -> Iterator[Image]:
    """The scene with a flat-coloured 'person' (90 x 150 px, a sixth of the frame) walking ``speed`` px a frame."""
    for f, frame in enumerate(frames):
        out = frame.copy()
        x = 40 + speed * f
        out[20:170, x : x + 90] = (40, 90, 200)
        out[30:60, x + 25 : x + 65] = (180, 200, 230)
        yield out


def test_people_walking_through_the_shot_are_not_the_camera() -> None:
    """The scene is still; a person crosses it: the camera did not move (the entry gate's synthetic demo is this)."""
    got = estimate_camera(with_walker(pan([(0, 0)] * 20), speed=6))
    assert max(abs(x) + abs(y) for x, y in got) <= 2


def test_a_pan_is_still_the_pan_with_a_person_crossing_it() -> None:
    truth = [(4 * f, 0) for f in range(16)]
    got = estimate_camera(with_walker(pan(truth), speed=-3))
    close(got[-1], truth[-1], 3)


def test_blank_frames_count_as_no_motion() -> None:
    blank = np.zeros((180, 320, 3), dtype=np.uint8)
    assert estimate_camera(iter([blank] * 5)) == [(0, 0)] * 5
    flat = np.full((180, 320, 3), 117, dtype=np.uint8)
    assert estimate_camera(iter([flat] * 5)) == [(0, 0)] * 5


def test_a_blank_frame_in_a_pan_is_no_motion_and_the_pan_carries_on() -> None:
    truth = [(5 * f, 0) for f in range(6)]
    frames = list(pan(truth))
    frames[3] = np.zeros_like(frames[3])  # two unreadable pairs: 2 -> 3 and 3 -> 4
    got = estimate_camera(iter(frames))
    assert got[3] == got[2] == (10, 0)
    assert got[4] == got[3]  # no estimate against the blank, so the pan resumes from there
    assert abs(got[5][0] - got[4][0] - 5) <= 2  # 4 -> 5 is the one pair after it that still measures


def test_one_frames_shift_is_clamped() -> None:
    truth = [(0, 0), (20, 0)]
    (_, (x, _)) = estimate_camera(pan(truth), max_shift=0.02)  # 2 % of 320 px
    assert 6 <= x <= 7
    assert estimate_camera(pan(truth))[1][0] >= 18


def test_the_estimate_is_in_full_frame_pixels_whatever_the_analysis_width() -> None:
    truth = [(8 * f, 0) for f in range(5)]
    small = estimate_camera(pan(truth), width=160)
    large = estimate_camera(pan(truth), width=320)
    close(small[-1], (32, 0))
    close(large[-1], (32, 0))


def write_clip(path: Path, offsets: list[tuple[int, int]], *, width: int = 320, height: int = 180) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), 30, (width, height))
    assert writer.isOpened()
    for frame in pan(offsets, width=width, height=height):
        writer.write(frame)
    writer.release()


def test_camera_for_reads_the_prepared_clip_and_is_none_without_one(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_cam"
    job_dir.mkdir()
    j = job(frames=10)
    assert camera_for(job_dir, j) is None  # no prepared.mp4: no camera, the guard holds boxes still
    write_clip(job_dir / "prepared.mp4", [(4 * f, 0) for f in range(10)])
    (job_dir / "job.json").write_text(j.model_dump_json())
    found = camera_for(job_dir, j)
    assert found is not None
    assert len(found) == 10
    assert found[0] == (0, 0)
    close(found[-1], (36, 0), 4)
    assert camera_for(job_dir) == found  # the second reading is the cached one
    still = tmp_path / "j_still"
    still.mkdir()
    write_clip(still / "prepared.mp4", [(0, 0)] * 10)
    (still / "job.json").write_text(j.model_dump_json())
    assert camera_for(still, j) is None  # a camera that never moved is no camera


# ------------------------------------------------------------------------------------------ the guard

PAN = [(5 * f, 0) for f in range(FRAMES)]  # the scene moves 5 px right a frame
BOX = (100, 60, 120, 80)


def moved(box: tuple[int, int, int, int], dx: int, dy: int = 0) -> tuple[int, int, int, int]:
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def test_back_fill_and_extend_follow_the_pan() -> None:
    ts = tracks(track("face:1", 20, 30, BOX))
    d = hide_all(ts)
    p = plan(JOB, ts, d, camera=PAN)
    assert p.camera == PAN
    for frame in range(20 - backfill_frames(JOB), 20):
        assert covered(p, frame, "i_1", moved(BOX, 5 * (frame - 20))), frame  # the first box, carried back with the pan
    for frame in range(31, 30 + EXTEND + 1):
        assert covered(p, frame, "i_1", moved(BOX, 5 * (frame - 30))), frame  # the last box, carried on with it
    still = plan(JOB, ts, d)
    far = 30 + EXTEND
    assert not covered(still, far, "i_1", moved(BOX, 5 * (far - 30)))  # held still, the cover lags the person
    assert covered(p, far, "i_1", moved(BOX, 5 * (far - 30)))


def test_a_long_gap_follows_the_pan() -> None:
    """SAM lost a person who stands still in the world while the camera panned 5 px a frame for 17 frames."""
    boxes = {
        20: BOX,
        21: moved(BOX, 5),
        22: moved(BOX, 10),
        40: moved(BOX, 90),
        41: moved(BOX, 95),
        42: moved(BOX, 100),
    }
    ts = tracks(track("face:1", 20, 42, BOX, anchors=[20, 21, 22, 40, 41, 42]).model_copy(update={"boxes": boxes}))
    p = plan(JOB, ts, hide_all(ts), camera=PAN)
    for frame in range(23, 40):
        assert covered(p, frame, "i_1", moved(BOX, 5 * (frame - 20))), frame
    contracts._check_plan_covers(p, hide_all(ts), ts, JOB)  # pyright: ignore[reportPrivateUsage]
    contracts._check_plan_geometry(p, hide_all(ts), ts, JOB)  # pyright: ignore[reportPrivateUsage]


def test_a_held_box_the_pan_carries_out_of_the_frame_is_not_drawn() -> None:
    edge = (280, 60, 300, 80)
    ts = tracks(track("face:1", 10, 30, edge))
    d = hide_all(ts)
    p = plan(JOB, ts, d, camera=PAN)
    drawn = [f for f in range(31, 31 + EXTEND) if entries(p, f, "i_1")]
    assert drawn == list(range(31, 38))  # frame 38 would sit at x 320..340: wholly out of the frame
    assert entries(p, 38, "i_1") == []
    for frame in drawn:
        assert covered(p, frame, "i_1", contracts.clip_box(moved(edge, 5 * (frame - 30)), W, H) or edge), frame
    contracts._check_plan_covers(p, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]
    contracts._check_plan_geometry(p, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]
    # ... and the other way: carried off the left edge before the first box
    left = tracks(track("face:1", 20, 30, (10, 60, 30, 80)))
    q = plan(JOB, left, hide_all(left), camera=PAN)
    assert entries(q, 11, "i_1") == []  # 5 px a frame x 9 frames: x -35..-15
    assert entries(q, 19, "i_1")
    contracts._check_plan_covers(q, hide_all(left), left, JOB)  # pyright: ignore[reportPrivateUsage]


def test_without_a_camera_plans_are_what_they_were() -> None:
    ts = tracks(
        track("face:1", 20, 30, BOX, step=(2, 0)),
        track("person:1", 5, 50, (150, 20, 200, 120), anchors=[5, 6, 7, 40, 41, 50]),
    )
    d = hide_all(ts)
    base = plan(JOB, ts, d)
    assert base.camera is None
    assert "camera" not in json.loads(base.model_dump_json())
    assert plan(JOB, ts, d, camera=None) == base
    assert plan(JOB, ts, d, camera=[(0, 0)] * FRAMES).frames == base.frames  # a camera at rest moves nothing
    assert Plan.model_validate_json(base.model_dump_json()) == base
    assert "camera" in json.loads(plan(JOB, ts, d, camera=PAN).model_dump_json())


def test_a_camera_of_the_wrong_length_is_refused() -> None:
    ts = tracks(track("face:1", 20, 30, BOX))
    with pytest.raises(ValueError, match="camera has 3 offsets"):
        plan(JOB, ts, hide_all(ts), camera=[(0, 0)] * 3)
    p = plan(JOB, ts, hide_all(ts)).model_copy(update={"camera": [(0, 0)] * 3})
    with pytest.raises(ContractError, match="camera has 3 offsets"):
        contracts._check_plan(p, JOB, hide_all(ts))  # pyright: ignore[reportPrivateUsage]


def test_cached_regions_never_cross_cameras() -> None:
    ts = tracks(track("face:1", 20, 30, BOX))
    d = hide_all(ts)
    cache: dict[object, object] = {}
    fresh = plan(JOB, ts, d, camera=PAN)
    still = plan(JOB, ts, d, cache=cache)  # type: ignore[arg-type]
    assert plan(JOB, ts, d, cache=cache, camera=PAN) == fresh  # type: ignore[arg-type]
    assert plan(JOB, ts, d, cache=cache) == still  # type: ignore[arg-type]
    assert fresh.frames != still.frames


# ------------------------------------------------------------------------------------------ audit patches


def patch(box: tuple[int, int, int, int], first: int, last: int, evidence: int) -> DecisionItem:
    return DecisionItem(
        item_id="p_1", track_ids=[], kind="person", decision="hide", reason="audit patch", evidence_frames=[evidence],
        style="solid", decided_by="policy", locked=True, origin="audit_patch", audit_label="A1", box=box,
        first=first, last=last,
    )  # fmt: skip


def test_an_audit_patch_follows_the_pan_from_its_evidence_frame() -> None:
    hold = backfill_frames(JOB)
    item = patch(BOX, 30 - hold, 30 + hold, 30)
    d = Decisions(items=[item])
    p = plan(JOB, tracks(), d, camera=PAN)
    for frame in range(30 - hold, 31 + hold):
        want = moved(BOX, 5 * (frame - 30))
        assert covered(p, frame, "p_1", want), frame
    assert covered(plan(JOB, tracks(), d), 30, "p_1", BOX)
    assert not covered(p, 30 + hold, "p_1", BOX)  # no longer where the leak was
    contracts._check_plan_covers(p, d, tracks(), JOB)  # pyright: ignore[reportPrivateUsage]


def test_a_merged_patch_stays_over_every_frame_its_leaks_were_seen_on() -> None:
    """A patch grouped over frames 30-36 keeps its union box on all of them (it must contain each leak); only its
    margins before and after move with the camera."""
    hold = backfill_frames(JOB)
    item = patch(BOX, 30 - hold, 36 + hold, 30)
    p = plan(JOB, tracks(), Decisions(items=[item]), camera=PAN)
    for frame in range(30, 37):
        assert covered(p, frame, "p_1", BOX), frame
    assert covered(p, 36 + hold, "p_1", moved(BOX, 5 * hold))
    contracts._check_plan_covers(p, Decisions(items=[item]), tracks(), JOB)  # pyright: ignore[reportPrivateUsage]


def test_a_patch_the_pan_carries_out_of_the_frame_is_not_drawn() -> None:
    hold = backfill_frames(JOB)
    item = patch((290, 60, 310, 80), 30 - hold, 30 + hold, 30)
    d = Decisions(items=[item])
    p = plan(JOB, tracks(), d, camera=PAN)
    assert entries(p, 30 + hold, "p_1") == []  # x 335..355
    assert entries(p, 31, "p_1")
    contracts._check_plan_covers(p, d, tracks(), JOB)  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------------------------------------ the contract checker


def test_a_plan_that_holds_boxes_still_is_refused_under_a_camera_that_moved_them() -> None:
    ts = tracks(track("face:1", 20, 30, BOX))
    d = hide_all(ts)
    good = plan(JOB, ts, d, camera=PAN)
    contracts._check_plan_covers(good, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]
    still = plan(JOB, ts, d).model_copy(update={"camera": PAN})  # the unmoved boxes under a panning camera
    with pytest.raises(ContractError, match=r"held box|no entry"):
        contracts._check_plan_covers(still, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]


def test_a_plan_that_draws_a_box_the_pan_carried_out_of_the_frame_is_still_fine() -> None:
    edge = (280, 60, 300, 80)
    ts = tracks(track("face:1", 10, 30, edge))
    d = hide_all(ts)
    p = plan(JOB, ts, d, camera=PAN)
    # Drawing more than the guard must is never refused: a cover on a frame whose held box left the frame.
    extra = p.frames[37][0]
    more = p.model_copy(update={"frames": {**p.frames, 38: [extra]}})
    contracts._check_plan_covers(more, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]
    # ... but a hole where the held box is still in the frame is refused.
    hole = p.model_copy(update={"frames": {f: e for f, e in p.frames.items() if f != 36}})
    with pytest.raises(ContractError, match="no entry"):
        contracts._check_plan_covers(hole, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]


def test_a_validated_job_dir_with_a_camera_validates(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(Path("fixtures/contracts/j_example"), job_dir)
    j = load(job_dir / "job.json", contracts.Job)
    base = load(job_dir / "plan.json", Plan)
    dump(base.model_copy(update={"camera": [(0, 0)] * j.frames}), job_dir / "plan.json")
    contracts.validate_job_dir(job_dir)
    with_cam = json.loads((job_dir / "plan.json").read_text())
    assert len(with_cam["camera"]) == j.frames
    dump(base.model_copy(update={"camera": [(0, 0)] * (j.frames - 1)}), job_dir / "plan.json")
    with pytest.raises(ContractError, match="camera has"):
        contracts.validate_job_dir(job_dir)


def test_the_guard_stage_measures_the_camera_and_validates(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(Path("fixtures/contracts/j_example"), job_dir)
    j = load(job_dir / "job.json", contracts.Job)
    assert not (job_dir / j.prepared).exists()
    assert "camera" not in json.loads(guard_run(job_dir).read_text())  # no clip to measure: held still, as always
    write_clip(job_dir / j.prepared, [(6 * f, 2 * f) for f in range(j.frames)], width=j.width, height=j.height)
    guarded_plan = json.loads(guard_run(job_dir).read_text())
    assert len(guarded_plan["camera"]) == j.frames
    assert guarded_plan["camera"][0] == [0, 0]
    assert guarded_plan["camera"][-1][0] > 40
    contracts.validate_job_dir(job_dir)


# ------------------------------------------------------------------------------------------ guard vs checker


@st.composite
def panned(draw: st.DrawFn) -> tuple[Tracks, Decisions, Plan]:
    ts, d, _ = draw(guarded())
    steps = draw(st.lists(st.tuples(st.integers(-14, 14), st.integers(-9, 9)), min_size=FRAMES, max_size=FRAMES))
    camera: list[tuple[int, int]] = []
    x = y = 0
    for i, (sx, sy) in enumerate(steps):
        x, y = (0, 0) if i == 0 else (x + sx, y + sy)
        camera.append((x, y))
    return ts, d, plan(JOB, ts, d, camera=camera)


@settings(max_examples=300, deadline=None)
@given(panned())
def test_property_the_checker_accepts_what_the_guard_draws_under_a_camera(case: tuple[Tracks, Decisions, Plan]) -> None:
    ts, d, p = case
    contracts._check_plan(p, JOB, d)  # pyright: ignore[reportPrivateUsage]
    contracts._check_plan_covers(p, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]
    contracts._check_plan_styles(p, d, None)  # pyright: ignore[reportPrivateUsage]
    contracts._check_plan_geometry(p, d, ts, JOB)  # pyright: ignore[reportPrivateUsage]


def test_held_box_helper_is_unchanged() -> None:
    assert held_box((100, 100, 200, 200), 10, 0.25, 1280, 720) == (80, 80, 220, 220)
