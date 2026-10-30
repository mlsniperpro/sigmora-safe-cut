"""The six pipeline variants the eval compares (EVAL.md §3), each run on a copy of a recorded job.

- ``full``: Safe Cut as shipped: every stage, the policy's decisions auto-approved, the audit and its patches.
- ``no_audit``: the same up to the render, without the audit pass (isolates what the second look adds).
- ``blur_all``: SAM 3.1 ``face`` only, everything hidden (YouTube Studio's "blur all faces", CapCut Face Mosaic).
- ``detector_only``: SAM 3.1 ``face``, ``license plate`` and ``screen``, everything hidden, no Muse reasoning.
- ``egoblur``: EgoBlur Gen 2 on every frame, every detection hidden (the audit lane's detector wrapper; without its
  gated weights that wrapper runs YuNet, and the run records which one ran).
- ``muse_no_track``: Muse Spark's per-keyframe boxes held until the next keyframe (the scout lane's baseline).

The hidden-everything baselines go through the same leak guard as Safe Cut (padding and temporal hold), so they
are as strong as our own guard makes them; the score is always what the renderer would draw.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from eval.metrics import IntBox, Region, frame_regions
from safecut import pipeline
from safecut.config import load_settings
from safecut.contracts import DecisionItem, Decisions, Job, Plan, Tracks, dump, load
from safecut.stages import stage

Variant = Literal["blur_all", "egoblur", "detector_only", "muse_no_track", "full", "no_audit"]
VARIANTS: tuple[Variant, ...] = ("blur_all", "egoblur", "detector_only", "muse_no_track", "full", "no_audit")
#: The concepts each hide-everything baseline asks SAM for (EVAL §3).
CONCEPTS: dict[str, tuple[str, ...]] = {"blur_all": ("face",), "detector_only": ("face", "license plate", "screen")}
#: EgoBlur's own default box growth (``--scale_factor_detections 1.15``).
EGOBLUR_SCALE = 1.15

KIND = {
    "face": "person",
    "person": "person",
    "license plate": "plate",
    "screen": "screen",
    "phone": "screen",
    "document": "document",
    "name badge": "document",
}


class VariantUnavailable(RuntimeError):
    """The variant needs a lane's baseline hook that isn't in this build."""


def _hook(module: str, name: str) -> Callable[..., dict[int, list[IntBox]]]:
    try:
        found = getattr(importlib.import_module(module), name, None)
    except ModuleNotFoundError as exc:
        if exc.name is not None and module.startswith(exc.name):
            found = None
        else:
            raise
    if not callable(found):
        raise VariantUnavailable(f"{module}.{name}(job_dir, *, replay) isn't in this build")
    return found  # type: ignore[return-value] -- checked callable; the hook's documented signature


def hide_everything(job_dir: Path, concepts: tuple[str, ...]) -> None:
    """Keep only the variant's concepts in ``tracks.json`` and hide every track, one item per track."""
    tracks = load(job_dir / "tracks.json", Tracks)
    kept = [t for t in tracks.tracks if t.concept in concepts]
    dump(
        tracks.model_copy(update={"tracks": kept, "concepts": [c for c in tracks.concepts if c in concepts]}),
        job_dir / "tracks.json",
    )
    items = [
        DecisionItem(
            item_id=f"i_{n}",
            track_ids=[t.track_id],
            kind="child" if t.child_phrase else KIND.get(t.concept, "other"),  # type: ignore[arg-type] -- a Kind
            decision="hide",
            reason=f"baseline: every {t.concept} hidden",
            evidence_frames=[t.first],
            style="solid",
            decided_by="policy",
            locked=t.child_phrase,
            origin=t.origin,
        )
        for n, t in enumerate(kept, 1)
    ]
    dump(Decisions(items=items), job_dir / "decisions.json")


