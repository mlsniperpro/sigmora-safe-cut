"""Tests for audit #18: one name's failed reconcile never strands the next, an earlier attempt's copy survives a
failed record, a red-team hit can't vanish, spots are consistent, and probes survive odd answers."""

from __future__ import annotations

import json
import shutil
import time
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
from safecut.meta.errors import MetaBadRequest
from safecut.meta.files import FileStore
from scripts.probes import probes
from tests.conftest import Harness
from tests.test_probes_replay import api  # noqa: F401 -- the replay server fixture, reused

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _copy(file_id: str, name: str) -> dict[str, object]:
    return {"id": file_id, "filename": f"j_test-{name}", "bytes": 300, "created_at": time.time()}


async def test_one_names_failed_reconcile_never_strands_the_next(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = FileStore(h.client, tmp_path / "job")
    orphans = [
        c.FileEntry(name=n, sha256="a" * 64, file_id=None, created_at=c.now_utc(), orphan=True)
        for n in ("a.mp4", "b.mp4")
    ]
    c.dump(c.FilesIndex(orphans), store.index_path)
    listing = [_copy("file-1", "a.mp4"), _copy("file-2", "b.mp4")]
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": listing}))
    mock_api.delete("/files/file-1").mock(return_value=httpx.Response(400, json={"error": {"message": "no"}}))
    b = mock_api.delete("/files/file-2").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(MetaBadRequest):
        await store.delete_all()
    assert b.call_count == 1
    open_orphans = [e.name for e in store.index().root if e.orphan and e.deleted_at is None]
    assert open_orphans == ["a.mp4"]  # only the failed name stays open


async def test_an_earlier_copy_survives_a_failed_record(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = make_harness()
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 300)
    mock_api.post("/files").mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"id": "file-2"})])
    mock_api.delete("/files/file-2").mock(return_value=httpx.Response(200, json={}))
    store = FileStore(h.client, tmp_path / "job")
    real = store._record  # pyright: ignore[reportPrivateUsage] -- fail the success record only
    failed: list[bool] = []

    async def record(entry: c.FileEntry) -> None:
        if entry.file_id == "file-2" and not failed:
            failed.append(True)
            raise OSError("disk full")
        await real(entry)

    monkeypatch.setattr(store, "_record", record)
    with pytest.raises(OSError, match="disk full"):
        await store.upload(clip, "sam_proxy.mp4")
    # The first attempt's 503 may have stored a copy: an orphan keeps files_deleted false until it's listed.
    assert any(e.orphan for e in store.index().root)
    assert not store.index().all_deleted


def _audit() -> dict[str, Any]:
    return json.loads((EXAMPLE / "audit.json").read_text())


def test_a_red_team_hit_needs_a_leak_or_an_exclusion() -> None:
    audit = _audit()
    hit = {"frame": 4, "finding": "hit", "kind": "text", "text": "A", "detail": "a name", "box": [1, 1, 9, 9],
           "confidence": "high", "excluded_by": None}  # fmt: skip
    with pytest.raises(ValidationError, match="red-team hit at frame 4 is neither excluded nor a leak"):
        c.Audit.model_validate(audit | {"redteam": [*audit["redteam"], hit]})
    excluded = hit | {"excluded_by": "i_1"}
    assert c.Audit.model_validate(audit | {"redteam": [*audit["redteam"], excluded]})


@pytest.mark.parametrize(
    ("spot", "message"),
    [
        ({"first": 8, "last": 3, "boxes": {"3": [1, 1, 9, 9]}}, "first 8 is after last 3"),
        ({"first": 6, "last": 8, "boxes": {"3": [1, 1, 9, 9]}}, "outside 6-8"),
    ],
)
def test_a_spot_is_consistent(spot: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        c.Spot.model_validate({"spot_id": "s1"} | spot)


def test_a_spot_cover_must_hide_its_frames(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    audit = json.loads((job_dir / "audit.json").read_text())
    audit["spots"] = [{"spot_id": "s1", "first": 2, "last": 3, "boxes": {"2": [1, 1, 9, 9]}, "covered_by": "i_1"}]
    (job_dir / "audit.json").write_text(json.dumps(audit))
    with pytest.raises(c.ContractError, match="covered by i_1, a kept item"):
        c.validate_job_dir(job_dir)


@pytest.mark.usefixtures("api")
async def test_a_non_object_answer_keeps_probe_c_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes.responses, "output_text", lambda _: "[1, 2]")
    results = await probes.run(
        ["c"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    c_out = results["c"]
    assert c_out["error"].startswith("TypeError: the answer is a list")
    assert "usd" in c_out  # the paid call is still on record
    assert set(c_out["max_length"]) == {"60s", "180s"}  # and the length checks still ran
