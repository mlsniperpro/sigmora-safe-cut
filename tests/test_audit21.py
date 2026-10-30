"""Tests for audit #21: bad keys are refused at load (never billed unsent), a disk fault never stops the delete
sweep, the receipt's leaks_patched is checked, and probe g measures the clamping at an edge."""

from __future__ import annotations

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
from safecut.config import ConfigError, Settings, load_settings
from safecut.meta.budget import LocalLedger
from safecut.meta.client import CallSpec
from safecut.meta.errors import MetaUnavailable
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import Harness
from tests.test_probes_replay import api  # noqa: F401 -- the replay server fixture, reused

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def test_a_pasted_newline_is_stripped_and_bad_keys_are_refused() -> None:
    assert load_settings({"MODEL_API_KEY": "sk-abc\n"}).api_key() == "sk-abc"
    for bad in ("sk-a bc", "sk-é"):
        with pytest.raises(ConfigError, match="whitespace or non-ASCII") as info:
            load_settings({"MODEL_API_KEY": bad})
        assert bad not in str(info.value)


async def test_a_request_h11_refuses_to_write_is_never_billed(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=httpx.LocalProtocolError("Illegal header value"))
    spec = CallSpec(
        stage="s",
        model="muse-spark-1.3",
        estimate_usd=0.068,
        estimate_units={},
        policy=RetryPolicy(attempts=4),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )
    with pytest.raises(MetaUnavailable):
        await h.client.request("POST", "thing", spec, meter=lambda _: ({}, 0.0))
    assert all((line.usd, line.estimated) == (0.0, False) for line in h.costs())


async def test_a_disk_fault_never_stops_the_delete_sweep(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = make_harness()
    store = FileStore(h.client, tmp_path / "job")
    entries = [
        c.FileEntry(name=n, sha256="a" * 64, file_id=f"file-{i}", created_at=c.now_utc())
        for i, n in ((1, "a.mp4"), (2, "b.mp4"))
    ]
    c.dump(c.FilesIndex(entries), store.index_path)
    deletes = mock_api.delete(url__regex=r".*/files/file-\d").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    real = store._mark_deleted  # pyright: ignore[reportPrivateUsage] -- fail the first index write only
    failed: list[str] = []

    async def mark(file_id: str) -> None:
        if not failed:
            failed.append(file_id)
            raise OSError("disk full")
        await real(file_id)

    monkeypatch.setattr(store, "_mark_deleted", mark)
    with pytest.raises(OSError, match="disk full"):
        await store.delete_all()
    assert deletes.call_count == 2  # the second file was still deleted


def test_receipt_leaks_patched_matches_the_audit(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    raw = json.loads((job_dir / "receipt.json").read_text())
    raw.pop("hash")
    raw["audit"]["leaks_patched"] = 47
    sealed = c.Receipt.seal(c.ReceiptBody.model_validate(raw))
    (job_dir / "receipt.json").write_text(json.dumps(sealed.model_dump(mode="json")))
    with pytest.raises(c.ContractError, match=r"leaks_patched 47 != audit\.json 2"):
        c.validate_job_dir(job_dir)


@pytest.mark.usefixtures("api")
async def test_probe_g_also_points_at_an_edge(tmp_path: Path) -> None:
    results = await probes.run(
        ["g"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    g: dict[str, Any] = results["g"]
    assert g["truth_frame_px"] == list(probes.DOT)
    assert g["edge"]["truth_frame_px"] == list(probes.EDGE_DOT)
    assert "raw_out_of_range" in g["edge"]
