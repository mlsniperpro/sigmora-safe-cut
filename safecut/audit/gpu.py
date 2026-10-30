"""EgoBlur on a GPU, for WP5's deploy (WP4 step 2: "if a 30 s clip at 1280 px takes over 3 minutes on CPU, add a
Modal GPU function").

EgoBlur Gen 2 runs about 1.5 s per frame per model on CPU and 21 ms on a GPU (``egoblur-gen2.md``), so a 30 s,
900-frame clip takes ~45 min on CPU (face + plate) and ~40 s on a T4/L4. YuNet runs in milliseconds per frame on CPU
(``raw/audit/run.json`` records the measured figure) and needs no GPU.

* :func:`detect_png` is what a Modal GPU function wraps: one lossless frame in, its detections out, with the detector
  built once per container (``deploy/modal_app.py`` owns the Modal decorators, the Volume with the weights and the
  GPU type).
* :class:`RemoteDetector` is the audit's :class:`~safecut.audit.detectors.Detector` that sends each frame there.
  Frames travel as PNG, so the GPU sees exactly the pixels the video holds.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import cv2
import numpy as np

from safecut.audit.detectors import AuditorModel, Detection, DetectionKind, Detector, to_box
from safecut.render.draw import Frame

Wire = list[dict[str, Any]]


def encode(frame: Frame) -> bytes:
    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        raise ValueError("couldn't encode a frame for the GPU auditor")
    return buf.tobytes()


def decode(png: bytes) -> Frame:
    frame = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("the GPU auditor got a frame it can't decode")
    return np.asarray(frame, dtype=np.uint8)


def detect_png(detector: Detector, png: bytes) -> Wire:
    """Run ``detector`` on one PNG frame; detections as plain JSON-able dicts."""
    return [{"kind": d.kind, "box": list(d.box), "score": d.score} for d in detector.detect(decode(png))]


class RemoteDetector:
    """A detector whose frames are judged elsewhere (a Modal GPU function's ``.remote``)."""

    def __init__(self, model: AuditorModel, call: Callable[[bytes], Wire], *, plates: bool = True) -> None:
        self._model: AuditorModel = model
        self._call = call
        self._plates = plates

    @property
    def model(self) -> AuditorModel:
        return self._model

    @property
    def detects_plates(self) -> bool:
        return self._plates

    def detect(self, frame: Frame) -> list[Detection]:
        height, width = frame.shape[:2]
        out: list[Detection] = []
        for raw in self._call(encode(frame)):
            kind = cast(DetectionKind, raw["kind"])
            if kind not in ("face", "plate") or (kind == "plate" and not self._plates):
                raise ValueError(f"the GPU auditor answered a {kind!r} detection")
            x1, y1, x2, y2 = (float(v) for v in raw["box"])
            box = to_box((x1, y1, x2, y2), width, height)
            if box is not None:
                out.append(Detection(kind, box, float(raw["score"])))
        return out
