"""Live test for the open-weight path the audit takes (E8): one Muse Spark Open call on Baseten through
``open_weight.second_opinion``, as the audit makes it, on two synthetic frames (about $0.002 of Baseten credit,
outside the Meta $150). Needs ``BASETEN_API_KEY`` and the probe-h price (``SAFECUT_OPEN_WEIGHT_PRICE``); without the
key it's skipped (the only skip E11 allows)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from safecut import open_weight
from safecut.audit.leaks import bar_height
from safecut.audit.opinion import data_url
from safecut.config import load_settings
from safecut.contracts import read_cost_lines
from safecut.meta.budget import Caller, LocalLedger
from tests.safety_jobs import H, Scenario, frame_image

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("BASETEN_API_KEY"), reason="needs BASETEN_API_KEY (owner input)"),
]


@pytest.mark.entry("E8:open_weight")
def test_the_second_opinion_answers_every_frame(tmp_path: Path) -> None:
    settings = load_settings().model_copy(
        update={"open_weight_audit": "on", "open_weight_code_kinds": ("owner",), "replay": False}
    )
    frames = [(f, data_url(frame_image(Scenario(), f), f, bar_height(H))) for f in (0, 30)]

    async def ask() -> open_weight.SecondOpinion:
        client = open_weight.open_weight_client(settings, job_id="j_live_opinion", caller=Caller.local("owner"),
                                                ledger=LocalLedger(), cost_path=tmp_path / "cost.jsonl")  # fmt: skip
        try:
            return await open_weight.second_opinion(client, settings, consented=True, frames=frames)
        finally:
            await client.aclose()

    got = asyncio.run(ask())
    assert got.status == "ok"
    assert sorted(f.frame for f in got.frames) == [0, 30]
    assert [line.provider for line in read_cost_lines(tmp_path / "cost.jsonl")] == ["baseten"]
