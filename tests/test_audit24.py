"""Tests for audits #24 and #25: an unflagged leak's patch is an audit patch, containment is checked against what
the plan renders, and a Files cost line records its bytes."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from safecut import contracts as c
from safecut.meta.files import FileStore
from tests.conftest import Harness

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
