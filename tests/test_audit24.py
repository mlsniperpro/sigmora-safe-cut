"""Tests for audits #24 and #25: an unflagged leak's patch is an audit patch, containment is checked against what
the plan renders, and a Files cost line records its bytes."""

from __future__ import annotations

import functools
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut import contracts as c
from safecut.config import Settings
from safecut.meta.budget import LocalLedger
from safecut.meta.client import CallSpec
from safecut.meta.errors import MetaBadRequest
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import BASE, Harness
from tests.test_probes_replay import api  # noqa: F401 -- the replay server fixture, reused

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _example(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    (job_dir / "receipt.json").unlink()  # it would (rightly) disagree with the edited files
    return job_dir


def _edit(job_dir: Path, name: str, change: Callable[[Any], None]) -> None:
    data = json.loads((job_dir / name).read_text())
    change(data)
    (job_dir / name).write_text(json.dumps(data))


def test_a_track_item_overlapping_a_sliver_never_patches_an_unflagged_leak(tmp_path: Path) -> None:
    # i_3 (the hidden screen) renders [884, 384, 1116, 616] on frame 3; the face overlaps it by 6 px.
    job_dir = _example(tmp_path)
    leak = {"frame": 3, "box": [1110, 420, 1210, 500], "kind": "face", "detector": "egoblur", "patched_item": "i_3"}
    _edit(job_dir, "audit.json", lambda d: d["leaks"].append(leak))
    with pytest.raises(c.ContractError, match="i_3 is neither an audit patch nor the flagged through_item"):
        c.validate_job_dir(job_dir)


def test_a_flagged_leak_may_name_another_item_only_as_its_through_item(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    leak = {"frame": 3, "box": [900, 400, 1000, 500], "kind": "text", "detector": "redteam", "patched_item": "i_3",
            "flag": "redaction_too_weak", "through_item": "p_1"}  # fmt: skip
    _edit(job_dir, "audit.json", lambda d: d["leaks"].append(leak))
    with pytest.raises(c.ContractError, match="i_3 is neither an audit patch nor the flagged through_item"):
        c.validate_job_dir(job_dir)


def test_containment_uses_the_rendered_box_not_the_declared_one(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def shrink(d: Any) -> None:
        for entries in d["frames"].values():
            for entry in entries:
                if entry["item_id"] == "p_1":
                    entry["box"] = [0, 0, 2, 2]

    _edit(job_dir, "plan.json", shrink)
    with pytest.raises(c.ContractError, match=r"p_1 doesn't cover box \[200, 200, 260, 280\] on frame 10"):
        c.validate_job_dir(job_dir)


async def test_an_upload_cost_line_records_its_bytes(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 300)
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-1"}))
    await FileStore(h.client, tmp_path / "job").upload(clip, "sam_proxy.mp4")
    [line] = [line for line in h.costs() if line.stage == "files"]
    assert (line.units, line.usd) == ({"bytes": 300.0}, 0.0)


# --- audit #26 ----------------------------------------------------------------------------------------------


def test_unresolved_counts_leaks_and_unscanned_frames_together(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def change(d: Any) -> None:
        d["leaks"][0] |= {"patched_item": None, "unresolved": True}
        d.update({"frames_scanned": 6, "unresolved": 6, "blocked_reason": "audit_failed"})

    _edit(job_dir, "audit.json", change)
    with pytest.raises(c.ContractError, match="6 frames weren't scanned and 1 leaks are unresolved"):
        c.validate_job_dir(job_dir)
    _edit(job_dir, "audit.json", lambda d: d.update({"unresolved": 7}))
    assert "audit.json" in c.validate_job_dir(job_dir)


async def test_probe_d_saves_the_asr_body_as_sent(api: respx.MockRouter, tmp_path: Path) -> None:  # noqa: F811 -- pytest injects the imported fixture by name
    sent = {"transcript": "", "audioDurationMs": 3000, "turns": [], "language": "en", "requestId": "r-1"}
    api.post(f"{BASE}/asr/transcribe").mock(return_value=httpx.Response(200, json=sent))
    results = await probes.run(
        ["d"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    assert results["d"]["audio_duration_ms"] == 3000
    assert json.loads((tmp_path / "d" / "asr.response.json").read_text()) == sent


# --- audit #28 ----------------------------------------------------------------------------------------------


async def _sam_like(client: Any, file_id: str) -> str:
    result = await client.request(
        "POST", "thing", _free_spec(), meter=lambda _: ({}, 0.0), json_body={"file_id": file_id}
    )
    return str(result.body["ok"])


def _free_spec() -> CallSpec:
    return CallSpec(stage="s", model=None, estimate_usd=0.0, estimate_units={}, policy=RetryPolicy(attempts=1),
                    timeout=httpx.Timeout(5.0), total_timeout_s=10.0)  # fmt: skip


GONE = httpx.Response(404, json={"error": {"message": "gone", "code": "file_not_found", "param": None}})


@pytest.mark.parametrize("second", ["ok", "gone"])
async def test_r10_reuploads_once_then_fails_closed(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path, second: str
) -> None:
    h = make_harness()
    clip = tmp_path / "sam_proxy.mp4"
    clip.write_bytes(b"x" * 300)
    store = FileStore(h.client, tmp_path / "job")
    mock_api.post("/files").mock(
        side_effect=[httpx.Response(200, json={"id": "file-1"}), httpx.Response(200, json={"id": "file-2"})]
    )
    first_id = await store.upload(clip, "sam_proxy.mp4")
    again = httpx.Response(200, json={"ok": "yes"}) if second == "ok" else GONE
    thing = mock_api.post("/thing").mock(side_effect=[GONE, again])
    call = functools.partial(_sam_like, h.client)
    if second == "ok":
        assert await store.call_with_reupload(clip, "sam_proxy.mp4", first_id, call) == "yes"
    else:
        with pytest.raises(MetaBadRequest, match="file_not_found again after one re-upload"):
            await store.call_with_reupload(clip, "sam_proxy.mp4", first_id, call)
    assert [json.loads(r.request.content)["file_id"] for r in thing.calls] == ["file-1", "file-2"]
    entries = {e.file_id: e for e in store.index().root}
    assert entries["file-1"].deleted_at is not None  # forgotten, so files.json points at the new copy
    assert entries["file-2"].deleted_at is None
