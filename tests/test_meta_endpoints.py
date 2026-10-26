"""Responses, Files, ASR, SAM, SSE and status helpers on top of the transport (respx-mocked)."""

from __future__ import annotations

import json
import time
import wave
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from hypothesis import given
from hypothesis import strategies as st
from meta_sam_parser import SegmentationBoxRecord, parse_responses_stream, video_segmentation_format
from pydantic import BaseModel, SecretStr

from safecut.config import ConfigError, Settings
from safecut.contracts import FilesIndex, load
from safecut.meta import asr, openweight, responses, sam
from safecut.meta.budget import Caller, job_limit
from safecut.meta.client import FORBIDDEN_PARAMS
from safecut.meta.errors import MetaConfigError, MetaIncomplete, MetaRefusal, MetaUnavailable
from safecut.meta.files import FileStore, sha256_file
from safecut.meta.sse import SSEDecodeError, iter_sse
from safecut.meta.status import StatusUnavailableError, fetch_status
from tests.conftest import BASE, Harness, completed, sse, stream_response, text_response

# --- SSE ---------------------------------------------------------------------


def test_sse_decodes_events_comments_and_multiline_data() -> None:
    lines = [
        ": keep-alive",
        "event: response.created",
        'data: {"response": {"id": "r"}}',
        "",
        'data: {"type": "a",',
        'data: "n": 1}',
        "",
        "data: [DONE]",
        "",
        'data: {"type": "tail"}',
    ]
    assert list(iter_sse(lines)) == [
        {"response": {"id": "r"}, "type": "response.created"},
        {"type": "a", "n": 1},
        {"type": "tail"},
    ]


def test_sse_rejects_non_object_data() -> None:
    with pytest.raises(SSEDecodeError):
        list(iter_sse(["data: [1, 2]", ""]))
    with pytest.raises(SSEDecodeError):
        list(iter_sse(["data: {", ""]))


_json_values = st.recursive(
    st.none() | st.booleans() | st.integers(-(10**6), 10**6) | st.text(max_size=10),
    lambda kids: st.lists(kids, max_size=3) | st.dictionaries(st.text(max_size=8), kids, max_size=3),
    max_leaves=10,
)


@given(st.lists(st.dictionaries(st.text(min_size=1, max_size=8), _json_values, min_size=1, max_size=4), max_size=8))
def test_sse_round_trips_any_json_objects(events: list[dict[str, Any]]) -> None:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    assert list(iter_sse(body.split("\n"))) == events


# --- Responses -----------------------------------------------------------------


def _user(text: str, *, image: bool = False) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    if image:
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64,AAAA"})
    return {"role": "user", "content": content}


def test_build_body_defaults() -> None:
    body = responses.build_body(
        "muse-spark-1.3", [_user("hi")], effort="max", schema={"type": "object"}, schema_name="role_pass"
    )
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "max"}
    assert body["max_output_tokens"] == 48_000
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "role_pass",
        "strict": True,
        "schema": {"type": "object"},
    }
    assert not FORBIDDEN_PARAMS & set(body)
    omit = responses.build_body("muse-spark-1.2", [_user("hi")], effort="omit")
    assert "reasoning" not in omit
    assert "text" not in omit


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model": "muse-spark-1.3-contributor"}, "Contributor"),
        ({"effort": "none"}, "unknown reasoning effort"),
        ({"messages": [{"role": "system", "content": [{"type": "input_image", "image_url": "x"}]}]}, "user messages"),
        ({"schema": {}, "schema_name": "bad name!"}, "schema name"),
    ],
)
def test_build_body_refuses(kwargs: dict[str, Any], message: str) -> None:
    args: dict[str, Any] = {"model": "muse-spark-1.3", "messages": [_user("hi")], "effort": "medium"} | kwargs
    with pytest.raises(ValueError, match=message):
        responses.build_body(args.pop("model"), args.pop("messages"), **args)


