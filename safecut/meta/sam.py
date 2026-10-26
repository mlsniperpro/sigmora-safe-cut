"""SAM 3.1 request bodies, cost metering and a call wrapper. Parsing is Meta's ``meta-sam-parser`` (WP1).

One noun phrase (or one batch of object prompts) per request; the proxy clip's file ID comes from
``files.json`` by name, never ``prepared.mp4`` (PRE-A §10.6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx

from safecut import config
from safecut.config import Settings
from safecut.meta import cost
from safecut.meta.client import CallSpec, MetaClient, StreamResult, Units
from safecut.meta.retry import RetryPolicy


def video_body(settings: Settings, *, file_id: str, text: str, object_prompt: bool = False) -> dict[str, Any]:
    """A SAM video request: ``text`` is a noun phrase, or ``build_object_prompt`` output when ``object_prompt``."""
    if not file_id.startswith(("file-", "file_")):
        raise ValueError(f"not a Files API id: {file_id!r}")
    if not text.strip():
        raise ValueError("SAM needs a noun phrase or object prompts")
    metadata: dict[str, str] = {"include_confidence": "true", "mask_encoding": "one_bit"}
    if object_prompt:
        metadata["propagation_direction"] = "both"
    body: dict[str, Any] = {
        "model": settings.sam_model,
        "metadata": metadata,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}, {"type": "input_video", "file_id": file_id}],
            }
        ],
    }
    if settings.sam_send_store:
        body["store"] = False
    return body


def image_body(settings: Settings, *, image_data_url: str, text: str) -> dict[str, Any]:
    if not image_data_url.startswith(("data:image/", "https://")):
        raise ValueError("SAM image input must be a data: URL or an https URL")
    body: dict[str, Any] = {
        "model": settings.sam_model,
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": image_data_url}],
            }
        ],
    }
    if settings.sam_send_store:
        body["store"] = False
    return body


def video_meter(response: Mapping[str, Any]) -> tuple[Units, float]:
    """Frames billed from ``usage.video_frames_processed`` (documented)."""
    usage = response.get("usage")
    frames = cast(Mapping[str, Any], usage).get("video_frames_processed") if isinstance(usage, Mapping) else None
    n = frames if isinstance(frames, int) and not isinstance(frames, bool) and frames >= 0 else 0
    return {"frames": n}, cost.sam_video_usd(n)


def image_meter(_response: Mapping[str, Any]) -> tuple[Units, float]:
    return {"images": 1}, cost.sam_image_usd(1)


async def segment_video(
    client: MetaClient, body: Mapping[str, Any], *, sam_frames: int, stage: str = "track"
) -> StreamResult:
    """Run one SAM video request; feed ``result.events`` to ``meta_sam_parser.parse_responses_stream``."""
    spec = CallSpec(
        stage=stage,
        model=cast(str, body["model"]),
        estimate_usd=cost.sam_video_estimate(sam_frames),
        estimate_units={"frames": float(max(config.SAM_MIN_FRAMES_BILLED, sam_frames))},
        policy=RetryPolicy.for_sam(),
        timeout=httpx.Timeout(config.SAM_IDLE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        lane="sam",
        total_timeout_s=config.SAM_TOTAL_TIMEOUT_S,
    )
    return await client.stream(spec, body, meter=video_meter)


async def segment_image(client: MetaClient, body: Mapping[str, Any], *, stage: str = "probe") -> StreamResult:
    spec = CallSpec(
        stage=stage,
        model=cast(str, body["model"]),
        estimate_usd=cost.sam_image_usd(1),
        estimate_units={"images": 1},
        policy=RetryPolicy.for_sam(),
        timeout=httpx.Timeout(config.SAM_IDLE_TIMEOUT_S, connect=config.CONNECT_TIMEOUT_S),
        lane="sam",
        total_timeout_s=config.SAM_TOTAL_TIMEOUT_S,
    )
    return await client.stream(spec, body, meter=image_meter)
