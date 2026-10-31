"""SAFECUT-MODAL: EgoBlur on a Modal GPU, through a fake Modal call. The GPU side (``GpuServer``) runs for real on the
job's render; a stand-in detector (YuNet, labelled so) plays EgoBlur, since the weights and a GPU aren't here.

Every branch of the fallback: success, timeout, error (retried once), missing weights, altered weights, no GPU, a
cap, a stale Volume, and a GPU that answers pass 1 but not a re-check. The audit and the receipt always name the
detector that actually ran."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from safecut import contracts, netguard, pipeline
from safecut.api.access import estimate_usd
from safecut.api.store import sweep_handoff
from safecut.audit import GPU_RECORD, auditor_available, detectors, gpu
from safecut.audit import run as audit_run
from safecut.audit.detectors import AuditorModel, Detector, YuNet
from safecut.audit.gpu import GpuDetector, GpuMeter, GpuRequest, GpuServer, GpuUnavailable, Handoff
from safecut.config import Settings
from safecut.contracts import Audit, CostLine, Receipt, load, read_cost_lines
from safecut.decide import run as decide_run
from safecut.guard import run as guard_run
from safecut.meta.budget import Caller, LocalLedger
from safecut.receipt import run as receipt_run
from safecut.receipt.build import (
    REPLAY_GPU_NOTE,
    REPLAY_NOTE,
    SYNTHETIC_GPU_NOTE,
    SYNTHETIC_NOTE,
    YUNET_FALLBACK_NOTE,
    YUNET_NOTE,
)
from safecut.render import render
from tests.safety_jobs import make_job

FACE, PLATE = "ego_blur_face_gen2.jit", "ego_blur_lp_gen2.jit"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def weights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand-in weight files, pinned as if they were Meta's (the real hashes are pinned in detectors.py)."""
    folder = tmp_path / "models" / "egoblur"
    folder.mkdir(parents=True)
    pins: dict[str, str] = {}
    for name in (FACE, PLATE):
        (folder / name).write_bytes(name.encode())
        pins[name] = hashlib.sha256(name.encode()).hexdigest()
    monkeypatch.setattr(detectors, "EGOBLUR_GEN2_SHA256", pins)
    return folder


def settings_for(tmp_path: Path, **extra: Any) -> Settings:
    return Settings(audit_gpu=True, egoblur_model="egoblur-gen2", egoblur_weights_dir=str(tmp_path / "nowhere"),
                    jobs_dir=str(tmp_path / "service"), audit_gpu_handoff_dir=str(tmp_path / "handoff"),
                    **extra)  # fmt: skip


def prepared(tmp_path: Path) -> Path:
    job_dir = make_job(tmp_path)
    decide_run(job_dir)
    guard_run(job_dir)
    render(job_dir)
    return job_dir


class FakeModal:
    """``spawn().get(timeout)`` on a :class:`GpuServer`, with the faults a real call can meet."""

    def __init__(self, server: GpuServer, faults: list[str | None] | None = None) -> None:
        self.server = server
        self.faults = list(faults or [])
        self.requests: list[GpuRequest] = []
        self.commits = 0
        self.timeouts: list[float] = []

    def call(self, request: GpuRequest, timeout_s: float) -> tuple[dict[str, Any], str | None]:
        self.requests.append(request)
        self.timeouts.append(timeout_s)
        fault = self.faults.pop(0) if self.faults else None
        if fault == "timeout":
            raise TimeoutError("no output")
        if fault == "error":
            raise ConnectionError("Modal control plane unreachable")
        if fault == "unspawned":
            raise gpu.NotSubmitted("NotFoundError: the GPU function isn't deployed")
        answer = self.server.serve(request.model_dump(mode="json"))
        if fault == "stale":
            answer = {**answer, "video_sha256": "0" * 64}
        return answer, f"fc-{len(self.requests)}"

    def commit(self) -> None:
        self.commits += 1


def stand_in(model: AuditorModel, face: Path, plate: Path, face_t: float, plate_t: float) -> Detector:
    """YuNet plays EgoBlur on the fake GPU (faces only): the wire, the Volume read and the fallbacks are real."""
    del model, face, plate, plate_t
    return YuNet(face_t)


def handoff_root(job_dir: Path) -> Path:
    """The handoff Volume's mount in these tests (``settings_for`` points the audit at the same folder)."""
    return job_dir.parent / "handoff"


def handoff(job_dir: Path, commit: Callable[[], None]) -> Handoff:
    return Handoff(handoff_root(job_dir), commit)


def server(job_dir: Path, weights_dir: Path, *, gpu_name: str | None = "Tesla T4") -> GpuServer:
    """The GPU function's side: it reads renders from the handoff Volume, never the jobs folder."""
    return GpuServer(handoff_root(job_dir), weights_dir, load=stand_in, gpu_name=lambda: gpu_name)


def audit_of(job_dir: Path) -> Audit:
    return load(job_dir / "audit.json", Audit)


def gpu_lines(job_dir: Path) -> list[CostLine]:
    return [line for line in read_cost_lines(job_dir / "cost.jsonl") if line.provider == "modal"]


def sealed(job_dir: Path, settings: Settings) -> Receipt:
    pipeline.approve(job_dir, how="auto_policy")
    receipt_run(job_dir, settings=settings)
    contracts.validate_job_dir(job_dir)
    return load(job_dir / "receipt.json", Receipt)


# ---------------------------------------------------------------------------------------------- success


