"""Synthetic SAM 3.1 streams, written from a synthetic clip's ground truth (never from a model).

The lines follow SAM's documented wire grammar (PRE-A §1.4) and the masks use Meta's own one-bit encoder, so the
same parser, linker and contracts that read live responses read these. Every recording made from them is
labelled ``synthetic: true``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from meta_sam_parser._mask_codec import (  # pyright: ignore[reportPrivateUsage] -- the parser's own encoder keeps synthetic masks canonical
    _encode_raster,  # pyright: ignore[reportPrivateUsage] -- see above
)
from numpy.typing import NDArray

from safecut.meta import replay

Box = tuple[int, int, int, int]


def ellipse(width: int, height: int) -> NDArray[np.uint8]:
    """A filled ellipse inscribed in a ``width × height`` box (a face- or body-like mask)."""
    yy, xx = np.mgrid[0:height, 0:width]
    cy, cx = (height - 1) / 2, (width - 1) / 2
    inside = ((yy - cy) / max(height / 2, 0.5)) ** 2 + ((xx - cx) / max(width / 2, 0.5)) ** 2 <= 1.0
    return inside.astype(np.uint8)


def mask_payload(local: NDArray[np.uint8]) -> str:
    """A canonical one-bit payload (``!…``) for a box-sized raster."""
    return _encode_raster(local.ravel().tolist(), local.shape[1], local.shape[0])


def record(object_id: str, box: Box, size: tuple[int, int], *, confidence: float | None = None,
           shape: str = "rect") -> str:  # fmt: skip
    """One ``objectId<|box…|><|mask…|>`` segment for a half-open ``box`` in a ``size = (w, h)`` frame."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    local = ellipse(w, h) if shape == "ellipse" else np.ones((h, w), dtype=np.uint8)
    c = f";c={confidence:.2f}" if confidence is not None else ""
    return (f"{object_id}<|box;x1={x1};y1={y1};x2={x2 - 1};y2={y2 - 1};w={size[0]};h={size[1]}{c}|>"
            f"<|mask;x=0;y=0;data={h},{w},{mask_payload(local)}|>")  # fmt: skip


def clip_box(box: Box, size: tuple[int, int]) -> Box | None:
    x1, y1 = max(0, box[0]), max(0, box[1])
    x2, y2 = min(size[0], box[2]), min(size[1], box[3])
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def stream_text(
    objects: Mapping[str, Mapping[int, Box]],
    size: tuple[int, int],
    *,
    shapes: Mapping[str, str] | None = None,
    confidence: float | None = 0.9,
) -> str:
    """Lines for every proxy frame with objects: ``{object_id: {proxy_frame: box}}``. Frames without objects
    emit no line, exactly as SAM does."""
    by_frame: dict[int, list[str]] = {}
    for object_id, frames in objects.items():
        for j, box in frames.items():
            clipped = clip_box(box, size)
            if clipped is None:
                continue
            shape = (shapes or {}).get(object_id, "rect")
            by_frame.setdefault(j, []).append(record(object_id, clipped, size, confidence=confidence, shape=shape))
    return "".join(f"<{j}f>{','.join(by_frame[j])}\n" for j in sorted(by_frame))


def events(text: str, *, response_id: str, frames_billed: int) -> list[dict[str, object]]:
    """The documented Responses event sequence around one SAM output lane (PRE-A §1.4, §10.6)."""
    lane = {"item_id": "msg_synthetic", "output_index": 0, "content_index": 0}
    deltas: Sequence[str] = [line + "\n" for line in text.splitlines()] or []
    return [
        {"type": "response.created", "response": {"id": response_id, "status": "in_progress"}},
        *({"type": "response.output_text.delta", "delta": d, **lane} for d in deltas),
        {"type": "response.content_part.done", **lane, "part": {"type": "output_text", "text": text}},
        {"type": "response.completed",
         "response": {"id": response_id, "status": "completed", "usage": {"video_frames_processed": frames_billed}}},
    ]  # fmt: skip


def record_sweep(
    job_dir: Path,
    *,
    text: str,
    objects: Mapping[str, Mapping[int, Box]],
    size: tuple[int, int],
    proxy_frames: int,
    model: str,
    shapes: Mapping[str, str] | None = None,
) -> Path:
    """Write the synthetic recording replay reads for a phrase sweep of ``text``."""
    from safecut.track.stage import RAW_STAGE, SamCall, recording  # noqa: PLC0415 -- the stage imports this module's users

    call = SamCall(kind="phrase", concept=text, text=text, file_id="file-synthetic")
    body = stream_text(objects, size, shapes=shapes)
    call.events = events(body, response_id=f"resp_synthetic_{replay.slug(text)}", frames_billed=proxy_frames)
    return replay.save(job_dir, RAW_STAGE, call.key, recording(call, model=model, frames=proxy_frames, synthetic=True))
