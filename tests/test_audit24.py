"""Tests for audits #24 and #25: an unflagged leak's patch is an audit patch, containment is checked against what
the plan renders, and a Files cost line records its bytes."""

from __future__ import annotations

import asyncio
import functools
import json
import os
import shutil
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut import config
from safecut import contracts as c
from safecut import open_weight as ow
from safecut.config import ConfigError, Settings, load_settings
from safecut.meta import asr as responses_asr
from safecut.meta import files as files_mod
from safecut.meta import responses, sam
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import (
    CallSpec,
    MetaClient,
    _ChatAccumulator,  # pyright: ignore[reportPrivateUsage] -- the unit under test
)
from safecut.meta.errors import MetaBadRequest, MetaConfigError, MetaIncomplete, MetaUnavailable, ReplayRefused
from safecut.meta.files import FileStore
from safecut.meta.retry import RetryPolicy, parse_retry_after
from safecut.meta.status import StatusUnavailableError, fetch_status
from scripts.probes import probes
from tests.conftest import BASE, Harness, narrow_patch, rle_string
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
    with pytest.raises(c.ContractError, match=r"p_1 doesn't cover (its held )?box \[200, 200, 260, 280\]"):
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


# --- audit #29 ----------------------------------------------------------------------------------------------


def _orphan_store(h: Harness, tmp_path: Path) -> FileStore:
    store = FileStore(h.client, tmp_path / "job")
    orphan = c.FileEntry(name="a.mp4", sha256="a" * 64, file_id=None, created_at=c.now_utc(), orphan=True)
    c.dump(c.FilesIndex([orphan]), store.index_path)
    return store


@pytest.mark.parametrize(
    ("listing", "message"),
    [
        ({"files": [{"id": "file-777", "filename": "j_test-a.mp4"}]}, "has no 'data' list"),
        ({"data": [], "has_more": True}, "truncated"),
    ],
)
async def test_a_listing_that_cant_rule_out_copies_keeps_the_orphan_open(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    tmp_path: Path,
    listing: dict[str, Any],
    message: str,
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    with pytest.raises(MetaConfigError, match=message):
        await store.delete_all()
    assert not store.index().all_deleted  # files_deleted stays false (PRE-A §10.4)


@pytest.mark.parametrize("body", [{"deleted": False}, {"id": "file-1"}, {}])
async def test_a_delete_without_deleted_true_leaves_the_entry_undeleted(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path, body: dict[str, Any]
) -> None:
    h = make_harness()
    store = FileStore(h.client, tmp_path / "job")
    entry = c.FileEntry(name="a.mp4", sha256="a" * 64, file_id="file-1", created_at=c.now_utc())
    c.dump(c.FilesIndex([entry]), store.index_path)
    mock_api.delete("/files/file-1").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(MetaConfigError, match="without deleted: true"):
        await store.delete_all()
    assert not store.index().all_deleted


async def test_a_stalled_ledger_call_is_retried_once(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PRE-A §10.2: a reserve with no answer in time is retried once (a cold start), with the same call_id.
    h = make_harness()
    monkeypatch.setattr(config, "BUDGET_RESERVE_TIMEOUT_S", 0.2)
    real = h.client.ledger.reserve
    calls: list[str] = []

    def reserve(call_id: str, *args: Any) -> None:
        calls.append(call_id)
        if len(calls) == 1:
            time.sleep(0.5)  # the cold start: the first attempt lands late
        real(call_id, *args)

    monkeypatch.setattr(h.client.ledger, "reserve", reserve)
    mock_api.post("/thing").mock(return_value=httpx.Response(200, json={"ok": "yes"}))
    spec = CallSpec(stage="s", model="muse-spark-1.3", estimate_usd=0.01, estimate_units={},
                    policy=RetryPolicy(attempts=1), timeout=httpx.Timeout(5.0), total_timeout_s=10.0)  # fmt: skip
    await h.client.request("POST", "thing", spec, meter=lambda _: ({}, 0.002))
    assert len(calls) == 2
    assert calls[0] == calls[1]  # one call_id: the late first attempt never doubles it
    await asyncio.sleep(0.5)  # let the stalled first attempt land
    [line] = h.costs()
    assert cast(LocalLedger, h.client.ledger).spent("job:j_test") == pytest.approx(line.usd)


async def test_an_explicitly_refused_response_delete_stays_pending(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    log = sam.ResponseLog(tmp_path)
    for response_id in ("resp_1", "resp_2"):
        log.note(response_id)
    mock_api.delete("/responses/resp_1").mock(return_value=httpx.Response(200, json={"deleted": False}))
    mock_api.delete("/responses/resp_2").mock(return_value=httpx.Response(200, json={"id": "resp_2"}))
    assert await log.delete_pending(h.client) == 1  # the body is unspecified; only an explicit refusal counts
    assert log.index().pending == ["resp_1"]


# --- audit #31 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "item",
    [
        {"id": "file-777", "filename": "j_test-a.mp4", "bytes": 300, "created_at": "2026-10-28T00:00:00Z"},
        {"id": "file-777", "filename": "j_test-a.mp4", "bytes": "300", "created_at": 9e12},
    ],
)
async def test_an_unreadable_field_never_hides_our_copy(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path, item: dict[str, Any]
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": [item]}))
    gone = mock_api.delete("/files/file-777").mock(return_value=httpx.Response(200, json={"deleted": True}))
    await store.delete_all()
    assert gone.call_count == 1  # matched by its job-unique name, then deleted


async def test_a_copy_with_an_unusable_id_keeps_the_orphan_open(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    listing = {"data": [{"id": "../x", "filename": "j_test-a.mp4", "bytes": 300, "created_at": 9e12}]}
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    with pytest.raises(MetaConfigError, match="unusable id"):
        await store.delete_all()
    assert not store.index().all_deleted


def test_the_open_weight_summary_counts_the_kept_entries(tmp_path: Path) -> None:
    # The model boxed our own frame label in the bar; WP4 drops it (PRE-A §5) and writes a `none` entry.
    label = ow.RedteamFinding(kind="text", detail="label", text="F 000030", box=(0, 0, 100, 20), confidence="high")
    opinion = ow.SecondOpinion(model="m", frames=[ow.RedteamFrame(frame=10, findings=[label])], failed_batches=0,
                               errors=[])  # fmt: skip
    kept = [c.RedteamNone(frame=10, finding="none")]
    assert opinion.summary().findings == 1  # the raw answer
    summary = opinion.summary(kept)
    assert (summary.frames, summary.findings) == (1, 0)
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    entries = [e.model_dump(mode="json") for e in kept]
    c.Audit.model_validate(audit | {"open_weight": summary.model_dump(mode="json"), "redteam_open": entries})


async def test_the_receipt_count_is_only_what_responses_json_records(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = make_harness()
    log = sam.ResponseLog(tmp_path)
    log.note("resp_1")
    mock_api.delete("/responses/resp_1").mock(return_value=httpx.Response(200, json={"deleted": True}))
    monkeypatch.setattr(sam, "dump", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    assert await log.delete_pending(h.client) == 1  # the request was made
    assert (log.requested(), log.unrecorded()) == (0, 1)  # but responses.json can't show it


async def test_a_video_body_needs_its_length_for_the_fallback_estimate(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    content = [{"type": "input_text", "text": "hi"}, {"type": "input_video", "file_id": "file-1"}]
    body = {"model": "muse-spark-1.3", "max_output_tokens": 50, "store": False,
            "input": [{"role": "user", "content": content}]}  # fmt: skip
    with pytest.raises(ValueError, match="needs video_seconds"):
        await responses.create(h.client, body, stage="s", effort="omit")


# --- audit #30 ----------------------------------------------------------------------------------------------


async def test_a_listing_item_of_another_shape_keeps_the_orphan_open(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    item = {"id": "file-777", "name": "j_test-a.mp4", "size": 300, "created_at": "2026-10-27T10:00:00Z"}
    other = {"id": 5, "filename": None}  # another job's unreadable item is skipped
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": [other, item], "has_more": False}))
    with pytest.raises(MetaConfigError, match="can't"):
        await store.delete_all()
    assert not store.index().all_deleted


async def test_probe_d_saves_an_empty_body_before_parsing(api: respx.MockRouter, tmp_path: Path) -> None:  # noqa: F811 -- pytest injects the imported fixture by name
    api.post(f"{BASE}/asr/transcribe").mock(return_value=httpx.Response(200, json=[1, 2]))
    results = await probes.run(
        ["d"], settings=Settings(model_api_key=SecretStr("k")), out_root=tmp_path, ledger=LocalLedger()
    )
    assert results["d"]["error"].startswith("MetaIncomplete")
    assert json.loads((tmp_path / "d" / "asr.response.json").read_text()) == [1, 2]  # kept, as sent


async def test_r4_a_sam_sweep_that_times_out_twice_keeps_both_charges(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings, tmp_path: Path
) -> None:
    # PRE-A §11 R4: 2 attempts, then MetaUnavailable; both were accepted, so both stay estimated charges.
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    route = mock_api.post("/responses").mock(side_effect=httpx.ReadTimeout("slow"))
    body = sam.video_body(cfg, file_id="file-1", text="face")
    with pytest.raises(MetaUnavailable):
        await sam.segment_video(h.client, body, sam_frames=60, responses=sam.ResponseLog(tmp_path))
    assert route.call_count == 2
    lines = [line for line in h.costs() if line.usd > 0]
    assert len(lines) == 2
    assert all(line.estimated for line in lines)


# --- audit #32 ----------------------------------------------------------------------------------------------


async def test_an_unrelated_unreadable_item_never_blocks_cleanup(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    other = {"id": "file-9", "filename": "j_other-a.mp4", "bytes": 1, "created_at": 9e12}
    listing = {"data": [other, {"id": "file-5", "filename": None}, {"name": "other-job.mp4"}], "has_more": False}
    mock_api.get("/files").mock(return_value=httpx.Response(200, json=listing))
    assert await store.delete_all()  # nothing of ours is listed, so the orphan is resolved


@pytest.mark.parametrize("url", ["https://api.meta.ai/v1\n", "https://api.meta.ai/v1 ", "https://api.meta.ai/\tv1"])
def test_a_base_url_with_whitespace_is_refused_at_load(url: str) -> None:
    with pytest.raises(ConfigError, match="whitespace or control"):
        load_settings({"SAFECUT_META_BASE_URL": url})


# --- audit #33 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (["file-777", "file-778"], "no item with a filename"),
        ([{"id": "file-777", "file": {"filename": "j_test-a.mp4"}}], "no item with a filename"),
        ([{"id": "file-1", "filename": "other.mp4"}, {"id": "file-777", "file": {"name": "j_test-a.mp4"}}],
         "can't rule out as our copy"),
        ([{"id": "file-1", "filename": "other.mp4"}, "file-777"], "can't rule out as our copy"),
    ],
)  # fmt: skip
async def test_a_listing_that_hides_our_name_keeps_the_orphan_open(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, tmp_path: Path, data: list[Any], message: str
) -> None:
    h = make_harness()
    store = _orphan_store(h, tmp_path)
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": data, "has_more": False}))
    with pytest.raises(MetaConfigError, match=message):
        await store.delete_all()
    assert not store.index().all_deleted


async def test_a_baseten_client_never_defaults_to_the_meta_key(tmp_path: Path) -> None:
    cfg = Settings(model_api_key=SecretStr("meta-key"), baseten_api_key=SecretStr("baseten-key"))
    client = MetaClient(cfg, job_id="j", caller=Caller.local(), ledger=LocalLedger(), cost_path=tmp_path / "c.jsonl",
                        provider="baseten")  # fmt: skip
    assert client.base_url == "https://inference.baseten.co/v1"
    assert client._key == "baseten-key"  # pyright: ignore[reportPrivateUsage] -- the key it would send
    await client.aclose()
    without = Settings(model_api_key=SecretStr("meta-key"))
    with pytest.raises(ConfigError):
        MetaClient(without, job_id="j", caller=Caller.local(), ledger=LocalLedger(), cost_path=tmp_path / "c.jsonl",
                   provider="baseten")  # fmt: skip


# --- audit #34 ----------------------------------------------------------------------------------------------


def _restyle(job_dir: Path, item_id: str, style: str) -> None:
    grid = [91, 288, 16] if style == "pixelate" else None

    def plan(d: Any) -> None:
        for entries in d["frames"].values():
            for entry in entries:
                if entry["item_id"] == item_id:
                    entry.update({"style": style, "grid": grid})

    _edit(job_dir, "plan.json", plan)


def test_a_flagged_leak_needs_its_through_item_rendered_solid(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "pixelate"}))  # fmt: skip
    _restyle(job_dir, "i_2", "pixelate")  # i_2 (face:2) as a mosaic, frames 5-9
    assert "plan.json" in c.validate_job_dir(job_dir)
    leak = {"frame": 9, "box": [110, 300, 170, 380], "kind": "text", "detector": "redteam", "patched_item": "i_2",
            "flag": "redaction_too_weak", "through_item": "i_2"}  # fmt: skip
    _edit(job_dir, "audit.json", lambda d: d["leaks"].append(leak))
    with pytest.raises(c.ContractError, match=r"i_2 renders pixelate, but its decision says solid"):
        c.validate_job_dir(job_dir)  # the guard must upgrade it on the re-plan
    _restyle(job_dir, "i_2", "solid")
    assert "audit.json" in c.validate_job_dir(job_dir)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"style": "pixelate"}, "solid and decided by policy"),
        ({"decided_by": "creator"}, "solid and decided by policy"),
        ({"evidence_frames": []}, "one evidence frame inside first..last"),
        ({"evidence_frames": [10], "first": 11}, "one evidence frame inside first..last"),
    ],
)
def test_an_audit_patch_follows_its_spec_row(change: dict[str, Any], message: str) -> None:
    items = json.loads((EXAMPLE / "decisions.json").read_text())["items"]
    patch = next(i for i in items if i["item_id"] == "p_1")
    with pytest.raises(ValueError, match=message):
        c.DecisionItem.model_validate(patch | change)


def test_a_publishable_audit_has_its_red_team_frames(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d.update({"redteam": [], "leaks": []}))
    with pytest.raises(c.ContractError, match=r"no red-team entry in seconds \[0\]"):
        c.validate_job_dir(job_dir)


async def test_a_body_json_cant_carry_is_refused_before_any_charge(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={}))
    for body in ({"x": float("nan")}, {"x": {1, 2}}, {"x": "\udcff"}):
        with pytest.raises(MetaBadRequest, match="can't be sent as JSON"):
            await h.client.request("POST", "thing", _free_spec(), meter=lambda _: ({}, 0.0), json_body=body)
    assert route.call_count == 0
    assert h.costs() == []


