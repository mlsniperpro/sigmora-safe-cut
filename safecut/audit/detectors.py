"""Face and plate detectors for the audit, behind one interface (WP4 step 2; ``docs/research/egoblur-gen2.md``).

* **EgoBlur Gen 2 / Gen 1** (Meta, Apache-2.0): face and licence-plate TorchScript detectors from Meta's gated
  download (owner step O8), read from ``SAFECUT_EGOBLUR_WEIGHTS_DIR``. Run at ``score_threshold`` 0.5 (a miss is a
  leak, a false alarm only an extra patch), Gen 2 NMS 0.5, BGR frames, ``ResizeShortestEdge(1200, 1200)``.
* **YuNet** (OpenCV zoo, MIT, bundled in ``weights/`` with its licence): faces only, so ``plates`` is null and
  plates fall to the red-team. It runs offline in milliseconds per frame on CPU.

:func:`load_detector` resolves what actually runs: EgoBlur when asked for and its weights are installed, else
YuNet, and the audit records the detector that ran (``audit.egoblur.model``, the receipt's ``auditor``), never the
one that was asked for (AGENTS rule 9).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import cv2
import numpy as np

from safecut.config import Settings
from safecut.decide.geometry import BoxT, clamp
from safecut.render.draw import Frame

log = logging.getLogger(__name__)

AuditorModel = Literal["egoblur-gen2", "egoblur-gen1", "yunet-face"]
DetectionKind = Literal["face", "plate"]

YUNET_PATH = Path(__file__).parent / "weights" / "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
#: OpenCV zoo's YuNet defaults: NMS 0.3, keep at most 5000 candidates.
YUNET_NMS = 0.3
YUNET_TOP_K = 5000
#: egoblur-gen2.md: Gen 2's own NMS default (the code's 0.5; the README's 0.3 is out of date), Gen 1's 0.3.
EGOBLUR_NMS = {"egoblur-gen2": 0.5, "egoblur-gen1": 0.3}
EGOBLUR_RESIZE = {"min_size_test": 1200, "max_size_test": 1200}
#: The Gen 2 TorchScript files from Meta's gated download, as uploaded to the ``safecut-models`` Volume (owner,
#: 2026-10-31). A file that doesn't match is never loaded.
EGOBLUR_GEN2_SHA256 = {
    "ego_blur_face_gen2.jit": "2ba183ff74a66752f6457846efb4379b351727d1c9eaef461ed4be8db18cc2e8",
    "ego_blur_lp_gen2.jit": "1d6b3fc37fce4158d3b7d4a364290cfeeccc86a9cd84a376c443d560f11497f4",
}


class AuditorUnavailable(RuntimeError):
    """The detector can't run here (missing or corrupt weights, a missing runtime)."""


@dataclass(frozen=True)
class Detection:
    kind: DetectionKind
    box: BoxT
    score: float


class Detector(Protocol):
    @property
    def model(self) -> AuditorModel: ...

    @property
    def detects_plates(self) -> bool: ...

    def detect(self, frame: Frame) -> list[Detection]: ...


def device_of(detector: Detector) -> str | None:
    """Where the detector ran: ``cpu``, ``cuda:0`` (a local GPU) or ``cuda:<GPU name>`` (the Modal GPU function)."""
    device = getattr(detector, "device", None)
    return device if isinstance(device, str) else None


def to_box(xyxy: tuple[float, float, float, float], width: int, height: int) -> BoxT | None:
    """A float detector box as a half-open int box: ``floor`` the corner, ``ceil`` the far corner, clamped."""
    x1, y1, x2, y2 = xyxy
    return clamp((math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2)), width, height)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_egoblur(face: Path, plate: Path, model: AuditorModel) -> None:
    """Refuse Gen 2 weights whose SHA-256 isn't Meta's (a truncated upload, the wrong file). Gen 1 has no pinned
    hashes here: it only ever runs on a machine the owner set up by hand."""
    if model != "egoblur-gen2":
        return
    for path in (face, plate):
        expected = EGOBLUR_GEN2_SHA256.get(path.name)
        if expected is None or _sha256(path) != expected:
            raise AuditorUnavailable(f"EgoBlur weights altered or unknown: {path.name} (SHA-256 mismatch)")


class YuNet:
    """OpenCV's YuNet face detector (``cv2.FaceDetectorYN``) on the bundled, hash-checked weights."""

    def __init__(self, threshold: float = 0.5, weights: Path = YUNET_PATH) -> None:
        if not weights.is_file() or _sha256(weights) != YUNET_SHA256:
            raise AuditorUnavailable(f"YuNet weights missing or altered: {weights.name}")
        self._net = cv2.FaceDetectorYN.create(str(weights), "", (320, 320), threshold, YUNET_NMS, YUNET_TOP_K)
        self._size: tuple[int, int] | None = None

    @property
    def model(self) -> AuditorModel:
        return "yunet-face"

    @property
    def device(self) -> str:
        return "cpu"

    @property
    def detects_plates(self) -> bool:
        return False

    def detect(self, frame: Frame) -> list[Detection]:
        height, width = frame.shape[:2]
        if self._size != (width, height):
            self._net.setInputSize((width, height))
            self._size = (width, height)
        faces: Any = self._net.detect(frame)[1]  # None when nothing was found (OpenCV's stub omits it)
        out: list[Detection] = []
        if faces is None:
            return out
        for row in np.asarray(faces, dtype=np.float64):
            x, y, w, h, score = float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[-1])
            box = to_box((x, y, x + w, y + h), width, height)
            if box is not None:
                out.append(Detection("face", box, score))
        return out


