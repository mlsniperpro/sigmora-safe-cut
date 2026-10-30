"""WP7 metrics (EVAL.md §2), pure functions over a finished job directory and its clip's labels.

**Coverage** of a ground-truth box on a frame is the share of its area under the redaction the renderer draws on
that frame: every ``plan.json`` entry (its box, or its mask's foreground for ``shape: "mask"``; audit patches
included) and every crowd fill listing that frame. Area is counted on the pixel grid (a pixel is in a box when its
centre is), so a box and its rendering agree exactly. Box area, not IoU: a redaction larger than the face is
correct (EVAL §2).

Per frame a should-hide entity is **covered** at ≥ 95 % and **exposed** below 90 %; a **leak burst** is a run of
≥ 3 consecutive exposed frames. A should-keep entity is **hidden** on a frame when ≥ 50 % of it is covered.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pycocotools import mask as coco_mask  # pyright: ignore[reportMissingTypeStubs] -- no stubs ship with it

from eval.labels import Box, ClipLabels, Entity
from safecut.contracts import CostLine, Decisions, Job, Plan, Rle, load, measured_usd, read_cost_lines

COVERED = 0.95
EXPOSED = 0.90
HIDDEN = 0.50
BURST = 3
RECALL_SHARE = 0.95
OVER_BLUR_SHARE = 0.10

IntBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class Region:
    box: IntBox
    mask: Rle | None = None


def frame_regions(plan: Plan) -> dict[int, list[Region]]:
    """What the renderer draws, per frame: plan entries and crowd fills."""
    regions: dict[int, list[Region]] = {}
    for frame, entries in plan.frames.items():
        for entry in entries:
            mask = entry.mask if entry.shape == "mask" else None
            regions.setdefault(int(frame), []).append(Region(tuple(entry.box), mask))  # type: ignore[arg-type] -- a 4-int box
    for fill in plan.crowd_fills:
        for frame in fill.frames:
            regions.setdefault(frame, []).append(Region(tuple(fill.box)))  # type: ignore[arg-type] -- a 4-int box
    return regions


def _pixel_span(lo: float, hi: float) -> tuple[int, int]:
    """Pixels whose centre lies in ``[lo, hi)``."""
    return math.ceil(lo - 0.5), math.ceil(hi - 0.5)


def _decode(rle: Rle) -> NDArray[np.bool_]:
    decoded = coco_mask.decode({"size": list(rle.size), "counts": rle.counts.encode("ascii")})  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] -- untyped C extension
    return np.asarray(decoded, dtype=bool)


def coverage(gt: Box, regions: Sequence[Region], *, width: int, height: int) -> float:
    """The share of ``gt``'s pixels (clipped to the frame) under any region."""
    x0, x1 = _pixel_span(max(gt[0], 0), min(gt[2], width))
    y0, y1 = _pixel_span(max(gt[1], 0), min(gt[3], height))
    if x1 <= x0 or y1 <= y0:
        return 1.0  # nothing of it is inside the frame, so nothing of it can show
    canvas = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    for region in regions:
        bx0, by0, bx1, by1 = region.box
        ix0, iy0, ix1, iy1 = max(bx0, x0), max(by0, y0), min(bx1, x1), min(by1, y1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        if region.mask is None:
            canvas[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] = True
        else:
            fg = _decode(region.mask)
            canvas[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0] |= fg[iy0:iy1, ix0:ix1]
    return float(canvas.mean())


def bursts(exposed_frames: Iterable[int], *, length: int = BURST) -> int:
    """Runs of ≥ ``length`` consecutive frame indices."""
    count = run = 0
    previous: int | None = None
    for frame in sorted(set(exposed_frames)):
        run = run + 1 if previous is not None and frame == previous + 1 else 1
        if run == length:
            count += 1
        previous = frame
    return count


@dataclass(frozen=True)
class EntityScore:
    id: str
    category: str
    should_hide: bool
    visible_frames: int
    frames_covered_95: int
    frames_exposed: int
    frames_hidden: int
    leak_bursts: int
    mean_coverage: float
    #: The worst frames (lowest coverage first), for the run's worst-exposure list.
    worst: tuple[tuple[int, float], ...] = ()

    @property
    def recalled(self) -> bool:
        return self.visible_frames == 0 or self.frames_covered_95 >= RECALL_SHARE * self.visible_frames

    @property
    def over_blurred(self) -> bool:
        return self.visible_frames > 0 and self.frames_hidden > OVER_BLUR_SHARE * self.visible_frames


def score_entity(
    entity: Entity,
    regions: dict[int, list[Region]],
    *,
    width: int,
    height: int,
    scale: tuple[float, float] = (1.0, 1.0),
) -> EntityScore:
    """``scale`` maps label pixels to prepared-clip pixels (labels are on the source frame)."""
    sx, sy = scale
    covered = exposed = hidden = 0
    exposed_frames: list[int] = []
    per_frame: list[tuple[int, float]] = []
    for frame, (x1, y1, x2, y2) in sorted(entity.dense.items()):
        value = coverage((x1 * sx, y1 * sy, x2 * sx, y2 * sy), regions.get(frame, ()), width=width, height=height)
        per_frame.append((frame, value))
        covered += value >= COVERED
        hidden += value >= HIDDEN
        if value < EXPOSED:
            exposed += 1
            exposed_frames.append(frame)
    mean = sum(v for _, v in per_frame) / len(per_frame) if per_frame else 1.0
    worst = tuple(sorted(per_frame, key=lambda fv: (fv[1], fv[0]))[:5])
    return EntityScore(
        entity.id,
        entity.category,
        entity.should_hide,
        len(per_frame),
        covered,
        exposed,
        hidden,
        bursts(exposed_frames),
        round(mean, 6),
        worst,
    )


@dataclass(frozen=True)
class JobScore:
    clip: str
    frames: int
    fps: float
    entities: list[EntityScore]
    needs_you: int
    cost_usd: float
    cost_usd_estimated: float

    @property
    def minutes(self) -> float:
        return self.frames / self.fps / 60


def score_job(job_dir: Path, labels: ClipLabels, regions: dict[int, list[Region]] | None = None) -> JobScore:
    """Score one finished job against its clip's labels: what ``plan.json`` renders, or ``regions`` when a
    baseline drew something else."""
    job = load(job_dir / "job.json", Job)
    if labels.frames != job.frames:
        raise ValueError(f"labels have {labels.frames} frames, the prepared clip {job.frames}")
    if regions is None:
        regions = frame_regions(load(job_dir / "plan.json", Plan))
    scale = (job.width / labels.width, job.height / labels.height)
    entities = [score_entity(e, regions, width=job.width, height=job.height, scale=scale) for e in labels.entities]
    decisions_path = job_dir / "decisions.json"
    decisions = load(decisions_path, Decisions) if decisions_path.is_file() else Decisions(items=[])
    needs_you = sum(item.decision == "needs_you" and item.decided_by != "creator" for item in decisions.items)
    cost_path = job_dir / "cost.jsonl"
    lines: list[CostLine] = list(read_cost_lines(cost_path)) if cost_path.is_file() else []
    measured, estimated = measured_usd(lines)
    return JobScore(labels.clip, job.frames, job.fps, entities, needs_you, round(measured, 6), round(estimated, 6))


@dataclass(frozen=True)
class Summary:
    clips: int
    should_hide: int
    should_keep: int
    entity_recall: float | None
    exposure_rate: float | None
    leak_bursts: int
    over_blur: float | None
    review_load_per_min: float | None
    cost_usd: float
    cost_usd_estimated: float
    cost_per_min: float | None
    minutes: float
    per_category_recall: dict[str, float] = field(default_factory=dict[str, float])


def _share(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def summarize(scores: Sequence[JobScore]) -> Summary:
    hide = [e for s in scores for e in s.entities if e.should_hide]
    keep = [e for s in scores for e in s.entities if not e.should_hide]
    minutes = sum(s.minutes for s in scores)
    visible = sum(e.visible_frames for e in hide)
    cost = sum(s.cost_usd for s in scores)
    categories = sorted({e.category for e in hide})
    per_category = {
        c: _share(sum(e.recalled for e in hide if e.category == c), sum(e.category == c for e in hide)) or 0.0
        for c in categories
    }
    return Summary(
        clips=len(scores),
        should_hide=len(hide),
        should_keep=len(keep),
        entity_recall=_share(sum(e.recalled for e in hide), len(hide)),
        exposure_rate=_share(sum(e.frames_exposed for e in hide), visible),
        leak_bursts=sum(e.leak_bursts for e in hide),
        over_blur=_share(sum(e.over_blurred for e in keep), len(keep)),
        review_load_per_min=round(sum(s.needs_you for s in scores) / minutes, 6) if minutes else None,
        cost_usd=round(cost, 6),
        cost_usd_estimated=round(sum(s.cost_usd_estimated for s in scores), 6),
        cost_per_min=round(cost / minutes, 6) if minutes else None,
        minutes=round(minutes, 6),
        per_category_recall=per_category,
    )