def held_boxes(boxes: dict[int, list[IntBox]], frames: int, *, hold: bool) -> dict[int, list[Region]]:
    """Per-frame regions from detections: each frame's own (``hold=False``), or each keyframe's boxes held until
    the next keyframe (``hold=True``)."""
    regions: dict[int, list[Region]] = {}
    keys = sorted(f for f in boxes if 0 <= f < frames)
    for n, key in enumerate(keys):
        end = (keys[n + 1] if n + 1 < len(keys) else frames) if hold else key + 1
        for frame in range(key, end):
            regions.setdefault(frame, []).extend(Region(b) for b in boxes[key])
    return regions


def scaled(box: IntBox, factor: float, job: Job) -> IntBox:
    x1, y1, x2, y2 = box
    cx, cy, half_w, half_h = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) * factor / 2, (y2 - y1) * factor / 2
    return (
        max(0, round(cx - half_w)),
        max(0, round(cy - half_h)),
        min(job.width, round(cx + half_w)),
        min(job.height, round(cy + half_h)),
    )


def detector_boxes(job_dir: Path) -> tuple[str, dict[int, list[IntBox]]]:
    """WP4's audit detector (EgoBlur Gen 2, or the bundled YuNet when its weights are missing) on every frame of
    the prepared clip: ``(the model that actually ran, boxes per frame)``."""
    from safecut.audit.detectors import load_detector  # noqa: PLC0415 -- heavy (OpenCV nets); this variant only
    from safecut.render.video import read_frames  # noqa: PLC0415 -- with the line above

    job = load(job_dir / "job.json", Job)
    detector = load_detector(load_settings())
    boxes: dict[int, list[IntBox]] = {}
    for index, frame in enumerate(read_frames(job_dir / job.prepared, job)):
        found = [d.box for d in detector.detect(frame)]
        if found:
            boxes[index] = found
    return detector.model, boxes


@dataclass(frozen=True)
class VariantResult:
    regions: dict[int, list[Region]]
    #: What the run actually used where it can differ from the config (the egoblur baseline's detector).
    detail: dict[str, str] = field(default_factory=dict[str, str])


def preflight(variant: Variant) -> None:
    """Raise :class:`VariantUnavailable` now, before anything is counted or spent, if the variant can't run here."""
    if variant == "muse_no_track":
        _hook("safecut.scout.baselines", "muse_keyframe_boxes")


def run_variant(variant: Variant, job_dir: Path, *, replay: bool) -> VariantResult:
    """Run ``variant`` in ``job_dir`` (a created job with its recording attached) and return what it renders."""
    analyse = pipeline.analyse
    if variant in ("full", "no_audit"):
        analyse(job_dir, replay=replay)
        pipeline.approve(job_dir, how="auto_policy")
        if variant == "full":
            pipeline.publish(job_dir, replay=replay)
        else:
            pipeline.run_stage(job_dir, stage("render"), replay=replay)
        return VariantResult(frame_regions(load(job_dir / "plan.json", Plan)))
    if variant in CONCEPTS:
        analyse(job_dir, replay=replay, until="track")
        hide_everything(job_dir, CONCEPTS[variant])
        pipeline.run_stage(job_dir, stage("guard"), replay=replay, force=True)
        return VariantResult(frame_regions(load(job_dir / "plan.json", Plan)))
    analyse(job_dir, replay=replay, until="prepare")
    job = load(job_dir / "job.json", Job)
    if variant == "egoblur":
        model, detections = detector_boxes(job_dir)
        grown = {f: [scaled(b, EGOBLUR_SCALE, job) for b in boxes] for f, boxes in detections.items()}
        return VariantResult(held_boxes(grown, job.frames, hold=False), {"detector": model})
    # Muse Spark's own boxes on the keyframes, no tracker: the hook needs only prepare, so SAM is never called.
    keyframes = _hook("safecut.scout.baselines", "muse_keyframe_boxes")(job_dir, replay=replay)
    return VariantResult(held_boxes(keyframes, job.frames, hold=True), {"keyframe_boxes": load_settings().role_model})
