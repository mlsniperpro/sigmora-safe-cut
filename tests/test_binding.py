"""WP3 step 1-2: point → track binding and face/person grouping, plus the geometry helpers they share."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from safecut.contracts import Rle, rle_runs
from safecut.decide import geometry as g
from safecut.decide.bind import Sighting, bind, match_point
from safecut.decide.group import group_tracks, inside_share
from tests.safety_factories import H, W, track


def disk_mask(cx: int, cy: int, r: int) -> Rle:
    yy, xx = np.mgrid[0:H, 0:W]
    return g.encode((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)


# ---------------------------------------------------------------------------------------------- geometry


@settings(max_examples=300, deadline=None)
@given(st.lists(st.booleans(), min_size=12, max_size=12), st.integers(1, 4))
def test_property_rle_round_trips(bits: list[bool], width: int) -> None:
    height = 12 // width if 12 % width == 0 else 1
    width = 12 // height
    mask = np.array(bits, dtype=np.bool_).reshape(height, width)
    rle = g.encode(mask)
    assert (g.decode(rle) == mask).all()
    assert sum(rle_runs(rle.counts)) == mask.size


def test_rle_round_trips_a_real_mask() -> None:
    rle = disk_mask(100, 90, 30)
    mask = g.decode(rle)
    assert mask.shape == (H, W)
    assert g.mask_bbox(mask) == (70, 60, 131, 121)
    assert g.encode(mask).counts == rle.counts


def test_dilate_and_shift() -> None:
    mask = g.decode(disk_mask(100, 90, 10))
    grown = g.dilate(mask, 5, 3)
    assert g.mask_bbox(grown) == (85, 77, 116, 104)
    assert (grown & mask).sum() == mask.sum()
    assert g.mask_bbox(g.shift(mask, 7, -4)) == (97, 76, 118, 97)
    assert not g.shift(mask, W, 0).any()
    assert not g.dilate(np.zeros((4, 4), dtype=np.bool_), 2, 2).any()


def test_box_helpers() -> None:
    assert g.iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert g.iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0
    assert g.grow((10, 10, 20, 20), 0.15, 8, W, H) == (0, 0, 30, 30)
    assert g.clamp((-3.2, 4.5, 400.1, 9.0), W, H) == (0, 4, W, 9)
    assert g.clamp((W + 1, 0, W + 9, 9), W, H) is None
    assert g.point_box_distance(25, 15, (10, 10, 20, 20)) == pytest.approx(6.0)
    assert g.union([(0, 5, 3, 9), (2, 1, 8, 4)]) == (0, 1, 8, 9)
    with pytest.raises(ValueError, match="outside"):
        g.grow((W, 0, W + 4, 4), 0.0, 0, W, H)


def test_box_at_interpolates_between_anchors_and_is_none_outside() -> None:
    t = track("face:1", 0, 10, (0, 0, 10, 10), step=(2, 0), anchors=[0, 10])
    assert g.box_at(t, 5) == (10, 0, 20, 10)
    assert g.box_at(t, 11) is None
    assert g.assign(np.array([[1.0, 5.0], [4.0, 1.0]])) == [(0, 1), (1, 0)]


# ---------------------------------------------------------------------------------------------- binding


def test_a_point_in_a_dilated_mask_binds_even_outside_the_raw_mask() -> None:
    t = track("face:1", 5, 5, (70, 60, 131, 121), masks={5: disk_mask(100, 90, 30)})
    assert match_point(100, 90, 5, [t], width=W, height=H) == "face:1"
    assert match_point(131, 90, 5, [t], width=W, height=H) == "face:1"  # 1 px outside, inside the 5 % dilation


def test_overlapping_masks_prefer_the_one_holding_the_point() -> None:
    a = track("face:1", 5, 5, (70, 60, 131, 121), masks={5: disk_mask(100, 90, 30)})
    b = track("face:2", 5, 5, (125, 60, 186, 121), masks={5: disk_mask(155, 90, 30)})
    assert match_point(110, 90, 5, [a, b], width=W, height=H) == "face:1"
    assert match_point(128, 90, 5, [a, b], width=W, height=H) is None  # in both raw masks: ambiguous


def test_near_two_dilated_masks_but_in_neither_raw_mask_is_ambiguous() -> None:
    a = track("face:1", 5, 5, (60, 60, 101, 101), masks={5: disk_mask(80, 80, 20)})
    b = track("face:2", 5, 5, (102, 60, 143, 101), masks={5: disk_mask(122, 80, 20)})
    assert match_point(101, 80, 5, [a, b], width=W, height=H) is None


def test_without_masks_the_nearest_box_within_a_tenth_of_the_diagonal_binds() -> None:
    a = track("face:1", 0, 9, (10, 10, 30, 30))
    b = track("face:2", 0, 9, (200, 10, 220, 30))
    assert match_point(40, 20, 3, [a, b], width=W, height=H) == "face:1"
    assert match_point(120, 100, 3, [a, b], width=W, height=H) is None  # > 0.1 x 367 px from both
    assert match_point(40, 20, 12, [a, b], width=W, height=H) is None  # no track on frame 12


def test_an_equal_distance_tie_binds_nothing() -> None:
    a = track("face:1", 0, 9, (10, 10, 30, 30))
    b = track("face:2", 0, 9, (51, 10, 71, 30))  # 11 px from the point either way
    assert match_point(40, 20, 3, [a, b], width=W, height=H) is None


def test_votes_across_keyframes_and_hungarian_conflicts() -> None:
    a = track("face:1", 0, 30, (10, 10, 30, 30))
    b = track("face:2", 0, 30, (60, 10, 80, 30))
    sightings = [
        Sighting("env", 1, 20, 20),
        Sighting("env", 2, 20, 20),
        Sighting("env", 3, 70, 20),
        Sighting("cup", 4, 70, 20),
        Sighting("cup", 5, 70, 20),
        Sighting("lost", 6, 300, 170),
    ]
    assert bind(sightings, [a, b], width=W, height=H) == {"cup": "face:2", "env": "face:1", "lost": None}


def test_a_key_that_loses_its_favourite_binds_nothing() -> None:
    a = track("face:1", 0, 30, (10, 10, 30, 30))
    b = track("face:2", 0, 30, (60, 10, 80, 30))
    sightings = [Sighting("x", f, 20, 20) for f in (1, 2, 3)] + [Sighting("y", f, 20, 20) for f in (1, 2, 3)]
    sightings.append(Sighting("y", 4, 70, 20))
    got = bind(sightings, [a, b], width=W, height=H)
    assert got["y"] is None or got["x"] is None
    assert bind([Sighting("t", 1, 20, 20), Sighting("t", 2, 70, 20)], [a, b], width=W, height=H) == {"t": None}
    assert bind([], [a], width=W, height=H) == {}


@settings(max_examples=500, deadline=None)
@given(st.integers(0, W - 21), st.integers(0, H - 21), st.integers(0, 19), st.integers(0, 19))
def test_property_a_point_inside_a_lone_box_binds_to_it(x: int, y: int, dx: int, dy: int) -> None:
    t = track("face:1", 0, 5, (x, y, x + 20, y + 20))
    assert bind([Sighting("k", 2, x + dx, y + dy)], [t], width=W, height=H) == {"k": "face:1"}


# ---------------------------------------------------------------------------------------------- grouping


def test_a_face_inside_a_body_on_80_percent_of_frames_groups() -> None:
    face = track("face:1", 0, 9, (20, 10, 40, 30))
    body = track("person:1", 0, 9, (10, 5, 60, 100))
    assert inside_share(face, body) == 1.0
    assert [[t.track_id for t in grp] for grp in group_tracks([face, body])] == [["face:1", "person:1"]]


def test_a_face_that_leaves_the_body_too_often_stays_apart() -> None:
    face = track("face:1", 0, 9, (20, 10, 40, 30), step=(12, 0))
    body = track("person:1", 0, 9, (10, 5, 60, 100))
    assert inside_share(face, body) < 0.8
    assert len(group_tracks([face, body])) == 2
    assert inside_share(face, track("person:2", 20, 29)) == 0.0


def test_a_face_equally_inside_two_bodies_pairs_with_neither() -> None:
    face = track("face:1", 0, 9, (20, 10, 40, 30))
    bodies = [track("person:1", 0, 9, (10, 5, 60, 100)), track("person:2", 0, 9, (15, 0, 70, 110))]
    assert len(group_tracks([face, *bodies])) == 3


def test_static_tracks_never_group() -> None:
    face = track("face:1", 3, 3, (20, 10, 40, 30), origin="static")
    body = track("person:1", 0, 9, (10, 5, 60, 100))
    assert len(group_tracks([face, body])) == 2
