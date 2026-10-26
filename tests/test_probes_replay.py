"""Replay end-to-end: every probe a-h runs against mocked Meta and Baseten APIs, writes its fixtures,
logs its spend and deletes its uploads. This is the path the live probes take once the keys exist."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
import respx
from pydantic import SecretStr

from safecut.config import Settings
from safecut.contracts import measured_usd, read_cost_lines
from safecut.meta.budget import LocalLedger
from scripts.probes import probes
from tests.conftest import BASE, completed, stream_response, text_response

SAM_LINE = "<10f>0<|box;x1=30;y1=60;x2=70;y2=100;w=320;h=180;c=0.9|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"


def _sam_stream() -> httpx.Response:
    lane = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    return stream_response(
        {"type": "response.output_text.delta", "delta": SAM_LINE, **lane},
        {"type": "response.content_part.done", **lane, "part": {"type": "output_text", "text": SAM_LINE}},
        completed({"id": "resp_sam", "status": "completed", "usage": {"video_frames_processed": 90}}),
    )


def _responses(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if body["model"] == "sam-3.1":
        return _sam_stream()
    fmt = body.get("text", {}).get("format", {}).get("name")
    if fmt == "point":
        return stream_response(completed(text_response('{"x": 732, "y": 330}')))
    answer = {
        "frame_red_centre_crosses_middle": 64,
        "beep_heard": True,
        "beep_first_frame": 30,
        "beep_last_frame": 44,
        "summary": "two squares",
    }
    usage = {"input_tokens": 6000, "output_tokens": 300}
    return stream_response(completed(text_response(json.dumps(answer), usage=usage)))


@pytest.fixture
def api(tmp_path: Path) -> Iterator[respx.MockRouter]:
    uploads = iter(range(1, 100))
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{BASE}/status").mock(
            return_value=httpx.Response(200, json={"is_alive": True, "service_status": "operational"})
        )
        router.get(f"{BASE}/models").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "sam-3.1"}, {"id": "muse-spark-1.3"}]})
        )
        router.post(f"{BASE}/files").mock(
            side_effect=lambda _: httpx.Response(200, json={"id": f"file-{next(uploads)}"})
        )
        router.delete(url__regex=rf"{BASE}/files/file-\d+").mock(
            return_value=httpx.Response(200, json={"deleted": True})
        )
        router.post(f"{BASE}/responses/input_tokens").mock(
            return_value=httpx.Response(200, json={"input_tokens": 6000})
        )
        router.post(f"{BASE}/responses").mock(side_effect=_responses)
        router.post(f"{BASE}/asr/transcribe").mock(
            return_value=httpx.Response(200, json={"transcript": "", "audioDurationMs": 3000, "turns": []})
        )
        router.post("https://inference.baseten.co/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"x": 731, "y": 331}'}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1600, "completion_tokens": 40},
                },
            )
        )
        yield router


async def test_all_probes_replay(api: respx.MockRouter, tmp_path: Path) -> None:
    cfg = Settings(model_api_key=SecretStr("k"), baseten_api_key=SecretStr("b"))
    out = tmp_path / "probes"
    results = await probes.run(list("abcdefgh"), settings=cfg, out_root=out, ledger=LocalLedger())
    assert all("error" not in r for r in results.values()), results
    assert results["a"]["missing"] == ["muse-wonder-1.0", "muse-voice-transcribe-1.0", "muse-spark-1.2"]
    red = results["b"]["concepts"]["red square"]
    assert red["records"] == 1
    assert red["confidence_present"] is True
    assert red["frames_billed"] == 90
    assert red["mean_iou_vs_truth"] is not None
    assert results["b"]["input_video_fps_8"]["accepted"] is True
    assert results["c"]["frame_error"] == abs(64 - probes._frame_when_red_crosses_centre())
    assert results["d"]["audio_duration_ms"] == 3000
    assert set(results["f"]) - {"uploads_deleted"} == {
        "muse-spark-1.3@max",
        "muse-wonder-1.0@max",
        "muse-wonder-1.0@medium",
    }
    assert results["g"]["error_px"] < 5
    assert results["h"]["model"] == "meta-models/muse-spark-open-1026"
    assert all(r["uploads_deleted"] is True for r in results.values())
    for name in "abcdefgh":
        assert json.loads((out / name / "summary.json").read_text()) == results[name]
    lines = list(read_cost_lines(out / "cost.jsonl"))
    measured, estimated = measured_usd(lines)
    assert estimated == 0
    assert 0 < measured < probes.PROBE_BUDGET_USD
    assert {line.code_kind for line in lines} == {"owner"}


async def test_probe_budget_stops_spend(api: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "PROBE_BUDGET_USD", 0.0001)
    cfg = Settings(model_api_key=SecretStr("k"))
    results = await probes.run(["c"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    assert "BudgetExceeded" in results["c"]["error"]
    lines = list(read_cost_lines(tmp_path / "cost.jsonl"))
    assert any(line.cap == "code" for line in lines)


async def test_a_failing_probe_does_not_stop_the_rest(api: respx.MockRouter, tmp_path: Path) -> None:
    api.get(f"{BASE}/models").mock(return_value=httpx.Response(401, json={"error": {"message": "bad key"}}))
    cfg = Settings(model_api_key=SecretStr("k"))
    results = await probes.run(["a", "g"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    assert "MetaAuthError" in results["a"]["error"]
    assert "error" not in results["g"]


def test_grid_mapping_vectors() -> None:
    # PRE-A §11.2 G1, G3, G4, G6 (frame 1280x720, bar 40).
    assert probes.grid_to_frame(500, 500) == (640, 340)
    assert probes.grid_to_frame(1001, 1000) == (1279, 719)
    assert probes.grid_to_frame(0, 52) == (0, 0)
    assert probes.grid_to_frame(250, 750) == (320, 530)


def test_cli_rejects_unknown_probes(capsys: pytest.CaptureFixture[str]) -> None:
    assert probes.main(["z"]) == 2
    assert "usage" in capsys.readouterr().err


def test_dot_image_is_the_documented_size() -> None:
    data = probes.dot_image().split(",", 1)[1]
    img = cv2.imdecode(np.frombuffer(base64.b64decode(data), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    assert img.shape == (760, 1280, 3)
    x, y = probes.DOT
    b, g, r = (int(v) for v in img[y + 40, x])
    assert r > 200
    assert g < 60
    assert b < 60


async def test_hero_clip_runs_the_base_concepts(api: respx.MockRouter, tmp_path: Path) -> None:
    hero = tmp_path / "hero.mp4"
    hero.write_bytes(probes.CLIP.read_bytes())
    cfg = Settings(model_api_key=SecretStr("k"))
    results = await probes.run(["b"], settings=cfg, out_root=tmp_path / "out", ledger=LocalLedger(), clip=hero)
    assert results["b"]["synthetic"] is False
    assert set(results["b"]["concepts"]) == set(probes.HERO_CONCEPTS)
    assert results["b"]["frames"] == 90
    assert "input_video_fps_8" not in results["b"]


def test_cli_rejects_a_missing_clip(capsys: pytest.CaptureFixture[str]) -> None:
    assert probes.main(["b", "--clip=/nonexistent.mp4"]) == 2
    assert "no such clip" in capsys.readouterr().err
