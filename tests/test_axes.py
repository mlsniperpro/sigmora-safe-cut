"""PRE-A §5b frame axes: vectors T1–T5, T10, T11 and the §5b property bounds."""

from __future__ import annotations

import math
from fractions import Fraction
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from safecut.track.axes import (
    backfill_frames,
    crowded_span,
    from_proxy_table,
    player_frame,
    round_half_up,
    sam_fps_eff,
    slot,
    time_to_frame,
    to_proxy,
)


def proxy_frames(frames: int, job_fps: int, proxy_fps: int) -> int:
    """ffmpeg's real end-of-stream proxy count (§5b): ``round_half_up(N × proxy / fps)``, at least one."""
    return max(1, slot(frames, rate_in=job_fps, rate_out=proxy_fps))


T30 = from_proxy_table(900, 30, 8, 240)


def test_t1_from_proxy() -> None:
    assert [T30[j] for j in (0, 1, 2, 3, 4, 8, 120, 239)] == [1, 5, 9, 13, 16, 31, 451, 898]


def test_t2_to_proxy() -> None:
    got = [to_proxy(f, T30) for f in (0, 1, 2, 3, 4, 5, 6, 7, 450, 898, 899)]
    assert got == [0, 0, 0, 0, 1, 1, 1, 1, 120, 239, 239]


def test_t3_t4_round_trip() -> None:
    assert max(abs(T30[to_proxy(f, T30)] - f) for f in range(900)) == 2
    assert all(to_proxy(T30[j], T30) == j for j in range(240))


@pytest.mark.parametrize(
    ("t", "frame"), [(0.0, 0), (0.0249, 0), (0.025, 1), (1 / 30, 1), (0.05, 1), (29.99, 899), (31.0, 899)]
)
def test_t5_player(t: float, frame: int) -> None:
    assert player_frame(t, 30, 900) == frame


@pytest.mark.parametrize(("fps", "proxy", "want"), [(30, 8, 57), (25, 8, 47), (6, 6, 15)])
def test_t10_backfill(fps: int, proxy: int, want: int) -> None:
    assert backfill_frames(fps, proxy) == want


def test_t11_crowded_span() -> None:
    table = from_proxy_table(300, 30, 8, proxy_frames(300, 30, 8))
    assert table[:6] == [1, 5, 9, 13, 16, 20]
    assert list(crowded_span(0, table, 300)) == list(range(5))
    assert list(crowded_span(3, table, 300)) == list(range(10, 16))
    spans = set(crowded_span(3, table, 300)) | set(crowded_span(4, table, 300))
    assert sorted(spans) == list(range(10, 20))
    assert crowded_span(len(table) - 1, table, 300)[-1] == 299


def test_turn_time_to_frame_clamps() -> None:
    assert time_to_frame(0.4, 30, 900) == 12
    assert time_to_frame(-1.0, 30, 900) == 0
    assert time_to_frame(99.0, 30, 900) == 899


def test_round_half_up_is_not_bankers() -> None:
    assert round_half_up(Fraction(1, 2)) == 1
    assert round_half_up(Fraction(5, 2)) == 3


def test_rejects_bad_rates() -> None:
    with pytest.raises(ValueError, match="positive"):
        sam_fps_eff(0, 8)
    with pytest.raises(ValueError, match="never faster"):
        from_proxy_table(10, 6, 8, 10)
    with pytest.raises(ValueError, match="at least one"):
        from_proxy_table(0, 30, 8, 1)
    with pytest.raises(ValueError, match="empty"):
        to_proxy(3, [])
    with pytest.raises(ValueError, match="out of range"):
        crowded_span(5, [0, 1], 2)


@given(
    frames=st.integers(1, 1800),
    job_fps=st.integers(1, 30),
    sam=st.integers(1, 10),
    data=st.data(),
)
def test_property_bounds(frames: int, job_fps: int, sam: int, data: st.DataObject) -> None:
    proxy = sam_fps_eff(job_fps, sam)
    n = proxy_frames(frames, job_fps, proxy)
    table = from_proxy_table(frames, job_fps, proxy, n)
    assert len(table) == n
    assert all(0 <= f < frames for f in table)
    assert all(a <= b for a, b in pairwise(table))
    for j in range(n):
        assert to_proxy(table[j], table) == j or table[to_proxy(table[j], table)] == table[j]
    f = data.draw(st.integers(0, frames - 1))
    j = to_proxy(f, table)
    assert 0 <= j < n
    assert abs(table[j] - f) <= math.ceil(job_fps / proxy) or f > table[-1]
    # The spans of all proxy frames cover the whole clip (fail closed: no prepared frame is left out), and each
    # contains the frame its proxy frame shows.
    assert {i for k in range(n) for i in crowded_span(k, table, frames)} == set(range(frames))
    assert all(table[k] in crowded_span(k, table, frames) for k in range(n))
    assert backfill_frames(job_fps, proxy) >= 15


@given(t=st.floats(0, 120, allow_nan=False), fps=st.integers(1, 30), frames=st.integers(1, 3600))
def test_property_time_maps_monotone_in_bounds(t: float, fps: int, frames: int) -> None:
    for fn in (player_frame, time_to_frame):
        a, b = fn(t, fps, frames), fn(t + 0.01, fps, frames)
        assert 0 <= a <= b < frames
