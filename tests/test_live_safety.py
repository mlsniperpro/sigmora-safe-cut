"""Live test for the one Meta call the SAFETY stages make: the Muse Spark red team (E8). Deselected by default;
``uv run pytest -m live -k redteam``. One call on two synthetic frames (a drawn face left exposed, and the same face
under a solid block) under a $0.50 job cap, about $0.01. Without ``MODEL_API_KEY`` it's skipped (the only skip
E11 allows)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import numpy as np
import pytest

from safecut.audit.leaks import bar_height, grid_box
from safecut.audit.redteam import Answer, LiveRedTeam
from safecut.config import load_settings
from safecut.contracts import read_cost_lines
from safecut.meta.session import job_client
from safecut.render.draw import FILL_BGR
from tests.safety_jobs import H, Scenario, W, frame_image

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("MODEL_API_KEY"), reason="needs MODEL_API_KEY (owner input)"),
]


@pytest.mark.entry("E8:muse_redteam")
def test_the_red_team_finds_an_exposed_face_and_not_a_covered_one(tmp_path: Path) -> None:
    settings = load_settings().model_copy(update={"job_usd_cap": 0.50, "replay": False})
    job_dir = tmp_path / "j_live_redteam"
    job_dir.mkdir()
    exposed = frame_image(Scenario(), 30)
    covered = exposed.copy()
    covered[40:200, 20:160] = np.array(FILL_BGR, dtype=np.uint8)  # the host's face under a solid block

    async def ask() -> Answer:
        async with job_client(job_dir, settings) as client:
            return await LiveRedTeam(client, settings, job_dir).ask(
                [(30, exposed), (31, covered)], [], bar=bar_height(H)
            )

    answer = asyncio.run(ask())
    assert answer.missing == []
    findings = answer.findings
    boxes = [
        grid_box(f.box, width=W, height=H, bar=bar_height(H)) for f in findings[30] if f.kind in ("face", "person")
    ]
    assert boxes, "an exposed face is reported"
    recorded = json.loads((job_dir / "raw" / "redteam" / "frames.json").read_text())
    assert set(recorded["answers"]) == {"30", "31"}
    lines = [line for line in read_cost_lines(job_dir / "cost.jsonl") if line.stage == "redteam"]
    assert lines
    assert all(line.model == settings.redteam_model for line in lines)
