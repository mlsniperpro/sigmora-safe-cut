"""render: ``plan.json`` → ``redacted.mp4`` + ``thumbs/<item_id>.jpg`` (WP4 step 1).

``run(job_dir)`` reads the prepared clip frame by frame, applies each frame's plan entries and crowd fills
(``draw.apply``), encodes H.264 with the clip's own audio muxed back, and cuts one thumbnail per decision item
from the redacted frames. Gaussian blur is never used: it is reversible (DESIGN §2.7). No API call, so ``replay``
changes nothing.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from safecut.contracts import CrowdFill, Decisions, Job, Plan, Tracks, load
from safecut.render.draw import apply
from safecut.render.video import RenderError, ThumbSpec, cut_thumb, h264_writer, read_frames, thumb_specs

REDACTED = "redacted.mp4"
THUMBS = "thumbs"
JPEG_QUALITY = 85


def fills_by_frame(plan: Plan) -> dict[int, list[CrowdFill]]:
    out: dict[int, list[CrowdFill]] = {}
    for fill in plan.crowd_fills:
        for frame in fill.frames:
            out.setdefault(frame, []).append(fill)
    return out


def render(job_dir: Path) -> Path:
    """Write ``redacted.mp4`` and the thumbnails; return the video's path."""
    job = load(job_dir / "job.json", Job)
    plan = load(job_dir / "plan.json", Plan)
    decisions = load(job_dir / "decisions.json", Decisions)
    tracks = load(job_dir / "tracks.json", Tracks)
    fills = fills_by_frame(plan)
    specs: dict[int, list[ThumbSpec]] = {}
    for spec in thumb_specs(decisions, tracks, plan, job):
        specs.setdefault(spec.frame, []).append(spec)
    thumbs = job_dir / THUMBS
    thumbs.mkdir(exist_ok=True)
    for stale in thumbs.glob("*.jpg"):
        stale.unlink()
    source = job_dir / job.prepared
    out = job_dir / REDACTED
    with h264_writer(out, job, source if job.audio else None) as write:
        for index, frame in enumerate(read_frames(source, job)):
            redacted = apply(frame, plan.frames.get(index, []), fills.get(index, []))
            write(redacted)
            for spec in specs.get(index, []):
                path = thumbs / f"{spec.item_id}.jpg"
                if not cv2.imwrite(str(path), cut_thumb(redacted, spec.box), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
                    raise RenderError(f"couldn't write {path.name}")
    return out


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The render stage: returns ``redacted.mp4``. A receipt from an earlier render is retired first: it sealed the
    old video, and the new one has no verdict until its own audit and receipt run."""
    from safecut.receipt import retire  # noqa: PLC0415 -- the receipt stage reads this package's thumbnails

    del replay  # no API call in this stage
    retire(job_dir)
    return render(job_dir)


__all__ = ["REDACTED", "THUMBS", "RenderError", "fills_by_frame", "render", "run"]
