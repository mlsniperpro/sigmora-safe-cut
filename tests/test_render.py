"""WP4 step 1: render. Pixel tests, locked grids, audio, thumbnails, coverage scoring, and the reversibility
check: a face detector finds the faces in the source and none of the ones the render pixelated."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from safecut import contracts
from safecut.audit.detectors import YuNet
from safecut.contracts import CrowdFill, Decisions, Job, Plan, PlanEntry, dump, load
from safecut.decide import run as decide_run
from safecut.decide.geometry import BoxT, encode
from safecut.decide.review import HideEdit, apply_review
from safecut.guard import run as guard_run
from safecut.render import REDACTED, THUMBS, RenderError, fills_by_frame, render
from safecut.render.coverage import ObjectScore, coverage, passes_e3, score
from safecut.render.draw import FILL_BGR, NOISE, apply, hidden_mask
from safecut.render.video import cut_thumb, probe_streams, read_frames
from tests.safety_jobs import POSTER, Scenario, frame_image, make_job

GREY = np.full((60, 80, 3), 128, dtype=np.uint8)


def entry(box: tuple[int, int, int, int], style: str = "solid", grid: tuple[int, int, int] | None = None) -> PlanEntry:
    return PlanEntry.model_validate(
        {"item_id": "i_1", "shape": "box", "box": box, "mask": None, "style": style, "grid": grid}
    )


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    job_dir = make_job(tmp_path_factory.mktemp("render"))
    decide_run(job_dir)
    guard_run(job_dir)
    render(job_dir)
    return job_dir


def decoded(job_dir: Path) -> list[np.ndarray]:
    job = load(job_dir / "job.json", Job)
    return list(read_frames(job_dir / REDACTED, job))


# ---------------------------------------------------------------------------------------------- draw (exact pixels)


def test_solid_fills_the_box_and_nothing_else() -> None:
    out = apply(GREY, [entry((10, 10, 30, 20))], [])
    assert (out[10:20, 10:30] == FILL_BGR).all()
    assert (out[0:10] == 128).all()
    assert (out[:, 30:] == 128).all()


def test_mask_entries_fill_only_the_mask() -> None:
    mask = np.zeros((60, 80), dtype=np.bool_)
    mask[12:18, 12:16] = True
    e = PlanEntry.model_validate({"item_id": "i_1", "shape": "mask", "box": (10, 10, 30, 20),
                                  "mask": encode(mask), "style": "person_solid", "grid": None})  # fmt: skip
    out = apply(GREY, [e], [])
    assert (out[mask] == FILL_BGR).all()
    assert (out[~mask] == 128).all()
    assert (hidden_mask([e], [], 60, 80) == mask).all()


def test_pixelate_cells_are_uniform_on_the_locked_grid_and_noise_is_bounded() -> None:
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(60, 80, 3), dtype=np.uint8)
    out = apply(img, [entry((5, 7, 45, 37), "pixelate", (3, 1, 10))], [])
    for y0 in range(7, 37, 10):
        for x0 in range(5, 45, 10):
            # cells start on the grid (origin 3,1; 10 px): within one cell, the colour is one value
            cy, cx = (y0 - 1) // 10 * 10 + 1, (x0 - 3) // 10 * 10 + 3
            ys, xs = slice(max(cy, 7), min(cy + 10, 37)), slice(max(cx, 5), min(cx + 10, 45))
            cell = out[ys, xs].reshape(-1, 3)
            assert (cell == cell[0]).all()
            mean = img[max(cy, 0) : cy + 10, max(cx, 0) : cx + 10].reshape(-1, 3).mean(axis=0)
            assert (np.abs(cell[0].astype(float) - mean) <= NOISE + 1).all()
    assert (out[:7] == img[:7]).all()


def test_a_still_object_renders_identical_cells_in_every_frame() -> None:
    a = frame_image(Scenario(actors=[]), 0)
    b = frame_image(Scenario(actors=[]), 40)
    e = entry(POSTER, "pixelate", (POSTER[0], POSTER[1], 20))
    assert (apply(a, [e], []) == apply(b, [e], [])).all()


def test_solid_wins_over_a_mosaic_and_crowd_fills_go_last() -> None:
    mosaic = entry((0, 0, 40, 40), "pixelate", (0, 0, 8))
    out = apply(GREY, [mosaic, entry((10, 10, 20, 20))], [CrowdFill(frames=[0], box=(50, 0, 80, 10))])
    assert (out[10:20, 10:20] == FILL_BGR).all()
    assert (out[0:10, 50:80] == FILL_BGR).all()


def test_fills_by_frame() -> None:
    plan = Plan.model_validate({"padding": {"face": 0.15, "default": 0.08, "px": 8},
                                "temporal": {"extend": 8, "backfill": 57, "gap_hold_s": 2.0}, "frames": {},
                                "crowd_fills": [{"frames": [1, 2], "box": [0, 0, 4, 4]}]})  # fmt: skip
    assert sorted(fills_by_frame(plan)) == [1, 2]


# ---------------------------------------------------------------------------------------------- video


def test_render_writes_h264_with_the_audio_and_every_frame(rendered: Path) -> None:
    assert probe_streams(rendered / REDACTED) == ["video:h264", "audio:aac"]
    assert len(decoded(rendered)) == 60
    contracts.validate_job_dir(rendered)


def test_the_hidden_bystander_is_mosaicked_and_the_host_is_untouched(rendered: Path) -> None:
    frames = decoded(rendered)
    source = list(read_frames(rendered / "prepared.mp4", load(rendered / "job.json", Job)))
    plan = load(rendered / "plan.json", Plan)
    host = next(t for t in json.loads((rendered / "tracks.json").read_text())["tracks"] if t["track_id"] == "face:1")
    x1, y1, x2, y2 = host["boxes"]["30"]
    assert np.abs(frames[30][y1:y2, x1:x2].astype(int) - source[30][y1:y2, x1:x2].astype(int)).mean() < 3
    (bystander,) = [e for e in plan.frames[30] if e.item_id == "i_2"]
    assert bystander.style == "pixelate"
    bx1, by1, bx2, by2 = bystander.box
    assert np.abs(frames[30][by1:by2, bx1:bx2].astype(int) - source[30][by1:by2, bx1:bx2].astype(int)).mean() > 5


def test_a_solid_region_decodes_to_the_fill_colour(tmp_path: Path) -> None:
    job_dir = make_job(tmp_path)
    decide_run(job_dir)
    decisions = load(job_dir / "decisions.json", Decisions)
    solid = Decisions(items=[i.model_copy(update={"style": "solid"}) if i.item_id == "i_2" else i
                             for i in decisions.items])  # fmt: skip
    dump(apply_review(solid, [HideEdit(type="hide", edit_id="h", item_id="i_2")]).decisions, job_dir / "decisions.json")
    guard_run(job_dir)
    render(job_dir)
    plan = load(job_dir / "plan.json", Plan)
    (e,) = [e for e in plan.frames[30] if e.item_id == "i_2"]
    x1, y1, x2, y2 = e.box
    inner = decoded(job_dir)[30][y1 + 4 : y2 - 4, x1 + 4 : x2 - 4].reshape(-1, 3).astype(int)
    error = np.abs(inner - np.array(FILL_BGR))
    assert error.max() <= 12  # x264 at CRF 18 with 4:2:0 chroma: a few levels near block edges
    assert error.mean() <= 3


def test_reversibility_a_face_detector_finds_no_pixelated_face(rendered: Path) -> None:
    """WP4: on the rendered mosaic (≤ 6 blocks + noise) the detector finds nothing, while it finds the same face in
    the source and the approved host in the render; a fine mosaic (16 blocks) would still be found."""
    yunet = YuNet()
    job = load(rendered / "job.json", Job)
    plan = load(rendered / "plan.json", Plan)
    source = list(read_frames(rendered / "prepared.mp4", job))
    out = decoded(rendered)
    tracks = {t["track_id"]: t for t in json.loads((rendered / "tracks.json").read_text())["tracks"]}
    by = tracks["face:2"]

    def hits(frame: np.ndarray, b: list[int]) -> int:
        return sum(contracts.boxes_overlap(d.box, (b[0], b[1], b[2], b[3])) for d in yunet.detect(frame))

    visible = [f for f in range(by["first"], by["last"] + 1) if str(f) in by["boxes"]]
    in_source = sum(hits(source[f], by["boxes"][str(f)]) > 0 for f in visible)
    in_render = sum(hits(out[f], by["boxes"][str(f)]) > 0 for f in visible)
    host = sum(hits(out[f], tracks["face:1"]["boxes"][str(f)]) > 0 for f in range(60))
    assert in_source >= 0.8 * len(visible)
    assert in_render == 0
    assert host >= 55
    fine = 0
    for f in visible[::5]:
        (e,) = [e for e in plan.frames[f] if e.item_id == "i_2"]
        w = by["boxes"][str(f)][2] - by["boxes"][str(f)][0]
        weak = e.model_copy(update={"grid": (e.grid[0], e.grid[1], max(2, math.ceil(w / 16)))}) if e.grid else e
        fine += hits(apply(source[f], [weak], []), by["boxes"][str(f)]) > 0
    assert fine >= 1  # why DESIGN §2.7 bans fine mosaics


def test_thumbnails_come_from_the_redacted_frames(rendered: Path) -> None:
    thumbs = sorted(p.name for p in (rendered / THUMBS).glob("*.jpg"))
    assert thumbs == ["i_1.jpg", "i_2.jpg"]
    yunet = YuNet()
    host = np.asarray(cv2.imread(str(rendered / THUMBS / "i_1.jpg")), dtype=np.uint8)
    bystander = np.asarray(cv2.imread(str(rendered / THUMBS / "i_2.jpg")), dtype=np.uint8)
    assert yunet.detect(host)
    assert not yunet.detect(bystander)
    assert max(bystander.shape[:2]) <= 240


def test_cut_thumb_bounds() -> None:
    big = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert max(cut_thumb(big, (0, 0, 1280, 720)).shape[:2]) == 240
    tiny = cut_thumb(big, (600, 300, 605, 305)).shape[:2]
    assert 64 <= min(tiny) <= max(tiny) <= 240  # a tiny item still gets 64 px of context
    assert cut_thumb(big, (5, 5, 10, 10)).shape[:2] == (56, 56)  # clamped at the corner


def test_no_audio_track_when_the_clip_has_none(tmp_path: Path) -> None:
    job_dir = make_job(tmp_path, Scenario(frames=20, audio=False))
    decide_run(job_dir)
    guard_run(job_dir)
    render(job_dir)
    assert probe_streams(job_dir / REDACTED) == ["video:h264"]


def test_a_clip_that_doesnt_match_the_job_is_refused(tmp_path: Path) -> None:
    job_dir = make_job(tmp_path, Scenario(frames=20))
    decide_run(job_dir)
    guard_run(job_dir)
    job = load(job_dir / "job.json", Job)
    dump(job.model_copy(update={"frames": 25, "times": [i / 30 for i in range(25)]}), job_dir / "job.json")
    with pytest.raises(RenderError, match="20 frames"):
        render(job_dir)
    assert not (job_dir / REDACTED).exists()  # no partial video left behind
    dump(job.model_copy(update={"frames": 10, "times": [i / 30 for i in range(10)]}), job_dir / "job.json")
    with pytest.raises(RenderError, match="more than"):
        render(job_dir)
    shutil.copy(job_dir / "prepared.mp4", job_dir / "other.mp4")
    dump(job.model_copy(update={"width": 321}), job_dir / "job.json")
    with pytest.raises(RenderError):
        render(job_dir)


# ---------------------------------------------------------------------------------------------- coverage


def test_coverage_scores_what_the_renderer_hides(rendered: Path) -> None:
    plan = load(rendered / "plan.json", Plan)
    tracks = json.loads((rendered / "tracks.json").read_text())["tracks"]
    truth: dict[int, dict[str, BoxT]] = {}
    for t in tracks:
        for f, b in t["boxes"].items():
            truth.setdefault(int(f), {})[t["track_id"]] = (b[0], b[1], b[2], b[3])
    scores = score(plan, truth, {"face:1": False, "face:2": True}, width=320, height=240)
    assert scores["face:2"].share == 1.0
    assert scores["face:1"].share == 0.0
    assert passes_e3(scores)
    leaky = plan.model_copy(update={"frames": {f: es for f, es in plan.frames.items() if f not in (30, 31, 32)}})
    bad = score(leaky, truth, {"face:1": False, "face:2": True}, width=320, height=240)
    assert bad["face:2"].exposed == [30, 31, 32]
    assert bad["face:2"].bursts == 1
    assert not passes_e3(bad)
    assert coverage(plan, 30, (0, 0, 0, 0), 320, 240) == 1.0
    assert ObjectScore("x", should_hide=True).share == 1.0
    assert ObjectScore("x", should_hide=False).share == 0.0