def test_output_text() -> None:
    assert responses.output_text(text_response("abc")) == "abc"
    with pytest.raises(MetaIncomplete):
        responses.output_text({"output": [{"type": "reasoning"}]})
    with pytest.raises(MetaRefusal):
        responses.output_text({"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]})


class _Verdict(BaseModel):
    role: str


async def test_create_json_reasks_once_r11(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(200, json={"input_tokens": 500}))
    mock_api.post("/responses").mock(
        side_effect=[
            stream_response(completed(text_response('{"nope": 1}'))),
            stream_response(completed(text_response('{"role": "bystander"}', rid="resp_2"))),
        ]
    )
    body = responses.build_body("muse-spark-1.3", [_user("who?", image=True)], effort="medium")
    verdict, result = await responses.create_json(h.client, _Verdict, body, stage="role", effort="medium")
    assert verdict.role == "bystander"
    assert result.request_id == "resp_2"
    paid = [line for line in h.costs() if line.stage == "role"]
    assert len(paid) == 2
    assert all(not line.estimated for line in paid)


async def test_create_json_fails_closed_after_two_invalid(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(404))
    mock_api.post("/responses").mock(return_value=stream_response(completed(text_response("not json"))))
    body = responses.build_body("muse-spark-1.3", [_user("who?")], effort="medium")
    with pytest.raises(responses.InvalidOutputError, match="twice"):
        await responses.create_json(h.client, _Verdict, body, stage="role", effort="medium")


async def test_count_failure_falls_back_to_the_estimate(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, ledger: Any
) -> None:
    h = make_harness()
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(500))
    mock_api.post("/responses").mock(return_value=stream_response(completed(text_response("{}"))))
    body = responses.build_body("muse-spark-1.3", [_user("x" * 400, image=True)], effort="medium")
    assert await responses.count_input_tokens(h.client, body, stage="role") is None
    result = await responses.create(h.client, body, stage="role", effort="medium", count=False)
    assert result.usd > 0


# --- Files ---------------------------------------------------------------------


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "sam_proxy.mp4"
    path.write_bytes(b"\x00\x01fake-mp4" * 100)
    return path


async def test_upload_is_idempotent_and_recorded(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    route = mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-42", "object": "file"}))
    store = FileStore(h.client, tmp_path / "job")
    assert await store.upload(clip, "sam_proxy.mp4") == "file-42"
    assert await store.upload(clip, "sam_proxy.mp4") == "file-42"
    assert route.call_count == 1
    form = route.calls[0].request.content
    assert b'name="purpose"' in form
    assert b"user_data" in form
    assert b"expires_after[seconds]" in form
    assert b"21600" in form
    assert b'filename="j_test-sam_proxy.mp4"' in form
    entry = load(store.index_path, FilesIndex).root[0]
    assert (entry.name, entry.file_id, entry.sha256) == ("sam_proxy.mp4", "file-42", sha256_file(clip))


async def test_delete_all_treats_file_not_found_as_deleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(
        side_effect=[httpx.Response(200, json={"id": "file-1"}), httpx.Response(200, json={"id": "file_2"})]
    )
    mock_api.delete("/files/file-1").mock(return_value=httpx.Response(200, json={"id": "file-1", "deleted": True}))
    mock_api.delete("/files/file_2").mock(
        return_value=httpx.Response(404, json={"error": {"code": "file_not_found", "param": None}})
    )
    store = FileStore(h.client, tmp_path / "job")
    await store.upload(clip, "sam_proxy.mp4")
    other = tmp_path / "prepared.mp4"
    other.write_bytes(b"other")
    await store.upload(other, "prepared.mp4")
    assert await store.delete_all() is True
    assert store.index().all_deleted


async def test_delete_with_empty_404_is_a_config_error_and_stays_undeleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-1"}))
    mock_api.delete("/files/file-1").mock(return_value=httpx.Response(404))
    store = FileStore(h.client, tmp_path / "job")
    await store.upload(clip, "sam_proxy.mp4")
    with pytest.raises(MetaConfigError):
        await store.delete_all()
    assert not store.index().all_deleted
    assert len(store.stale(older_than=timedelta(0))) == 1


async def test_upload_timeout_finds_and_deletes_the_orphan(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    size = len(clip.read_bytes())
    mock_api.post("/files").mock(side_effect=httpx.ReadTimeout("slow"))
    listing = {
        "data": [
            {
                "id": "file-9",
                "filename": "j_test-sam_proxy.mp4",
                "bytes": size,
                "created_at": time.time(),
            },
            {"id": "file-8", "filename": "other-job.mp4", "bytes": 1, "created_at": time.time()},
        ]
    }
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    deleted = mock_api.delete("/files/file-9").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable):
        await store.upload(clip, "sam_proxy.mp4")
    assert deleted.call_count == 1
    (entry,) = store.index().root
    assert entry.file_id == "file-9"
    assert entry.deleted_at is not None


async def test_upload_timeout_without_listing_records_an_orphan(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(side_effect=httpx.ReadTimeout("slow"))
    mock_api.get("/files").mock(return_value=httpx.Response(404))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable):
        await store.upload(clip, "sam_proxy.mp4")
    (entry,) = store.index().root
    assert entry.orphan
    assert entry.file_id is None
    assert not store.index().all_deleted


async def test_upload_response_without_an_id(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"object": "file"}))
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(MetaConfigError, match="no file id"):
        await FileStore(h.client, tmp_path / "job").upload(clip, "sam_proxy.mp4")


