"""The documented-shape API fixtures (and their live twins, once the probes ran) go through our parsers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from meta_sam_parser import (
    CompletedOutcome,
    IncompleteOutcome,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    parse_responses_stream,
    video_segmentation_format,
)

from safecut.meta import asr, responses, sam
from safecut.meta.client import MetaClient
from safecut.meta.errors import MetaIncomplete, MetaRefusal
from scripts.probes.trim import trim

FIX = Path(__file__).resolve().parent.parent / "fixtures"
VECTORS = json.loads((FIX / "sam" / "vectors.json").read_text())


def _parse_lines(lines: list[str], *, terminal: bool) -> Any:
    parser = video_segmentation_format().create_parser()
    for line in lines:
        parser.push(line + "\n")
    outcome = CompletedOutcome() if terminal else IncompleteOutcome(reason="eof")
    return parser.finish(outcome).result


def _boxes(result: Any) -> list[SegmentationBoxRecord]:
    return [r for r in result.records if isinstance(r, SegmentationBoxRecord)]


def _errors(result: Any) -> list[Any]:
    return [d for d in result.diagnostics if str(getattr(d, "severity", "")).endswith("error")]


def test_s1_one_box_and_mask() -> None:
    result = _parse_lines(VECTORS["S1"]["lines"], terminal=True)
    (box,) = _boxes(result)
    assert box.frame is not None
    assert (box.object_id, box.frame.frame_index, box.left, box.top, box.right, box.bottom) == ("0", 7, 10, 20, 15, 25)
    (mask,) = [r for r in result.records if isinstance(r, SegmentationMaskRecord)]
    assert (mask.mask.width, mask.mask.height) == (5, 5)
    assert not _errors(result)


def test_s3_confidence_and_s4_arrival_order() -> None:
    (box,) = _boxes(_parse_lines(VECTORS["S3"]["lines"], terminal=True))
    assert box.confidence == pytest.approx(0.75)
    order = [
        (b.object_id, b.frame.frame_index)
        for b in _boxes(_parse_lines(VECTORS["S4"]["lines"], terminal=True))
        if b.frame
    ]
    assert order == [("12", 9), ("0", 7)]


def test_s5_malformed_s6_empty_s7_eof() -> None:
    s5 = _parse_lines(VECTORS["S5"]["lines"], terminal=True)
    assert not _boxes(s5)
    assert len(_errors(s5)) == 1
    s6 = _parse_lines(VECTORS["S6"]["lines"], terminal=True)
    assert not _boxes(s6)
    assert not _errors(s6)
    s7 = _parse_lines(VECTORS["S7"]["lines"], terminal=False)
    assert len(_boxes(s7)) == 1
    assert str(s7.outcome.status).endswith("incomplete")


def _twins(folder: str, stem: str) -> list[Path]:
    return [p for p in (FIX / folder / stem, *sorted((FIX / folder).glob("live-*"))) if p.exists()]


async def _aiter(events: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for event in events:
        yield event


@pytest.mark.parametrize("path", _twins("sam", "s1_stream.events.json"), ids=lambda p: p.name)
async def test_sam_stream_fixtures_parse(path: Path) -> None:
    events = json.loads(path.read_text())
    async with parse_responses_stream(_aiter(events), video_segmentation_format()) as parsed:
        final = await parsed.final_result()
    assert not _errors(final)
    usage, usd = sam.video_meter(events[-1]["response"])
    assert usage["frames"] >= 0
    assert usd >= 0


def test_muse_fixtures() -> None:
    role = json.loads((FIX / "muse" / "role_pass.events.json").read_text())[-1]["response"]
    assert json.loads(responses.output_text(role))["tracks"][0]["role"] == "participant"
    units, usd = responses.meter_for("muse-spark-1.3")(role)
    assert units["cached"] == 45_000
    assert usd == pytest.approx(0.02625)
    with pytest.raises(MetaRefusal):
        responses.output_text(json.loads((FIX / "muse" / "refusal.events.json").read_text())[-1]["response"])
    incomplete = json.loads((FIX / "muse" / "incomplete.events.json").read_text())[-1]
    outcome = MetaClient._terminal(incomplete, responses.meter_for("muse-spark-1.3"))  # pyright: ignore[reportPrivateUsage] -- the terminal-event rule under test
    assert outcome is not None
    assert isinstance(outcome.error, MetaIncomplete)
    assert not outcome.error.eof
    assert outcome.usd > 0


@pytest.mark.parametrize("path", _twins("asr", "diarization.json"), ids=lambda p: p.name)
def test_asr_fixtures_map_to_transcripts(path: Path) -> None:
    raw = asr.AsrResponse.model_validate_json(path.read_text())
    transcript = asr.to_transcript(raw, source_model="muse-voice-transcribe-1.0")
    assert all(t.end >= t.start for t in transcript.turns)


def test_diarization_fixture_labels() -> None:
    raw = asr.AsrResponse.model_validate_json((FIX / "asr" / "diarization.json").read_text())
    assert [t.speaker for t in asr.to_transcript(raw, source_model="m").turns] == ["S1", "S2", "U1"]


def test_trim_copies_live_probe_responses(tmp_path: Path) -> None:
    probes = tmp_path / "fixtures" / "probes"
    for sub in ("b", "c", "d"):
        (probes / sub).mkdir(parents=True)
    for folder in ("sam", "muse", "asr"):
        (tmp_path / "fixtures" / folder).mkdir(parents=True)
    (probes / "b" / "sam-red_square.events.json").write_text("[]")
    (probes / "c" / "probe_c-muse-spark-1.3-medium.response.json").write_text('{"id": "r"}')
    assert trim(tmp_path) == ["sam/live-red_square.events.json", "muse/live-scene.events.json"]
    assert trim(tmp_path / "nothing") == []
