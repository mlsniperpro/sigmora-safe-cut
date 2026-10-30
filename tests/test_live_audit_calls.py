"""Live tests for the audit's two model calls (E8): Muse Spark's red-team look at rendered frames, and the open-weight
second opinion (Muse Spark Open on Baseten). Deselected by default; ``uv run pytest -m live``.

Both send one rendered frame of the synthetic demo clip (drawn shapes; no real footage, PRE-A §3.8), with the
frame-number bar added above it, in the request shapes ``docs/prompts/redteam.md`` and ``safecut/open_weight.py``
define. Spend: about $0.01 on Meta, about $0.01 of Baseten credit. Skipped without the matching key (the only skip
E11 allows).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from safecut.config import OpenWeightPrice, load_settings
from safecut.meta import responses
from safecut.meta.budget import Caller, CapLimit, LocalLedger
from safecut.meta.client import MetaClient
from safecut.open_weight import REDTEAM_SYSTEM, REDTEAM_USER, RedteamAnswer, open_weight_client, second_opinion
from safecut.scout.grid import BAR_H
from scripts import make_demo_job as demo

pytestmark = pytest.mark.live
FRAME = 250  # the envelope, the plate and the passer-by are all on screen


def _frame_url(tmp_path: Path) -> str:
    """The demo frame as sent to an auditor: the picture under a black bar carrying ``F 000250``."""
    image = demo.draw(FRAME)
    sent = np.zeros((image.shape[0] + BAR_H, image.shape[1], 3), dtype=np.uint8)
    sent[BAR_H:] = image
    cv2.putText(sent, f"F {FRAME:06d}", (8, BAR_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    path = tmp_path / "frame.jpg"
    cv2.imwrite(str(path), sent, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


#: redteam.md's strict output schema.
REDTEAM_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["frames"],
    "properties": {"frames": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["frame", "findings"],
        "properties": {
            "frame": {"type": "integer"},
            "findings": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["kind", "detail", "text", "box", "confidence"],
                "properties": {
                    "kind": {"type": "string",
                             "enum": ["face", "person", "text", "plate", "screen", "misaligned_redaction", "other"]},
                    "detail": {"type": "string"},
                    "text": {"type": ["string", "null"]},
                    "box": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                }}},
        }}}},
}  # fmt: skip


#: Without the key the test can't run (the only skip E11 allows).
needs_meta = pytest.mark.skipif(not os.environ.get("MODEL_API_KEY"), reason="needs MODEL_API_KEY (owner input)")
needs_baseten = pytest.mark.skipif(not os.environ.get("BASETEN_API_KEY"), reason="needs BASETEN_API_KEY (owner input)")


@pytest.mark.entry("E8:muse_redteam")
@needs_meta
async def test_muse_redteam_reads_the_unredacted_frame(tmp_path: Path) -> None:
    settings = load_settings()
    url = _frame_url(tmp_path)
    messages = [
        {"role": "system", "content": [{"type": "input_text", "text": REDTEAM_SYSTEM}]},
        {"role": "user", "content": [
            {"type": "input_text", "text": REDTEAM_USER.format(kept_clear="none")},
            {"type": "input_text", "text": f"Frame {FRAME}:"},
            {"type": "input_image", "image_url": url},
        ]},
    ]  # fmt: skip
    body = responses.build_body(settings.redteam_model, messages, effort=settings.redteam_effort,
                                schema=REDTEAM_SCHEMA, schema_name="redteam")  # fmt: skip
    caller = Caller(code_kind="owner", limits=(CapLimit("code", "live-tests", 0.10),))
    async with MetaClient(settings, job_id="live_redteam", caller=caller, ledger=LocalLedger(),
                          cost_path=tmp_path / "cost.jsonl") as client:  # fmt: skip
        answer, result = await responses.create_json(
            client, RedteamAnswer, body, stage="redteam", effort=settings.redteam_effort
        )
    assert result.usd > 0
    assert [f.frame for f in answer.frames] == [FRAME]
    assert answer.frames[0].findings  # nothing is redacted here: the plate and envelope text are readable


@pytest.mark.entry("E8:open_weight")
@needs_baseten
async def test_open_weight_second_opinion(tmp_path: Path) -> None:
    price = load_settings().open_weight_price or OpenWeightPrice.model_validate({"in": 0.5, "out": 2.0})
    settings = load_settings().model_copy(update={
        "open_weight_audit": "on", "open_weight_code_kinds": ("owner",), "open_weight_price": price,
    })  # fmt: skip
    client = open_weight_client(settings, job_id="live_open_weight", caller=Caller.local(), ledger=LocalLedger(),
                                cost_path=tmp_path / "cost.jsonl")  # fmt: skip
    async with client:
        opinion = await second_opinion(client, settings, consented=True, frames=[(FRAME, _frame_url(tmp_path))])
    assert opinion.status == "ok", opinion.errors
    assert [f.frame for f in opinion.frames] == [FRAME]