# --- ASR -------------------------------------------------------------------------


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24_000)
        out.writeframes(b"\x00\x00" * 24_000 * 2)
    return path


def test_request_part_validates_mode() -> None:
    part = asr.request_part("muse-voice-transcribe-1.0", mode="DIARIZATION", language_bias=["English"])
    assert part == {
        "mode": "DIARIZATION",
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "keywords": [],
        "languageBias": ["English"],
    }
    assert "languageBias" not in asr.request_part("m", mode="ENDPOINTING", language_bias=[])
    with pytest.raises(ValueError, match="ignore it silently"):
        asr.request_part("m", mode="diarization", language_bias=[])


def test_to_transcript_maps_letters_and_unattributed_turns() -> None:
    raw = asr.AsrResponse.model_validate(
        {
            "audioDurationMs": 9000,
            "turns": [
                {"startMs": 3000, "endMs": 4000, "transcript": "b", "speaker": "B"},
                {"startMs": 0, "endMs": 1500, "transcript": "a", "speaker": "A"},
                {"startMs": 5000, "endMs": 4900, "transcript": "?"},
                {"startMs": 6000, "endMs": 7000, "transcript": "a again", "speaker": "A"},
                {"startMs": 8000, "endMs": 8500, "transcript": "??"},
            ],
        }
    )
    t = asr.to_transcript(raw, source_model="muse-voice-transcribe-1.0")
    assert [(x.speaker, x.start, x.end) for x in t.turns] == [
        ("S1", 0.0, 1.5),
        ("S2", 3.0, 4.0),
        ("U1", 5.0, 5.0),
        ("S1", 6.0, 7.0),
        ("U2", 8.0, 8.5),
    ]
    assert t.source_kind == "primary"


async def test_transcribe_sends_multipart_and_meters(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, wav: Path, settings: Settings
) -> None:
    h = make_harness()
    route = mock_api.post("/asr/transcribe").mock(
        return_value=httpx.Response(
            200, json={"transcript": "hi", "audioDurationMs": 2000, "turns": [], "sessionId": "s"}
        )
    )
    result = await asr.transcribe(h.client, wav, model=settings.asr_model, language_bias=settings.asr_language_bias)
    assert result.audio_duration_ms == 2000
    content = route.calls[0].request.content
    assert b'name="request"' in content
    assert b"application/json" in content
    assert b"DIARIZATION" in content
    assert b'name="audio"' in content
    (line,) = h.costs()
    assert line.units == {"audio_s": 2}
    assert line.usd == pytest.approx(0.0001)


async def test_r14_asr_500_retries_once(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, wav: Path
) -> None:
    h = make_harness()
    route = mock_api.post("/asr/transcribe").mock(return_value=httpx.Response(500))
    with pytest.raises(MetaUnavailable):
        await asr.transcribe(h.client, wav, model="muse-voice-transcribe-1.0", language_bias=[])
    assert route.call_count == 2
    assert [line.usd for line in h.costs()] == [0, 0]


