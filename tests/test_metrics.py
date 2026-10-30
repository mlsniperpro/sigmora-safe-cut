"""WP7 metric unit tests: coverage, bursts, recall, exposure, over-blur, labels and MOT, on hand-made cases."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pycocotools import mask as coco_mask  # pyright: ignore[reportMissingTypeStubs] -- no stubs ship with it

from eval.labels import ClipLabels, Entity, LabelError, interpolate, load_labels, read_mot
from eval.metrics import EntityScore, Region, bursts, coverage, frame_regions, score_entity, score_job, summarize
from safecut.contracts import Plan, Rle

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def labels_file(
    tmp_path: Path,
    entities: list[dict[str, object]],
    *,
    frames: int = 12,
    width: int = 1280,
    height: int = 720,
    mot: dict[str, str] | None = None,
) -> Path:
    for name, text in (mot or {}).items():
        (tmp_path / name).write_text(text)
    path = tmp_path / "clip.json"
    path.write_text(
        json.dumps(
            {
                "clip": "clip.mp4",
                "fps": 30,
                "frames": frames,
                "width": width,
                "height": height,
                "split": "synthetic",
                "entities": entities,
            }
        )
    )
    return path


def entity(
    eid: str, boxes: dict[str, list[float]] | str, *, hide: bool = True, first: int = 0, last: int = 0
) -> dict[str, object]:
    return {
        "id": eid,
        "category": "bystander" if hide else "participant",
        "should_hide": hide,
        "frames": {"first": first, "last": last},
        "boxes": boxes,
    }


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def test_full_cover_and_no_cover() -> None:
    gt = (10.0, 10.0, 20.0, 20.0)
    assert coverage(gt, [Region((0, 0, 100, 100))], width=100, height=100) == 1.0
    assert coverage(gt, [], width=100, height=100) == 0.0
    assert coverage(gt, [Region((50, 50, 60, 60))], width=100, height=100) == 0.0


def test_partial_cover_is_area_not_iou() -> None:
    gt = (0.0, 0.0, 10.0, 10.0)
    assert coverage(gt, [Region((0, 0, 5, 10))], width=100, height=100) == 0.5
    assert coverage(gt, [Region((0, 0, 5, 10)), Region((0, 0, 10, 5))], width=100, height=100) == 0.75
    # a redaction much larger than the box still covers it fully (padding is deliberate)
    assert coverage(gt, [Region((0, 0, 100, 100))], width=100, height=100) == 1.0


def test_a_box_outside_the_frame_cannot_show() -> None:
    assert coverage((200.0, 200.0, 210.0, 210.0), [], width=100, height=100) == 1.0
    assert coverage((90.0, 0.0, 110.0, 10.0), [Region((90, 0, 100, 10))], width=100, height=100) == 1.0


def test_mask_regions_count_only_their_foreground() -> None:
    fg = np.zeros((20, 20), dtype=np.uint8, order="F")
    fg[0:10, 0:20] = 1
    encoded = coco_mask.encode(np.asfortranarray(fg))  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] -- untyped
    counts: object = encoded["counts"]  # pyright: ignore[reportUnknownVariableType] -- untyped C extension
    assert isinstance(counts, bytes)
    rle = Rle(size=(20, 20), counts=counts.decode())
    assert coverage((0.0, 0.0, 20.0, 20.0), [Region((0, 0, 20, 20), rle)], width=20, height=20) == 0.5


@given(
    gt=st.tuples(st.integers(0, 50), st.integers(0, 50), st.integers(1, 30), st.integers(1, 30)),
    boxes=st.lists(
        st.tuples(st.integers(0, 80), st.integers(0, 80), st.integers(1, 40), st.integers(1, 40)), max_size=4
    ),
    extra=st.tuples(st.integers(0, 80), st.integers(0, 80), st.integers(1, 40), st.integers(1, 40)),
)
def test_coverage_is_a_share_and_never_drops_when_a_region_is_added(
    gt: tuple[int, int, int, int],
    boxes: list[tuple[int, int, int, int]],
    extra: tuple[int, int, int, int],
) -> None:
    box = (float(gt[0]), float(gt[1]), float(gt[0] + gt[2]), float(gt[1] + gt[3]))
    regions = [Region((x, y, x + w, y + h)) for x, y, w, h in boxes]
    before = coverage(box, regions, width=100, height=100)
    after = coverage(
        box, [*regions, Region((extra[0], extra[1], extra[0] + extra[2], extra[1] + extra[3]))], width=100, height=100
    )
    assert 0.0 <= before <= after <= 1.0
    assert coverage(box, [Region((gt[0], gt[1], gt[0] + gt[2], gt[1] + gt[3]))], width=100, height=100) == 1.0


# ---------------------------------------------------------------------------
# Bursts and entity scores
# ---------------------------------------------------------------------------


def test_two_exposed_frames_are_not_a_burst_but_three_are() -> None:
    assert bursts([4, 5]) == 0
    assert bursts([4, 5, 6]) == 1
    assert bursts([4, 5, 6, 7, 8]) == 1
    assert bursts([1, 2, 3, 7, 8, 9]) == 2
    assert bursts([1, 3, 5]) == 0
    assert bursts([]) == 0


def _score(boxes: dict[str, list[float]], regions: dict[int, list[Region]], *, hide: bool = True) -> EntityScore:
    e = Entity.model_validate(entity("e", boxes, hide=hide, first=0, last=max(int(f) for f in boxes)))
    e._dense = {int(f): (b[0], b[1], b[2], b[3]) for f, b in boxes.items()}  # pyright: ignore[reportPrivateUsage] -- what load_labels fills
    return score_entity(e, regions, width=100, height=100)


def test_entity_score_counts_covered_exposed_and_bursts() -> None:
    boxes = {str(f): [0.0, 0.0, 10.0, 10.0] for f in range(10)}
    cover = [Region((0, 0, 10, 10))]
    half = [Region((0, 0, 5, 10))]
    regions = {0: cover, 1: cover, 2: half, 3: half, 4: half, 5: cover, 6: half, 7: half, 8: cover, 9: cover}
    score = _score(boxes, regions)
    assert score.visible_frames == 10
    assert score.frames_covered_95 == 5
    assert score.frames_exposed == 5
    assert score.leak_bursts == 1  # frames 2-4 burst; 6-7 is too short
    assert not score.recalled
    assert score.worst[0][1] == 0.5


def test_over_blur_threshold_is_more_than_ten_percent() -> None:
    boxes = {str(f): [0.0, 0.0, 10.0, 10.0] for f in range(20)}
    hidden_two = {0: [Region((0, 0, 10, 10))], 1: [Region((0, 0, 10, 10))]}
    exactly_ten = _score(boxes, hidden_two, hide=False)
    assert exactly_ten.frames_hidden == 2
    assert not exactly_ten.over_blurred  # 10 % is not more than 10 %
    hidden_three = {**hidden_two, 2: [Region((0, 0, 10, 10))]}
    assert _score(boxes, hidden_three, hide=False).over_blurred


def test_recall_needs_95_percent_of_visible_frames() -> None:
    boxes = {str(f): [0.0, 0.0, 10.0, 10.0] for f in range(20)}
    all_but_one = {f: [Region((0, 0, 10, 10))] for f in range(19)}
    assert _score(boxes, all_but_one).recalled  # 19/20 = 95 %
    all_but_two = {f: [Region((0, 0, 10, 10))] for f in range(18)}
    assert not _score(boxes, all_but_two).recalled


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_mot_is_one_based_and_interpolated(tmp_path: Path) -> None:
    path = labels_file(
        tmp_path,
        [entity("e1", "e1.mot.txt", first=0, last=4)],
        mot={"e1.mot.txt": "1,1,0,0,10,10,1,-1,-1,-1\n5,1,40,0,10,10,1,-1,-1,-1\n"},
    )
    labels = load_labels(path)
    dense = labels.by_id["e1"].dense
    assert sorted(dense) == [0, 1, 2, 3, 4]
    assert dense[0] == (0.0, 0.0, 10.0, 10.0)
    assert dense[2] == (20.0, 0.0, 30.0, 10.0)
    assert dense[4] == (40.0, 0.0, 50.0, 10.0)


@pytest.mark.parametrize(
    ("mot", "message"),
    [
        ("0,1,0,0,1,1\n", "1-based"),
        ("1,1,0,0,0,1\n", "positive"),
        ("1,1,0,0\n", "6 columns"),
        ("1,1,0,0,1,1\n1,1,0,0,1,1\n", "twice"),
        ("1,1,0,0,1,1\n2,2,0,0,1,1\n", "one entity"),
        ("x,1,0,0,1,1\n", "number"),
    ],
)
def test_bad_mot_rows_are_refused(tmp_path: Path, mot: str, message: str) -> None:
    (tmp_path / "e.mot.txt").write_text(mot)
    with pytest.raises(LabelError, match=message):
        read_mot(tmp_path / "e.mot.txt")


def test_label_validation(tmp_path: Path) -> None:
    with pytest.raises(LabelError, match="ends after"):
        load_labels(labels_file(tmp_path, [entity("e", {"0": [0, 0, 1, 1]}, first=0, last=12)]))
    with pytest.raises(LabelError, match="outside the frame"):
        load_labels(labels_file(tmp_path, [entity("e", {"0": [0, 0, 2000, 1]}, first=0, last=0)]))
    with pytest.raises(LabelError, match="no box"):
        load_labels(labels_file(tmp_path, [entity("e", {"5": [0, 0, 1, 1]}, first=0, last=2)]))
    with pytest.raises(LabelError, match="unique"):
        load_labels(labels_file(tmp_path, [entity("e", {"0": [0, 0, 1, 1]}), entity("e", {"0": [0, 0, 1, 1]})]))
    with pytest.raises(LabelError, match="beside the label file"):
        load_labels(labels_file(tmp_path, [entity("e", "../outside.mot.txt")]))


def test_interpolate_never_extrapolates() -> None:
    keys = {2: (0.0, 0.0, 1.0, 1.0), 4: (2.0, 0.0, 3.0, 1.0)}
    assert sorted(interpolate(keys, 0, 10)) == [2, 3, 4]
    assert interpolate(keys, 3, 3) == {}


# ---------------------------------------------------------------------------
# A job, end to end
# ---------------------------------------------------------------------------


def test_score_job_on_the_example_job_is_deterministic(tmp_path: Path) -> None:
    job = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job)
    plan = Plan.model_validate_json((job / "plan.json").read_text())
    regions = frame_regions(plan)
    frame, entries = next(iter(sorted(regions.items())))
    x0, y0, x1, y1 = entries[0].box
    inside = [x0 + 1.0, y0 + 1.0, x1 - 1.0, y1 - 1.0]
    labels = ClipLabels.model_validate(
        {
            "clip": "SC-A-01.mp4",
            "fps": 30,
            "frames": 12,
            "width": 1280,
            "height": 720,
            "split": "synthetic",
            "entities": [
                entity("hidden", {str(frame): inside}, first=frame, last=frame),
                entity("clear", {"0": [1200.0, 650.0, 1210.0, 660.0]}, hide=False),
            ],
        }
    )
    path = tmp_path / "labels.json"
    path.write_text(labels.model_dump_json())
    first = score_job(job, load_labels(path))
    second = score_job(job, load_labels(path))
    assert first == second
    by_id = {e.id: e for e in first.entities}
    assert by_id["hidden"].frames_covered_95 == 1
    assert by_id["clear"].frames_hidden == 0
    assert first.cost_usd > 0
    summary = summarize([first])
    assert summary.entity_recall == 1.0
    assert summary.over_blur == 0.0
    assert summary.exposure_rate == 0.0
    assert summary.leak_bursts == 0
    assert summary.review_load_per_min is not None


def test_summary_of_nothing_has_no_rates() -> None:
    summary = summarize([])
    assert summary.entity_recall is None
    assert summary.cost_per_min is None