# --- audit #36 ----------------------------------------------------------------------------------------------


def test_the_red_team_step_is_the_jobs_fps(tmp_path: Path) -> None:
    # A writer declaring sample_step 900 would otherwise shrink the 1 fps floor to one frame.
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d.update({"sample_step": 900}))
    with pytest.raises(c.ContractError, match="sample_step 900 != the job's 30 fps"):
        c.validate_job_dir(job_dir)


def test_probe_f_compares_the_named_pair() -> None:
    assert (config.COMPARE_SPARK_MODEL, config.COMPARE_WONDER_MODEL) == ("muse-spark-1.3", "muse-wonder-1.0")
    source = Path(probes.__file__).read_text()
    assert '"muse-spark-1.3"' not in source
    assert '"muse-wonder-1.0"' not in source


# --- audit #37 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("item", "style"), [("p_1", "pixelate"), ("i_3", "person_solid")])
def test_a_plan_entry_renders_its_decisions_style(tmp_path: Path, item: str, style: str) -> None:
    job_dir = _example(tmp_path)
    _restyle(job_dir, item, style)
    with pytest.raises(c.ContractError, match=f"{item} renders {style}, but its decision says solid"):
        c.validate_job_dir(job_dir)


def test_an_audit_patch_entry_is_marked_as_one(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def unmark(d: Any) -> None:
        for entries in d["frames"].values():
            for entry in entries:
                if entry["item_id"] == "p_1":
                    entry["source"] = "decision"

    _edit(job_dir, "plan.json", unmark)
    with pytest.raises(c.ContractError, match="p_1 source decision != its origin"):
        c.validate_job_dir(job_dir)


@pytest.mark.parametrize("kind", ["plate", "screen", "document"])
def test_text_screens_plates_and_documents_are_never_pixelated(kind: str) -> None:
    items = json.loads((EXAMPLE / "decisions.json").read_text())["items"]
    screen = next(i for i in items if i["item_id"] == "i_3")
    with pytest.raises(ValueError, match=f"a {kind} item is always solid"):
        c.DecisionItem.model_validate(screen | {"kind": kind, "style": "pixelate"})


def test_an_unresolved_flagged_leaks_item_may_still_be_soft(tmp_path: Path) -> None:
    # Found by the last pass, after the last re-plan: the job is blocked, and the plan isn't rebuilt yet.
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "pixelate"}))  # fmt: skip
    _restyle(job_dir, "i_2", "pixelate")
    leak = {"frame": 9, "box": [110, 300, 170, 380], "kind": "text", "detector": "redteam", "patched_item": None,
            "unresolved": True, "flag": "redaction_too_weak", "through_item": "i_2"}  # fmt: skip

    def block(d: Any) -> None:
        d["leaks"].append(leak)
        d.update({"unresolved": 1, "blocked_reason": "unresolved_leaks"})

    _edit(job_dir, "audit.json", block)
    assert "audit.json" in c.validate_job_dir(job_dir)


