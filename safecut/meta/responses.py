"""Muse Spark / Muse Wonder through the Responses API: request building, cost metering, JSON output.

Every request is Standard mode with ``store: false`` (AGENTS rule 6), streamed (Muse reasons silently
before output), and structured with ``text.format`` ``json_schema`` + ``strict`` when a schema is given.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import httpx
from pydantic import BaseModel, ValidationError

from safecut import config
from safecut.meta import cost
from safecut.meta.client import CallSpec, MetaClient, Meter, StreamResult, Units
from safecut.meta.errors import BudgetExceeded, MetaError, MetaIncomplete, MetaRefusal
from safecut.meta.retry import RetryPolicy

#: Parameters that are no-ops or 400s on Responses (PRE-A §3.6): never sent.
FORBIDDEN_PARAMS = frozenset(
    {
        "temperature",
        "top_p",
        "stop",
        "n",
        "logprobs",
        "logit_bias",
        "response_format",
        "truncation",
        "previous_response_id",
    }
)
_SCHEMA_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


class InvalidOutputError(MetaError):
    """A complete response whose JSON failed validation twice (the call and its one re-ask)."""


def ensure_standard(model: str) -> str:
    if model.endswith("-contributor"):
        raise ValueError(f"{model!r} is a Contributor-mode model; Safe Cut uses Standard mode only")
    return model


def _check_images_in_user_messages(messages: Sequence[Mapping[str, Any]]) -> None:
    """Images on non-user roles are silently ignored by Meta, so refuse them before sending."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in cast(list[Any], content):
            is_image = isinstance(part, Mapping) and cast(Mapping[str, Any], part).get("type") == "input_image"
            if is_image and message.get("role") != "user":
                raise ValueError(
                    f"an input_image sits in a {message.get('role')!r} message; images go in user messages"
                )


