"""The open-weight second opinion on Baseten (PRE-A §3.8): its own provider, cap and streamed chat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel, SecretStr

from safecut import open_weight
from safecut.config import ConfigError, OpenWeightPrice, Settings, load_settings
from safecut.contracts import measured_usd, read_cost_lines
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import MetaClient
from safecut.meta.errors import BudgetExceeded, MetaBadRequest, MetaIncomplete

BT = "https://inference.baseten.co/v1"
PRICE = OpenWeightPrice.model_validate({"in": 1.25, "out": 4.25})


def _chunks(*texts: str, finish: str | None = "stop", usage: dict[str, Any] | None = None) -> bytes:
    events: list[dict[str, Any]] = [{"id": "c1", "choices": [{"delta": {"content": t}}]} for t in texts]
    if finish:
        events.append({"id": "c1", "choices": [{"delta": {}, "finish_reason": finish}]})
    if usage:
        events.append({"id": "c1", "choices": [], "usage": usage})
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return body.encode()


@pytest.fixture
def cfg(settings: Settings) -> Settings:
    return settings.model_copy(update={"baseten_api_key": SecretStr("bt-test-key")})


def _client(
    cfg: Settings, ledger: LocalLedger, tmp_path: Path, *, job_id: str = "j_open", caller: Caller | None = None
):
    return open_weight.open_weight_client(
        cfg, job_id=job_id, caller=caller or Caller.local("eval"), ledger=ledger, cost_path=tmp_path / "cost.jsonl"
    )


class _Answer(BaseModel):
    findings: list[dict[str, Any]]


async def test_streamed_chat_is_metered_as_baseten(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path)
    usage = {"prompt_tokens": 2000, "completion_tokens": 300, "completion_tokens_details": {"reasoning_tokens": 250}}
    with respx.mock(base_url=BT) as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, content=_chunks('{"findings": ', "[]}", usage=usage))
        )
        body = open_weight.chat_body(cfg, [{"role": "user", "content": "hi"}])
        result = await open_weight.create(client, body, stage="redteam_open", price=PRICE)
    await client.aclose()
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "meta-models/muse-spark-open-1026"
    assert "response_format" not in sent
    assert sent["reasoning_effort"] == "medium"
    assert sent["max_tokens"] == 16_000
    assert sent["stream"] is True
    assert route.calls[0].request.headers["authorization"] == "Bearer bt-test-key"
    assert open_weight.parse_json(_Answer, result.body).findings == []
    (line,) = read_cost_lines(tmp_path / "cost.jsonl")
    assert line.provider == "baseten"
    assert line.usd == pytest.approx((2000 * 1.25 + 300 * 4.25) / 1e6)
    assert line.units["reasoning"] == 250
    lines = list(read_cost_lines(tmp_path / "cost.jsonl"))
    assert measured_usd(lines) == (0.0, 0.0)  # Meta totals never include Baseten spend
    assert measured_usd(lines, provider="baseten")[0] == pytest.approx(line.usd)


async def test_baseten_spend_is_off_the_meta_caps(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    ledger.reserve("meta-spent", "j_open", 3.0, [CapLimit("job", "job:j_open", 3.0)])  # the Meta job cap is full
    client = _client(cfg, ledger, tmp_path)
    with respx.mock(base_url=BT) as router:
        router.post("/chat/completions").mock(
            return_value=httpx.Response(200, content=_chunks("{}", usage={"prompt_tokens": 10, "completion_tokens": 1}))
        )
        await open_weight.create(client, open_weight.chat_body(cfg, []), stage="s", price=PRICE)
    await client.aclose()
    assert ledger.spent("baseten_job:j_open") > 0


async def test_baseten_job_cap_stops_the_call(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg.model_copy(update={"open_weight_job_usd_cap": 0.01}), ledger, tmp_path)
    with pytest.raises(BudgetExceeded) as info:
        await open_weight.create(client, open_weight.chat_body(cfg, []), stage="s", price=PRICE)
    await client.aclose()
    assert info.value.cap == "baseten_job"
    (line,) = read_cost_lines(tmp_path / "cost.jsonl")
    assert (line.cap, line.provider, line.stage) == ("baseten_job", "baseten", "budget:s")


async def test_no_price_refuses_the_call(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path)
    with pytest.raises(ConfigError, match="PRICE"):
        await open_weight.create(client, open_weight.chat_body(cfg, []), stage="s", price=None)
    await client.aclose()


async def test_stream_without_finish_fails_without_a_retry(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    # PRE-A §3.8: no transport retry; the accepted, cut-off call keeps its estimate (audit #6).
    client = _client(cfg, ledger, tmp_path)
    good = _chunks("{}", usage={"prompt_tokens": 10, "completion_tokens": 1})
    with respx.mock(base_url=BT) as router:
        route = router.post("/chat/completions").mock(
            side_effect=[httpx.Response(200, content=_chunks("{", finish=None)), httpx.Response(200, content=good)]
        )
        with pytest.raises(MetaIncomplete):
            await open_weight.create(client, open_weight.chat_body(cfg, []), stage="s", price=PRICE)
    await client.aclose()
    assert route.call_count == 1
    (line,) = list(read_cost_lines(tmp_path / "cost.jsonl"))
    assert (line.provider, line.estimated) == ("baseten", True)


@pytest.mark.parametrize(
    "answer",
    [
        {"text": "not json", "finish_reason": "stop"},
        {"text": '{"findings": []}', "finish_reason": "length"},
        {"finish_reason": "stop"},
        "nope",
    ],
)
def test_invalid_answers_are_a_failed_opinion(answer: Any) -> None:
    with pytest.raises(MetaIncomplete):
        open_weight.parse_json(_Answer, answer)


def test_fenced_json_is_accepted() -> None:
    parsed = open_weight.parse_json(_Answer, {"text": '```json\n{"findings": []}\n```', "finish_reason": "stop"})
    assert parsed.findings == []


def test_chat_body_rules(cfg: Settings) -> None:
    omit = open_weight.chat_body(cfg, [], effort="omit")
    assert "reasoning_effort" not in omit
    too_many = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}] * 9}]
    with pytest.raises(ValueError, match="at most 8"):
        open_weight.chat_body(cfg, too_many)
    assert open_weight.calls_for(0) == 0
    assert open_weight.calls_for(8) == 1
    assert open_weight.calls_for(9) == 2


async def test_open_client_must_be_baseten(make_harness: Any) -> None:
    h = make_harness()
    with pytest.raises(ValueError, match="Baseten client"):
        await open_weight.create(h.client, {"model": "m", "max_tokens": 1}, stage="s", price=PRICE)


def test_enabled_for_needs_switch_consent_and_kind(cfg: Settings) -> None:
    on = cfg.model_copy(update={"open_weight_audit": "on", "open_weight_code_kinds": ("owner", "recording")})
    assert open_weight.enabled_for(on, consented=True, code_kind="owner")
    assert not open_weight.enabled_for(on, consented=False, code_kind="owner")
    assert not open_weight.enabled_for(on, consented=True, code_kind="judge")
    assert not open_weight.enabled_for(cfg, consented=True, code_kind="owner")


def test_open_weight_config() -> None:
    s = load_settings(
        {
            "SAFECUT_OPEN_WEIGHT_AUDIT": "on",
            "SAFECUT_OPEN_WEIGHT_PRICE": '{"in": 1.25, "out": 4.25}',
            "SAFECUT_OPEN_WEIGHT_CODE_KINDS": '["owner"]',
            "SAFECUT_OPEN_WEIGHT_GRID_OK": "true",
            "SAFECUT_OPEN_WEIGHT_EFFORT": "omit",
            "BASETEN_API_KEY": "bt",
        }
    )
    assert s.open_weight_price == PRICE
    assert s.open_weight_code_kinds == ("owner",)
    assert s.open_weight_grid_ok is True
    assert s.open_api_key() == "bt"
    for bad in ('["judge"]', '["pilot"]', '["public"]', '["service"]'):
        with pytest.raises(ConfigError):
            load_settings({"SAFECUT_OPEN_WEIGHT_CODE_KINDS": bad})
    with pytest.raises(ConfigError):
        load_settings({"SAFECUT_OPEN_WEIGHT_PRICE": '{"in": 0, "out": 1}'})
    with pytest.raises(ConfigError, match="BASETEN_API_KEY"):
        load_settings({}).open_api_key()


# --- audit #4 -----------------------------------------------------------------------------------


def test_image_data_urls_are_not_counted_as_text(cfg: Settings) -> None:
    big = "data:image/jpeg;base64," + "A" * 130_000
    frames = [(i, big) for i in range(8)]
    body = open_weight.chat_body(cfg, open_weight.redteam_messages(frames))
    text_bytes, images = open_weight._parts(body)  # pyright: ignore[reportPrivateUsage] -- the estimate's input
    assert images == 8
    assert text_bytes < 5_000


def _answer_for_sent_frames(request: httpx.Request) -> httpx.Response:
    content = json.loads(request.content)["messages"][1]["content"]
    sent = [int(p["text"].split()[1].rstrip(":")) for p in content if p.get("text", "").startswith("Frame ")]
    answer = json.dumps({"frames": [{"frame": f, "findings": []} for f in sent]})
    usage = {"prompt_tokens": 1_600 * len(sent), "completion_tokens": 2_000}
    return httpx.Response(200, content=_chunks(answer, usage=usage))


def _on(cfg: Settings) -> Settings:
    return cfg.model_copy(
        update={"open_weight_audit": "on", "open_weight_code_kinds": ("owner",), "open_weight_price": PRICE}
    )


async def test_a_frame_set_is_split_into_calls_of_at_most_8(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path, caller=Caller.local("owner"))
    frames = [(i, "data:image/jpeg;base64," + "A" * 130_000) for i in range(20)]
    with respx.mock(base_url=BT) as router:
        route = router.post("/chat/completions").mock(side_effect=_answer_for_sent_frames)
        result = await open_weight.second_opinion(client, _on(cfg), consented=True, frames=frames)
    await client.aclose()
    assert route.call_count == open_weight.calls_for(20) == 3
    sizes = sorted(json.dumps(json.loads(c.request.content)).count('"image_url": {') for c in route.calls)
    assert sizes == [4, 8, 8]
    assert [f.frame for f in result.frames] == list(range(20))


async def test_a_frame_set_over_the_cap_is_skipped_whole(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    # 50 frames need 7 calls at ≈ $0.08 each: more than the $0.50 cap, so none runs (never partially).
    client = _client(cfg, ledger, tmp_path, caller=Caller.local("owner"))
    frames = [(i, "data:image/jpeg;base64,AA") for i in range(50)]
    with respx.mock(base_url=BT, assert_all_called=False) as router:
        route = router.post("/chat/completions").mock(side_effect=_answer_for_sent_frames)
        with pytest.raises(BudgetExceeded):
            await open_weight.second_opinion(client, _on(cfg), consented=True, frames=frames)
    await client.aclose()
    assert route.call_count == 0
    (line,) = list(read_cost_lines(tmp_path / "cost.jsonl"))
    assert (line.stage, line.cap) == ("budget:redteam_open", "baseten_job")
    assert ledger.spent("baseten_job:j_open") == 0


async def test_one_failed_batch_fails_the_whole_opinion(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path, caller=Caller.local("owner"))
    frames = [(i, "data:image/jpeg;base64,AA") for i in range(16)]

    def second_batch_fails(request: httpx.Request) -> httpx.Response:
        if '"Frame 8:"' in request.content.decode():
            return httpx.Response(400, json={"error": {"message": "bad image"}})
        return _answer_for_sent_frames(request)

    with respx.mock(base_url=BT) as router:
        router.post("/chat/completions").mock(side_effect=second_batch_fails)
        with pytest.raises(MetaBadRequest):
            await open_weight.second_opinion(client, _on(cfg), consented=True, frames=frames)
    await client.aclose()


def test_negative_usage_is_unknown_not_a_crash() -> None:
    assert open_weight.chat_units({"prompt_tokens": 1000, "completion_tokens": -50}) is None
    assert open_weight.chat_units({"prompt_tokens": True, "completion_tokens": 5}) is None
    units = open_weight.chat_units(
        {"prompt_tokens": 10, "completion_tokens": 5, "completion_tokens_details": {"reasoning_tokens": -1}}
    )
    assert units == {"input": 10, "cached": 0, "output": 5, "reasoning": 0}


def test_complete_answer_rules() -> None:
    finding = {"kind": "text", "detail": "a name", "text": "AMINA K.", "box": [1, 2, 3, 4], "confidence": "high"}
    answer = {
        "text": json.dumps(
            {
                "frames": [
                    {"frame": 0, "findings": [finding]},
                    {"frame": 0, "findings": []},
                    {"frame": 9, "findings": []},
                    {"frame": 30, "findings": []},
                ]
            }
        ),
        "finish_reason": "stop",
    }
    parsed = open_weight.complete_answer(answer, [0, 30])
    assert [f.frame for f in parsed.frames] == [0, 30]  # duplicates merged, unsent frame 9 dropped
    with pytest.raises(MetaIncomplete, match="missing"):
        open_weight.complete_answer(answer, [0, 30, 60])
    bad = {
        "text": json.dumps({"frames": [{"frame": 0, "findings": [finding | {"kind": "tattoo"}]}]}),
        "finish_reason": "stop",
    }
    with pytest.raises(MetaIncomplete):
        open_weight.complete_answer(bad, [0])


def test_redteam_messages_bounds() -> None:
    with pytest.raises(ValueError, match="1 to 8"):
        open_weight.redteam_messages([])
    with pytest.raises(ValueError, match="1 to 8"):
        open_weight.redteam_messages([(i, "x") for i in range(9)])
    messages = open_weight.redteam_messages([(90, "data:image/jpeg;base64,AA")], kept_clear="the host")
    assert messages[0]["role"] == "system"
    assert "the host" in messages[1]["content"][0]["text"]
    assert "Report every frame" in messages[1]["content"][0]["text"]


async def test_second_opinion_enforces_the_privacy_gate(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path, caller=Caller.local("owner"))
    judge = _client(cfg, ledger, tmp_path, caller=Caller(code_kind="judge", code_id="j1"))
    frames = [(0, "data:image/jpeg;base64,AA")]
    with respx.mock(base_url=BT) as router:
        route = router.post("/chat/completions")
        with pytest.raises(open_weight.SecondOpinionRefusedError):
            await open_weight.second_opinion(client, cfg, consented=True, frames=frames)
        on = cfg.model_copy(
            update={"open_weight_audit": "on", "open_weight_code_kinds": ("owner",), "open_weight_price": PRICE}
        )
        with pytest.raises(open_weight.SecondOpinionRefusedError):
            await open_weight.second_opinion(client, on, consented=False, frames=frames)
        # The code kind is the client's own caller, never an argument (audit #6).
        with pytest.raises(open_weight.SecondOpinionRefusedError):
            await open_weight.second_opinion(judge, on, consented=True, frames=frames)
        assert route.call_count == 0
        answer = json.dumps({"frames": [{"frame": 0, "findings": []}]})
        route.mock(
            return_value=httpx.Response(
                200, content=_chunks(answer, usage={"prompt_tokens": 1600, "completion_tokens": 40})
            )
        )
        result = await open_weight.second_opinion(client, on, consented=True, frames=frames)
    await client.aclose()
    await judge.aclose()
    assert result.frames[0].findings == []


def test_keys_never_cross_providers(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base URLs"):
        MetaClient(cfg, job_id="j", caller=Caller.local(), ledger=ledger, cost_path=tmp_path / "c", base_url=BT)
    with pytest.raises(ValueError, match="base URLs"):
        MetaClient(
            cfg,
            job_id="j",
            caller=Caller.local(),
            ledger=ledger,
            cost_path=tmp_path / "c",
            base_url="https://api.meta.ai/v1",
            api_key="bt",
            provider="baseten",
        )
