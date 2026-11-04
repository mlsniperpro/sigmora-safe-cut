"""Baseline plans for the eval (EVAL.md §3, WP7 step 3) built from SAFETY's stages, scored by ``eval/metrics.py``
exactly like the full system: each writes ``decisions.json`` and ``plan.json`` into a job directory.

* :func:`blur_all`: the industry default. Every SAM ``face`` track hidden where SAM saw it: the same spatial padding
  as the real guard, but no temporal guard (no back-fill, extend or gap hold) and no policy (nothing else hidden,
  nobody kept). It isolates what the leak guard and the policy add.
* :func:`detector_plan` (``audit/baselines.py`` feeds it): a per-frame detector's boxes, padded, nothing else.
* :func:`no_audit_baseline`: the full system's policy and leak guard without the audit pass (EVAL.md §3 row 5): no
  audit patches and no read-through re-render, so it isolates what the second-look loop adds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from safecut.contracts import DecisionItem, Decisions, Job, Plan, PlanEntry, Temporal, Tracks, dump, load
from safecut.decide import policy_decisions
from safecut.decide.geometry import BoxT, grow
from safecut.guard.plan import PADDING, backfill_frames, plan
from safecut.guard.regions import ratio_for


def _item(item_id: str, track_ids: list[str], reason: str) -> DecisionItem:
    return DecisionItem(item_id=item_id, track_ids=track_ids, kind="person", decision="hide", reason=reason,
                        evidence_frames=[], style="solid", decided_by="policy", locked=False)  # fmt: skip


def _plan(frames: Mapping[int, list[PlanEntry]], backfill: int) -> Plan:
    # Declares the guard's spatial padding (which these baselines do apply) and no temporal padding beyond the
    # contract's floor: the entries themselves are only where the detections were.
    return Plan(padding=PADDING, temporal=Temporal(extend=8, backfill=backfill, gap_hold_s=0.0),
                frames=dict(sorted(frames.items())))  # fmt: skip


def blur_all(job: Job, tracks: Tracks) -> tuple[Decisions, Plan]:
    items: list[DecisionItem] = []
    frames: dict[int, list[PlanEntry]] = {}
    faces = [t for t in tracks.tracks if t.concept == "face"]
    for number, track in enumerate(faces, start=1):
        item_id = f"i_{number}"
        items.append(_item(item_id, [track.track_id], "baseline blur_all: every SAM face, where SAM saw it"))
        for frame, box in track.boxes.items():
            padded = grow(box, ratio_for("face", PADDING.face, PADDING.default), PADDING.px, job.width, job.height)
            frames.setdefault(frame, []).append(
                PlanEntry(item_id=item_id, shape="box", box=padded, mask=None, style="solid", grid=None)
            )
    return Decisions(items=items), _plan(frames, backfill_frames(job))


def detector_plan(job: Job, detections: Mapping[int, Sequence[BoxT]], *, backfill: int) -> tuple[Decisions, Plan]:
    """One item for the detector's output; each detection padded like a face, on its own frame only."""
    frames: dict[int, list[PlanEntry]] = {}
    for frame, boxes in detections.items():
        for box in boxes:
            padded = grow(box, PADDING.face, PADDING.px, job.width, job.height)
            frames.setdefault(frame, []).append(
                PlanEntry(item_id="i_1", shape="box", box=padded, mask=None, style="solid", grid=None)
            )
    item = _item("i_1", ["detections"], "baseline: per-frame detector boxes, nothing else")
    return Decisions(items=[item]), _plan(frames, backfill)


def blur_all_baseline(job_dir: Path) -> Path:
    """Write the ``blur_all`` baseline's ``decisions.json`` and ``plan.json`` into ``job_dir``; return the plan."""
    decisions, plan = blur_all(load(job_dir / "job.json", Job), load(job_dir / "tracks.json", Tracks))
    dump(decisions, job_dir / "decisions.json")
    (job_dir / "baseline.json").write_text(json.dumps({"variant": "blur_all", "detector": None}))
    return dump(plan, job_dir / "plan.json")


def no_audit_baseline(job_dir: Path) -> Path:
    """Write the ``no_audit`` baseline (the policy's own decisions, no creator edits, no audit patches) and its plan
    (no item read through solid) into ``job_dir``; return the plan."""
    decisions = Decisions(items=[i for i in policy_decisions(job_dir).items if i.origin != "audit_patch"])
    built = plan(load(job_dir / "job.json", Job), load(job_dir / "tracks.json", Tracks), decisions)
    dump(decisions, job_dir / "decisions.json")
    (job_dir / "baseline.json").write_text(json.dumps({"variant": "no_audit", "detector": None}))
    return dump(built, job_dir / "plan.json")