def json_format(name: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    if not name or len(name) > 64 or not set(name) <= _SCHEMA_NAME_CHARS:
        raise ValueError("schema name must be 1-64 chars of [a-zA-Z0-9_-]")
    return {"format": {"type": "json_schema", "name": name, "strict": True, "schema": dict(schema)}}


def build_body(
    model: str,
    messages: Sequence[Mapping[str, Any]],
    *,
    effort: str,
    schema: Mapping[str, Any] | None = None,
    schema_name: str | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """A Responses request body. ``effort`` ``omit`` sends no ``reasoning`` field (the Spark 1.2 fallback)."""
    ensure_standard(model)
    if effort not in ("omit", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError(f"unknown reasoning effort {effort!r}")
    _check_images_in_user_messages(messages)
    body: dict[str, Any] = {
        "model": model,
        "store": False,
        "input": [dict(m) for m in messages],
        "max_output_tokens": max_output_tokens or config.max_output_tokens(model, effort),
    }
    if effort != "omit":
        body["reasoning"] = {"effort": effort}
    if schema is not None:
        body["text"] = json_format(schema_name or "output", schema)
    return body


def _count_parts(body: Mapping[str, Any]) -> tuple[int, int]:
    """``(text_bytes, images)`` over the input messages, for the fallback estimate."""
    text_bytes = 0
    images = 0
    for message in cast(list[Mapping[str, Any]], body.get("input", [])):
        content = message.get("content")
        parts: list[Any] = cast(list[Any], content) if isinstance(content, list) else [content]
        for part in parts:
            if isinstance(part, str):
                text_bytes += len(part.encode())
            elif isinstance(part, Mapping):
                p = cast(Mapping[str, Any], part)
                if p.get("type") == "input_image":
                    images += 1
                elif isinstance(p.get("text"), str):
                    text_bytes += len(cast(str, p["text"]).encode())
    fmt = body.get("text")
    if fmt is not None:
        text_bytes += len(str(fmt).encode())
    return text_bytes, images


def meter_for(model: str) -> Meter:
    """Actual cost from a completed response's ``usage``."""

    def meter(response: Mapping[str, Any]) -> tuple[Units, float]:
        usage = response.get("usage")
        units = cost.usage_units(cast(Mapping[str, Any], usage) if isinstance(usage, Mapping) else None)
        return units, cost.responses_usd_from_units(model, units)

    return meter


async def count_input_tokens(client: MetaClient, body: Mapping[str, Any], *, stage: str) -> int | None:
    """``POST /responses/input_tokens`` (free). Any failure returns ``None``: the fallback estimate applies."""
    count_body = {k: v for k, v in body.items() if k in ("model", "input", "text", "reasoning")}
    spec = CallSpec(
        stage=f"count:{stage}",
        model=cast(str, body["model"]),
        estimate_usd=0.0,
        estimate_units={},
        policy=RetryPolicy(attempts=config.ATTEMPTS_DEFAULT),
        timeout=httpx.Timeout(30.0, connect=config.CONNECT_TIMEOUT_S),
    )
    try:
        result = await client.request(
            "POST", "responses/input_tokens", spec, meter=lambda _: ({}, 0.0), json_body=count_body
        )
    except (MetaError, BudgetExceeded):
        return None
    raw: Any = result.body
    value = cast(Mapping[str, Any], raw).get("input_tokens") if isinstance(raw, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


async def create(
    client: MetaClient,
    body: Mapping[str, Any],
    *,
    stage: str,
    effort: str,
    video_seconds: float = 0.0,
    count: bool = True,
) -> StreamResult:
    """Stream one Responses call after reserving its worst-case cost."""
    model = cast(str, body["model"])
    max_out = cast(int, body["max_output_tokens"])
    text_bytes, images = _count_parts(body)
    fallback = cost.fallback_input_tokens(text_bytes=text_bytes, images=images, video_seconds=video_seconds)
    counted = await count_input_tokens(client, body, stage=stage) if count else None
    estimate = cost.responses_estimate(model, counted=counted, fallback=fallback, max_output_tokens=max_out)
    spec = CallSpec(
        stage=stage,
        model=model,
        estimate_usd=estimate,
        estimate_units={"input": max(counted or 0, fallback), "cached": 0, "output": max_out, "reasoning": 0},
        policy=RetryPolicy.for_responses(effort),
        timeout=httpx.Timeout(config.responses_idle_timeout(effort), connect=config.CONNECT_TIMEOUT_S),
        lane="responses",
        total_timeout_s=config.RESPONSES_TOTAL_TIMEOUT_S,
    )
    return await client.stream(spec, body, meter=meter_for(model))


def output_text(response: Mapping[str, Any]) -> str:
    """The ``output_text`` of the ``message`` item; a refusal part raises, no text is ``MetaIncomplete``."""
    texts: list[str] = []
    for item in cast(list[Any], response.get("output") or []):
        if not isinstance(item, Mapping) or cast(Mapping[str, Any], item).get("type") != "message":
            continue
        for part in cast(list[Any], cast(Mapping[str, Any], item).get("content") or []):
            if not isinstance(part, Mapping):
                continue
            p = cast(Mapping[str, Any], part)
            if p.get("type") == "refusal":
                raise MetaRefusal(f"the model refused: {str(p.get('refusal') or '')[:200]}")
            if p.get("type") == "output_text" and isinstance(p.get("text"), str):
                texts.append(cast(str, p["text"]))
    if not texts:
        raise MetaIncomplete("the response has no output_text", eof=False)
    return "".join(texts)


async def create_json[M: BaseModel](
    client: MetaClient,
    model_type: type[M],
    body: Mapping[str, Any],
    *,
    stage: str,
    effort: str,
    video_seconds: float = 0.0,
) -> tuple[M, StreamResult]:
    """Create, parse the JSON output and validate it; one re-ask on invalid output, then fail closed."""
    last_error: Exception | None = None
    for _ in range(2):
        result = await create(client, body, stage=stage, effort=effort, video_seconds=video_seconds)
        try:
            return model_type.model_validate_json(output_text(result.response)), result
        except ValidationError as exc:
            last_error = exc
    raise InvalidOutputError(f"{stage}: output failed validation twice: {last_error}")
