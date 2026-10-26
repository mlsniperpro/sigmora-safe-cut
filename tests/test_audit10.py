"""Tests for audit #10: every orphan copy recorded before any delete, cross-file pointers, the plan covering
every hidden item, and no NaN or infinity in a contract."""

from __future__ import annotations

import json
import math
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from safecut import contracts as c
from safecut.meta.errors import MetaUnavailable
from safecut.meta.files import FileStore
from tests.conftest import Harness

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _example(tmp_path: Path) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    return job_dir


def _edit(job_dir: Path, name: str, change: Callable[[Any], None]) -> None:
    data = json.loads((job_dir / name).read_text())
    change(data)
    (job_dir / name).write_text(json.dumps(data))


async def test_a_failed_orphan_delete_never_leaves_a_later_copy_unrecorded(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 300)
    mock_api.post("/files").mock(side_effect=httpx.ReadTimeout("slow"))  # accepted twice, never answered
    copies = [
        {"id": f"file-{n}", "filename": "j_test-sam_proxy.mp4", "bytes": 300, "created_at": time.time()}
        for n in (9, 10)
    ]
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": copies}))
    mock_api.delete("/files/file-9").mock(return_value=httpx.Response(503))
    ten = mock_api.delete("/files/file-10").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(MetaUnavailable):
        await store.upload(clip, "sam_proxy.mp4")
    assert ten.call_count == 1  # the loop carried on past file-9's failure
    recorded = {e.file_id: e.deleted_at is not None for e in store.index().root}
    assert recorded == {"file-9": False, "file-10": True}
    assert not store.index().all_deleted  # file-9 is still live and recorded: no false files_deleted


@pytest.mark.parametrize(
    ("name", "change", "message"),
    [
        ("roles.json", lambda d: d["tracks"][0].update({"matches_participant": 7}), "matches_participant 7"),
        ("scene.json", lambda d: d["participants"][0].update({"introduced_in_turn": 99}), "introduced_in_turn 99"),
        ("audit.json", lambda d: d["leaks"][0].update({"patched_item": "i_99"}), "patched_item"),
        (
            "audit.json",
            lambda d: d["spots"].append(
                {"spot_id": "s1", "first": 2, "last": 3, "boxes": {"2": [10, 10, 50, 50]}, "covered_by": "i_99"}
            ),
            "covered_by",
        ),
    ],
)
def test_cross_file_pointers_must_resolve(
    tmp_path: Path, name: str, change: Callable[[Any], None], message: str
) -> None:
    job_dir = _example(tmp_path)
    before = (job_dir / name).read_text()
    _edit(job_dir, name, change)
    if (job_dir / name).read_text() == json.dumps(json.loads(before)):
        pytest.fail(f"the example {name} has nothing to point from")
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_every_hidden_item_is_planned_on_every_frame_of_its_span(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    assert "plan.json" in c.validate_job_dir(job_dir)
    _edit(job_dir, "plan.json", lambda d: d["frames"].pop("7"))
    with pytest.raises(c.ContractError, match="hidden item i_2 has no entry on frames \\[7\\]"):
        c.validate_job_dir(job_dir)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -5.0])
def test_times_must_be_finite_and_non_negative(bad: float) -> None:
    job = json.loads((EXAMPLE / "job.json").read_text())
    job["times"][0] = bad
    with pytest.raises(ValidationError):
        c.Job.model_validate(job)


def test_cost_lines_refuse_nan() -> None:
    line = {
        "ts": "2026-10-27T10:00:00Z",
        "provider": "meta",
        "job_id": "j",
        "stage": "role",
        "model": "muse-spark-1.3",
        "attempt": 1,
        "units": {},
        "usd": math.nan,
        "estimated": False,
        "request_id": None,
        "code_kind": "owner",
        "code_id": None,
    }
    with pytest.raises(ValidationError):
        c.CostLine.model_validate(line)
