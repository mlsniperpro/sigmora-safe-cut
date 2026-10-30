"""Properties of the SAM stream wrapper and the linker (WP1 steps 2 and 4), over random streams and detections."""

from __future__ import annotations

import asyncio
import string
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from safecut.meta import sam
from safecut.meta.errors import MetaIncomplete, MetaRefusal
from safecut.track import link
from safecut.track.axes import from_proxy_table
from safecut.track.synthetic import events, stream_text

W, H = 64, 48

box = st.tuples(st.integers(0, W - 2), st.integers(0, H - 2), st.integers(1, 12), st.integers(1, 12)).map(
    lambda b: (b[0], b[1], min(W, b[0] + b[2]), min(H, b[1] + b[3]))
)
#: {object_id: {proxy_frame: box}}
objects = st.dictionaries(st.integers(0, 40).map(str), st.dictionaries(st.integers(0, 30), box, max_size=8), max_size=4)


def chunked(text: str, cuts: list[int], response_id: str = "resp_p") -> list[dict[str, Any]]:
    """The documented event sequence, with the lane text split into deltas at ``cuts``."""
    whole = events(text, response_id=response_id, frames_billed=50)
    points = sorted({c % (len(text) + 1) for c in cuts} | {0, len(text)})
    deltas = [text[a:b] for a, b in pairwise(points) if b > a]
    lane = {"item_id": "msg_synthetic", "output_index": 0, "content_index": 0}
    middle = [{"type": "response.output_text.delta", "delta": d, **lane} for d in deltas]
    return [whole[0], *middle, *whole[-2:]]


def parse(evs: list[dict[str, Any]]) -> sam.Segmentation:
    return asyncio.run(sam.parse_video_events(evs))


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(objs=objects, cuts=st.lists(st.integers(0, 10_000), max_size=12))
def test_any_valid_stream_parses_to_exactly_its_boxes(objs: dict[str, dict[int, Any]], cuts: list[int]) -> None:
    text = stream_text(objs, (W, H))
    seg = parse(chunked(text, cuts))
    got = {(d.object_id, d.frame): d.box for d in seg.detections}
    want = {(oid, f): b for oid, frames in objs.items() for f, b in frames.items()}
    assert got == want
    assert all(d.mask is not None for d in seg.detections)
    assert seg.frames_billed == 50


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(
    objs=objects.filter(bool),
    at=st.integers(0, 10_000),
    junk=st.text(alphabet=string.printable, min_size=1, max_size=6),
)
def test_a_corrupted_stream_never_parses_silently_wrong(objs: dict[str, dict[int, Any]], at: int, junk: str) -> None:
    """Splice junk anywhere into a valid stream. Junk without digits gives exactly the original boxes (e.g. an extra
    optional comma) or a typed error. A digit can legitimately make another valid number (``<0f>`` → ``<10f>``: the
    wire is the truth), so then the result is a typed error or well-formed, in-frame detections."""
    text = stream_text(objs, (W, H))
    if not text:
        return
    cut = at % len(text)
    broken = text[:cut] + junk + text[cut:]
    want = {(oid, f): b for oid, frames in objs.items() for f, b in frames.items()}
    try:
        seg = parse(chunked(broken, []))
    except (MetaIncomplete, MetaRefusal):
        return
    got = {(d.object_id, d.frame): d.box for d in seg.detections}
    if not any(c.isdigit() for c in junk):
        assert got == want
    for d in seg.detections:
        assert d.object_id.isdigit()
        assert 0 <= d.box[0] < d.box[2] <= W
        assert 0 <= d.box[1] < d.box[3] <= H


@given(objs=objects.filter(bool))
def test_a_stream_that_stops_early_is_incomplete(objs: dict[str, dict[int, Any]]) -> None:
    evs = chunked(stream_text(objs, (W, H)), [])
    with pytest.raises(MetaIncomplete) as err:
        parse(evs[:-1])
    assert err.value.eof


