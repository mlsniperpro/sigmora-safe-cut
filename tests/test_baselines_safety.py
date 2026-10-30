"""E9: the two eval baselines that sit in SAFETY's stages, scored by eval/metrics.py on the synthetic demo job against
the full system. The full system must beat both on what reaches the viewer."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from eval.labels import load_labels
from eval.metrics import score_job
from safecut import netguard, pipeline
from safecut.audit.baselines import BASELINE, detector_baseline
from safecut.audit.detectors import YuNet
from safecut.contracts import DecisionItem, Decisions, dump, load
from safecut.guard.baselines import blur_all_baseline, no_audit_baseline

DEMO = Path("fixtures/jobs/demo")
MANIFEST = json.loads((DEMO / "raw" / "manifest.json").read_text())


@pytest.fixture(scope="module")
def analysed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    job_dir = tmp_path_factory.mktemp("e9") / "j_e9"
    pipeline.create_job(Path(MANIFEST["source"]), job_dir, mode="replay")
    pipeline.attach_recording(job_dir, DEMO)
    with netguard.blocked():
        pipeline.analyse(job_dir, replay=True)
    return job_dir


def copy(job_dir: Path, name: str) -> Path:
    out = job_dir.parent / name
    shutil.copytree(job_dir, out)
    return out


def exposed(job_dir: Path) -> dict[str, float]:
    """Per should-hide entity: the share of its visible frames under 95 % coverage."""
    score = score_job(job_dir, load_labels(Path(MANIFEST["truth"])))
    return {
        e.id: 1 - e.frames_covered_95 / e.visible_frames for e in score.entities if e.should_hide and e.visible_frames
    }


def test_blur_all_leaves_everything_but_faces_and_the_full_system_beats_it(analysed: Path) -> None:
    full = exposed(analysed)  # decide + guard: the plan as rendered
    blur = blur_all_baseline(copy(analysed, "j_blur")).parent
    base = exposed(blur)
    assert json.loads((blur / BASELINE).read_text())["variant"] == "blur_all"
    assert max(full.values()) == 0.0
    assert sum(base.values()) > sum(full.values())
    assert max(base.values()) > 0.5  # the plate, the screen and the envelope are never hidden


def test_the_detector_baseline_names_the_detector_that_ran(analysed: Path) -> None:
    job_dir = copy(analysed, "j_det")
    detector_baseline(job_dir, YuNet())
    record = json.loads((job_dir / BASELINE).read_text())
    assert (record["variant"], record["detector"]) == ("egoblur", "yunet-face")
    base = exposed(job_dir)
    assert sum(base.values()) > sum(exposed(analysed).values())  # drawn shapes: a face detector finds little


def test_no_audit_is_the_policy_and_guard_without_any_audit_patch(analysed: Path) -> None:
    job_dir = copy(analysed, "j_no_audit")
    decided = load(job_dir / "decisions.json", Decisions)
    patch = DecisionItem.model_validate({
        "item_id": "p_1", "track_ids": [], "kind": "person", "decision": "hide", "style": "solid",
        "reason": "Added by the audit: the final check found this after rendering and covered it.",
        "evidence_frames": [10], "decided_by": "policy", "locked": True, "origin": "audit_patch",
        "audit_label": "A1", "box": [0, 0, 40, 40], "first": 5, "last": 15,
    })  # fmt: skip
    dump(Decisions(items=[*decided.items, patch]), job_dir / "decisions.json")
    no_audit_baseline(job_dir)
    assert json.loads((job_dir / BASELINE).read_text())["variant"] == "no_audit"
    assert load(job_dir / "decisions.json", Decisions) == decided  # the patch the audit added is gone
    assert (job_dir / "plan.json").read_text() == (analysed / "plan.json").read_text()  # the guard's plan as is
