"""Tests for audit #2 and code-review hardening: breaker trials, refusals, typed httpx errors, guards,
config input checks, Files concurrency and cleanup, and the probe runner's robustness."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from safecut.config import ConfigError, Settings, load_settings
from safecut.contracts import read_cost_lines
from safecut.meta import asr, sam
from safecut.meta.budget import Caller, LocalLedger
from safecut.meta.client import CallSpec, MetaClient, guard_body
from safecut.meta.errors import MetaConfigError, MetaRefusal, MetaUnavailable, classify
from safecut.meta.files import FileStore
from safecut.meta.responses import count_input_tokens, meter_for
from safecut.meta.retry import CircuitBreaker, RetryPolicy
from scripts.probes import probes
from tests.conftest import BASE, Harness, completed, stream_response, text_response


def _spec(**kw: Any) -> CallSpec:
    base: dict[str, Any] = {
        "stage": "s",
        "model": "muse-spark-1.3",
        "estimate_usd": 0.05,
        "estimate_units": {"n": 0},
        "policy": RetryPolicy(attempts=4),
        "timeout": httpx.Timeout(5.0),
        "total_timeout_s": 30.0,
    }
    return CallSpec(**(base | kw))


def _meter(_: object) -> tuple[dict[str, float], float]:
    return {"n": 1}, 0.002


def _open(breaker: CircuitBreaker) -> None:
    for _ in range(5):
        breaker.record_failure()


# --- breaker -------------------------------------------------------------------------


async def test_cancel_during_backoff_frees_the_trial(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    now = [0.0]
    h = make_harness()
    h.client.breaker = CircuitBreaker(clock=lambda: now[0])
    _open(h.client.breaker)
    now[0] = 61.0
    gate = asyncio.Event()

    async def stuck(_: float) -> None:
        await gate.wait()

    h.client._sleep = stuck  # pyright: ignore[reportPrivateUsage] -- block in the backoff
    mock_api.post("/thing").mock(return_value=httpx.Response(503))
    task = asyncio.create_task(h.client.request("POST", "thing", _spec(), meter=_meter))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert h.client.breaker.before_call() is True  # a new trial is admitted, not refused forever


def test_a_late_failure_does_not_admit_a_second_trial() -> None:
    now = [0.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    _open(breaker)
    now[0] = 61.0
    assert breaker.before_call() is True
    breaker.record_failure(trial=False)
    now[0] = 200.0
    with pytest.raises(MetaUnavailable):
        breaker.before_call()


async def test_best_effort_calls_ignore_the_breaker(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(503))
    for _ in range(8):
        assert await count_input_tokens(h.client, {"model": "muse-spark-1.3", "input": []}, stage="x") is None
    assert h.client.breaker.state == "closed"
    _open(h.client.breaker)
    mock_api.post("/responses/input_tokens").mock(return_value=httpx.Response(200, json={"input_tokens": 7}))
    assert await count_input_tokens(h.client, {"model": "muse-spark-1.3", "input": []}, stage="x") == 7


# --- streams and errors ------------------------------------------------------------------


async def test_streamed_refusal_is_billed_at_usage(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    usage = {"input_tokens": 1000, "output_tokens": 12}
    mock_api.post("/responses").mock(
        return_value=stream_response(
            {"type": "response.refusal.delta", "delta": "I can't"},
            completed({"id": "r", "status": "completed", "output": [], "usage": usage}),
        )
    )
    with pytest.raises(MetaRefusal, match="I can't"):
        await h.client.stream(
            _spec(estimate_usd=0.2), {"model": "muse-spark-1.3", "store": False}, meter=meter_for("muse-spark-1.3")
        )
    (line,) = h.costs()
    assert line.estimated is False
    assert line.usd == pytest.approx((1000 * 1.25 + 12 * 4.25) / 1e6)


async def test_refusal_without_terminal_event(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.post("/responses").mock(return_value=stream_response({"type": "response.refusal.done", "refusal": "no"}))
    with pytest.raises(MetaRefusal):
        await h.client.stream(_spec(), {"model": "m", "store": False}, meter=_meter)
    assert [line.estimated for line in h.costs()] == [True]


async def test_non_transport_httpx_errors_are_typed(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter
) -> None:
    h = make_harness()
    mock_api.post("/thing").mock(side_effect=httpx.DecodingError("bad gzip"))
    with pytest.raises(MetaUnavailable, match="DecodingError"):
        await h.client.request("POST", "thing", _spec(policy=RetryPolicy(attempts=1)), meter=_meter)
    mock_api.post("/responses").mock(side_effect=httpx.TooManyRedirects("loop"))
    with pytest.raises(MetaUnavailable, match="TooManyRedirects"):
        await h.client.stream(_spec(policy=RetryPolicy(attempts=1)), {"model": "m", "store": False}, meter=_meter)


@pytest.mark.parametrize("param", ["reasoning.effort", "text.format.schema", "model", "max_output_tokens"])
def test_dotted_params_are_config_errors(param: str) -> None:
    assert isinstance(classify(400, {"error": {"message": "invalid", "param": param}}), MetaConfigError)


def test_guard_requires_an_explicit_store_false() -> None:
    with pytest.raises(ValueError, match="store"):
        guard_body({"model": "muse-spark-1.3"})
    guard_body({"model": "muse-spark-1.3", "store": False})
    guard_body({"model": "sam-3.1"}, store_param=False)
    with pytest.raises(ValueError, match="no store parameter"):
        guard_body({"model": "sam-3.1", "store": False}, store_param=False)


async def test_sam_without_store_param_passes_the_guard(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, settings: Settings
) -> None:
    cfg = settings.model_copy(update={"sam_send_store": False})
    h = make_harness(cfg=cfg)
    usage = {"video_frames_processed": 60}
    route = mock_api.post("/responses").mock(
        return_value=stream_response(completed({"id": "r", "status": "completed", "usage": usage}))
    )
    body = sam.video_body(cfg, file_id="file-1", text="face")
    result = await sam.segment_video(h.client, body, sam_frames=60)
    assert result.usd == pytest.approx(0.012)
    assert "store" not in json.loads(route.calls[0].request.content)


# --- client construction ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["https://evil.example/v1", "https://api.meta.ai@evil.example/v1", "http://api.meta.ai/v1"]
)
def test_client_refuses_untrusted_base_urls(settings: Settings, ledger: LocalLedger, url: str) -> None:
    with pytest.raises(ValueError, match="base URLs"):
        MetaClient(settings, job_id="j", caller=Caller.local(), ledger=ledger, cost_path="/dev/null", base_url=url)


async def test_client_uses_the_operators_tls_and_proxy_settings(
    settings: Settings, ledger: LocalLedger, tmp_path: Path
) -> None:
    # Decided (audit #3): httpx's default trust_env keeps the operator's CA bundle and egress proxy, which
    # cloud sandboxes need; the key still only goes to the pinned provider host.
    client = MetaClient(settings, job_id="j", caller=Caller.local(), ledger=ledger, cost_path=tmp_path / "c.jsonl")
    assert client._http._trust_env is True  # pyright: ignore[reportPrivateUsage] -- the setting under test
    assert client.base_url == "https://api.meta.ai/v1"
    await client.aclose()


# --- config input checks ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "message"),
    [
        (
            {"SAFECUT_ACCESS_CODES": '[{"code": "abcd", "kind": "judge", "valid_from": "2026-11-06T00:00:00"}]'},
            "timezone",
        ),
        ({"SAFECUT_JOB_USD_CAP": "inf"}, "job_usd_cap"),
        ({"SAFECUT_DAILY_USD_CAP": "nan"}, "daily_usd_cap"),
        ({"SAFECUT_ACCESS_CODES": '[{"code": "pilot-1", "kind": "pilot", "cap_usd": 1e999}]'}, "cap_usd"),
        ({"SAFECUT_ROLE_MODEL": "muse-spark-1.4"}, "price"),
        ({"SAFECUT_CODE_WINDOWS": '{"judge": ["2026-11-05T00:00:00", null]}'}, "SAFECUT_CODE_WINDOWS"),
    ],
)
def test_config_rejects_unsafe_values(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(env)


# --- Files -------------------------------------------------------------------------------


@pytest.fixture
def two_clips(tmp_path: Path) -> tuple[Path, Path]:
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"a" * 300)
    b.write_bytes(b"b" * 400)
    return a, b


async def test_concurrent_uploads_are_all_recorded(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, two_clips: tuple[Path, Path], tmp_path: Path
) -> None:
    h = make_harness()
    ids = iter(["file-1", "file-2"])

    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"id": next(ids)})

    mock_api.post("/files").mock(side_effect=slow)
    store = FileStore(h.client, tmp_path / "job")
    got = await asyncio.gather(store.upload(two_clips[0], "sam_proxy.mp4"), store.upload(two_clips[1], "prepared.mp4"))
    assert sorted(got) == ["file-1", "file-2"]
    assert sorted(e.name for e in store.index().root) == ["prepared.mp4", "sam_proxy.mp4"]


async def test_cancelled_upload_records_an_orphan(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, two_clips: tuple[Path, Path], tmp_path: Path
) -> None:
    h = make_harness()

    async def hang(_: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        return httpx.Response(200)

    mock_api.post("/files").mock(side_effect=hang)
    store = FileStore(h.client, tmp_path / "job")
    task = asyncio.create_task(store.upload(two_clips[0], "sam_proxy.mp4"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    (entry,) = store.index().root
    assert entry.orphan
    assert await store.delete_all() is False


async def test_cleanup_works_while_the_breaker_is_open(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, two_clips: tuple[Path, Path], tmp_path: Path
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-1"}))
    deleted = mock_api.delete("/files/file-1").mock(return_value=httpx.Response(200, json={"deleted": True}))
    store = FileStore(h.client, tmp_path / "job")
    await store.upload(two_clips[0], "sam_proxy.mp4")
    _open(h.client.breaker)
    assert await store.delete_all() is True
    assert deleted.call_count == 1


@pytest.mark.parametrize("bad_id", ["file-abc.123", "file-", "abc", "file-a b"])
async def test_upload_rejects_malformed_ids(
    make_harness: Callable[..., Harness],
    mock_api: respx.MockRouter,
    two_clips: tuple[Path, Path],
    tmp_path: Path,
    bad_id: str,
) -> None:
    h = make_harness()
    mock_api.post("/files").mock(return_value=httpx.Response(200, json={"id": bad_id}))
    mock_api.get("/files").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(MetaConfigError):
        await FileStore(h.client, tmp_path / "job").upload(two_clips[0], "sam_proxy.mp4")


# --- probe runner ---------------------------------------------------------------------------


async def test_probe_runner_survives_any_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(_: probes.Probe) -> dict[str, Any]:
        raise RuntimeError("status page down")

    async def fine(_: probes.Probe) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setitem(probes.PROBES, "a", boom)
    monkeypatch.setitem(probes.PROBES, "g", fine)
    cfg = Settings(model_api_key=SecretStr("k"))
    with respx.mock(base_url=BASE, assert_all_called=False):
        results = await probes.run(["a", "g"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    assert "RuntimeError" in results["a"]["error"]
    assert results["g"]["ok"] is True


async def test_role_call_probe(tmp_path: Path) -> None:
    frames = tmp_path / "kf"
    frames.mkdir()
    (frames / "f1.jpg").write_bytes(b"\xff\xd8fakejpeg")
    (frames / "role_calls.json").write_text(
        json.dumps([{"image": "f1.jpg", "label": "face:3", "context": "walks past", "expected": "bystander"}])
    )

    def answer(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        role = "bystander" if model == "muse-spark-1.3" else "participant"
        usage = {"input_tokens": 1600, "output_tokens": 300}
        return stream_response(completed(text_response(json.dumps({"role": role, "evidence": "x"}), usage=usage)))

    cfg = Settings(model_api_key=SecretStr("k"))
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.post("/responses/input_tokens").mock(return_value=httpx.Response(200, json={"input_tokens": 1600}))
        router.post("/responses").mock(side_effect=answer)
        router.post("/files").mock(return_value=httpx.Response(200, json={"id": "file-1"}))
        router.delete("/files/file-1").mock(return_value=httpx.Response(200, json={"deleted": True}))
        results = await probes.run(
            ["f"], settings=cfg, out_root=tmp_path / "out", ledger=LocalLedger(), keyframes=frames
        )
    calls = results["f"]["role_calls"]
    assert calls["muse-spark-1.3"]["correct"] == 1
    assert calls["muse-wonder-1.0"]["correct"] == 0
    assert calls["muse-spark-1.3"]["answered"] == 1


def test_cli_checks_the_keyframes_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert probes.main(["f", f"--keyframes={tmp_path}"]) == 2
    assert "role_calls.json" in capsys.readouterr().err


# --- audit #3 ---------------------------------------------------------------------------------


class _BrokenLedger(LocalLedger):
    def __init__(self, *, fail: str) -> None:
        super().__init__()
        self.fail = fail

    def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
        if self.fail == "reserve":
            raise RuntimeError("ledger down")
        super().reserve(call_id, job_id, usd, limits)

    def settle(self, call_id: str, usd: float) -> None:
        if self.fail == "settle":
            raise RuntimeError("ledger down")
        super().settle(call_id, usd)


async def test_ledger_faults_are_typed_and_never_lose_a_call(
    settings: Settings, tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    route = mock_api.post("/thing").mock(return_value=httpx.Response(200, json={"id": "r1"}))
    broken = MetaClient(
        settings,
        job_id="j",
        caller=Caller.local(),
        ledger=_BrokenLedger(fail="reserve"),
        cost_path=tmp_path / "a.jsonl",
    )
    with pytest.raises(MetaUnavailable, match="ledger"):
        await broken.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 0
    await broken.aclose()
    flaky = MetaClient(
        settings, job_id="j", caller=Caller.local(), ledger=_BrokenLedger(fail="settle"), cost_path=tmp_path / "b.jsonl"
    )
    result = await flaky.request("POST", "thing", _spec(), meter=_meter)
    assert result.body == {"id": "r1"}
    (line,) = list(read_cost_lines(tmp_path / "b.jsonl"))
    assert (line.usd, line.estimated, line.request_id) == (0.002, False, "r1")
    await flaky.aclose()


async def test_504s_open_the_breaker(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    route = mock_api.post("/thing").mock(return_value=httpx.Response(504))
    for _ in range(5):
        with pytest.raises(MetaUnavailable):
            await h.client.request("POST", "thing", _spec(), meter=_meter)
    assert route.call_count == 5
    assert h.client.breaker.state == "open"


async def test_redirects_are_never_success(make_harness: Callable[..., Harness], mock_api: respx.MockRouter) -> None:
    h = make_harness()
    mock_api.delete("/files/file-1").mock(return_value=httpx.Response(307, headers={"location": "https://x"}))
    with pytest.raises(MetaConfigError, match="redirect"):
        await h.client.request("DELETE", "files/file-1", _spec(estimate_usd=0.0), meter=_meter)


async def test_cancel_during_orphan_recovery_still_records(
    make_harness: Callable[..., Harness], mock_api: respx.MockRouter, two_clips: tuple[Path, Path], tmp_path: Path
) -> None:
    h = make_harness()

    async def no_sleep(_: float) -> None:
        return None

    async def hang(_: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        return httpx.Response(200)

    h.client._sleep = no_sleep  # pyright: ignore[reportPrivateUsage] -- skip backoff
    mock_api.post("/files").mock(side_effect=httpx.ReadTimeout("slow"))
    mock_api.get("/files").mock(side_effect=hang)
    store = FileStore(h.client, tmp_path / "job")
    task = asyncio.create_task(store.upload(two_clips[0], "sam_proxy.mp4"))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [e.orphan for e in store.index().root] == [True]
    assert not store.index().all_deleted


async def test_probe_h_runs_without_the_meta_key(tmp_path: Path) -> None:
    cfg = Settings(baseten_api_key=SecretStr("bt"))
    with respx.mock(assert_all_called=False) as router:
        router.post("https://inference.baseten.co/v1/chat/completions").mock(return_value=httpx.Response(401))
        results = await probes.run(["h"], settings=cfg, out_root=tmp_path, ledger=LocalLedger())
    assert "error" not in results["h"]
    assert "MetaAuthError" in results["h"]["four_frames"]["error"]
    no_key = await probes.run(["h"], settings=Settings(), out_root=tmp_path / "x", ledger=LocalLedger())
    assert "BASETEN_API_KEY" in no_key["h"]["error"]


def test_config_hygiene() -> None:
    s = load_settings({"SAFECUT_ACCESS_CODES": '[{"code": "judge-secret-7", "kind": "judge"}]'})
    assert "judge-secret-7" not in repr(s)
    assert "judge-secret-7" not in s.model_dump_json()
    for bad in ('[{"key": "", "name": "sigmora"}]', '[{"key": "short", "name": "sigmora"}]'):
        with pytest.raises(ConfigError):
            load_settings({"SAFECUT_SERVICE_KEYS": bad})
    with pytest.raises(ConfigError, match="REPLAY"):
        load_settings({"SAFECUT_REPLAY": "ture"})
    with pytest.raises(ConfigError, match="Contributor"):
        load_settings({"SAFECUT_SAM_MODEL": "sam-3.1-Contributor"})
    assert load_settings({}).speech_fallback_pair() == ("muse-spark-1.2", "omit")


def test_asr_request_refuses_contributor_models() -> None:
    with pytest.raises(ValueError, match="Contributor"):
        asr.request_part("muse-voice-transcribe-1.0-contributor", mode="DIARIZATION", language_bias=[])


def test_probe_h_grid_mapping() -> None:
    _, box = probes.synthetic_frame(2, name=True)
    assert box is not None
    x1, y1, x2, y2 = box
    grid = (
        round(x1 * 1000 / 1280),
        round((y1 + 40) * 1000 / 760),
        round(x2 * 1000 / 1280),
        round((y2 + 40) * 1000 / 760),
    )
    mapped = probes.grid_box_to_frame(grid)
    assert all(abs(a - b) <= 2 for a, b in zip(mapped, box, strict=True))
    assert probes.grid_box_to_frame((1001, 1001, -5, -5)) == (0, 0, 1280, 720)
