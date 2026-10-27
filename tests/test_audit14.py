"""Tests for audit #14: a leak that names a through_item must be flagged, probe c's length check never costs
the frame answer, and a multipart factory that fails before sending is never charged."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr, ValidationError

from safecut import contracts as c
from safecut.config import Settings
from safecut.meta.budget import LocalLedger
from safecut.meta.client import CallSpec
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import Harness
from tests.test_probes_replay import api  # noqa: F401 -- the replay server fixture, reused

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def test_a_through_item_needs_a_flag() -> None:
    leak = {"frame": 4, "box": [10, 10, 50, 50], "kind": "text", "detector": "redteam", "patched_item": None}
    with pytest.raises(ValidationError, match="through_item is set exactly on a flagged leak"):
        c.Leak.model_validate(leak | {"through_item": "i_3"})
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    audit["redteam"] = [r for r in audit["redteam"] if r["finding"] == "none"]  # its hit needs its own leak
    with pytest.raises(ValidationError):
        c.Audit.model_validate(audit | {"leaks": [leak | {"through_item": "i_3"}]})
    flagged = leak | {"through_item": "i_3", "flag": "redaction_too_weak"}
    # A flag alone fixes nothing (audit #16): the item read through is re-rendered, so it is the patch.
    with pytest.raises(ValidationError, match="neither patched nor unresolved"):
        c.Audit.model_validate(audit | {"leaks": [flagged]})
    patched = flagged | {"patched_item": "i_3"}
    assert c.Audit.model_validate(audit | {"leaks": [patched]}).leaks[0].flag == "redaction_too_weak"


@pytest.mark.usefixtures("api")
async def test_a_failed_long_clip_keeps_probe_c_frame_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = probes.make_long_clip

    def fails_at_180(path: Path, seconds: int) -> None:
        if seconds == 180:
            raise subprocess.CalledProcessError(1, ["ffmpeg"])
        real(path, seconds)

    monkeypatch.setattr(probes, "make_long_clip", fails_at_180)
    cfg = Settings(model_api_key=SecretStr("k"))
    results = await probes.run(["c"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    c_out = results["c"]
    assert "frame_error" in c_out  # the paid frame answer survives
    assert c_out["max_length"]["60s"]["accepted"] is True
    assert c_out["max_length"]["180s"] == {
        "accepted": None,  # a local failure: not measured, never "Meta refused 180 s" (audit #16)
        "error": "CalledProcessError: Command '['ffmpeg']' returned non-zero exit status 1.",
    }


async def test_a_failing_multipart_factory_is_never_charged(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/asr").mock(return_value=httpx.Response(200, json={}))
    spec = CallSpec(
        stage="speech",
        model=None,
        estimate_usd=0.05,
        estimate_units={},
        policy=RetryPolicy(attempts=1),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )

    def missing() -> Any:
        raise FileNotFoundError("audio.wav")

    with pytest.raises(FileNotFoundError):
        await h.client.request("POST", "asr", spec, meter=lambda _: ({}, 0.0), files=missing)
    assert route.call_count == 0
    assert [(line.usd, line.estimated) for line in h.costs()] == [(0.0, False)]
