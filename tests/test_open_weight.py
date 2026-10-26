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
from safecut.meta.errors import BudgetExceeded, MetaIncomplete

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


def _client(cfg: Settings, ledger: LocalLedger, tmp_path: Path, *, job_id: str = "j_open"):
    return open_weight.open_weight_client(
        cfg, job_id=job_id, caller=Caller.local("eval"), ledger=ledger, cost_path=tmp_path / "cost.jsonl"
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


async def test_stream_without_finish_is_eof_then_retried(cfg: Settings, ledger: LocalLedger, tmp_path: Path) -> None:
    client = _client(cfg, ledger, tmp_path)
    client._sleep = _no_sleep  # pyright: ignore[reportPrivateUsage] -- no real backoff in tests
    good = _chunks("{}", usage={"prompt_tokens": 10, "completion_tokens": 1})
    with respx.mock(base_url=BT) as router:
        router.post("/chat/completions").mock(
            side_effect=[httpx.Response(200, content=_chunks("{", finish=None)), httpx.Response(200, content=good)]
        )
        result = await open_weight.create(client, open_weight.chat_body(cfg, []), stage="s", price=PRICE)
    await client.aclose()
    assert result.attempts == 2


async def _no_sleep(_: float) -> None:
    return None


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
    too_many = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}] * 51}]
    with pytest.raises(ValueError, match="at most 50"):
        open_weight.chat_body(cfg, too_many)
    assert open_weight.calls_for(0) == 0
    assert open_weight.calls_for(50) == 1
    assert open_weight.calls_for(51) == 2


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