# --- audit #38 ----------------------------------------------------------------------------------------------


def test_an_item_over_a_child_phrase_track_is_a_child(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:1").update(
        {"child_phrase": True}))  # fmt: skip
    with pytest.raises(c.ContractError, match="face:1 is a child_phrase track, so the item is kind child"):
        c.validate_job_dir(job_dir)


@pytest.mark.parametrize(("role", "votes"), [("child", ["child", "child", "child"]),
                                            ("unsure", ["participant", "child", "participant"])])  # fmt: skip
def test_a_track_with_a_child_vote_or_ruling_is_a_child(tmp_path: Path, role: str, votes: list[str]) -> None:
    # escalation.md rule 1: any child vote makes the track a child (locked, hidden), never kept.
    job_dir = _example(tmp_path)
    _edit(job_dir, "roles.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:1").update(
        {"role": role, "votes": votes, "matches_participant": None}))  # fmt: skip
    with pytest.raises(c.ContractError, match="face:1 has a child vote or ruling, so the item is kind child"):
        c.validate_job_dir(job_dir)


# --- audit #40 ----------------------------------------------------------------------------------------------


def test_a_mask_must_cover_the_whole_frame() -> None:
    assert c.rle_runs(rle_string([5, 3, 92])) == [5, 3, 92]
    assert c.Rle(size=(10, 10), counts=rle_string([5, 3, 92]))
    with pytest.raises(ValueError, match="cover 100 pixels, not the 720x1280 frame"):
        c.Rle(size=(720, 1280), counts=rle_string([5, 3, 92]))  # a box-sized mask labelled frame-sized
    with pytest.raises(ValueError, match="aren't COCO compressed RLE"):
        c.Rle(size=(10, 10), counts="~~~notrle")


def test_only_people_are_pixelated() -> None:
    items = json.loads((EXAMPLE / "decisions.json").read_text())["items"]
    envelope = next(i for i in items if i["item_id"] == "i_4")
    with pytest.raises(ValueError, match="a other item is always solid"):
        c.DecisionItem.model_validate(envelope | {"style": "pixelate"})


def test_load_infers_the_job_file_model() -> None:
    assert isinstance(c.load(EXAMPLE / "tracks.json"), c.Tracks)
    with pytest.raises(c.ContractError, match="not a job file"):
        c.load(EXAMPLE.parent / "README.md")


# --- audit #39 ----------------------------------------------------------------------------------------------


def _entries(job_dir: Path, item_id: str, change: dict[str, Any]) -> None:
    def edit(d: Any) -> None:
        for entries in d["frames"].values():
            for entry in entries:
                if entry["item_id"] == item_id:
                    entry.update(change)

    _edit(job_dir, "plan.json", edit)


def test_a_plan_entry_must_cover_its_track(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _entries(job_dir, "i_2", {"box": [0, 0, 2, 2]})
    with pytest.raises(c.ContractError, match=r"i_2 doesn't cover (face:2's|its held) box \[100, 300, 160, 380\]"):
        c.validate_job_dir(job_dir)


def test_a_pixelate_grid_keeps_a_face_within_six_blocks(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "pixelate"}))  # fmt: skip
    _entries(job_dir, "i_2", {"style": "pixelate", "grid": [83, 280, 1]})
    with pytest.raises(c.ContractError, match="1 px grid leaves face:2 more than 6 blocks across"):
        c.validate_job_dir(job_dir)
    _entries(job_dir, "i_2", {"grid": [83, 280, 12]})  # 60 px wide face / 12 px cells = 5 blocks
    assert "plan.json" in c.validate_job_dir(job_dir)


def test_every_crowded_frame_has_a_crowd_fill(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: d.update({"crowded_frames": [3, 4, 5]}))
    with pytest.raises(c.ContractError, match=r"crowded frames \[3, 4, 5\] have no crowd fill"):
        c.validate_job_dir(job_dir)
    _edit(job_dir, "plan.json", lambda d: d.update({"crowd_fills": [{"frames": [3, 4, 5], "box": [0, 0, 1280, 720]}]}))
    assert "plan.json" in c.validate_job_dir(job_dir)


def test_the_backfill_is_the_hotstart_in_prepared_frames(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "plan.json", lambda d: d["temporal"].update({"backfill": 15}))
    with pytest.raises(c.ContractError, match=r"backfill 15 != ceil\(15 x fps / sam_fps\) = 57"):
        c.validate_job_dir(job_dir)


def test_every_track_is_in_an_item(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: d.update({"items": [i for i in d["items"] if i["item_id"] != "i_3"]}))
    _edit(job_dir, "plan.json", lambda d: d.update(
        {"frames": {f: [e for e in es if e["item_id"] != "i_3"] for f, es in d["frames"].items()}}))  # fmt: skip
    with pytest.raises(c.ContractError, match="track screen:1 is in no item"):
        c.validate_job_dir(job_dir)


def test_only_a_unanimous_participant_is_kept_without_the_creator(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    doubt = {"role": "unsure", "votes": ["participant", "bystander", "participant"], "matches_participant": None}
    _edit(job_dir, "roles.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:1").update(doubt))
    with pytest.raises(c.ContractError, match="kept by model, but face:1 isn't a unanimous participant"):
        c.validate_job_dir(job_dir)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_1").update(
        {"decided_by": "creator"}))  # fmt: skip
    assert "decisions.json" in c.validate_job_dir(job_dir)


@pytest.mark.parametrize("file_id", ["file-123457", "file-999"])
def test_sam_is_sent_the_proxy(tmp_path: Path, file_id: str) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: d["requests"][0].update({"file_id": file_id}))
    with pytest.raises(c.ContractError, match=f"{file_id} isn't sam_proxy.mp4 in files.json"):
        c.validate_job_dir(job_dir)


def test_a_reentry_follows_a_track_that_ended(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:2").update(
        {"reentry_of": "face:1"}))  # fmt: skip  # face:1 is still on screen at frame 5
    with pytest.raises(c.ContractError, match="reentry_of face:1 must be a track that ended before it starts"):
        c.validate_job_dir(job_dir)


def test_a_red_team_hit_needs_its_own_red_team_leak() -> None:
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    egoblur_only = [leak for leak in audit["leaks"] if leak["detector"] != "redteam"]
    with pytest.raises(ValueError, match="neither excluded nor a leak on its box"):
        c.Audit.model_validate(audit | {"leaks": egoblur_only})


# --- audits #41 and #42 -------------------------------------------------------------------------------------


def _pixelate_person(job_dir: Path) -> None:
    """i_2 (face:2) pixelated, plus a person:2 track 3x wider in the same item, each with its own entry and grid."""

    def tracks(d: Any) -> None:
        d["tracks"].append({"track_id": "person:2", "concept": "person", "first": 5, "last": 9,
                            "boxes": {"5": [40, 280, 220, 700], "9": [50, 280, 230, 700]}, "source": None,
                            "prompt": "person", "origin": "static"})  # fmt: skip

    _edit(job_dir, "tracks.json", tracks)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "pixelate", "track_ids": ["face:2", "person:2"]}))  # fmt: skip

    def plan(d: Any) -> None:
        for entries in d["frames"].values():
            for e in [e for e in entries if e["item_id"] == "i_2"]:
                e.update({"style": "pixelate", "grid": [83, 280, 12]})
                entries.append(e | {"box": [0, 240, 300, 720], "grid": [0, 240, 40]})

    _edit(job_dir, "plan.json", plan)


