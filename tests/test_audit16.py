"""Tests for audits #16 and #17 (both at 2ca6ba8): a leak needs a patch whose item covers its frame, proxy
refusals are never billed, and the probes keep their paid results when one part fails."""

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
from safecut.config import Settings
from safecut.meta.budget import LocalLedger
from safecut.meta.client import CallSpec
from safecut.meta.errors import MetaUnavailable
from safecut.meta.retry import RetryPolicy
from scripts.probes import probes
from tests.conftest import BASE, Harness
from tests.test_probes_replay import api  # noqa: F401 -- the replay server fixture, reused

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "j_example"


def _with_leak(tmp_path: Path, **leak: Any) -> Path:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    audit = json.loads((job_dir / "audit.json").read_text())
    audit["leaks"] = [{"frame": 10, "box": [200, 200, 260, 280], "kind": "face", "detector": "redteam"} | leak]
    audit["redteam"] = [r for r in audit["redteam"] if r["finding"] == "none"]  # its hit would need its own leak
    (job_dir / "audit.json").write_text(json.dumps(audit))
    return job_dir


@pytest.mark.parametrize(
    ("leak", "message"),
    [
        (
            {"patched_item": "i_3"},
            r"patch: i_3 doesn't hide frames \[10\]",
        ),  # a track-span item that doesn't cover frame 10
        (
            {"patched_item": "p_1", "flag": "redaction_too_weak", "through_item": "i_1"},
            "through_item: i_1 is a kept item",
        ),
        (
            {"patched_item": "p_1", "flag": "redaction_too_weak", "through_item": "i_3"},
            r"through_item: i_3 doesn't hide frames \[10\]",
        ),
    ],
)
def test_patches_and_through_items_must_cover_the_leak(tmp_path: Path, leak: dict[str, Any], message: str) -> None:
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(_with_leak(tmp_path, **leak))


def test_a_flagged_leak_without_a_patch_is_refused(tmp_path: Path) -> None:
    job_dir = _with_leak(tmp_path, patched_item=None, flag="redaction_too_weak", through_item="i_2")
    with pytest.raises(c.ContractError, match="neither patched nor unresolved"):
        c.validate_job_dir(job_dir)


async def test_a_proxy_refusal_is_never_billed(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=httpx.ProxyError("403 Forbidden from the egress proxy"))
    spec = CallSpec(
        stage="s",
        model="muse-spark-1.3",
        estimate_usd=0.08,
        estimate_units={},
        policy=RetryPolicy(attempts=4),
        timeout=httpx.Timeout(5.0),
        total_timeout_s=10.0,
    )
    with pytest.raises(MetaUnavailable):
        await h.client.request("POST", "thing", spec, meter=lambda _: ({}, 0.0))
    assert all((line.usd, line.estimated) == (0.0, False) for line in h.costs())


@pytest.mark.usefixtures("api")
async def test_a_parser_error_on_one_concept_keeps_the_others(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = probes._sam_once  # pyright: ignore[reportPrivateUsage] -- wrap the per-concept call

    async def fails_on_face(p: Any, file_id: str, concept: str, frames: int, log: Any) -> Any:
        if concept == "face":
            raise RuntimeError("parser")
        return await real(p, file_id, concept, frames, log)

    monkeypatch.setattr(probes, "_sam_once", fails_on_face)
    results = await probes.run(
        ["b"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    concepts = results["b"]["concepts"]
    assert concepts["face"] == {"error": "RuntimeError: parser"}
    assert concepts["red square"]["records"] == 1
    assert "delete_without_store" in results["b"]  # the later paid checks still ran


async def test_probe_a_survives_a_status_outage(api: respx.MockRouter, tmp_path: Path) -> None:  # noqa: F811
    api.get(f"{BASE}/status").mock(return_value=httpx.Response(503))
    results = await probes.run(
        ["a"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    a = results["a"]
    assert a["service_status"] is None
    assert a["status_error"]
    assert "sam-3.1" in a["model_ids"]


@pytest.mark.usefixtures("api")
async def test_a_hero_clip_moves_only_b_and_d(tmp_path: Path) -> None:
    hero = tmp_path / "hero.mp4"
    shutil.copy(probes.CLIP, hero)
    out, hero_root = tmp_path / "fixtures", tmp_path / "hero"
    await probes.run(
        ["a", "b"],
        settings=Settings(model_api_key=SecretStr("k")),
        out_root=out,
        ledger=LocalLedger(),
        clip=hero,
        hero_root=hero_root,
    )
    assert (out / "a" / "summary.json").exists()
    assert (hero_root / "hero" / "b" / "summary.json").exists()  # one folder per hero clip (audit #21)
    assert not (out / "b").exists()


@pytest.mark.usefixtures("api")
async def test_an_outage_during_the_length_check_is_not_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def outage(*_: Any, **__: Any) -> Any:
        raise MetaUnavailable("HTTP 503")

    real_create = probes.responses.create

    async def create(client: Any, body: Any, **kw: Any) -> Any:
        if "How many seconds" in json.dumps(body):
            return await outage()
        return await real_create(client, body, **kw)

    monkeypatch.setattr(probes.responses, "create", create)
    results = await probes.run(
        ["c"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    lengths = results["c"]["max_length"]
    assert all(r["accepted"] is None for r in lengths.values())  # never "Meta refused 60 s"
