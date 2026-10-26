"""The open-weight second opinion: Muse Spark Open on Baseten (PRE-A §3.8).

Muse Spark Open runs on partner inference (Baseten, Chat Completions, streamed). It sits outside
``safecut/meta/`` because it isn't the Meta Model API. Its spend is logged with ``provider: "baseten"`` and
reserved only against ``SAFECUT_OPEN_WEIGHT_JOB_USD_CAP``, never against the $150 Meta caps. The model
doesn't support structured output, so the prompt asks for JSON and the answer is validated client-side;
an invalid answer is a failed second opinion (no re-ask). With no ``SAFECUT_OPEN_WEIGHT_PRICE`` the
call is refused, because a zero reservation would let it spend unchecked.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel, ValidationError

from safecut import config
from safecut.config import ConfigError, OpenWeightPrice, Settings
from safecut.meta import cost
from safecut.meta.budget import Caller, Ledger
from safecut.meta.client import CallResult, CallSpec, MetaClient, Units
from safecut.meta.errors import MetaIncomplete
from safecut.meta.retry import RetryPolicy

MAX_TOKENS = 16_000
MAX_IMAGES = 50
IDLE_TIMEOUT_S = 300.0
_EMPTY: Mapping[str, Any] = {}


class InvalidOpenWeightOutputError(MetaIncomplete):
    """The answer wasn't valid JSON for the expected model: the second opinion counts as failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, eof=False)


def open_weight_client(
    settings: Settings, *, job_id: str | None, caller: Caller, ledger: Ledger, cost_path: str | Path
) -> MetaClient:
    """A transport pointed at Baseten with ``BASETEN_API_KEY``, logging ``provider: "baseten"``."""
    return MetaClient(
        settings,
        job_id=job_id,
        caller=caller,
        ledger=ledger,
        cost_path=cost_path,
        base_url=settings.open_weight_base_url,
        api_key=settings.open_api_key(),
        provider="baseten",
    )


def chat_body(
    settings: Settings, messages: Sequence[Mapping[str, Any]], *, effort: str | None = None
) -> dict[str, Any]:
    """A Chat Completions body: no ``response_format`` (unsupported), reasoning effort unless ``omit``."""
    images = sum(
        1
        for m in messages
        for part in cast(list[Any], m.get("content") if isinstance(m.get("content"), list) else [])
        if isinstance(part, Mapping) and cast(Mapping[str, Any], part).get("type") == "image_url"
    )
    if images > MAX_IMAGES:
        raise ValueError(f"{images} images in one call; split frame sets into calls of at most {MAX_IMAGES}")
    body: dict[str, Any] = {
        "model": settings.open_weight_model,
        "messages": [dict(m) for m in messages],
        "max_tokens": MAX_TOKENS,
    }
    chosen = effort or settings.open_weight_effort
    if chosen != "omit":
        body["reasoning_effort"] = chosen
    return body


def usd_for(price: OpenWeightPrice, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * price.input + output_tokens * price.output) / 1e6


def chat_units(usage: object) -> Units | None:
    """Chat Completions ``usage`` → the unit names every cost line uses; ``None`` when absent."""
    if not isinstance(usage, Mapping):
        return None
    data = cast(Mapping[str, Any], usage)
    details = data.get("completion_tokens_details")
    detail_map = cast(Mapping[str, Any], details) if isinstance(details, Mapping) else _EMPTY
    prompt, completion = data.get("prompt_tokens"), data.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int) or prompt <= 0:
        return None
    reasoning = detail_map.get("reasoning_tokens")
    return {
        "input": prompt,
        "cached": 0,
        "output": completion,
        "reasoning": reasoning if isinstance(reasoning, int) else 0,
    }


async def create(
    client: MetaClient, body: Mapping[str, Any], *, stage: str, price: OpenWeightPrice | None, images: int = 0
) -> CallResult:
    """One streamed second-opinion call, its worst case reserved from ``price`` first."""
    if client.provider != "baseten":
        raise ValueError("open-weight calls go through a Baseten client (open_weight_client)")
    if price is None:
        raise ConfigError("SAFECUT_OPEN_WEIGHT_PRICE is not set; the open-weight call is refused")
    text_bytes = len(str(body.get("messages", "")).encode())
    fallback = cost.fallback_input_tokens(text_bytes=text_bytes, images=images, video_seconds=0)
    max_tokens = cast(int, body["max_tokens"])

    def meter(answer: Mapping[str, Any]) -> tuple[Units, float | None]:
        units = chat_units(answer.get("usage"))
        if units is None:
            return {}, None
        return units, usd_for(price, int(units["input"]), int(units["output"]))

    spec = CallSpec(
        stage=stage,
        model=cast(str, body["model"]),
        estimate_usd=usd_for(price, fallback, max_tokens),
        estimate_units={"input": fallback, "cached": 0, "output": max_tokens, "reasoning": 0},
        policy=RetryPolicy(attempts=config.ATTEMPTS_DEFAULT),
        timeout=httpx.Timeout(IDLE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        lane="responses",
        total_timeout_s=config.RESPONSES_TOTAL_TIMEOUT_S,
        breaker=False,  # Baseten trouble must never trip the breaker guarding the Meta calls
    )
    return await client.stream_chat(spec, body, meter=meter)


def parse_json[M: BaseModel](model_type: type[M], answer: Any) -> M:
    """Validate the JSON answer (no re-ask, PRE-A §3.8). A length stop or bad JSON is a failed opinion."""
    data = cast(Mapping[str, Any], answer) if isinstance(answer, Mapping) else _EMPTY
    if data.get("finish_reason") == "length":
        raise InvalidOpenWeightOutputError("the answer hit max_tokens")
    text = data.get("text")
    if not isinstance(text, str):
        raise InvalidOpenWeightOutputError("the answer has no text")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").removeprefix("json").strip()
    try:
        return model_type.model_validate_json(stripped)
    except ValidationError as exc:
        raise InvalidOpenWeightOutputError(f"invalid JSON answer: {exc.error_count()} error(s)") from exc


def enabled_for(settings: Settings, *, consented: bool, code_kind: str) -> bool:
    """Whether a job gets the second opinion: switched on, consented, and an allowed code kind."""
    return settings.open_weight_audit == "on" and consented and code_kind in settings.open_weight_code_kinds


def calls_for(frames: int) -> int:
    """How many calls a frame set needs at ≤ 50 images per call."""
    return math.ceil(frames / MAX_IMAGES) if frames else 0