def test_a_face_and_person_item_may_pixelate_each_track_with_its_own_grid(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _pixelate_person(job_dir)
    assert "plan.json" in c.validate_job_dir(job_dir)  # the person's 40 px grid is never held to the face's rule


def test_a_grid_that_moves_between_frames_is_refused(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _pixelate_person(job_dir)

    def shift(d: Any) -> None:
        for frame, entries in d["frames"].items():
            for e in entries:
                if e["item_id"] == "i_2" and e["grid"] == [83, 280, 12]:
                    e["grid"] = [83 + int(frame), 280, 12]

    _edit(job_dir, "plan.json", shift)
    with pytest.raises(c.ContractError, match="i_2's pixelate grid moves between frames"):
        c.validate_job_dir(job_dir)


def test_an_empty_mask_entry_hides_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "person_solid"}))  # fmt: skip
    empty = {"size": [720, 1280], "counts": rle_string([720 * 1280])}
    _entries(job_dir, "i_2", {"style": "person_solid", "shape": "mask", "mask": empty, "box": [0, 0, 1280, 720]})
    with pytest.raises(c.ContractError, match=r"i_2 doesn't cover (face:2's|its held) box"):
        c.validate_job_dir(job_dir)
    # Foreground over face:2 (columns 100-169, rows 280-399): one run per column.
    runs: list[int] = []
    for col in range(1280):
        runs += [280, 120, 320] if 83 <= col < 180 else [720, 0, 0]
    full = {"size": [720, 1280], "counts": rle_string(runs)}
    _entries(job_dir, "i_2", {"mask": full})
    assert "plan.json" in c.validate_job_dir(job_dir)


def test_a_never_judged_track_or_a_screen_is_never_kept_without_the_creator(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_3").update(
        {"decision": "keep", "style": None, "decided_by": "policy"}))  # fmt: skip
    _edit(job_dir, "plan.json", lambda d: d.update(
        {"frames": {f: [e for e in es if e["item_id"] != "i_3"] for f, es in d["frames"].items()}}))  # fmt: skip
    with pytest.raises(c.ContractError, match="a screen item is never kept without the creator"):
        c.validate_job_dir(job_dir)


def test_matches_participant_only_on_a_unanimous_participant() -> None:
    roles = json.loads((EXAMPLE / "roles.json").read_text())
    face_2 = next(t for t in roles["tracks"] if t["track_id"] == "face:2")
    with pytest.raises(ValueError, match="matches_participant is only for a unanimous participant"):
        c.RoleTrack.model_validate(face_2 | {"matches_participant": 0})


async def test_a_replay_refusal_leaves_no_orphan(
    make_harness: Callable[..., Harness], settings: Settings, tmp_path: Path
) -> None:
    h = make_harness(cfg=settings.model_copy(update={"replay": True}))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 300)
    store = FileStore(h.client, tmp_path / "job")
    with pytest.raises(ReplayRefused):
        await store.upload(clip, "sam_proxy.mp4")
    assert store.index().root == []  # nothing was sent, so there's nothing to reconcile


# --- audits #43 and #44 -------------------------------------------------------------------------------------


def test_a_one_pixel_mask_hides_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "person_solid"}))  # fmt: skip
    runs = [130 * 720 + 340, 1, 720 * 1280 - 130 * 720 - 341]  # one pixel at the centre of face:2
    dot = {"size": [720, 1280], "counts": rle_string(runs)}
    _entries(job_dir, "i_2", {"style": "person_solid", "shape": "mask", "mask": dot, "box": [0, 0, 1280, 720]})
    with pytest.raises(c.ContractError, match=r"i_2 doesn't cover (face:2's|its held) box"):
        c.validate_job_dir(job_dir)


def test_the_guards_temporal_padding_is_planned(tmp_path: Path) -> None:
    # face:2 spans 5-9; with back-fill 57 and extend 8 the guard plans it on the whole 12-frame clip.
    job_dir = _example(tmp_path)

    def trim(d: Any) -> None:
        for f, entries in d["frames"].items():
            entries[:] = [e for e in entries if not (e["item_id"] == "i_2" and int(f) < 5)]

    _edit(job_dir, "plan.json", trim)
    with pytest.raises(c.ContractError, match=r"hidden item i_2 has no entry on frames \[0, 1, 2, 3, 4\]"):
        c.validate_job_dir(job_dir)


def test_an_entry_without_the_pixel_padding_is_refused(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["5"] if e["item_id"] == "i_2").update(
        {"box": [100, 300, 160, 380]}))  # fmt: skip  # exactly face:2's box, no padding
    with pytest.raises(c.ContractError, match=r"i_2 doesn't cover (face:2's|its held) box"):
        c.validate_job_dir(job_dir)


def test_a_crowd_fill_covers_a_crowded_frame(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: d.update({"crowded_frames": [6, 7]}))

    def fill_only(d: Any) -> None:
        d["crowd_fills"] = [{"frames": [6, 7], "box": [0, 0, 1280, 720]}]
        for f in ("6", "7"):
            d["frames"][f] = [e for e in d["frames"][f] if e["item_id"] != "i_2"]

    _edit(job_dir, "plan.json", fill_only)
    assert "plan.json" in c.validate_job_dir(job_dir)


def test_a_person_only_item_is_never_pixelated(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def person(d: Any) -> None:
        track = next(t for t in d["tracks"] if t["track_id"] == "face:2")
        track.update({"track_id": "person:9", "concept": "person"})

    _edit(job_dir, "tracks.json", person)
    _edit(job_dir, "roles.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:2").update(
        {"track_id": "person:9"}))  # fmt: skip
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_2").update(
        {"style": "pixelate", "track_ids": ["person:9"]}))  # fmt: skip
    _entries(job_dir, "i_2", {"style": "pixelate", "grid": [83, 280, 40]})
    with pytest.raises(c.ContractError, match="i_2: a pixelated item needs a face track"):
        c.validate_job_dir(job_dir)


@pytest.mark.parametrize(
    ("env", "message"),
    [({"SAFECUT_REPLAY": "1", "MODEL_API_KEY": "k"}, "SAFECUT_REPLAY is on"), ({}, "need MODEL_API_KEY")],
)
def test_the_probes_refuse_to_start_without_keys_or_in_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], env: dict[str, str],
    message: str,
) -> None:  # fmt: skip
    root = tmp_path / "repo"
    (root / "fixtures" / "probes").mkdir(parents=True)
    monkeypatch.setattr(probes, "ROOT", root)
    monkeypatch.setattr(probes, "load_settings", lambda: load_settings(env))
    assert probes.main(["a"]) == 2
    assert message in capsys.readouterr().err


def test_a_failed_rerun_keeps_the_recorded_summary(tmp_path: Path) -> None:
    out = tmp_path / "a"
    probes.save_summary(out, {"model_ids": ["sam-3.1"]})
    failed = probes.save_summary(out, {"error": "MetaUnavailable: down"})
    assert json.loads((out / "summary.json").read_text()) == {"model_ids": ["sam-3.1"]}
    assert failed.name.startswith("summary.failed-")


async def test_replay_mode_needs_no_key_and_refuses_the_call(tmp_path: Path) -> None:
    client = MetaClient(load_settings({"SAFECUT_REPLAY": "1"}), job_id="j", caller=Caller.local(),
                        ledger=LocalLedger(), cost_path=tmp_path / "c.jsonl")  # fmt: skip
    with pytest.raises(ReplayRefused):
        await client.request("POST", "thing", _free_spec(), meter=lambda _: ({}, 0.0))
    await client.aclose()


# --- audit #46 ----------------------------------------------------------------------------------------------


async def test_the_baseten_client_needs_no_key_in_replay(tmp_path: Path) -> None:
    cfg = load_settings({"SAFECUT_REPLAY": "1", "SAFECUT_OPEN_WEIGHT_PRICE": '{"in": 1.25, "out": 4.25}'})
    client = ow.open_weight_client(cfg, job_id="j", caller=Caller.local(), ledger=LocalLedger(),
                                   cost_path=tmp_path / "c.jsonl")  # fmt: skip
    with pytest.raises(ReplayRefused):
        await client.request("POST", "thing", _free_spec(), meter=lambda _: ({}, 0.0))
    await client.aclose()


