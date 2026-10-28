"""Tests for audits #24 and #25: an unflagged leak's patch is an audit patch, containment is checked against what
the plan renders, and a Files cost line records its bytes."""

from __future__ import annotations

import asyncio
import functools
import json
import shutil
import time
from collections.abc import Callable
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
from safecut.meta import responses, sam
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import CallSpec, MetaClient
from safecut.meta.errors import MetaBadRequest, MetaConfigError, MetaUnavailable
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
