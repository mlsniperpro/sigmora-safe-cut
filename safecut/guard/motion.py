"""Camera motion for the leak guard (DESIGN §2.6): where a held box goes while the camera pans.

When SAM loses a person the guard holds the edge box (back-fill, extend, a re-entry or gap hold). A box held still
drifts off its person while the camera pans, so the guard moves it with the scene instead: ``camera[f]`` is the
cumulative translation of the scene on frame ``f`` relative to frame 0, in full-frame pixels (a point at ``p`` on
frame 0 sits near ``p + camera[f]`` on frame ``f`` when it is fixed in the world), and a box held from frame ``e`` to
frame ``f`` moves by ``camera[f] - camera[e]``.

The estimate is global and cheap: each frame is reduced to a small grey image and ``cv2.phaseCorrelate`` (Hanning
windowed) finds the shift from the frame before. A weak correlation (a blank or featureless frame, a cut) counts as no
motion, and one frame's shift is clamped to a quarter of the frame. It is a pure function over a frame iterator, so it
tests on synthetic shifted images; :func:`camera_for` reads the job's prepared clip.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
from numpy.typing import NDArray

from safecut.contracts import Job, load
from safecut.render.video import RenderError, read_frames

#: Frames are shrunk to this width (never enlarged) before correlating: a pan is a global shift, so little is lost.
ANALYSIS_WIDTH = 160
#: A frame-to-frame shift is at most this share of the frame's side; a larger estimate is clamped to it.
MAX_SHIFT_SHARE = 0.25
#: ``cv2.phaseCorrelate``'s response below this is a poor match (a blank frame scores 0, a clean shift about 1):
#: that pair of frames counts as no motion.
MIN_RESPONSE = 0.1

Image = NDArray[np.uint8] | NDArray[np.float32]


def _grey(frame: Image, size: tuple[int, int]) -> NDArray[np.float32]:
    """``frame`` as a float32 grey image of ``size`` (width, height)."""
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if (grey.shape[1], grey.shape[0]) != size:
        grey = cv2.resize(grey, size, interpolation=cv2.INTER_AREA)
    return np.asarray(grey, dtype=np.float32)


def estimate_camera(
    frames: Iterable[Image],
    *,
    width: int = ANALYSIS_WIDTH,
    max_shift: float = MAX_SHIFT_SHARE,
    min_response: float = MIN_RESPONSE,
) -> list[tuple[int, int]]:
    """The cumulative scene offset ``(dx, dy)`` on every frame, relative to the first (which is ``(0, 0)``), in the
    frames' own pixels and rounded to ints. A scene that moves right and down between two frames has a positive shift.
    """
    out: list[tuple[int, int]] = []
    previous: NDArray[np.float32] | None = None
    window: NDArray[np.float32] | None = None
    total_x = total_y = 0.0
    for frame in frames:
        height, full = frame.shape[:2]
        size = (min(width, full), max(1, round(height * min(width, full) / full)))
        scale_x, scale_y = full / size[0], height / size[1]
        grey = _grey(frame, size)
        if previous is not None and previous.shape == grey.shape:
            if window is None or window.shape != grey.shape:
                window = np.asarray(cv2.createHanningWindow((size[0], size[1]), cv2.CV_32F), dtype=np.float32)
            (sx, sy), response = cv2.phaseCorrelate(previous, grey, window)
            if math.isfinite(sx) and math.isfinite(sy) and math.isfinite(response) and response >= min_response:
                limit_x, limit_y = max_shift * full, max_shift * height
                total_x += min(max(sx * scale_x, -limit_x), limit_x)
                total_y += min(max(sy * scale_y, -limit_y), limit_y)
        out.append((round(total_x), round(total_y)))
        previous = grey
    return out


#: Cameras of the last few jobs this process measured, each scoped to the exact ``job.json`` and prepared clip it came
#: from (path, size, modification time), so a re-plan after a review edit, or the audit's re-plans, never decode the
#: clip again.
_CAMERAS: OrderedDict[tuple[object, ...], list[tuple[int, int]] | None] = OrderedDict()
_KEEP = 4
_LOCK = Lock()


def camera_for(job_dir: Path, job: Job | None = None) -> list[tuple[int, int]] | None:
    """The camera of ``job_dir``'s prepared clip (:func:`estimate_camera` over its frames), or None when the clip is
    missing or unreadable, or the camera never moved: the guard then holds boxes exactly as it always has."""
    job = job if job is not None else load(job_dir / "job.json", Job)
    clip = job_dir / job.prepared
    try:
        stats = [(job_dir / "job.json").stat(), clip.stat()]
    except OSError:
        return None
    key = (str(job_dir.resolve()), *((s.st_size, s.st_mtime_ns, s.st_ino) for s in stats))
    with _LOCK:
        if key in _CAMERAS:
            _CAMERAS.move_to_end(key)
            return _CAMERAS[key]
    try:
        found = estimate_camera(read_frames(clip, job))
    except (
        RenderError,
        cv2.error,
        OSError,
    ):  # an unreadable clip or a wrong frame count: no camera, not a failed guard
        found = []
    camera = found if len(found) == job.frames and any(c != (0, 0) for c in found) else None
    with _LOCK:
        _CAMERAS[key] = camera
        while len(_CAMERAS) > _KEEP:
            _CAMERAS.popitem(last=False)
    return camera