@pytest.mark.parametrize("url", ["https://api.meta.ai/v1?", "https://api.meta.ai/v1#"])
def test_a_base_url_with_an_empty_query_or_fragment_is_refused(url: str) -> None:
    with pytest.raises(ConfigError, match="base URLs must be"):
        load_settings({"SAFECUT_META_BASE_URL": url})


# --- audit #45 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "field"),
    [({"padding": {"face": 0, "default": 0, "px": 0}}, "padding"), ({"temporal": {"extend": 0, "backfill": 57,
                                                                                  "gap_hold_s": 2.0}}, "extend")],
)  # fmt: skip
def test_the_guards_padding_is_at_least_designs(tmp_path: Path, change: dict[str, Any], field: str) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "plan.json", lambda d: d.update(change))
    with pytest.raises(c.ContractError, match=field):
        c.validate_job_dir(job_dir)


def test_a_backfill_frame_must_cover_the_held_box(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # face:2 starts at 5: frames 0-4 are back-fill holding its first box
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["2"] if e["item_id"] == "i_2").update(
        {"box": [0, 0, 2, 2]}))  # fmt: skip
    with pytest.raises(c.ContractError, match=r"frame 2: i_2 doesn't cover its held box \[100, 300, 160, 380\]"):
        c.validate_job_dir(job_dir)


def test_every_audit_patch_frame_covers_its_box(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["3"] if e["item_id"] == "p_1").update(
        {"box": [0, 0, 2, 2]}))  # fmt: skip
    with pytest.raises(c.ContractError, match=r"frame 3: p_1 doesn't cover its held box \[200, 200, 260, 280\]"):
        c.validate_job_dir(job_dir)


def test_a_crowd_fill_covers_a_capped_concept(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def crowd(d: Any) -> None:
        d["crowded_frames"] = [3]
        for n in range(16):
            d["tracks"].append({"track_id": f"face:{50 + n}", "concept": "face", "first": 3, "last": 3,
                                "boxes": {"3": [40 * n, 600, 40 * n + 30, 640]}, "source": None, "prompt": "face",
                                "origin": "static"})  # fmt: skip

    _edit(job_dir, "tracks.json", crowd)

    def items(d: Any) -> None:
        crowd_item = {"item_id": "i_9", "track_ids": [f"face:{50 + n}" for n in range(16)], "kind": "person",
                      "decision": "hide", "reason": "crowd", "evidence_frames": [3], "style": "solid",
                      "decided_by": "policy", "locked": False}  # fmt: skip
        d["items"].append(crowd_item)

    _edit(job_dir, "decisions.json", items)

    def plan(d: Any) -> None:
        entry = {"item_id": "i_9", "shape": "box", "box": [0, 560, 1280, 720], "mask": None, "style": "solid",
                 "grid": None, "source": "decision"}  # fmt: skip
        for f in range(12):
            d["frames"].setdefault(str(f), []).append(entry)
        d["crowd_fills"] = [{"frames": [3], "box": [0, 0, 2, 2]}]

    _edit(job_dir, "plan.json", plan)
    with pytest.raises(c.ContractError, match="frame 3: no crowd fill covers 16 of the 16 face objects"):
        c.validate_job_dir(job_dir)


# --- audit #47 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"votes": ["participant"] * 2}, "tracks.0.votes"),  # role-pass step 7 always writes three
        ({"frames": [1]}, "kept by model, but face:1 isn't a unanimous participant"),
        ({"failed_votes": 1}, "kept by model, but face:1 isn't a unanimous participant"),
    ],
)
def test_a_policy_keep_needs_three_votes_on_two_keyframes(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "roles.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:1").update(change))
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_an_in_band_failure_never_replaces_a_recorded_summary(tmp_path: Path) -> None:
    out = tmp_path / "e"
    probes.save_summary(out, {"model": "m", "answer": "x", "usd": 0.01})
    failed = probes.save_summary(out, {"model": "m", "effort": "low", "error": "MetaBadRequest: 400"})
    assert json.loads((out / "summary.json").read_text())["answer"] == "x"
    assert failed.name.startswith("summary.failed-")


def test_a_huge_extend_never_hangs_validation(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "plan.json", lambda d: d["temporal"].update({"extend": 10**9}))
    started = time.monotonic()
    c.validate_job_dir(job_dir)  # more padding than the clip is valid; the loops stay within the clip
    assert time.monotonic() - started < 5


# --- audit #48 ----------------------------------------------------------------------------------------------


def test_a_crowd_fill_must_cover_every_track_of_the_item(tmp_path: Path) -> None:
    # i_2 gains a wide person:2 track; on crowded frame 7 its entries are dropped and the fill covers only the face.
    job_dir = _example(tmp_path)
    _pixelate_person(job_dir)
    _edit(job_dir, "tracks.json", lambda d: d.update({"crowded_frames": [7]}))

    def fill(d: Any) -> None:
        d["frames"]["7"] = [e for e in d["frames"]["7"] if e["item_id"] != "i_2"]
        d["crowd_fills"] = [{"frames": [7], "box": [60, 260, 200, 420]}]

    _edit(job_dir, "plan.json", fill)
    with pytest.raises(c.ContractError, match=r"hidden item i_2 has no entry on frames \[7\]"):
        c.validate_job_dir(job_dir)


def test_split_crowd_fills_may_cover_a_capped_concept(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)

    def crowd(d: Any) -> None:
        d["crowded_frames"] = [3]
        for n in range(16):
            x = 40 * n + (400 if n >= 8 else 0)
            d["tracks"].append({"track_id": f"face:{50 + n}", "concept": "face", "first": 3, "last": 3,
                                "boxes": {"3": [x, 600, x + 30, 640]}, "source": None, "prompt": "face",
                                "origin": "static"})  # fmt: skip

    _edit(job_dir, "tracks.json", crowd)
    item = {"item_id": "i_9", "track_ids": [f"face:{50 + n}" for n in range(16)], "kind": "person",
            "decision": "hide", "reason": "crowd", "evidence_frames": [3], "style": "solid", "decided_by": "policy",
            "locked": False}  # fmt: skip
    _edit(job_dir, "decisions.json", lambda d: d["items"].append(item))
    every = list(range(12))
    tiles = [{"frames": every, "box": [0, 590, 330, 650]}, {"frames": every, "box": [710, 590, 1040, 650]}]
    _edit(job_dir, "plan.json", lambda d: d.update({"crowd_fills": tiles}))
    assert "plan.json" in c.validate_job_dir(job_dir)  # two tiles, each over one cluster


def test_the_receipt_names_the_models_that_ran(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    raw = json.loads((job_dir / "receipt.json").read_text())
    raw.pop("hash")

    def seal(change: Callable[[Any], None]) -> None:
        body = json.loads(json.dumps(raw))
        change(body)
        sealed = c.Receipt.seal(c.ReceiptBody.model_validate(body))
        (job_dir / "receipt.json").write_text(json.dumps(sealed.model_dump(mode="json")))

    seal(lambda b: b["audit"].update({"auditor": "egoblur-gen2-FAKE"}))
    with pytest.raises(c.ContractError, match=r"auditor 'egoblur-gen2-FAKE' != audit\.json 'egoblur-gen2'"):
        c.validate_job_dir(job_dir)
    seal(lambda b: b["models"].update({"scene": "gpt-x"}))
    with pytest.raises(c.ContractError, match=r"models\.scene 'gpt-x' != the job's 'muse-spark-1\.3'"):
        c.validate_job_dir(job_dir)


# --- audit #49 ----------------------------------------------------------------------------------------------


def test_a_frame_between_anchors_must_be_near_the_track(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # screen:1 has boxes on frames 1 and 5 only
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["2"] if e["item_id"] == "i_3").update(
        {"box": [0, 0, 2, 2]}))  # fmt: skip
    with pytest.raises(c.ContractError, match="frame 2: i_3 is nowhere near screen:1"):
        c.validate_job_dir(job_dir)


def test_a_runaway_mask_varint_is_refused_fast() -> None:
    started = time.monotonic()
    with pytest.raises(ValueError, match="aren't COCO compressed RLE"):
        c.Rle(size=(720, 1280), counts="o" * 300_000)  # every char sets the continuation bit
    assert time.monotonic() - started < 2


