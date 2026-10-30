"""Set-of-Mark rendering: deterministic pixels, the bar above the frame, tags inside the frame and apart."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from safecut import prepare
from safecut.contracts import Job, Track, Tracks, load
from safecut.scout import som
from safecut.scout.grid import BAR_H


def track(track_id: str, box: tuple[int, int, int, int], frames: range, origin: str = "sam") -> Track:
    concept = track_id.rsplit(":", 1)[0]
    return Track(
        track_id=track_id,
        concept=concept,
        first=frames[0],
        last=frames[-1],
        boxes=dict.fromkeys(frames, box),
        source=None if origin == "static" else "sam-3.1",
        prompt=concept,
        origin="static" if origin == "static" else "sam",
    )


GREY = np.full((180, 320, 3), 128, dtype=np.uint8)


def test_bar_is_added_above_and_content_kept() -> None:
    t = track("face:1", (200, 100, 260, 160), range(90, 91))
    out = som.render(GREY, 90, [t], {"face:1": som.PALETTE[0]})
    assert out.shape == (180 + BAR_H, 320, 3)
    bar = out[:BAR_H]
    assert (bar.max(axis=2) < 40).mean() > 0.85  # mostly black
    assert bar.max() > 200  # the white frame number
    assert np.array_equal(out[BAR_H + 10 : BAR_H + 50, 10:150], GREY[10:50, 10:150])  # untouched content
    outline = out[BAR_H + 130, 200]
    assert tuple(int(c) for c in outline) == som.PALETTE[0]


def test_render_is_deterministic() -> None:
    tracks = [track("face:1", (20, 20, 80, 90), range(1)), track("person:2", (150, 30, 300, 170), range(1))]
    colours = {"face:1": som.PALETTE[0], "person:2": som.PALETTE[1]}
    a = som.render(GREY, 0, tracks, colours)
    b = som.render(GREY.copy(), 0, tracks, colours)
    assert np.array_equal(a, b)


def _inside(rect: tuple[int, int, int, int]) -> bool:
    return 0 <= rect[0] < rect[2] <= 320 and 0 <= rect[1] < rect[3] <= 180


def test_labels_legible_at_320px_and_inside_the_frame() -> None:
    # A box flush with the bottom-right corner: its tag must move inside the frame, not off it.
    t = track("license plate:12", (290, 160, 320, 180), range(1))
    rect = som.place_tags([t], 0, 320, 180)[t.track_id]
    assert _inside(rect)
    assert rect[3] - rect[1] >= som.MIN_TEXT_PX + 4  # cap height plus padding
    out = som.render(GREY, 0, [t], {t.track_id: som.PALETTE[2]})
    tag = out[BAR_H + rect[1] : BAR_H + rect[3], rect[0] : rect[2]]
    fill = np.all(tag == np.array(som.PALETTE[2], dtype=np.uint8), axis=2)
    ink = np.abs(tag.astype(int) - np.array(som.text_colour(som.PALETTE[2]))).max(axis=2) < 60
    assert fill.mean() > 0.5
    assert ink.sum() > 30


@pytest.mark.parametrize("offset", [(4, 2), (0, 0), (2, 30)])
def test_nearby_tags_are_kept_apart(offset: tuple[int, int]) -> None:
    dx, dy = offset
    tracks = [track(f"face:{k}", (40 + k * dx, 40 + k * dy, 90 + k * dx, 100 + k * dy), range(1)) for k in range(1, 5)]
    rects = list(som.place_tags(tracks, 0, 320, 180).values())
    assert all(_inside(r) for r in rects)
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


@pytest.fixture(scope="module")
def job_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("som") / "j_som"
    prepare.prepare(Path("fixtures/clips/counter_30fps_audio.mp4"), path)
    return path


def test_write_keyframes_on_the_synthetic_clip(job_dir: Path) -> None:
    job = load(job_dir / "job.json", Job)
    tracks = Tracks(
        concepts=["face"], sam_fps=8, sam_frames=24,
        tracks=[track("face:1", (10, 60, 51, 101), range(90)), track("face:2", (220, 28, 261, 69), range(40)),
                track("envelope:1", (100, 100, 140, 120), range(25, 35), origin="static")],
    )  # fmt: skip
    written = som.write(job_dir, job, tracks)
    assert [k.frame for k in written] == [0, 30, 60]
    assert [k.labels for k in written] == [("face:1", "face:2"), ("face:1", "face:2"), ("face:1",)]
    first = (job_dir / written[0].path).read_bytes()
    img = cv2.imdecode(np.frombuffer(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    assert img.shape == (180 + BAR_H, 320, 3)
    again = som.write(job_dir, job, tracks)
    assert again == written
    assert (job_dir / written[0].path).read_bytes() == first


def test_missing_keyframe_is_an_error(job_dir: Path) -> None:
    job = load(job_dir / "job.json", Job)
    tracks = Tracks(concepts=[], sam_fps=8, sam_frames=24, tracks=[])
    with pytest.raises(FileNotFoundError):
        som.write(job_dir, job, tracks, frames=[200])  # past the clip: nothing to extract


def test_a_track_between_keyframes_gets_its_own_keyframe(job_dir: Path) -> None:
    job = load(job_dir / "job.json", Job)
    brief = track("face:9", (100, 100, 140, 140), range(40, 50))  # 1/3 s, between keyframes 30 and 60
    static = track("envelope:1", (10, 10, 30, 30), range(40, 50), origin="static")
    assert som.extra_keyframes(job, [brief, static, track("face:1", (0, 0, 9, 9), range(90))]) == [45]
    tracks = Tracks(concepts=["face"], sam_fps=8, sam_frames=24, tracks=[brief])
    written = som.write(job_dir, job, tracks, frames=[45])
    assert written[0].labels == ("face:9",)
    assert (job_dir / "keyframes" / "000045.jpg").is_file()
