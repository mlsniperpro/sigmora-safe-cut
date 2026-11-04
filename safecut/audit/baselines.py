"""The ``egoblur`` eval baseline (EVAL.md §3 row 1b, WP7 step 3): the audit's own detector on every prepared frame,
its boxes hidden on that frame and nothing else (no tracking, no policy, no audit loop).

``detector_baseline(job_dir)`` writes ``decisions.json`` and ``plan.json`` for ``eval/metrics.py`` to score, and
``baseline.json`` naming the detector that actually ran: with EgoBlur's weights installed that is ``egoblur-gen2``;
without them it is ``yunet-face`` (faces only), and the run must be reported as that, never as EgoBlur.
"""

from __future__ import annotations

import json
from pathlib import Path

from safecut.audit.detectors import Detector
from safecut.contracts import Job, dump, load
from safecut.decide.geometry import BoxT
from safecut.guard.baselines import detector_plan
from safecut.guard.plan import backfill_frames
from safecut.render.video import read_frames

BASELINE = "baseline.json"


def detector_baseline(job_dir: Path, detector: Detector) -> Path:
    """Run ``detector`` on every frame of the prepared clip; write the baseline's plan; return ``plan.json``."""
    job = load(job_dir / "job.json", Job)
    detections: dict[int, list[BoxT]] = {}
    for index, frame in enumerate(read_frames(job_dir / job.prepared, job)):
        found = [d.box for d in detector.detect(frame)]
        if found:
            detections[index] = found
    decisions, plan = detector_plan(job, detections, backfill=backfill_frames(job))
    dump(decisions, job_dir / "decisions.json")
    (job_dir / BASELINE).write_text(json.dumps({"variant": "egoblur", "detector": detector.model,
                                                "frames_with_detections": len(detections)}))  # fmt: skip
    return dump(plan, job_dir / "plan.json")