async def test_a_deeply_nested_error_body_is_a_typed_error(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    body = b'{"error":' * 1000 + b'"x"' + b"}" * 1000
    mock_api.post("/thing").mock(return_value=httpx.Response(400, content=body))
    with pytest.raises(MetaBadRequest):
        await h.client.request("POST", "thing", _free_spec(), meter=lambda _: ({}, 0.0))


def test_a_deeply_nested_listing_item_never_overflows() -> None:
    nested: Any = "j_test-a.mp4"
    for _ in range(5000):
        nested = {"x": nested}
    assert "j_test-a.mp4" in files_mod._strings(nested)  # pyright: ignore[reportPrivateUsage]


def test_deeply_nested_env_json_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="not usable JSON"):
        load_settings({"SAFECUT_ACCESS_CODES": "[" * 100_000})


def test_a_detector_that_never_ran_scanned_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d["egoblur"].update({"faces": None, "plates": None}))
    with pytest.raises(c.ContractError, match=r"egoblur\.faces is null"):
        c.validate_job_dir(job_dir)


# --- audit #50 ----------------------------------------------------------------------------------------------


def test_the_red_team_samples_every_second(tmp_path: Path) -> None:
    # 1800 frames at 30 fps: 60 entries on frames 0-59 count 60 but leave seconds 2-59 unsampled.
    job_dir = _example(tmp_path)
    _edit(job_dir, "job.json", lambda d: d.update({"frames": 1800, "times": [i / 30 for i in range(1800)]}))
    _edit(job_dir, "audit.json", lambda d: d.update(
        {"frames_scanned": 1800, "redteam": [{"frame": f, "finding": "none"} for f in range(60)]}))  # fmt: skip
    audit = c.load(job_dir / "audit.json", c.Audit)
    job = c.load(job_dir / "job.json", c.Job)
    with pytest.raises(c.ContractError, match=r"no red-team entry in seconds \[2, 3, 4, 5, 6\]"):
        c._check_audit(audit, job)  # pyright: ignore[reportPrivateUsage]


def test_yunet_reports_no_plates() -> None:
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    with pytest.raises(ValueError, match="yunet-face detects no plates"):
        c.Audit.model_validate(audit | {"egoblur": {"model": "yunet-face", "faces": 1, "plates": 0}})
    plate = {"frame": 3, "box": [10, 10, 60, 40], "kind": "plate", "detector": "egoblur", "patched_item": "p_1"}
    with pytest.raises(ValueError, match="yunet-face can't report a plate"):
        c.Audit.model_validate(audit | {"egoblur": {"model": "yunet-face", "faces": 1, "plates": None},
                                        "leaks": [*audit["leaks"], plate]})  # fmt: skip


def test_a_crowd_fill_covers_a_sparse_track_between_anchors(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # screen:1 has anchors on frames 1 and 5 only
    _edit(job_dir, "tracks.json", lambda d: d.update({"crowded_frames": [2]}))

    def fill(d: Any) -> None:
        next(e for e in d["frames"]["2"] if e["item_id"] == "i_3")["box"] = [0, 0, 2, 2]
        d["crowd_fills"] = [{"frames": [2], "box": [800, 300, 1200, 700]}]

    _edit(job_dir, "plan.json", fill)
    assert "plan.json" in c.validate_job_dir(job_dir)


# --- audits #51 and #52 -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "change", "hold"),
    [
        ("scene.json", {"status": "failed", "model": None}, "no_scene"),
        ("transcript.json", {"status": "failed", "turns": [], "degraded": True, "source": None,
                             "source_kind": None}, "no_speech"),
        ("scene.json", {"children": [{"description": "a small child by the door"}]}, "unmatched_child"),
    ],
)  # fmt: skip
def test_a_policy_keep_respects_the_holds(tmp_path: Path, name: str, change: dict[str, Any], hold: str) -> None:
    job_dir = _example(tmp_path)
    if hold == "no_speech":  # no turns left for the scene's introduction to point at
        _edit(job_dir, "scene.json", lambda d: d["participants"][0].update(
            {"introduced_in_turn": None, "introduction_quote": None}))  # fmt: skip
    _edit(job_dir, name, lambda d: d.update(change))
    with pytest.raises(c.ContractError, match=hold):
        c.validate_job_dir(job_dir)


def test_a_policy_keep_needs_a_speech_link(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "roles.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "face:1").update(
        {"matches_participant": None}))  # fmt: skip
    with pytest.raises(c.ContractError, match="no_speech_link"):
        c.validate_job_dir(job_dir)


def test_a_keep_never_carries_a_hold(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "i_1").update(
        {"hold": "no_speech"}))  # fmt: skip
    with pytest.raises(c.ContractError, match="i_1: a keep carries hold no_speech"):
        c.validate_job_dir(job_dir)


def test_an_open_weight_opinion_needs_consent(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d.update({"open_weight": {"model": "m", "status": "ok", "frames": 0,
                                                                     "findings": 0}}))  # fmt: skip
    with pytest.raises(c.ContractError, match="isn't consented and attempted"):
        c.validate_job_dir(job_dir)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"frames_scanned": 7, "unresolved": 5, "blocked_reason": "unresolved_leaks"}, "unscanned frames block"),
        ({"unresolved": 3, "blocked_reason": "unresolved_leaks"}, "needs an unresolved leak"),
    ],
)
def test_the_blocked_reason_follows_its_precedence(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d.update(change))
    with pytest.raises(c.ContractError, match=message):
        c.validate_job_dir(job_dir)


def test_a_worse_rerun_never_replaces_a_recorded_summary(tmp_path: Path) -> None:
    out = tmp_path / "b"
    probes.save_summary(out, {"concepts": {"face": {"records": 3}, "person": {"records": 1}}})
    failed = probes.save_summary(out, {"concepts": {"face": {"error": "x"}, "person": {"error": "y"}}})
    assert json.loads((out / "summary.json").read_text())["concepts"]["face"] == {"records": 3}
    assert failed.name.startswith("summary.failed-")
    better = probes.save_summary(out, {"concepts": {"face": {"records": 4}, "person": {"records": 2}}})
    assert better.name == "summary.json"


class _Drip(httpx.AsyncByteStream):
    async def __aiter__(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        for _ in range(100):
            await asyncio.sleep(0.1)
            yield b" "


async def test_a_dripping_error_body_is_bounded_by_the_total_timeout(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/responses").mock(return_value=httpx.Response(500, stream=_Drip()))
    spec = CallSpec(stage="s", model="muse-spark-1.3", estimate_usd=0.01, estimate_units={},
                    policy=RetryPolicy(attempts=1), timeout=httpx.Timeout(5.0), total_timeout_s=0.5)  # fmt: skip
    started = time.monotonic()
    with pytest.raises(MetaUnavailable):
        await h.client.stream(spec, {"model": "muse-spark-1.3", "store": False}, meter=lambda _: ({}, 0.0))
    assert time.monotonic() - started < 3


def test_a_held_and_growing_box_through_a_gap_passes(tmp_path: Path) -> None:
    # screen:1 anchors on 1 and 5; the guard holds frame 1's box (grown) through 2-4 while the object moves away.
    job_dir = _example(tmp_path)
    _edit(job_dir, "tracks.json", lambda d: next(t for t in d["tracks"] if t["track_id"] == "screen:1")["boxes"]
          .update({"5": [700, 400, 900, 600]}))  # fmt: skip

    def plan(d: Any) -> None:
        for f in ("2", "3", "4"):
            next(e for e in d["frames"][f] if e["item_id"] == "i_3")["box"] = [884, 384, 1116, 616]
        for f in ("5", "6", "7", "8", "9", "10", "11"):
            next(e for e in d["frames"][f] if e["item_id"] == "i_3")["box"] = [684, 384, 916, 616]

    _edit(job_dir, "plan.json", plan)
    assert "plan.json" in c.validate_job_dir(job_dir)


def test_an_oversized_integer_in_env_json_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="not usable JSON"):
        load_settings({"SAFECUT_ACCESS_CODES": "[" + "1" * 5000 + "]"})


@pytest.mark.parametrize("content", [b"", b"RIFF\\x00\\x00", b"not a wav at all"])
async def test_an_unreadable_wav_is_refused_before_any_spend(
    make_harness: Callable[..., Harness], tmp_path: Path, content: bytes
) -> None:
    h = make_harness()
    wav = tmp_path / "a.wav"
    wav.write_bytes(content)
    with pytest.raises(MetaBadRequest, match="not a readable WAV"):
        await responses_asr.transcribe_raw(h.client, wav, model="muse-voice-transcribe-1.0", language_bias=[])
    assert h.costs() == []


def test_an_empty_mask_between_anchors_hides_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # screen:1 has anchors on frames 1 and 5 only
    empty = {"size": [720, 1280], "counts": rle_string([720 * 1280])}
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["3"] if e["item_id"] == "i_3").update(
        {"shape": "mask", "mask": empty}))  # fmt: skip
    with pytest.raises(c.ContractError, match="frame 3: i_3 is nowhere near screen:1"):
        c.validate_job_dir(job_dir)


