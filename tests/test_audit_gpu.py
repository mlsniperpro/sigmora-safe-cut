"""WP4: the GPU auditor hook (a Modal function in deploy) round-trips frames losslessly and its answers are checked."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from safecut.audit import auditor_available, detectors, gpu
from safecut.audit.detectors import YuNet
from safecut.config import Settings
from tests.safety_jobs import Scenario, frame_image


def test_a_remote_detector_sees_exactly_the_rendered_pixels() -> None:
    frame = frame_image(Scenario(), 30)
    assert (gpu.decode(gpu.encode(frame)) == frame).all()
    local = YuNet()
    remote = gpu.RemoteDetector("yunet-face", lambda png: gpu.detect_png(local, png), plates=False)
    assert remote.model == "yunet-face"
    assert not remote.detects_plates
    assert remote.detect(frame) == local.detect(frame)


def test_a_remote_answer_is_validated() -> None:
    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    bad = gpu.RemoteDetector("egoblur-gen2", lambda _png: [{"kind": "cat", "box": [0, 0, 5, 5], "score": 0.9}])
    with pytest.raises(ValueError, match="cat"):
        bad.detect(frame)
    outside = gpu.RemoteDetector("egoblur-gen2", lambda _png: [{"kind": "plate", "box": [40, 0, 50, 5], "score": 0.9}])
    assert outside.detect(frame) == []
    clipped = gpu.RemoteDetector(
        "egoblur-gen2", lambda _png: [{"kind": "face", "box": [-2.5, 1.2, 9.1, 25], "score": 1}]
    )
    (d,) = clipped.detect(frame)
    assert d.box == (0, 1, 10, 20)
    with pytest.raises(ValueError, match="decode"):
        gpu.decode(b"not a png")


def test_auditor_available_says_whether_any_detector_can_run(monkeypatch: pytest.MonkeyPatch) -> None:
    assert auditor_available(Settings(egoblur_weights_dir="/nonexistent"))  # EgoBlur missing: YuNet stands in
    monkeypatch.setattr(detectors, "YUNET_SHA256", "0" * 64)  # altered weights are refused
    assert not auditor_available(Settings(egoblur_model="yunet-face"))


def test_egoblur_weights_without_torch_fall_back_to_yunet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The docstring's promise: EgoBlur when it can run, else YuNet (recorded as ``yunet-face``), never a 503."""
    for name in ("ego_blur_face_gen2.jit", "ego_blur_lp_gen2.jit"):
        (tmp_path / name).write_bytes(b"weights")

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
