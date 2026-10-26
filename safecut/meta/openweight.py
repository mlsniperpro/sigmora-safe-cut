"""Muse Spark Open (open weights) on Baseten's OpenAI-compatible Chat Completions API.

Used for the open-weight probe and as an optional second opinion (the "Best Build on Meta Open-Weight
Models" bonus). It runs through the same attempt loop, caps and ``cost.jsonl`` as the Meta client.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import httpx

from safecut import config
from safecut.config import Settings
from safecut.meta import cost
from safecut.meta.budget import Caller, Ledger
from safecut.meta.client import CallResult, CallSpec, MetaClient, Units
from safecut.meta.errors import MetaIncomplete, MetaRefusal
from safecut.meta.retry import RetryPolicy

_EMPTY: Mapping[str, Any] = {}


def open_client(
    settings: Settings, *, job_id: str | None, caller: Caller, ledger: Ledger, cost_path: str | Path
) -> MetaClient:
    """A transport pointed at Baseten with ``BASETEN_API_KEY``."""
    return MetaClient(
        settings,
        job_id=job_id,
        caller=caller,
        ledger=ledger,
        cost_path=cost_path,
        base_url=settings.open_base_url,
        api_key=settings.open_api_key(),
    )


def chat_body(
    model: str,
    messages: Sequence[Mapping[str, Any]],
    *,
    max_tokens: int = config.MAX_OUTPUT_TOKENS_DEFAULT,
    schema: Mapping[str, Any] | None = None,
    schema_name: str = "output",
) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "messages": [dict(m) for m in messages], "max_tokens": max_tokens}
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": dict(schema)},
        }
    return body


def chat_units(usage: Mapping[str, Any] | None) -> Units:
    """Chat Completions ``usage`` → the same unit names Responses lines use."""
    usage = usage or _EMPTY
    details = usage.get("prompt_tokens_details")
    detail_map = cast(Mapping[str, Any], details) if isinstance(details, Mapping) else _EMPTY
    completion = usage.get("completion_tokens_details")
    completion_map = cast(Mapping[str, Any], completion) if isinstance(completion, Mapping) else _EMPTY
    return cost.usage_units(
        {
            "input_tokens": usage.get("prompt_tokens"),
            "input_tokens_details": {"cached_tokens": detail_map.get("cached_tokens")},
            "output_tokens": usage.get("completion_tokens"),
            "output_tokens_details": {"reasoning_tokens": completion_map.get("reasoning_tokens")},
        }
    )


async def create_chat(client: MetaClient, body: Mapping[str, Any], *, stage: str, image_count: int = 0) -> CallResult:
    """One non-streamed chat completion with the worst-case estimate reserved first."""
    model = cast(str, body["model"])
    max_tokens = cast(int, body["max_tokens"])
    text_bytes = len(str(body.get("messages", "")).encode())
    fallback = cost.fallback_input_tokens(text_bytes=text_bytes, images=image_count, video_seconds=0)
    estimate = cost.responses_estimate(model, counted=None, fallback=fallback, max_output_tokens=max_tokens)

    def meter(response: Mapping[str, Any]) -> tuple[Units, float | None]:
        usage = response.get("usage")
        if not isinstance(usage, Mapping):
            return {}, None
        units = chat_units(cast(Mapping[str, Any], usage))
        if units["input"] <= 0:
            return {}, None
        return units, cost.responses_usd_from_units(model, units)

    spec = CallSpec(
        stage=stage,
        model=model,
        estimate_usd=estimate,
        estimate_units={"input": fallback, "cached": 0, "output": max_tokens, "reasoning": 0},
        policy=RetryPolicy(attempts=config.ATTEMPTS_DEFAULT),
        timeout=httpx.Timeout(config.responses_idle_timeout("medium"), connect=config.CONNECT_TIMEOUT_S),
        lane="responses",
    )
    return await client.request("POST", "chat/completions", spec, meter=meter, json_body=dict(body))


def chat_text(body: Any) -> str:
    """The first choice's text; a refusal or a length stop fails closed."""
    choices = cast(Mapping[str, Any], body).get("choices") if isinstance(body, Mapping) else None
    if not isinstance(choices, list) or not choices:
        raise MetaIncomplete("chat completion has no choices", eof=False)
    choice = cast(list[Any], choices)[0]
    choice_map = cast(Mapping[str, Any], choice) if isinstance(choice, Mapping) else _EMPTY
    message = choice_map.get("message")
    message_map = cast(Mapping[str, Any], message) if isinstance(message, Mapping) else _EMPTY
    if message_map.get("refusal"):
        raise MetaRefusal(f"the model refused: {str(message_map['refusal'])[:200]}")
    if choice_map.get("finish_reason") == "length":
        raise MetaIncomplete("chat completion hit max_tokens", eof=False)
    content = message_map.get("content")
    if not isinstance(content, str):
        raise MetaIncomplete("chat completion has no text content", eof=False)
    return content