async def test_asr_bad_shape_and_bad_audio(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, wav: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/asr/transcribe").mock(return_value=httpx.Response(200, json={"turns": "nope"}))
    with pytest.raises(MetaIncomplete, match="documented shape"):
        await asr.transcribe(h.client, wav, model="m", language_bias=[])
    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(b"\x00" * 64)
    with pytest.raises(ValueError, match="mono"):
        await asr.transcribe(h.client, stereo, model="m", language_bias=[])


# --- SAM through Meta's official parser ----------------------------------------


def test_sam_bodies(settings: Settings) -> None:
    body = sam.video_body(settings, file_id="file-1", text="face")
    assert body["store"] is False
    assert body["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}
    assert body["input"][0]["content"][1] == {"type": "input_video", "file_id": "file-1"}
    no_store = sam.video_body(
        settings.model_copy(update={"sam_send_store": False}),
        file_id="file_1",
        text="<0f>1<|point;x=1;y=1;w=2;h=2|>",
        object_prompt=True,
    )
    assert "store" not in no_store
    assert no_store["metadata"]["propagation_direction"] == "both"
    with pytest.raises(ValueError, match="Files API"):
        sam.video_body(settings, file_id="abc", text="face")
    with pytest.raises(ValueError, match="noun phrase"):
        sam.video_body(settings, file_id="file-1", text="  ")
    assert sam.image_body(settings, image_data_url="data:image/png;base64,AA", text="square")["model"] == "sam-3.1"


S1_LINE = "<7f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"


async def _events(events: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for event in events:
        yield event


async def test_sam_stream_feeds_the_official_parser(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings
) -> None:
    h = make_harness()
    lane = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    events = [
        {"type": "response.created", "response": {"id": "resp_sam"}},
        {"type": "response.output_text.delta", "delta": S1_LINE[:30], **lane},
        {"type": "response.output_text.delta", "delta": S1_LINE[30:], **lane},
        {"type": "response.content_part.done", **lane, "part": {"type": "output_text", "text": S1_LINE}},
        completed({"id": "resp_sam", "status": "completed", "usage": {"video_frames_processed": 240}}),
    ]
    mock_api.post("/responses").mock(return_value=stream_response(*events))
    body = sam.video_body(settings, file_id="file-1", text="face")
    result = await sam.segment_video(h.client, body, sam_frames=240)
    assert result.usd == pytest.approx(0.048)
    async with parse_responses_stream(_events(result.events), video_segmentation_format()) as parsed:
        final = await parsed.final_result()
    boxes = [r for r in final.records if isinstance(r, SegmentationBoxRecord)]
    assert boxes, final
    box = boxes[0]
    assert box.frame is not None
    assert (box.object_id, box.frame.frame_index, box.left, box.top, box.right, box.bottom) == ("0", 7, 10, 20, 15, 25)
    (line,) = h.costs()
    assert line.units == {"frames": 240}


# --- status --------------------------------------------------------------------


async def test_fetch_status() -> None:
    with respx.mock(base_url=BASE) as router:
        router.get("/status").mock(
            side_effect=[
                httpx.Response(200, json={"is_alive": True, "service_status": "operational", "model_statuses": []}),
                httpx.Response(200, json={"is_alive": True, "service_status": "degraded"}),
                httpx.Response(200, json={"nope": 1}),
                httpx.ConnectError("down"),
            ]
        )
        async with httpx.AsyncClient() as http:
            assert (await fetch_status(http, BASE)).healthy
            assert not (await fetch_status(http, BASE)).healthy
            for _ in range(2):
                with pytest.raises(StatusUnavailableError):
                    await fetch_status(http, BASE)


def test_sse_helper_matches_stream_format() -> None:
    assert list(iter_sse(sse({"type": "x", "a": 1}).decode().split("\n"))) == [{"type": "x", "a": 1}]


# --- open weights on Baseten ------------------------------------------------------


async def test_open_weight_chat_uses_baseten_and_meters(settings: Settings, ledger: Any, tmp_path: Path) -> None:
    cfg = settings.model_copy(update={"baseten_api_key": SecretStr("bt-test-key")})
    client = openweight.open_client(
        cfg, job_id="j_open", caller=Caller.local("eval"), ledger=ledger, cost_path=tmp_path / "cost.jsonl"
    )
    reply = {
        "id": "chatcmpl-1",
        "choices": [{"message": {"role": "assistant", "content": '{"x": 1}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 200}},
    }
    with respx.mock(base_url="https://inference.baseten.co/v1") as router:
        route = router.post("/chat/completions").mock(return_value=httpx.Response(200, json=reply))
        body = openweight.chat_body(cfg.open_model, [{"role": "user", "content": "hi"}], schema={"type": "object"})
        result = await openweight.create_chat(client, body, stage="probe_h")
    await client.aclose()
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "meta-models/muse-spark-open-1026"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert route.calls[0].request.headers["authorization"] == "Bearer bt-test-key"
    assert openweight.chat_text(result.body) == '{"x": 1}'
    assert result.usd == pytest.approx((800 * 1.25 + 200 * 0.15 + 100 * 4.25) / 1e6)


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"choices": []}, MetaIncomplete),
        ({"choices": [{"message": {"refusal": "no"}}]}, MetaRefusal),
        ({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}, MetaIncomplete),
        ({"choices": [{"message": {"content": None}}]}, MetaIncomplete),
        ("nope", MetaIncomplete),
    ],
)
def test_chat_text_fails_closed(body: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        openweight.chat_text(body)


def test_open_key_is_required(settings: Settings) -> None:
    with pytest.raises(ConfigError, match="BASETEN_API_KEY"):
        settings.open_api_key()


async def test_retried_upload_deletes_the_copy_an_earlier_attempt_left(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    size = len(clip.read_bytes())
    mock_api.post("/files").mock(side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={"id": "file-2"})])
    listing = {
        "data": [
            {"id": "file-1", "filename": "j_test-sam_proxy.mp4", "bytes": size, "created_at": time.time()},
            {"id": "file-2", "filename": "j_test-sam_proxy.mp4", "bytes": size, "created_at": time.time()},
        ]
    }
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    stale = mock_api.delete("/files/file-1").mock(return_value=httpx.Response(200, json={"deleted": True}))
    kept = mock_api.delete("/files/file-2").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    assert await store.upload(clip, "sam_proxy.mp4") == "file-2"
    assert stale.call_count == 1
    assert kept.call_count == 0
    live = store.index().live("sam_proxy.mp4")
    assert live is not None
    assert live.file_id == "file-2"


async def test_reupload_after_file_gone(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    route = mock_api.post("/files").mock(
        side_effect=[httpx.Response(200, json={"id": "file-1"}), httpx.Response(200, json={"id": "file-2"})]
    )
    store = FileStore(h.client, tmp_path / "job")
    assert await store.upload(clip, "sam_proxy.mp4") == "file-1"
    assert await store.reupload(clip, "sam_proxy.mp4", gone="file-1") == "file-2"
    assert route.call_count == 2
    live = store.index().live("sam_proxy.mp4")
    assert live is not None
    assert live.file_id == "file-2"


async def test_delete_all_works_after_the_job_cap_is_spent(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path, ledger: Any
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-1"}))
    deleted = mock_api.delete("/files/file-1").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    await store.upload(clip, "sam_proxy.mp4")
    ledger.reserve("big", "j_test", 3.0, [job_limit(h.client.settings, "j_test")])
    ledger.settle("big", 3.5)
    assert await store.delete_all() is True
    assert deleted.call_count == 1


async def test_upload_without_an_id_recovers_the_copy(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "abc123"}))
    listing = {
        "data": [
            {
                "id": "file-7",
                "filename": "j_test-sam_proxy.mp4",
                "bytes": len(clip.read_bytes()),
                "created_at": time.time(),
            }
        ]
    }
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    deleted = mock_api.delete("/files/file-7").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaConfigError):
        await store.upload(clip, "sam_proxy.mp4")
    assert deleted.call_count == 1
    assert store.index().all_deleted


async def test_breaker_refusal_records_no_orphan(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, clip: Path, tmp_path: Path
) -> None:
    h = make_harness()
    for _ in range(5):
        h.client.breaker.record_failure()
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable, match="breaker"):
        await store.upload(clip, "sam_proxy.mp4")
    assert store.index().root == []


def test_asr_tolerates_numeric_speakers_and_float_durations() -> None:
    raw = asr.AsrResponse.model_validate(
        {"audioDurationMs": 5230.0, "turns": [{"startMs": 0, "endMs": 10, "transcript": "a", "speaker": 0}]}
    )
    assert raw.audio_duration_ms == 5230
    assert asr.to_transcript(raw, source_model="m").turns[0].speaker == "S1"
    assert asr._meter({"audioDurationMs": 5230.0}) == ({"audio_s": 5}, pytest.approx(5 * 0.18 / 3600))  # pyright: ignore[reportPrivateUsage]
    assert asr._meter({}) == ({}, None)  # pyright: ignore[reportPrivateUsage]