def test_egoblur_on_the_gpu_audits_and_the_receipt_names_the_gpu(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    audit = audit_of(job_dir)
    assert (audit.egoblur.model, audit.egoblur.device) == ("egoblur-gen2", "cuda:Tesla T4")
    assert (audit.unresolved, audit.frames_scanned) == (0, 60)
    # Pass 1 is one call for every frame, made before the red team runs; the Volume is committed before each call,
    # and once more when the audit removes its copy.
    assert len(fake.requests) == 1
    assert fake.commits == 2
    assert fake.requests[0].frames == list(range(60))
    # The render went through the handoff Volume (named by job and render hash), and was removed after the audit.
    assert fake.requests[0].job.startswith(f"{job_dir.name}-")
    assert list(handoff_root(job_dir).iterdir()) == []
    assert fake.timeouts == [settings.audit_gpu_timeout_s]
    record = json.loads((job_dir / GPU_RECORD).read_text())
    assert record["gpu_wall_s"] > 0
    expected = {"requested": True, "ran": "egoblur-gen2", "device": "cuda:Tesla T4", "fallback": None, "gpu_calls": 1}
    assert {k: v for k, v in record.items() if k != "gpu_wall_s"} == expected
    run = json.loads((job_dir / "raw/audit/run.json").read_text())
    assert (run["detector"], run["device"]) == ("egoblur-gen2", "cuda:Tesla T4")
    (line,) = gpu_lines(job_dir)
    assert (line.stage, line.model, line.estimated, line.request_id) == ("audit", "egoblur-gen2", True, "fc-1")
    assert line.units["idle_s"] == settings.audit_gpu_idle_s
    assert line.usd == pytest.approx(
        (line.units["gpu_s"] + line.units["idle_s"]) * settings.audit_gpu_usd_per_hour / 3600, rel=1e-3
    )
    receipt = sealed(job_dir, settings)
    assert (receipt.audit.auditor, receipt.audit.auditor_device) == ("egoblur-gen2", "cuda:Tesla T4")
    assert receipt.models["auditor"] == "egoblur-gen2"
    assert receipt.cost_usd_gpu == pytest.approx(line.usd)
    assert "cuda:Tesla T4" in (job_dir / "receipt.html").read_text()
    assert pipeline.job_spend(job_dir) == 0  # Meta's caps count Meta lines only; the GPU is in the ledger
    ledger = LocalLedger(Path(settings.jobs_dir) / "ledger.sqlite")
    assert ledger.spent(f"job:{job_dir.name}") == pytest.approx(line.usd)


def test_a_leak_is_patched_and_rechecked_on_the_gpu(tmp_path: Path, weights: Path) -> None:
    """The E4 injected leak, with the GPU auditing: each re-render is committed and re-scanned on the GPU, and the
    idle tail is billed once per audit."""
    from tests.test_audit_loop import drop  # noqa: PLC0415 -- the E4 test's own injector

    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    audit = audit_of(job_dir)
    assert audit.egoblur.model == "egoblur-gen2"
    assert {30, 31, 32} <= {leak.frame for leak in audit.leaks if leak.detector == "egoblur"}
    assert audit.unresolved == 0
    assert audit.passes >= 2
    assert len(fake.requests) >= 2  # the patched render is re-scanned on the GPU, not locally
    assert fake.commits == len(fake.requests) + 1  # one per call, and the cleanup's
    lines = gpu_lines(job_dir)
    assert len(lines) == len(fake.requests)
    assert [line.units["idle_s"] for line in lines] == [settings.audit_gpu_idle_s] + [0.0] * (len(lines) - 1)
    assert sealed(job_dir, settings).audit.auditor_device == "cuda:Tesla T4"


def test_a_transient_error_is_retried_once(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    fake = FakeModal(server(job_dir, weights), ["error"])
    slept: list[float] = []
    settings = settings_for(tmp_path)
    detector = GpuDetector(job_dir, settings, fake.call, meter(job_dir, settings),
                           handoff=handoff(job_dir, fake.commit), sleep=slept.append)  # fmt: skip
    detector.prefetch()
    assert len(fake.requests) == 2
    assert slept == [gpu.RETRY_DELAY_S]
    assert detector.failure is None
    assert detector.device == "cuda:Tesla T4"
    assert len(gpu_lines(job_dir)) == 2  # the failed attempt is priced too: Modal may have billed it


# ---------------------------------------------------------------------------------------------- fallbacks


def no_weights(tmp_path: Path, weights: Path) -> Path:
    del weights
    return tmp_path / "empty"


def altered(tmp_path: Path, weights: Path) -> Path:
    del tmp_path
    (weights / PLATE).write_bytes(b"a truncated upload")
    return weights


def as_is(tmp_path: Path, weights: Path) -> Path:
    del tmp_path
    return weights


Setup = tuple[list[str | None], Callable[[Path, Path], Path], str | None]


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ((["timeout"], as_is, "Tesla T4"), "timeout"),
        ((["error", "error"], as_is, "Tesla T4"), "error"),
        ((["stale", "stale"], as_is, "Tesla T4"), "stale_volume"),
        (([], no_weights, "Tesla T4"), "no_weights"),
        (([], altered, "Tesla T4"), "altered_weights"),
        (([], as_is, None), "no_gpu"),
    ],
)
def test_the_audit_falls_back_to_yunet_and_says_so(tmp_path: Path, weights: Path, setup: Setup, reason: str) -> None:
    faults, folder, gpu_name = setup
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, folder(tmp_path, weights), gpu_name=gpu_name), faults)
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    audit = audit_of(job_dir)
    assert (audit.egoblur.model, audit.egoblur.device, audit.egoblur.plates) == ("yunet-face", "cpu", None)
    assert audit.unresolved == 0  # the audit still ran, whole, on YuNet
    record = json.loads((job_dir / GPU_RECORD).read_text())
    assert record["ran"] == "yunet-face"
    assert record["fallback"].startswith(f"{reason}:")
    receipt = sealed(job_dir, settings)
    assert (receipt.audit.auditor, receipt.audit.auditor_device) == ("yunet-face", "cpu")
    assert "egoblur" not in receipt.models["auditor"]


def test_a_cap_that_cant_cover_the_gpu_falls_back_without_calling_it(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path, job_usd_cap=0.001)  # below one call's worst case (300 s at $0.95/h)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert fake.requests == []
    assert audit_of(job_dir).egoblur.model == "yunet-face"
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("over_budget:")
    (stop,) = gpu_lines(job_dir)
    assert (stop.stage, stop.cap, stop.usd) == ("budget:audit", "job", 0)


def test_a_gpu_that_stops_mid_audit_reruns_the_whole_audit_on_yunet(tmp_path: Path, weights: Path) -> None:
    """Pass 1 on the GPU, then the re-check of a patch times out: that audit can't pass (unscanned frames), so it
    runs again, whole, on YuNet, and only YuNet is named (an EgoBlur plate count never survives into it)."""
    from tests.test_audit_loop import drop  # noqa: PLC0415 -- the E4 test's own injector

    job_dir = prepared(tmp_path)
    drop(job_dir, "i_2", {30, 31, 32})
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), [None, "timeout"])
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    audit = audit_of(job_dir)
    assert (audit.egoblur.model, audit.egoblur.device, audit.egoblur.plates) == ("yunet-face", "cpu", None)
    assert audit.unresolved == 0
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("timeout:")
    assert sealed(job_dir, settings).audit.auditor == "yunet-face"