def test_a_red_team_read_through_carries_the_flag(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # i_3 (the screen) is hidden on frame 3; the model reads text through it
    hit = {
        "frame": 3,
        "finding": "hit",
        "kind": "text",
        "text": "AB",
        "detail": "a name on the screen",
        "box": [950, 450, 1050, 500],
        "confidence": "high",
        "excluded_by": None,
    }
    leak = {"frame": 3, "box": [950, 450, 1050, 500], "kind": "text", "detector": "redteam", "patched_item": "p_1"}

    def add(d: Any) -> None:
        d["redteam"].append(hit)
        d["leaks"].append(leak)

    _edit(job_dir, "audit.json", add)
    with pytest.raises(c.ContractError, match="reads through a hidden region"):
        c.validate_job_dir(job_dir)


# --- audit #53 ----------------------------------------------------------------------------------------------


def test_a_text_hit_patched_by_its_own_audit_patch_needs_no_flag(tmp_path: Path) -> None:
    # The re-planned plan.json carries p_1 over the finding; that is the fix, not a region read through.
    job_dir = _example(tmp_path)

    def text(d: Any) -> None:
        for entry in [*d["leaks"], *d["redteam"]]:
            if entry.get("kind") == "face" and entry.get("detector", "redteam") == "redteam":
                entry["kind"] = "text"

    _edit(job_dir, "audit.json", text)
    assert "audit.json" in c.validate_job_dir(job_dir)


@pytest.mark.parametrize(("quote", "valid"), [("I'm", False), ("Im Amina", True)])
def test_an_introduction_quote_is_normalised_as_pre_a_says(tmp_path: Path, quote: str, valid: bool) -> None:
    # "I'm" is one word ("im"), so no evidence (P11c); "Im Amina" is in "hi im amina, and today…".
    job_dir = _example(tmp_path)
    _edit(job_dir, "scene.json", lambda d: d["participants"][0].update(
        {"speaker": None, "introduced_in_turn": 0, "introduction_quote": quote}))  # fmt: skip
    if valid:
        assert "decisions.json" in c.validate_job_dir(job_dir)
    else:
        with pytest.raises(c.ContractError, match="no_speech_link"):
            c.validate_job_dir(job_dir)


def test_an_audit_patch_spans_its_finding(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    narrow_patch(job_dir, 10)
    _edit(job_dir, "decisions.json", lambda d: next(i for i in d["items"] if i["item_id"] == "p_1").update(
        {"last": 10}))  # fmt: skip
    _edit(job_dir, "plan.json", lambda d: d["frames"].update(
        {"11": [e for e in d["frames"]["11"] if e["item_id"] != "p_1"]}))  # fmt: skip
    with pytest.raises(c.ContractError, match="audit patch for frame 10 spans at least 0-11, not 10-10"):
        c.validate_job_dir(job_dir)


# --- audit #54 ----------------------------------------------------------------------------------------------


def test_an_audit_runs_at_most_three_passes() -> None:
    audit = json.loads((EXAMPLE / "audit.json").read_text())
    with pytest.raises(ValueError, match="passes"):
        c.Audit.model_validate(audit | {"passes": 9})


@pytest.mark.parametrize("body", [{"output": 5}, {"output": [{"type": "message", "content": 5}]}])
def test_a_malformed_output_is_a_typed_error(body: dict[str, Any]) -> None:
    with pytest.raises(MetaIncomplete, match="isn't a list"):
        responses.output_text(body)


@pytest.mark.parametrize(("bias", "message"), [("English", "not one string"), (["Klingon"], "unsupported")])
def test_the_asr_language_bias_is_a_list_of_known_languages(bias: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        responses_asr.request_part("muse-voice-transcribe-1.0", mode="DIARIZATION", language_bias=bias)


async def test_a_wav_reporting_no_frames_is_refused_before_any_spend(
    make_harness: Callable[..., Harness], tmp_path: Path
) -> None:
    import wave  # noqa: PLC0415 -- only this test writes a WAV

    h = make_harness()
    path = tmp_path / "empty.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
    with pytest.raises(MetaBadRequest, match="no audio frames"):
        await responses_asr.transcribe_raw(h.client, path, model="muse-voice-transcribe-1.0", language_bias=[])
    assert h.costs() == []


def test_a_job_file_that_is_a_directory_is_a_contract_error(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    (job_dir / "tracks.json").unlink()
    (job_dir / "tracks.json").mkdir()
    with pytest.raises(c.ContractError, match=r"tracks\.json: unreadable"):
        c.validate_job_dir(job_dir)


# --- audit #55 ----------------------------------------------------------------------------------------------


def test_an_outline_mask_between_anchors_hides_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # screen:1 has anchors on frames 1 and 5 only
    runs: list[int] = []
    end = 0
    for col in (900, 1099):  # two one-pixel columns at the track box's edges: they span it but fill 1 %
        runs += [col * 720 + 400 - end, 200]
        end = col * 720 + 600
    runs.append(720 * 1280 - end)
    outline = {"size": [720, 1280], "counts": rle_string(runs)}
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["3"] if e["item_id"] == "i_3").update(
        {"shape": "mask", "mask": outline}))  # fmt: skip
    with pytest.raises(c.ContractError, match="frame 3: i_3 is nowhere near screen:1"):
        c.validate_job_dir(job_dir)


def test_the_store_claim_covers_every_meta_model(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    data = json.loads((job_dir / "receipt.json").read_text())
    data.pop("hash")
    data["data_handling"]["no_store_param"] = []  # the ASR model ran, but nothing says how it was stored
    sealed = c.Receipt.seal(c.ReceiptBody.model_validate(data))
    (job_dir / "receipt.json").write_text(sealed.model_dump_json())
    with pytest.raises(c.ContractError, match="says nothing about the store setting of"):
        c.validate_job_dir(job_dir)


def test_an_egoblur_leak_needs_the_detector_to_have_run(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "audit.json", lambda d: d["egoblur"].update({"faces": None, "plates": None}))
    with pytest.raises(c.ContractError, match=r"an egoblur leak, but egoblur\.faces is null"):
        c.validate_job_dir(job_dir)


def _baseten_line(**overrides: Any) -> c.CostLine:
    line: dict[str, Any] = {
        "ts": "2026-10-27T10:05:00Z",
        "provider": "baseten",
        "job_id": "j_example",
        "stage": "audit",
        "model": "m",
        "attempt": 1,
        "units": {"frames": 2.0},
        "usd": 0.01,
        "estimated": False,
        "request_id": "b_1",
        "code_kind": "owner",
        "code_id": None,
    }
    return c.CostLine.model_validate(line | overrides)


def test_frames_go_to_baseten_only_with_consent(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    c.append_cost_line(_baseten_line(), job_dir / "cost.jsonl")
    with pytest.raises(c.ContractError, match="without a consented, recorded second opinion"):
        c.validate_job_dir(job_dir)
    _edit(job_dir, "job.json", lambda d: d.update({"consented": True, "open_weight_attempted": True}))
    with pytest.raises(c.ContractError, match="without a consented, recorded second opinion"):
        c.validate_job_dir(job_dir)  # the opinion is still recorded as off
    _edit(job_dir, "audit.json", lambda d: d.update({"open_weight": {"model": "m", "status": "failed"}}))
    c.validate_job_dir(job_dir)
    c.append_cost_line(_baseten_line(request_id="b_2", code_kind="eval"), job_dir / "cost.jsonl")
    with pytest.raises(c.ContractError, match=r"for \['eval'\] code kinds"):
        c.validate_job_dir(job_dir)


def test_an_open_weight_read_through_carries_the_flag(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # i_3 (the screen) is hidden on frame 3; the open model reads text through it
    hit = {
        "frame": 3,
        "finding": "hit",
        "kind": "text",
        "text": "AB",
        "detail": "a name on the screen",
        "box": [950, 450, 1050, 500],
        "confidence": "high",
        "excluded_by": None,
    }
    _edit(job_dir, "job.json", lambda d: d.update({"consented": True, "open_weight_attempted": True}))

    def add(d: Any) -> None:
        d["open_weight"] = {"model": "m", "status": "ok", "frames": 1, "findings": 1}
        d["redteam_open"] = [hit]

    _edit(job_dir, "audit.json", add)
    c.validate_job_dir(job_dir)  # advisory: the grid never confirmed it, so there is no leak to flag
    leak = {"frame": 3, "box": [950, 450, 1050, 500], "kind": "text", "detector": "redteam_open", "patched_item": "p_1"}
    _edit(job_dir, "audit.json", lambda d: d["leaks"].append(leak))
    with pytest.raises(c.ContractError, match="reads through a hidden region"):
        c.validate_job_dir(job_dir)


# --- audit #56 ----------------------------------------------------------------------------------------------


def test_one_mask_pixel_between_anchors_hides_nothing(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)  # screen:1's box on frame 3 is about [900, 400, 1100, 600]
    at = 1000 * 720 + 500
    dot = {"size": [720, 1280], "counts": rle_string([at, 1, 720 * 1280 - at - 1])}
    _edit(job_dir, "plan.json", lambda d: next(e for e in d["frames"]["3"] if e["item_id"] == "i_3").update(
        {"shape": "mask", "mask": dot}))  # fmt: skip
    with pytest.raises(c.ContractError, match="frame 3: i_3 is nowhere near screen:1"):
        c.validate_job_dir(job_dir)


def test_the_receipt_names_every_model_cost_jsonl_billed(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)  # cost.jsonl bills sam-3.1
    data = json.loads((job_dir / "receipt.json").read_text())
    data.pop("hash")
    del data["models"]["sam"]
    data["data_handling"]["store_by_model"].pop("sam-3.1")
    (job_dir / "receipt.json").write_text(c.Receipt.seal(c.ReceiptBody.model_validate(data)).model_dump_json())
    with pytest.raises(c.ContractError, match=r"models leaves out \['sam-3\.1'\]"):
        c.validate_job_dir(job_dir)


def test_an_unreadable_cost_jsonl_is_a_contract_error(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    (job_dir / "cost.jsonl").unlink()
    (job_dir / "cost.jsonl").mkdir()
    with pytest.raises(c.ContractError, match=r"cost\.jsonl: unreadable"):
        c.validate_job_dir(job_dir)


def test_an_outright_failure_never_replaces_a_summary_with_an_in_band_error(tmp_path: Path) -> None:
    recorded = {"max_length": {"180s": {"accepted": False, "error": "too long"}}, "60s": {"accepted": True}}
    assert probes.save_summary(tmp_path, recorded).name == "summary.json"
    aside = probes.save_summary(tmp_path, {"error": "MetaUnavailable: down"})
    assert aside.name.startswith("summary.failed-")
    assert json.loads((tmp_path / "summary.json").read_text()) == recorded


def test_an_unreadable_recorded_summary_is_kept(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text("{not json")
    assert probes.save_summary(tmp_path, {"ok": True}).name.startswith("summary.failed-")
    assert (tmp_path / "summary.json").read_text() == "{not json"


def test_a_dripping_status_body_is_bounded() -> None:
    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"{"
            while True:
                await asyncio.sleep(0.05)
                yield b" "

    async def run() -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=Drip()))
        async with httpx.AsyncClient(transport=transport) as http:
            started = time.monotonic()
            with pytest.raises(StatusUnavailableError):
                await fetch_status(http, BASE, timeout_s=0.3)
            assert time.monotonic() - started < 2

    asyncio.run(run())


def test_an_oversized_status_body_is_refused() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b" " * (65 * 1024)))
        async with httpx.AsyncClient(transport=transport) as http:
            with pytest.raises(StatusUnavailableError, match="over 64 KiB"):
                await fetch_status(http, BASE)

    asyncio.run(run())


def test_every_call_has_a_deadline() -> None:
    spec = CallSpec(stage="s", model=None, estimate_usd=0.0, estimate_units={}, policy=RetryPolicy(attempts=1),
                    timeout=httpx.Timeout(1.0))  # fmt: skip
    assert spec.total_timeout_s == config.DEFAULT_TOTAL_TIMEOUT_S


@pytest.mark.parametrize("choices", [5, 1.5, True, "x", {"a": 1}])
def test_a_malformed_chat_chunk_is_ignored_not_a_type_error(choices: Any) -> None:
    acc = _ChatAccumulator()
    acc.add({"id": "x", "choices": choices})
    assert acc.answer()["text"] == ""


# --- audit #57 ----------------------------------------------------------------------------------------------


def test_an_out_of_range_retry_after_date_is_ignored() -> None:
    assert parse_retry_after("Sun, 06 Nov 99999999999 08:49:37 GMT") is None


def test_a_torn_cost_line_is_cut_back_and_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cost.jsonl"
    line = c.CostLine.model_validate_json((EXAMPLE / "cost.jsonl").read_text().splitlines()[0])
    c.append_cost_line(line, path)
    before = path.read_bytes()
    real = os.write
    calls: list[int] = []

    def short(fd: int, data: bytes) -> int:
        calls.append(len(data))
        if len(calls) == 1:
            return real(fd, data[:10])  # the disk takes 10 bytes, then is full
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(c.os, "write", short)
    with pytest.raises(OSError, match="No space left"):
        c.append_cost_line(line, path)
    monkeypatch.undo()
    assert path.read_bytes() == before
    c.append_cost_line(line, path)
    assert len(list(c.read_cost_lines(path))) == 2


def test_a_short_write_is_finished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cost.jsonl"
    line = c.CostLine.model_validate_json((EXAMPLE / "cost.jsonl").read_text().splitlines()[0])
    real = os.write
    monkeypatch.setattr(c.os, "write", lambda fd, data: real(fd, data[:7]))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType] -- a stand-in
    c.append_cost_line(line, path)
    monkeypatch.undo()
    assert list(c.read_cost_lines(path)) == [line]


# --- audit #58 ----------------------------------------------------------------------------------------------


def test_a_model_whose_calls_were_all_refused_need_not_be_named(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_example"
    shutil.copytree(EXAMPLE, job_dir)
    first = json.loads((job_dir / "cost.jsonl").read_text().splitlines()[0])
    refused = first | {"stage": "escalate", "model": "muse-wonder-1.0", "usd": 0.0, "request_id": "resp_refused"}
    with (job_dir / "cost.jsonl").open("a") as handle:
        handle.write(json.dumps(refused) + "\n")
    c.validate_job_dir(job_dir)


def test_a_huge_frame_is_refused_before_any_mask_check(tmp_path: Path) -> None:
    job_dir = _example(tmp_path)
    _edit(job_dir, "job.json", lambda d: d.update({"width": 20_000_000}))
    with pytest.raises(c.ContractError, match="less than or equal to 8192"):
        c.validate_job_dir(job_dir)


def test_a_recorded_outright_failure_is_replaced_by_a_run_that_got_further(tmp_path: Path) -> None:
    probes.save_summary(tmp_path, {"error": "MetaConfigError: no key"})
    better = {"red square": {"objects": 1}, "a": {"error": "x"}, "b": {"error": "y"}}
    assert probes.save_summary(tmp_path, better).name == "summary.json"
    assert json.loads((tmp_path / "summary.json").read_text()) == better


async def test_a_stream_whose_headers_never_arrive_is_bounded(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()

    async def stall(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        return httpx.Response(200)

    mock_api.post("/responses").mock(side_effect=stall)
    spec = CallSpec(stage="s", model="muse-spark-1.3", estimate_usd=0.01, estimate_units={},
                    policy=RetryPolicy(attempts=1), timeout=httpx.Timeout(5.0), total_timeout_s=0.5)  # fmt: skip
    started = time.monotonic()
    with pytest.raises(MetaUnavailable):
        await h.client.stream(spec, {"model": "muse-spark-1.3", "store": False}, meter=lambda _: ({}, 0.0))
    assert time.monotonic() - started < 3
    assert h.costs()[0].estimated  # sent, so the estimate is kept