@given(
    frames=st.lists(st.integers(0, 60), min_size=1, max_size=40, unique=True),
    gap=st.integers(0, 4),
)
def test_split_never_merges_across_a_long_gap(frames: list[int], gap: int) -> None:
    pieces = link.split_on_gaps(frames, gap)
    assert sorted(f for p in pieces for f in p) == sorted(frames)
    for piece in pieces:
        assert all(b - a - 1 <= gap for a, b in pairwise(piece))
    for a, b in pairwise(pieces):
        assert b[0] - a[-1] - 1 > gap


@given(
    detections=st.lists(
        st.tuples(st.integers(0, 3).map(str), st.integers(0, 23), box),
        min_size=1,
        max_size=40,
        unique_by=lambda d: d[:2],
    )
)
def test_linked_tracks_are_dense_in_frame_and_numbered_once(detections: list[tuple[str, int, Any]]) -> None:
    table = from_proxy_table(90, 30, 8, 24)
    geometry = link.Frame(width=W, height=H, frames=90, from_proxy=table)
    dets = [sam.Detection(frame=j, object_id=o, box=b, mask=None, confidence=None) for o, j, b in detections]
    tracks = link.link_request(dets, request=0, labels=lambda _o: link.ObjectLabel("face", "face"), geometry=geometry,
                               source="sam-3.1", numbering={})  # fmt: skip
    assert len({t.track_id for t in tracks}) == len(tracks)
    by_id = {t.track_id: t for t in tracks}
    for t in tracks:
        assert list(t.boxes) == list(range(t.first, t.last + 1))
        assert all(0 <= b[0] < b[2] <= W and 0 <= b[1] < b[3] <= H for b in t.boxes.values())
        if t.reentry_of is not None:
            before = by_id[t.reentry_of]
            assert before.last < t.first
            assert before.sam_object == t.sam_object
    anchors = {(t.sam_object.object_id if t.sam_object else "", f) for t in tracks for f in t.boxes}
    for o, j, _ in detections:
        assert (o, table[j]) in anchors  # every detection lands on its prepared frame


@given(a=box, b=box, t=st.floats(0, 1, allow_nan=False))
def test_interpolation_rounds_outward_and_stays_in_frame(a: Any, b: Any, t: float) -> None:
    raw = link.interpolate(a, b, t)
    got = link.clamp_box(raw, W, H)
    assert got is not None
    assert got[0] <= raw[0] + 1e-9
    assert got[1] <= raw[1] + 1e-9
    assert got[2] >= min(raw[2], W) - 1e-9
    assert got[3] >= min(raw[3], H) - 1e-9


async def test_parsing_never_blocks_the_event_loop() -> None:
    """Other SAM streams of the job keep being read while a long one is parsed (the parse runs off the loop)."""
    text = stream_text({str(k): dict.fromkeys(range(40), (0, 0, 40, 30)) for k in range(4)}, (W, H))
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    task = asyncio.create_task(ticker())
    seg = await sam.parse_video_events(chunked(text, []))
    task.cancel()
    assert len(seg.detections) == 160
    assert ticks > 10


def test_a_repeated_object_on_a_frame_is_joined_never_dropped() -> None:
    """Two records for one object on one frame: the union box (hides both), without a mask (neither fits it)."""
    first = stream_text({"0": {3: (10, 10, 20, 20)}, "1": {3: (40, 30, 50, 40)}}, (W, H))
    again = stream_text({"0": {3: (30, 12, 44, 30)}}, (W, H))
    seg = parse(chunked(first + again, []))
    got = {d.object_id: d for d in seg.detections}
    assert got["0"].box == (10, 10, 44, 30)
    assert got["0"].mask is None
    assert got["1"].box == (40, 30, 50, 40)
    assert got["1"].mask is not None


def test_a_mask_larger_than_the_proxy_is_refused_before_decoding() -> None:
    text = stream_text({"0": {3: (10, 10, 20, 20)}}, (W, H)).replace("data=10,10,", f"data={H + 1},10,", 1)
    assert f"data={H + 1},10," in text
    with pytest.raises(MetaIncomplete, match="larger than"):
        asyncio.run(sam.parse_video_events(chunked(text, []), size=(W, H)))