def test_without_the_setting_the_gpu_is_never_called(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    settings = Settings(egoblur_model="egoblur-gen2", egoblur_weights_dir=str(tmp_path / "x"),
                        jobs_dir=str(tmp_path / "service"))  # fmt: skip
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert fake.requests == []
    assert not (job_dir / GPU_RECORD).exists()
    assert audit_of(job_dir).egoblur.model == "yunet-face"


def test_a_machine_without_modal_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job_dir = prepared(tmp_path)

    def missing() -> Any:
        raise ModuleNotFoundError("No module named 'modal'")

    monkeypatch.setattr(gpu, "_modal", missing)
    audit_run(job_dir, replay=True, settings=settings_for(tmp_path))
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("no_modal:")


# ---------------------------------------------------------------------------------------------- the wire


def meter(job_dir: Path, settings: Settings) -> GpuMeter:
    ledger = LocalLedger(tmp_ledger(job_dir))
    return GpuMeter(settings, ledger, Caller.local(), job_dir.name, job_dir / "cost.jsonl")


def tmp_ledger(job_dir: Path) -> Path:
    return job_dir.parent / "ledger.sqlite"


def test_the_gpu_server_checks_every_request(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    loads: list[str] = []

    def counting(model: AuditorModel, face: Path, plate: Path, face_t: float, plate_t: float) -> Detector:
        loads.append(model)
        return stand_in(model, face, plate, face_t, plate_t)

    srv = GpuServer(job_dir.parent, weights, load=counting, gpu_name=lambda: "NVIDIA L4")
    base = {"job": job_dir.name, "frames": [0, 59], "model": "egoblur-gen2", "face_threshold": 0.5,
            "plate_threshold": 0.5}  # fmt: skip
    answer = srv.serve(base)
    assert set(answer["frames"]) == {"0", "59"}
    assert answer["gpu"] == "NVIDIA L4"
    assert srv.serve(base)["video_sha256"] == answer["video_sha256"]
    assert loads == ["egoblur-gen2"]  # the detectors load once per container
    for bad, reason in (
        ({**base, "job": "../etc"}, "bad_request"),
        ({**base, "job": ".."}, "bad_request"),
        ({**base, "frames": []}, "bad_request"),
        ({**base, "frames": [60]}, "bad_request"),
        ({**base, "frames": [-1]}, "bad_request"),
        ({**base, "model": "yunet-face"}, "bad_request"),
        ({**base, "extra": 1}, "bad_request"),
        ({**base, "job": "j_missing"}, "no_render"),
    ):
        assert srv.serve(bad)["refused"] == reason, bad


def test_the_gpu_answer_is_schema_checked(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    real = server(job_dir, weights)

    def answering(change: Callable[[dict[str, Any]], dict[str, Any]]) -> GpuDetector:
        def call(request: GpuRequest, timeout_s: float) -> tuple[dict[str, Any], str | None]:
            del timeout_s
            return change(real.serve(request.model_dump(mode="json"))), None

        return GpuDetector(job_dir, settings, call, meter(job_dir, settings), handoff=handoff(job_dir, lambda: None),
                           sleep=lambda _s: None)  # fmt: skip

    face = {"kind": "face", "box": [-2.5, 1.2, 9.1, 999], "score": 1}
    clipped = answering(lambda a: {**a, "frames": {**a["frames"], "0": [face]}})
    assert clipped.detect_frames(job_dir, {0})[0][0].box == (0, 1, 10, 240)  # clamped to the frame
    off_frame = {"kind": "face", "box": [400, 400, 410, 410], "score": 0.9}  # wholly outside the 320 x 240 frame
    dropped = answering(lambda a: {**a, "frames": {**a["frames"], "0": [off_frame]}})
    assert dropped.detect_frames(job_dir, {0})[0] == []  # dropped, never a box-less detection
    for change in (
        lambda a: {**a, "model": "egoblur-gen1"},
        lambda a: {**a, "frames": {"0": []}},  # fewer frames than asked
        lambda a: {**a, "frames": {**a["frames"], "0": [{**face, "kind": "cat"}]}},
        lambda a: {**a, "frames": {**a["frames"], "0": [{**face, "score": 7}]}},
        lambda a: {**a, "surprise": True},
        lambda a: {"refused": "no_gpu", "detail": "x", "extra": 1},
    ):
        with pytest.raises(GpuUnavailable) as caught:
            answering(change).detect_frames(job_dir, {0, 1})
        assert caught.value.reason == "bad_answer"
    detector = answering(lambda a: a)
    with pytest.raises(TypeError, match="whole renders"):
        detector.detect(None)
    with pytest.raises(ValueError, match="audits"):
        detector.detect_frames(tmp_path, {0})
    assert detector.detect_frames(job_dir, set()) == {}


def test_answers_are_cached_per_render(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    detector = GpuDetector(
        job_dir, settings, fake.call, meter(job_dir, settings), handoff=handoff(job_dir, fake.commit)
    )
    detector.prefetch()
    detector.detect_frames(job_dir, {3, 4})
    assert len(fake.requests) == 1  # served from pass 1's answers
    (job_dir / "redacted.mp4").write_bytes((job_dir / "redacted.mp4").read_bytes() + b"\0")  # a new render
    assert set(detector.detect_frames(job_dir, {3})) == {3}
    assert len(fake.requests) == 2  # the new render's frames are asked for again
    assert fake.requests[-1].frames == [3]  # only what this scan wanted


def test_the_gpu_detector_needs_egoblur(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = Settings(audit_gpu=True, egoblur_model="yunet-face", jobs_dir=str(tmp_path / "s"))
    with pytest.raises(ValueError, match="yunet-face"):
        GpuDetector(job_dir, settings, FakeModal(server(job_dir, tmp_path)).call, meter(job_dir, settings),
                    handoff=handoff(job_dir, lambda: None))  # fmt: skip


def test_the_up_front_estimate_includes_the_gpu() -> None:
    plain = Settings()
    on = Settings(audit_gpu=True)
    assert estimate_usd(None, plain) == pytest.approx(1.12)
    assert estimate_usd(60, plain) == pytest.approx(2.24)
    extra = estimate_usd(60, on) - estimate_usd(60, plain)
    # Three passes, each up to its timeout, and the idle tail, at the GPU container's hourly rate.
    assert extra == pytest.approx((3 * on.audit_gpu_timeout_s + on.audit_gpu_idle_s) * on.audit_gpu_usd_per_hour / 3600)
    assert estimate_usd(None, on) > estimate_usd(None, plain)


# ---------------------------------------------------------------------------------------------- weights


def test_egoblur_gen2_weights_are_pinned_to_the_owners_upload() -> None:
    assert detectors.EGOBLUR_GEN2_SHA256 == {
        FACE: "2ba183ff74a66752f6457846efb4379b351727d1c9eaef461ed4be8db18cc2e8",
        PLATE: "1d6b3fc37fce4158d3b7d4a364290cfeeccc86a9cd84a376c443d560f11497f4",
    }


def test_auditor_available_says_whether_any_detector_can_run(monkeypatch: pytest.MonkeyPatch) -> None:
    assert auditor_available(Settings(egoblur_weights_dir="/nonexistent"))  # EgoBlur missing: YuNet stands in
    monkeypatch.setattr(detectors, "YUNET_SHA256", "0" * 64)  # altered weights are refused
    assert not auditor_available(Settings(egoblur_model="yunet-face"))


def test_altered_egoblur_weights_fall_back_to_yunet_locally(tmp_path: Path) -> None:
    for name in (FACE, PLATE):
        (tmp_path / name).write_bytes(b"weights")
    settings = Settings(egoblur_model="egoblur-gen2", egoblur_weights_dir=str(tmp_path))
    assert detectors.load_detector(settings).model == "yunet-face"


def test_egoblur_weights_without_torch_fall_back_to_yunet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The docstring's promise: EgoBlur when it can run, else YuNet (recorded as ``yunet-face``), never a 503."""
    pins = {}
    for name in (FACE, PLATE):
        (tmp_path / name).write_bytes(b"weights")
        pins[name] = hashlib.sha256(b"weights").hexdigest()
    monkeypatch.setattr(detectors, "EGOBLUR_GEN2_SHA256", pins)

    def no_torch(*_: object, **__: object) -> None:
        raise detectors.AuditorUnavailable("EgoBlur needs the audit dependency group")

    monkeypatch.setattr(detectors, "EgoBlur", no_torch)
    settings = Settings(egoblur_model="egoblur-gen2", egoblur_weights_dir=str(tmp_path))
    assert detectors.load_detector(settings).model == "yunet-face"
    assert auditor_available(settings)


def test_auditor_availability_is_cached_until_the_weights_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = detectors.load_detector

    def counting(settings: Settings) -> detectors.Detector:
        calls.append(settings.egoblur_weights_dir)
        return real(settings)

    monkeypatch.setattr("safecut.audit.load_detector", counting)
    settings = Settings(egoblur_weights_dir=str(tmp_path))
    assert auditor_available(settings)
    assert auditor_available(settings)
    assert len(calls) == 1  # not a model load per POST /start
    (tmp_path / "gen2").mkdir()  # the folder changed (weights arriving): asked again
    assert auditor_available(settings)
    assert len(calls) == 2


# ---------------------------------------------------------------------------------------------- replay guard


def test_replay_lets_only_the_modal_control_plane_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay refuses every remote host; the GPU auditor's ``permitting`` lets exactly Modal's host (and the
    addresses it resolved to) through, and only inside its scope."""
    import socket  # noqa: PLC0415 -- imported in the test that uses it

    resolved = {"api.modal.com": "203.0.113.7", "api.meta.ai": "203.0.113.9"}

    def fake_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved[host], port))]

    def fake_connect(self: socket.socket, address: Any) -> None:
        del self, address

    netguard.block()
    monkeypatch.setitem(netguard._original, "getaddrinfo", fake_getaddrinfo)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setitem(netguard._original, "connect", fake_connect)  # pyright: ignore[reportPrivateUsage]
    try:
        with socket.socket() as sock:
            with pytest.raises(netguard.NetworkBlocked):
                socket.getaddrinfo("api.modal.com", 443)
            with netguard.permitting("api.modal.com"):
                ((*_, address),) = socket.getaddrinfo("api.modal.com", 443)
                sock.connect(address)  # the address Modal's host resolved to
                with pytest.raises(netguard.NetworkBlocked):
                    socket.getaddrinfo("api.meta.ai", 443)  # Meta stays blocked
                with pytest.raises(netguard.NetworkBlocked):
                    sock.connect(("203.0.113.9", 443))
            with pytest.raises(netguard.NetworkBlocked):
                sock.connect(address)  # the scope closed
        with pytest.raises(ValueError, match="remote host"):
            netguard.permitting("localhost").__enter__()
    finally:
        netguard.unblock()


# ---------------------------------------------------------------------------------------------- round-1 audit fixes


def test_anything_that_stops_the_gpu_path_being_set_up_still_audits(tmp_path: Path, weights: Path) -> None:
    """A job folder the GPU request can't name, a broken ledger: the audit runs on YuNet, never crashes the job."""
    job_dir = prepared(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    settings = settings_for(tmp_path).model_copy(update={"jobs_dir": str(tmp_path / "not-a-dir.sqlite" / "x")})
    (tmp_path / "not-a-dir.sqlite").write_text("a file where the ledger's folder should be")
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert audit_of(job_dir).egoblur.model == "yunet-face"
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("setup:")
    assert fake.requests == []


def test_a_handoff_commit_that_fails_is_retried_then_falls_back(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    commits: list[int] = []

    def refusing() -> None:
        commits.append(1)
        raise RuntimeError("there are open files preventing the operation")

    audit_run(job_dir, replay=True, settings=settings_for(tmp_path), gpu_call=fake.call, gpu_commit=refusing)
    assert len(commits) == 3  # once, the one retry, and the cleanup's (which fails too, logged; the cron sweeps it)
    assert fake.requests == []  # never asked the GPU about a render it might not see
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("error: handoff: RuntimeError")
    assert list(handoff_root(job_dir).iterdir()) == []  # the copy is removed on the way out
    # No GPU ran: nothing priced, nothing reserved, and the receipt never says EgoBlur was called.
    assert gpu_lines(job_dir) == []
    settings = settings_for(tmp_path)
    assert LocalLedger(Path(settings.jobs_dir) / "ledger.sqlite").spent(f"job:{job_dir.name}") == 0
    notes = sealed(job_dir, settings).data_handling.notes
    assert SYNTHETIC_NOTE in notes
    assert SYNTHETIC_GPU_NOTE not in notes


def test_the_handoff_copies_each_render_once_and_names_every_gpu(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    names = iter(["NVIDIA L4", "Tesla T4"])
    real = GpuServer(handoff_root(job_dir), weights, load=stand_in, gpu_name=lambda: next(names))
    fake = FakeModal(real)
    box = handoff(job_dir, fake.commit)
    detector = GpuDetector(job_dir, settings, fake.call, meter(job_dir, settings), handoff=box)
    detector.detect_frames(job_dir, {0})
    detector.detect_frames(job_dir, {1})
    (folder,) = handoff_root(job_dir).iterdir()  # one render, copied once, committed per call
    assert (folder / "redacted.mp4").read_bytes() == (job_dir / "redacted.mp4").read_bytes()
    assert fake.commits == 2
    assert detector.device == "cuda:NVIDIA L4+Tesla T4"  # a pass on a T4 is named too
    box.close()
    assert list(handoff_root(job_dir).iterdir()) == []


def test_without_torch_the_weights_are_never_hashed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (FACE, PLATE):
        (tmp_path / name).write_bytes(b"weights")
    hashed: list[Path] = []
    monkeypatch.setattr(detectors, "_sha256", lambda path: hashed.append(path) or detectors.YUNET_SHA256)
    monkeypatch.setattr(detectors.importlib.util, "find_spec", lambda name: None)
    settings = Settings(egoblur_model="egoblur-gen2", egoblur_weights_dir=str(tmp_path))
    assert detectors.load_detector(settings).model == "yunet-face"
    assert [p.name for p in hashed] == ["face_detection_yunet_2023mar.onnx"]  # only YuNet's own check


def test_the_cron_sweeps_handoff_folders_an_audit_left_behind(tmp_path: Path) -> None:
    import os  # noqa: PLC0415 -- imported in the test that uses it

    old, fresh = tmp_path / "j_old-0123456789abcdef", tmp_path / "j_new-0123456789abcdef"
    for folder in (old, fresh):
        folder.mkdir()
        (folder / "redacted.mp4").write_bytes(b"x")
    os.utime(old, (1_000, 1_000))
    assert sweep_handoff(tmp_path, older_than_s=3600, now=10_000) == [old.name]
    assert [p.name for p in tmp_path.iterdir()] == [fresh.name]
    assert sweep_handoff(tmp_path / "missing") == []


# ---------------------------------------------------------------------------------------------- round-2 audit fixes


@pytest.mark.parametrize("kind", ["synthetic", "replay"])
def test_a_replayed_job_audited_on_the_gpu_keeps_its_label(tmp_path: Path, weights: Path, kind: str) -> None:
    """The public demo is a synthetic replay audited on the GPU: its Modal seconds are not a model call, so its
    receipt still says it was replayed, and names the one model that ran."""
    from safecut.contracts import Intake, dump  # noqa: PLC0415 -- imported in the test that uses it

    job_dir = prepared(tmp_path)
    if kind == "synthetic":
        (job_dir / "raw").mkdir(exist_ok=True)
        (job_dir / "raw" / "manifest.json").write_text(json.dumps({"synthetic": True}))
    else:
        dump(Intake(source="clip.mp4", created_at=contracts.now_utc(), consented=False, mode="replay",
                    code_kind=None, code_id=None), job_dir / "intake.json")  # fmt: skip
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert gpu_lines(job_dir)  # Modal seconds were spent
    if kind == "replay":  # the test job's red team is the synthetic oracle; as a recorded replay it isn't synthetic
        (job_dir / "raw" / "redteam" / "synthetic_truth.json").unlink()
    notes = sealed(job_dir, settings).data_handling.notes
    expected = SYNTHETIC_GPU_NOTE if kind == "synthetic" else REPLAY_GPU_NOTE
    assert expected in notes
    assert SYNTHETIC_NOTE not in notes  # "no model was called" would be false: EgoBlur ran
    assert REPLAY_NOTE not in notes


def test_a_gpu_fallback_receipt_says_why_yunet_ran(tmp_path: Path, weights: Path) -> None:

    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), ["timeout"])
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    notes = sealed(job_dir, settings).data_handling.notes
    assert YUNET_FALLBACK_NOTE.format(reason="timeout") in notes
    assert YUNET_NOTE not in notes  # the weights are installed; the GPU timed out


def test_the_handoff_waits_for_another_process_writing_the_same_mount(tmp_path: Path) -> None:
    """The API and its demo-build child share the handoff mount: one's commit must never meet the other's open file."""
    import subprocess  # noqa: PLC0415 -- imported in the test that uses it
    import sys  # noqa: PLC0415 -- imported in the test that uses it
    import time  # noqa: PLC0415 -- imported in the test that uses it

    job_dir = prepared(tmp_path)
    lock = tmp_path / "handoff.lock"
    holder = subprocess.Popen(  # noqa: S603 -- this interpreter, a fixed script
        [sys.executable, "-c", "import fcntl, sys, time; f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX);"
         " print('locked', flush=True); time.sleep(1.5)", str(lock)],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "locked"
    box = Handoff(tmp_path / "handoff", lambda: None, lock_file=lock)
    started = time.monotonic()
    box.put(job_dir, "0" * 64)
    assert time.monotonic() - started >= 1.0  # waited for the other process to finish with the mount
    holder.wait(10)


def test_a_commit_that_hangs_falls_back_instead_of_holding_every_audit(tmp_path: Path, weights: Path) -> None:
    import threading  # noqa: PLC0415 -- imported in the test that uses it

    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    stuck = threading.Event()

    def hung() -> None:
        stuck.wait(30)

    box = Handoff(handoff_root(job_dir), hung, commit_timeout_s=0.2, lock_file=tmp_path / "l")
    detector = GpuDetector(job_dir, settings, fake.call, meter(job_dir, settings), handoff=box)
    with pytest.raises(GpuUnavailable) as caught:
        detector.prefetch()
    stuck.set()
    assert caught.value.reason == "timeout"
    assert "handoff commit" in str(caught.value)
    assert fake.requests == []
    assert not (job_dir / "cost.jsonl").exists() or gpu_lines(job_dir) == []  # a hung commit isn't GPU time
    box.put(job_dir, "1" * 64)  # the lock was released: the next audit isn't blocked behind the hung one


def test_a_stale_handoff_copy_is_discarded_before_the_retry(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), ["stale", None])
    box = handoff(job_dir, fake.commit)
    removed: list[str] = []
    real = box.discard

    def counting(name: str) -> None:
        removed.append(name)
        real(name)

    box.discard = counting  # type: ignore[method-assign] -- a stand-in for the test, on purpose
    detector = GpuDetector(job_dir, settings, fake.call, meter(job_dir, settings), handoff=box,
                           sleep=lambda _s: None)  # fmt: skip
    detector.prefetch()
    assert removed == [fake.requests[0].job]  # the copy the GPU disagreed with went before the retry re-copied it
    assert detector.failure is None


# ---------------------------------------------------------------------------------------------- round-4 audit fixes


def test_the_estimate_counts_one_gpu_scan_per_audit_pass() -> None:
    from safecut.api.access import GPU_SCANS_PER_JOB  # noqa: PLC0415 -- imported in the test that uses it
    from safecut.audit.loop import MAX_PASSES  # noqa: PLC0415 -- imported in the test that uses it

    assert GPU_SCANS_PER_JOB == MAX_PASSES


def test_an_unreadable_render_is_refused_not_retried(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    srv = server(job_dir, weights)
    box = handoff(job_dir, lambda: None)
    name = box.put(job_dir, "2" * 64)
    (handoff_root(job_dir) / name / "redacted.mp4").write_bytes(b"not a video")
    request = {"job": name, "frames": [0], "model": "egoblur-gen2", "face_threshold": 0.5, "plate_threshold": 0.5}
    assert srv.serve(request)["refused"] == "no_render"
    (handoff_root(job_dir) / name / "job.json").write_text("{}")
    assert srv.serve(request)["refused"] == "no_render"


def test_a_paid_gpu_call_that_didnt_answer_still_isnt_no_model_called(tmp_path: Path, weights: Path) -> None:
    """A synthetic job whose GPU scan was paid but timed out, so YuNet audited: the receipt doesn't say "no model was
    called"; it names the call, and the YuNet note says why."""
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), ["timeout"])
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert audit_of(job_dir).egoblur.model == "yunet-face"
    notes = sealed(job_dir, settings).data_handling.notes
    assert SYNTHETIC_GPU_NOTE in notes
    assert SYNTHETIC_NOTE not in notes
    run = json.loads((job_dir / "raw/audit/run.json").read_text())
    assert (run["detector"], run["gpu_calls"]) == ("yunet-face", 0)  # the audit that stands ran on YuNet
    record = json.loads((job_dir / GPU_RECORD).read_text())
    assert record["gpu_calls"] == 1  # but the paid, timed-out call is on record, as in cost.jsonl
    assert len(gpu_lines(job_dir)) == 1


def test_run_json_records_the_gpu_time(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    run = json.loads((job_dir / "raw/audit/run.json").read_text())
    assert run["gpu_calls"] == 1
    assert run["gpu_wall_s"] > 0


# ---------------------------------------------------------------------------------------------- round-6 audit fixes


def test_a_job_waiting_on_the_gpu_never_keeps_a_finished_interpreter_alive() -> None:
    """A container replaced mid-scan exits at once: the Modal call waits on a daemon thread, not an executor's."""
    import subprocess  # noqa: PLC0415 -- imported in the test that uses it
    import sys  # noqa: PLC0415 -- imported in the test that uses it
    import time  # noqa: PLC0415 -- imported in the test that uses it

    script = (
        "import threading, time\n"
        "from safecut.audit.gpu import off_loop\n"
        "threading.Thread(target=lambda: off_loop(lambda: time.sleep(60)), daemon=True).start()\n"
        "time.sleep(0.3)\n"
        "print('exiting', flush=True)\n"
    )
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False)  # noqa: S603 -- fixed argv: this interpreter and our own code
    assert proc.returncode == 0, proc.stderr
    assert time.monotonic() - started < 20  # not the 60 s call


def test_on_daemon_answers_raises_and_times_out() -> None:
    import threading  # noqa: PLC0415 -- imported in the test that uses it

    assert gpu.on_daemon(lambda: 7) == 7

    def failing() -> int:
        raise ConnectionError("Modal unreachable")

    with pytest.raises(ConnectionError, match="unreachable"):
        gpu.on_daemon(failing)
    gate = threading.Event()

    def blocked() -> bool:
        return gate.wait(30)

    with pytest.raises(TimeoutError):
        gpu.on_daemon(blocked, timeout_s=0.1)
    gate.set()


# ---------------------------------------------------------------------------------------------- round-7 audit fixes


@pytest.mark.parametrize("failure", [TimeoutError("no output"), ConnectionError("Modal client lost the server")])
def test_a_gpu_call_we_stop_waiting_for_is_cancelled(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    """Timed out or errored after the spawn: the scan is cancelled with its container, never left running unpriced."""
    from types import SimpleNamespace  # noqa: PLC0415 -- imported in the test that uses it

    cancelled: list[bool] = []

    class Handle:
        object_id = "fc-1"

        def get(self, timeout: float) -> dict[str, Any]:
            del timeout
            raise failure

        def cancel(self, terminate_containers: bool = False) -> None:
            cancelled.append(terminate_containers)

    function = SimpleNamespace(spawn=lambda request: Handle())
    fake_modal = SimpleNamespace(
        Function=SimpleNamespace(from_name=lambda app, name: function),
        exception=SimpleNamespace(TimeoutError=type("ModalTimeout", (Exception,), {})),
        config=SimpleNamespace(config={"server_url": "https://api.modal.com"}),
    )
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    call = gpu.modal_call(Settings(audit_gpu=True))
    request = GpuRequest(job="j_x-0123456789abcdef", frames=[0], model="egoblur-gen2", face_threshold=0.5,
                         plate_threshold=0.5)  # fmt: skip
    with pytest.raises(type(failure)):
        call(request, 1.0)
    assert cancelled == [True]


# ---------------------------------------------------------------------------------------------- round-8 audit fixes


def test_replay_reaches_every_host_of_modals_default_server_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """modal 1.6.2's default ``server_url`` lists two hosts, comma-separated: both are let through, nothing else."""
    import socket  # noqa: PLC0415 -- the guard patches it; imported where the test uses it
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal config, local to this test

    import modal.config  # noqa: PLC0415 -- the deploy group: its real default, not a copy

    fake_modal = SimpleNamespace(config=SimpleNamespace(config={"server_url": modal.config.DEFAULT_SERVER_URL}))
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    assert gpu.modal_hosts() == ["api.modal.com", "api.modal2.com"]
    resolved = {"api.modal.com": "203.0.113.7", "api.modal2.com": "203.0.113.8", "api.meta.ai": "203.0.113.9"}

    def fake_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved[host], port))]

    netguard.block()
    monkeypatch.setitem(netguard._original, "getaddrinfo", fake_getaddrinfo)  # pyright: ignore[reportPrivateUsage]
    try:
        with gpu.modal_permitted():
            socket.getaddrinfo("api.modal.com", 443)
            socket.getaddrinfo("api.modal2.com", 443)  # the client's fallback host too
            with pytest.raises(netguard.NetworkBlocked):
                socket.getaddrinfo("api.meta.ai", 443)
        with pytest.raises(netguard.NetworkBlocked):
            socket.getaddrinfo("api.modal.com", 443)
    finally:
        netguard.unblock()


def test_a_call_that_never_reached_modal_costs_and_claims_nothing(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), ["unspawned", "unspawned"])
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    assert json.loads((job_dir / GPU_RECORD).read_text())["fallback"].startswith("error: not submitted:")
    assert gpu_lines(job_dir) == []  # no GPU ran: nothing priced
    assert LocalLedger(Path(settings.jobs_dir) / "ledger.sqlite").spent(f"job:{job_dir.name}") == 0
    notes = sealed(job_dir, settings).data_handling.notes
    assert SYNTHETIC_NOTE in notes
    assert SYNTHETIC_GPU_NOTE not in notes


# ---------------------------------------------------------------------------------------------- round-9 audit fixes


def test_a_modal_lookup_that_fails_is_not_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real wrapper: a failure before Modal accepts the call (the function isn't deployed) is NotSubmitted."""
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal, local to this test

    def missing(app: str, name: str) -> Any:
        raise LookupError(f"{app}/{name} isn't deployed")

    fake_modal = SimpleNamespace(
        Function=SimpleNamespace(from_name=missing),
        exception=SimpleNamespace(TimeoutError=type("ModalTimeout", (Exception,), {})),
        config=SimpleNamespace(config={"server_url": "https://api.modal.com"}),
    )
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    request = GpuRequest(job="j_x-0123456789abcdef", frames=[0], model="egoblur-gen2", face_threshold=0.5,
                         plate_threshold=0.5)  # fmt: skip
    with pytest.raises(gpu.NotSubmitted, match="isn't deployed"):
        gpu.modal_call(Settings(audit_gpu=True))(request, 1.0)


def test_after_a_failure_the_gpu_is_never_called_again_in_that_audit(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights), [None, "timeout"])
    detector = GpuDetector(
        job_dir, settings, fake.call, meter(job_dir, settings), handoff=handoff(job_dir, fake.commit)
    )
    detector.prefetch()
    (job_dir / "redacted.mp4").write_bytes((job_dir / "redacted.mp4").read_bytes() + b"\0")  # a re-render
    with pytest.raises(GpuUnavailable):
        detector.detect_frames(job_dir, {1})
    asked = len(fake.requests)
    with pytest.raises(GpuUnavailable):
        detector.detect_frames(job_dir, {2})
    assert len(fake.requests) == asked  # no second paid timeout


# ---------------------------------------------------------------------------------------------- round-10 audit fixes


def test_a_permit_that_fails_is_not_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The replay permit is set up inside NotSubmitted: a server_url it can't permit (a loopback dev server) means no
    call was made, so nothing is priced."""
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal, local to this test

    spawned: list[object] = []
    fake_modal = SimpleNamespace(
        Function=SimpleNamespace(from_name=lambda app, name: SimpleNamespace(spawn=spawned.append)),
        exception=SimpleNamespace(TimeoutError=type("ModalTimeout", (Exception,), {})),
        config=SimpleNamespace(config={"server_url": "http://localhost:8889"}),
    )
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    request = GpuRequest(job="j_x-0123456789abcdef", frames=[0], model="egoblur-gen2", face_threshold=0.5,
                         plate_threshold=0.5)  # fmt: skip
    with pytest.raises(gpu.NotSubmitted, match="remote host"):
        gpu.modal_call(Settings(audit_gpu=True))(request, 1.0)
    assert spawned == []


def test_the_sweep_keeps_the_privacy_pages_hour() -> None:
    """A copy a cut-short check left is gone within the hour: the sweep's age plus the cron's period."""
    import re  # noqa: PLC0415 -- imported in the test that uses it

    from safecut.api.store import HANDOFF_GRACE_S  # noqa: PLC0415 -- imported in the test that uses it

    source = (ROOT / "deploy" / "modal_app.py").read_text()
    period = int(re.search(r"schedule=modal\.Period\(minutes=(\d+)\)", source).group(1))  # type: ignore[union-attr] -- the cron exists (test_deploy)
    assert HANDOFF_GRACE_S + period * 60 + 10 * 60 <= 3600  # ten minutes left for the cron's own latency
    privacy = (ROOT / "web" / "src" / "app" / "privacy" / "page.tsx").read_text()
    assert "within the hour if the check is cut short" in privacy


# ---------------------------------------------------------------------------------------------- round-14 audit fixes


def _reseal(job_dir: Path, change: Callable[[dict[str, Any]], None]) -> None:
    """Edit a sealed receipt and seal it again (a valid hash over the edit), as a forger would."""
    from safecut.contracts import ReceiptBody, receipt_hash  # noqa: PLC0415 -- imported in the test that uses it

    path = job_dir / "receipt.json"
    data = json.loads(path.read_text())
    change(data)
    data.pop("hash")
    data["hash"] = receipt_hash(ReceiptBody.model_validate(data))
    path.write_text(json.dumps(data))


def test_a_receipt_that_claims_another_device_or_gpu_cost_never_validates(tmp_path: Path, weights: Path) -> None:
    """validate_job_dir holds the receipt to audit.json's device and to cost.jsonl's Modal lines: a receipt claiming
    EgoBlur on a GPU that audit.json doesn't record, or a GPU cost the cost lines don't add up to, never publishes."""
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    fake = FakeModal(server(job_dir, weights))
    audit_run(job_dir, replay=True, settings=settings, gpu_call=fake.call, gpu_commit=fake.commit)
    sealed(job_dir, settings)
    original = (job_dir / "receipt.json").read_text()

    def other_device(data: dict[str, Any]) -> None:
        data["audit"]["auditor_device"] = "cuda:NVIDIA H100"

    _reseal(job_dir, other_device)
    with pytest.raises(contracts.ContractError, match="auditor_device"):
        contracts.validate_job_dir(job_dir)
    (job_dir / "receipt.json").write_text(original)

    def other_cost(data: dict[str, Any]) -> None:
        data["cost_usd_gpu"] = round(data["cost_usd_gpu"] + 1.0, 6)

    _reseal(job_dir, other_cost)
    with pytest.raises(contracts.ContractError, match="cost_usd_gpu"):
        contracts.validate_job_dir(job_dir)
    (job_dir / "receipt.json").write_text(original)
    contracts.validate_job_dir(job_dir)  # the untouched receipt still validates


def test_each_render_is_copied_to_the_handoff_once(tmp_path: Path, weights: Path) -> None:
    job_dir = prepared(tmp_path)
    box = handoff(job_dir, lambda: None)
    name = box.put(job_dir, "3" * 64)
    copied = handoff_root(job_dir) / name / "redacted.mp4"
    first = copied.stat().st_mtime_ns
    import time  # noqa: PLC0415 -- imported in the test that uses it

    time.sleep(0.01)
    import os  # noqa: PLC0415 -- imported in the test that uses it

    os.utime(copied.parent, (1_000, 1_000))  # long in use: the sweep would take it
    assert box.put(job_dir, "3" * 64) == name
    assert copied.stat().st_mtime_ns == first  # not copied again
    assert copied.parent.stat().st_mtime > 1_000_000  # but its age refreshed, so the sweep never takes it mid-audit


def test_a_gpu_call_is_reserved_at_its_worst_case_with_the_idle_tail(tmp_path: Path) -> None:
    job_dir = prepared(tmp_path)
    settings = settings_for(tmp_path)
    reserved: list[float] = []

    class Ledger(LocalLedger):
        def reserve(self, call_id: str, job_id: str | None, usd: float, limits: Any) -> None:
            reserved.append(usd)
            super().reserve(call_id, job_id, usd, limits)

    box = GpuMeter(settings, Ledger(tmp_path / "l.sqlite"), Caller.local(), job_dir.name, job_dir / "cost.jsonl")
    box.reserve("c1")
    expected = (settings.audit_gpu_timeout_s + settings.audit_gpu_idle_s) * settings.audit_gpu_usd_per_hour / 3600
    assert reserved == [pytest.approx(expected)]


# ---------------------------------------------------------------------------------------------- round-16 audit fixes


def test_the_handoff_commit_commits_the_handoff_volume_inside_the_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager  # noqa: PLC0415 -- a recording permit, local to this test
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal, local to this test

    inside: list[bool] = []
    events: list[tuple[str, str, bool]] = []

    @contextmanager
    def permit() -> Any:
        inside.append(True)
        yield
        inside.pop()

    def from_name(name: str) -> Any:
        def commit() -> None:
            events.append(("commit", name, bool(inside)))
            if name == "broken":
                raise RuntimeError("Volume commit failed")

        return SimpleNamespace(commit=commit)

    monkeypatch.setattr(gpu, "_modal", lambda: SimpleNamespace(Volume=SimpleNamespace(from_name=from_name)))
    monkeypatch.setattr(gpu, "modal_permitted", permit)
    gpu.modal_commit(Settings())()
    assert events == [("commit", "safecut-audit", True)]
    with pytest.raises(RuntimeError, match="commit failed"):
        gpu.modal_commit(Settings(audit_gpu_volume="broken"))()


def test_the_handoff_copy_never_carries_the_uploads_file_name(tmp_path: Path) -> None:
    from safecut.contracts import Job, dump  # noqa: PLC0415 -- imported in the test that uses it

    job_dir = prepared(tmp_path)
    job = load(job_dir / "job.json", Job)
    dump(job.model_copy(update={"source": "Amina_birthday_party.mov"}), job_dir / "job.json")
    name = handoff(job_dir, lambda: None).put(job_dir, "4" * 64)
    copied = (handoff_root(job_dir) / name / "job.json").read_text()
    assert "Amina" not in copied
    assert load(handoff_root(job_dir) / name / "job.json", Job).frames == job.frames  # what the GPU needs is kept


# ---------------------------------------------------------------------------------------------- round-21 audit fixes


@pytest.mark.parametrize("stall", ["spawn", "cancel"])
def test_a_control_plane_that_stalls_is_a_timeout_not_a_hung_audit(monkeypatch: pytest.MonkeyPatch, stall: str) -> None:
    """Only the wait used to be bounded: a spawn that never returns, or a cancel after a timeout that never returns,
    held the audit (and its job) until the hold's limit. The whole call is bounded now, by the timeout itself."""
    import threading  # noqa: PLC0415 -- imported in the test that uses it
    import time  # noqa: PLC0415 -- imported in the test that uses it
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal, local to this test

    gate = threading.Event()
    modal_timeout = type("ModalTimeout", (Exception,), {})

    class Handle:
        object_id = "fc-1"

        def get(self, timeout: float) -> dict[str, Any]:
            del timeout
            raise modal_timeout("no output")

        def cancel(self, terminate_containers: bool = False) -> None:
            del terminate_containers
            gate.wait(30)

    def spawn(request: object) -> Handle:
        del request
        if stall == "spawn":
            gate.wait(30)
        return Handle()

    fake_modal = SimpleNamespace(
        Function=SimpleNamespace(from_name=lambda app, name: SimpleNamespace(spawn=spawn)),
        exception=SimpleNamespace(TimeoutError=modal_timeout),
        config=SimpleNamespace(config={"server_url": "https://api.modal.com"}),
    )
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    request = GpuRequest(job="j_x-0123456789abcdef", frames=[0], model="egoblur-gen2", face_threshold=0.5,
                         plate_threshold=0.5)  # fmt: skip
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            gpu.modal_call(Settings(audit_gpu=True))(request, 0.1)
        assert time.monotonic() - started < 5
    finally:
        gate.set()


def stand_in_modal(spawn: Callable[[object], Any]) -> tuple[Any, type[Exception]]:
    from types import SimpleNamespace  # noqa: PLC0415 -- a stand-in Modal, local to these tests

    modal_timeout = type("ModalTimeout", (Exception,), {})
    return SimpleNamespace(
        Function=SimpleNamespace(from_name=lambda app, name: SimpleNamespace(spawn=spawn)),
        exception=SimpleNamespace(TimeoutError=modal_timeout),
        config=SimpleNamespace(config={"server_url": "https://api.modal.com"}),
    ), modal_timeout


GPU_REQUEST = GpuRequest(job="j_x-0123456789abcdef", frames=[0], model="egoblur-gen2", face_threshold=0.5,
                         plate_threshold=0.5)  # fmt: skip


def test_a_timed_out_call_and_its_cancel_fit_inside_the_reserved_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """The meter reserves for ``timeout_s``: the wait leaves room for the cancel, so a call that times out and is
    cancelled is still settled inside its reservation."""
    import threading  # noqa: PLC0415 -- imported in the test that uses it
    import time  # noqa: PLC0415 -- imported in the test that uses it

    waited: list[float] = []
    cancelled = threading.Event()

    class Handle:
        object_id = "fc-1"

        def get(self, timeout: float) -> dict[str, Any]:
            waited.append(timeout)
            time.sleep(timeout)
            raise modal_timeout("no output")

        def cancel(self, terminate_containers: bool = False) -> None:
            del terminate_containers
            time.sleep(0.2)  # the control plane takes a moment to stop it
            cancelled.set()

    fake_modal, modal_timeout = stand_in_modal(lambda request: Handle())
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    monkeypatch.setattr(gpu, "CANCEL_MARGIN_S", 0.3)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="no output"):  # the scan's own timeout, not the outer bound
        gpu.modal_call(Settings(audit_gpu=True))(GPU_REQUEST, 1.6)
    elapsed = time.monotonic() - started
    assert cancelled.is_set()
    assert len(waited) == 1
    assert waited[0] <= 1.6 - 0.3  # the wait left the cancel its margin inside the bound
    assert elapsed < 1.6 + 0.4  # and the call ended about there (the slack is the scheduler's, under load)


def test_a_spawn_that_returns_after_the_bound_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The audit has fallen back to YuNet by then: the late scan must not run unwatched and unpriced."""
    import threading  # noqa: PLC0415 -- imported in the test that uses it

    gate = threading.Event()
    cancelled = threading.Event()
    waited: list[float] = []

    class Handle:
        object_id = "fc-late"

        def get(self, timeout: float) -> dict[str, Any]:
            waited.append(timeout)
            return {}

        def cancel(self, terminate_containers: bool = False) -> None:
            assert terminate_containers
            cancelled.set()

    def spawn(request: object) -> Handle:
        del request
        gate.wait(30)
        return Handle()

    fake_modal, _ = stand_in_modal(spawn)
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    with pytest.raises(TimeoutError):
        gpu.modal_call(Settings(audit_gpu=True))(GPU_REQUEST, 0.2)
    gate.set()  # the control plane comes back: the spawn returns
    assert cancelled.wait(5)
    assert waited == []  # never waited on


# ---------------------------------------------------------------------------------------------- round-23 audit fixes


def test_a_short_timeout_keeps_most_of_its_bound_for_the_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel's margin is at most a quarter of the bound: a timeout shorter than ``CANCEL_MARGIN_S`` still
    waits about three quarters of it for the scan, never zero."""
    import time  # noqa: PLC0415 -- imported in the test that uses it

    waited: list[float] = []

    class Handle:
        object_id = "fc-short"

        def get(self, timeout: float) -> dict[str, Any]:
            waited.append(timeout)
            time.sleep(timeout)
            raise modal_timeout("no output")

        def cancel(self, terminate_containers: bool = False) -> None:
            del terminate_containers

    fake_modal, modal_timeout = stand_in_modal(lambda request: Handle())
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    assert gpu.CANCEL_MARGIN_S > 1.6  # the default margin: longer than this whole bound
    with pytest.raises(TimeoutError, match="no output"):
        gpu.modal_call(Settings(audit_gpu=True))(GPU_REQUEST, 1.6)
    assert len(waited) == 1
    assert 1.6 * 0.7 <= waited[0] <= 1.6 * 0.75 + 0.01


# ---------------------------------------------------------------------------------------------- round-29 audit fixes


class BrokenLedger:
    """A ledger whose reservation works and whose settle and release fail (a locked or full disk)."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def reserve(self, *args: object) -> None:
        self.asked.append("reserve")

    def settle(self, call_id: str, usd: float) -> None:
        self.asked.append("settle")
        raise OSError("disk I/O error")

    def release(self, call_id: str) -> None:
        self.asked.append("release")
        raise OSError("disk I/O error")


def test_the_gpu_meter_never_raises_after_a_call(tmp_path: Path) -> None:
    """``settle`` and ``release`` run in the GPU call's ``finally``: a ledger or ``cost.jsonl`` that fails there is
    logged, never raised, so a scan's good answer is never swapped for an error (and a second, paid call)."""
    ledger = BrokenLedger()
    unwritable = tmp_path / "cost.jsonl"
    unwritable.mkdir()  # a folder where the cost file goes: every append fails with an OSError
    gauge = GpuMeter(settings_for(tmp_path), ledger, Caller.local(), "j_x-0123456789abcdef", unwritable)  # type: ignore[arg-type] -- a stand-in ledger, on purpose
    gauge.reserve("gpu-1")
    gauge.settle("gpu-1", 12.0, "egoblur-gen2", "fc-1")
    gauge.reserve("gpu-2")
    gauge.release("gpu-2")
    assert ledger.asked == ["reserve", "settle", "reserve", "release"]


def test_a_gpu_answer_that_isnt_an_object_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handle:
        object_id = "fc-list"

        def get(self, timeout: float) -> list[object]:
            del timeout
            return ["not", "an", "answer"]

    fake_modal, _ = stand_in_modal(lambda request: Handle())
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    with pytest.raises(TypeError, match="answered a list"):
        gpu.modal_call(Settings(audit_gpu=True))(GPU_REQUEST, 5.0)


def test_a_cancel_that_fails_still_reports_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel is best effort (Modal's own function timeout ends the scan): its failure never hides the timeout
    the audit falls back on."""
    cancels: list[bool] = []

    class Handle:
        object_id = "fc-stuck"

        def get(self, timeout: float) -> dict[str, Any]:
            del timeout
            raise modal_timeout("no output")

        def cancel(self, terminate_containers: bool = False) -> None:
            cancels.append(terminate_containers)
            raise ConnectionError("Modal control plane: 503")

    fake_modal, modal_timeout = stand_in_modal(lambda request: Handle())
    monkeypatch.setattr(gpu, "_modal", lambda: fake_modal)
    with pytest.raises(TimeoutError, match="no output"):
        gpu.modal_call(Settings(audit_gpu=True))(GPU_REQUEST, 5.0)
    assert cancels == [True]
