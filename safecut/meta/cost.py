"""Prices, pre-call estimates and actual cost per call (PRE-A §10.5). Pure functions only."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

from safecut import config

_EMPTY: Mapping[str, Any] = {}


class UnknownPrice(ValueError):
    """No dated price for this model: refuse to call it rather than log a wrong cost."""


def token_price(model: str) -> config.TokenPrice:
    try:
        return config.TOKEN_PRICES[model]
    except KeyError:
        raise UnknownPrice(f"no price for {model!r} in the {config.PRICE_TABLE_DATE} table") from None


def responses_usd(model: str, *, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """``(in - cached) × P_in + cached × P_cached + out × P_out``; reasoning tokens are inside ``out``."""
    if min(input_tokens, cached_tokens, output_tokens) < 0 or cached_tokens > input_tokens:
        raise ValueError("token counts must be non-negative and cached <= input")
    p = token_price(model)
    return ((input_tokens - cached_tokens) * p.input + cached_tokens * p.cached + output_tokens * p.output) / 1e6


def sam_video_usd(frames: int) -> float:
    if frames < 0:
        raise ValueError("frames must be non-negative")
    return frames * config.SAM_USD_PER_FRAME


def sam_video_estimate(sam_frames: int) -> float:
    """Reserve every proxy frame, with Meta's 50-frame minimum per video request."""
    return sam_video_usd(max(config.SAM_MIN_FRAMES_BILLED, sam_frames))


def sam_image_usd(images: int) -> float:
    if images < 0:
        raise ValueError("images must be non-negative")
    return images * config.SAM_USD_PER_IMAGE


def asr_billed_seconds(audio_duration_ms: int) -> int:
    """Meta bills Voice Transcribe rounded down to whole seconds."""
    if audio_duration_ms < 0:
        raise ValueError("audio duration must be non-negative")
    return audio_duration_ms // 1000


def asr_usd(audio_seconds: int) -> float:
    return audio_seconds * config.ASR_USD_PER_SECOND


def asr_estimate(duration_s: float) -> float:
    return asr_usd(math.ceil(duration_s))


# Fallback token estimates when the free count endpoint fails or under-counts (PRE-A §10.5, A3/A4).
TOKENS_PER_IMAGE = 1_500
TOKENS_PER_VIDEO_SECOND = 2_200


def fallback_input_tokens(*, text_bytes: int, images: int, video_seconds: float) -> int:
    return (
        math.ceil(1.3 * text_bytes / 4) + images * TOKENS_PER_IMAGE + math.ceil(video_seconds * TOKENS_PER_VIDEO_SECOND)
    )


def responses_estimate(model: str, *, counted: int | None, fallback: int, max_output_tokens: int) -> float:
    """Worst case: the larger of the counted and fallback input, all uncached, plus the full output cap."""
    input_tokens = max(counted or 0, fallback)
    return responses_usd(model, input_tokens=input_tokens, cached_tokens=0, output_tokens=max_output_tokens)


def _int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def has_token_usage(usage: object) -> bool:
    """A usage object we can bill from: integer ``input_tokens`` and ``output_tokens``, input above zero."""
    if not isinstance(usage, Mapping):
        return False
    data = cast(Mapping[str, Any], usage)
    tokens = (data.get("input_tokens"), data.get("output_tokens"))
    if not all(isinstance(t, int) and not isinstance(t, bool) and t >= 0 for t in tokens):
        return False
    return cast(int, tokens[0]) > 0


def usage_units(usage: Mapping[str, Any] | None) -> dict[str, float]:
    """``{"input", "cached", "output", "reasoning"}`` from a Responses ``usage`` object (missing → 0)."""
    usage = usage or {}
    in_details = usage.get("input_tokens_details")
    out_details = usage.get("output_tokens_details")
    in_map = cast(Mapping[str, Any], in_details) if isinstance(in_details, Mapping) else _EMPTY
    out_map = cast(Mapping[str, Any], out_details) if isinstance(out_details, Mapping) else _EMPTY
    input_tokens = _int(usage, "input_tokens")
    return {
        "input": input_tokens,
        "cached": min(_int(in_map, "cached_tokens"), input_tokens),
        "output": _int(usage, "output_tokens"),
        "reasoning": _int(out_map, "reasoning_tokens"),
    }


def responses_usd_from_units(model: str, units: Mapping[str, float]) -> float:
    return responses_usd(
        model,
        input_tokens=int(units.get("input", 0)),
        cached_tokens=int(units.get("cached", 0)),
        output_tokens=int(units.get("output", 0)),
    )