def egoblur_weights(weights_dir: Path, model: AuditorModel) -> tuple[Path, Path] | None:
    """The face and plate ``.jit`` files for ``model``, directly in ``weights_dir`` or in its ``gen1/``/``gen2/``
    folder (the layout of owner step O8), or None when either is missing."""
    gen = "gen2" if model == "egoblur-gen2" else "gen1"
    for folder in (weights_dir, weights_dir / gen):
        face, plate = folder / f"ego_blur_face_{gen}.jit", folder / f"ego_blur_lp_{gen}.jit"
        if face.is_file() and plate.is_file():
            return face, plate
    return None


class EgoBlur:
    """Meta's EgoBlur face and plate detectors (two models, two passes per frame)."""

    def __init__(self, model: AuditorModel, face: Path, plate: Path, *, face_threshold: float, plate_threshold: float):
        try:
            self._torch: Any = importlib.import_module("torch")
            gen = "gen2" if model == "egoblur-gen2" else "gen1"
            self._predictor: Any = importlib.import_module(f"{gen}.script.predictor") if gen == "gen2" else None
            self._ops: Any = importlib.import_module("torchvision.ops")
        except ImportError as exc:
            raise AuditorUnavailable("EgoBlur needs the audit dependency group (uv sync --group audit)") from exc
        self._model: AuditorModel = model
        self._device = "cuda:0" if self._torch.cuda.is_available() else "cpu"
        self._thresholds = {"face": face_threshold, "plate": plate_threshold}
        self._nets: dict[DetectionKind, Any] = {}
        pairs: tuple[tuple[DetectionKind, Path], ...] = (("face", face), ("plate", plate))
        for kind, path in pairs:
            if self._predictor is not None:
                cls = self._predictor.ClassID.FACE if kind == "face" else self._predictor.ClassID.LICENSE_PLATE
                self._nets[kind] = self._predictor.EgoblurDetector(
                    model_path=str(path),
                    device=self._device,
                    detection_class=cls,
                    score_threshold=self._thresholds[kind],
                    nms_iou_threshold=EGOBLUR_NMS[model],
                    resize_aug=EGOBLUR_RESIZE,
                    use_gpu_resize=True,  # F.interpolate: works on CPU tensors too, no PIL round trip
                )
            else:
                self._nets[kind] = self._torch.jit.load(str(path), map_location=self._device).eval()

    @property
    def model(self) -> AuditorModel:
        return self._model

    @property
    def detects_plates(self) -> bool:
        return True

    @property
    def device(self) -> str:
        return self._device

    def detect(self, frame: Frame) -> list[Detection]:
        height, width = frame.shape[:2]
        tensor = self._torch.from_numpy(np.ascontiguousarray(frame.transpose(2, 0, 1))).to(self._device)
        out: list[Detection] = []
        for kind, net in self._nets.items():
            for x1, y1, x2, y2, score in self._run(kind, net, tensor):
                box = to_box((x1, y1, x2, y2), width, height)
                if box is not None:
                    out.append(Detection(kind, box, score))
        return out

    def _run(self, kind: DetectionKind, net: Any, tensor: Any) -> list[tuple[float, float, float, float, float]]:
        with self._torch.no_grad():
            if self._predictor is not None:  # Gen 2: the scored path (egoblur-gen2.md "Decided for the audit")
                batch, original, resized = net.pre_process(tensor.unsqueeze(0))
                found = net.get_detections(net.inference(batch), 0.0, "audit", 0.0, resized, original)[0]
                if found is None:
                    return []
                boxes = found.face_bboxes if kind == "face" else found.lp_bboxes
                scores = found.face_scores if kind == "face" else found.lp_scores
                return [_scored(b, np.ravel(s)[0]) for b, s in zip(boxes, scores, strict=True)]
            boxes, _, scores, _ = net(tensor)  # Gen 1: (boxes, labels, scores, dims), NMS here at 0.3
            keep = self._ops.nms(boxes, scores, EGOBLUR_NMS["egoblur-gen1"])
            boxes, scores = boxes[keep].cpu().numpy(), scores[keep].cpu().numpy()
            threshold = self._thresholds[kind]
            return [_scored(b, s) for b, s in zip(boxes, scores, strict=True) if s >= threshold]


def _scored(box: Any, score: Any) -> tuple[float, float, float, float, float]:
    return float(box[0]), float(box[1]), float(box[2]), float(box[3]), float(score)


def load_detector(settings: Settings) -> Detector:
    """EgoBlur when it is asked for and installed; otherwise the bundled YuNet (recorded as ``yunet-face``)."""
    if settings.egoblur_model != "yunet-face":
        files = egoblur_weights(Path(settings.egoblur_weights_dir), settings.egoblur_model)
        if files is not None and importlib.util.find_spec("torch") is None:
            # No torch here (the slim API container): don't hash hundreds of MB of weights only to fall back.
            log.warning(
                "EgoBlur needs the audit dependency group: auditing with YuNet (faces only; plates by the red team)"
            )
            return YuNet(settings.egoblur_face_threshold)
        if files is not None:
            try:
                verify_egoblur(*files, settings.egoblur_model)
                return EgoBlur(
                    settings.egoblur_model,
                    *files,
                    face_threshold=settings.egoblur_face_threshold,
                    plate_threshold=settings.egoblur_plate_threshold,
                )
            except AuditorUnavailable as exc:  # altered weights, or no torch: YuNet, recorded as such, like missing
                log.warning("EgoBlur can't load (%s): auditing with YuNet (faces only; plates by the red team)", exc)
                return YuNet(settings.egoblur_face_threshold)
        log.warning(
            "EgoBlur weights not found in %s (owner step O8): auditing with YuNet (faces only; plates by the red team)",
            settings.egoblur_weights_dir,
        )
    return YuNet(settings.egoblur_face_threshold)
