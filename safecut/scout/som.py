"""Set-of-Mark keyframes (WP2 step 3; ``role-pass.md`` inputs; PRE-A §5).

Every 1 fps keyframe gets each SAM track's box in a high-contrast colour with its ``<concept>:<n>`` label in a
filled tag at the box's top-left (kept inside the frame and clear of other tags), and a black ``bar_h`` bar
**added above** the picture carrying ``F 000090``, so no content is covered and the 0–1000 grid maps back
exactly (§5). Rendering is deterministic: the same inputs give the same pixels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from safecut.contracts import Job, Track, Tracks
from safecut.scout.grid import BAR_H

SOM_DIR = "som"
KEYFRAMES = "keyframes"
JPEG_QUALITY = 90
FONT = cv2.FONT_HERSHEY_SIMPLEX
#: High-contrast colours (BGR), cycled by each track's place in the job's sorted track list.
PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 214, 255),  # amber
    (255, 229, 0),  # cyan
    (129, 64, 255),  # pink
    (3, 255, 118),  # green
    (0, 145, 255),  # orange
    (249, 0, 213),  # violet
    (182, 233, 29),  # teal
    (255, 255, 255),  # white
)
#: The smallest label cap height in sent pixels: legible on a 320 px wide frame.
MIN_TEXT_PX = 11
#: The frame number's cap height in the 40 px bar, the same at every frame size.
BAR_TEXT_PX = 20

Image = NDArray[np.uint8]


@dataclass(frozen=True)
class Keyframe:
    frame: int
    path: str
    labels: tuple[str, ...]


def keyframe_numbers(job: Job) -> list[int]:
    """The 1 fps keyframes: prepared frames ``0, fps, 2·fps, …`` (the frames ``prepare`` extracted)."""
    return list(range(0, job.frames, job.fps))


def judged(track: Track) -> bool:
    """Static miss-loop boxes are never sent to a role pass (``miss-loop.md``)."""
    return track.origin != "static"


def labels_on(tracks: Sequence[Track], frame: int) -> list[Track]:
    return [t for t in tracks if judged(t) and frame in t.boxes]


def _scale(width: int) -> tuple[float, int]:
    """Font scale and stroke for a frame ``width`` px wide: cap height ≥ ``MIN_TEXT_PX``, growing with width."""
    base = cv2.getTextSize("F", FONT, 1.0, 1)[0][1]
    scale = max(MIN_TEXT_PX / base, 0.6 * width / 1280 * 22 / base)
    return scale, 1 if scale < 0.9 else 2


def text_colour(fill: tuple[int, int, int]) -> tuple[int, int, int]:
    b, g, r = fill
    return (0, 0, 0) if 0.299 * r + 0.587 * g + 0.114 * b > 140 else (255, 255, 255)


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def place_tags(tracks: Sequence[Track], frame: int, width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    """Each label's tag rectangle in frame pixels: at its box's top-left corner (above it when there's room), inside
    the frame, clear of earlier tags."""
    scale, stroke = _scale(width)
    placed: dict[str, tuple[int, int, int, int]] = {}
    for track in tracks:
        x1, y1, _, _ = track.boxes[frame]
        (tw, th), base = cv2.getTextSize(track.track_id, FONT, scale, stroke)
        pad = max(2, th // 4)
        tag_w, tag_h = tw + 2 * pad, th + base + 2 * pad
        tx = min(max(x1, 0), max(width - tag_w, 0))
        # Just above the box when there's room, so the tag never covers the object (a face) it names.
        ty = y1 - tag_h if y1 - tag_h >= 0 else min(max(y1, 0), max(height - tag_h, 0))
        rect = (tx, ty, tx + tag_w, ty + tag_h)
        for _ in range(2 * height // max(tag_h, 1)):
            if not any(_overlaps(rect, other) for other in placed.values()):
                break
            ty = ty + tag_h if ty + 2 * tag_h <= height else max(ty - tag_h, 0)
            rect = (tx, ty, tx + tag_w, ty + tag_h)
        placed[track.track_id] = rect
    return placed


def render(image: Image, frame: int, tracks: Sequence[Track], colours: dict[str, tuple[int, int, int]]) -> Image:
    """The sent image: ``W × (H + BAR_H)``, the bar on top, boxes and tags on the picture."""
    height, width = image.shape[:2]
    canvas = np.zeros((height + BAR_H, width, 3), dtype=np.uint8)
    canvas[BAR_H:] = image
    scale, stroke = _scale(width)
    bar_scale = BAR_TEXT_PX / cv2.getTextSize("F", FONT, 1.0, 2)[0][1]
    cv2.putText(canvas, f"F {frame:06d}", (8, BAR_H - 10), FONT, bar_scale, (255, 255, 255), 2, cv2.LINE_AA)
    thickness = max(2, round(width / 400))
    for track in tracks:
        x1, y1, x2, y2 = track.boxes[frame]
        cv2.rectangle(canvas, (x1, y1 + BAR_H), (x2 - 1, y2 - 1 + BAR_H), colours[track.track_id], thickness)
    for track_id, rect in place_tags(tracks, frame, width, height).items():
        colour = colours[track_id]
        (_, th), base = cv2.getTextSize(track_id, FONT, scale, stroke)
        pad = max(2, th // 4)
        cv2.rectangle(canvas, (rect[0], rect[1] + BAR_H), (rect[2] - 1, rect[3] - 1 + BAR_H), colour, -1)
        origin = (rect[0] + pad, rect[3] - pad - base + BAR_H)
        cv2.putText(canvas, track_id, origin, FONT, scale, text_colour(colour), stroke, cv2.LINE_AA)
    return canvas


def colour_map(tracks: Tracks) -> dict[str, tuple[int, int, int]]:
    ordered = sorted(tracks.tracks, key=lambda t: (t.concept, int(t.track_id.rsplit(":", 1)[1])))
    return {t.track_id: PALETTE[i % len(PALETTE)] for i, t in enumerate(ordered)}


def write(job_dir: Path, job: Job, tracks: Tracks, frames: Sequence[int] | None = None) -> list[Keyframe]:
    """Render ``som/<frame:06d>.jpg`` for each keyframe (JPEG quality 90) from ``keyframes/<frame:06d>.jpg``."""
    out_dir = job_dir / SOM_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    colours = colour_map(tracks)
    written: list[Keyframe] = []
    for frame in frames if frames is not None else keyframe_numbers(job):
        source = job_dir / KEYFRAMES / f"{frame:06d}.jpg"
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"keyframe {source.name} is missing: run prepare first")
        on = labels_on(tracks.tracks, frame)
        sent = render(image.astype(np.uint8), frame, on, colours)
        rel = f"{SOM_DIR}/{frame:06d}.jpg"
        if not cv2.imwrite(str(job_dir / rel), sent, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
            raise OSError(f"could not write {rel}")
        written.append(Keyframe(frame=frame, path=rel, labels=tuple(t.track_id for t in on)))
    return written
