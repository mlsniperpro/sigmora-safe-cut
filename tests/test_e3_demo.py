"""E3 in the SAFETY lane's own suite: the whole pipeline in replay on SENSE's synthetic demo job (SC-A-91), with the
network blocked, scored against its ground truth on exactly the pixels the renderer changed.

Every should-hide object ≥ 95 % covered on ≥ 99 % of its visible frames, no should-keep object hidden on more than
10 % of its frames, zero leak bursts; the audit leaves nothing unresolved, the receipt verifies, the video is H.264
with the source's audio. Synthetic: every recorded answer was generated from the ground truth, never a model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecut import contracts, netguard, pipeline
from safecut.audit.truth import load_labels
from safecut.contracts import Audit, Job, Plan, Receipt, load
from safecut.receipt import verify_chain
from safecut.render.coverage import passes_e3, score
from safecut.render.video import probe_streams

DEMO = Path("fixtures/jobs/demo")
MANIFEST = json.loads((DEMO / "raw" / "manifest.json").read_text())


@pytest.fixture(scope="module")
def demo_job(tmp_path_factory: pytest.TempPathFactory) -> Path:
    clip = Path(MANIFEST["source"])
    job_dir = tmp_path_factory.mktemp("e3") / "j_e3"
    pipeline.create_job(clip, job_dir, mode="replay")
    pipeline.attach_recording(job_dir, DEMO)
    with netguard.blocked():
        pipeline.analyse(job_dir, replay=True)
        pipeline.approve(job_dir, how="auto_policy")
        pipeline.publish(job_dir, replay=True)
    return job_dir


def test_e3_the_demo_job_is_redacted_audited_and_receipted(demo_job: Path) -> None:
    contracts.validate_job_dir(demo_job)
    audit = load(demo_job / "audit.json", Audit)
    assert (audit.unresolved, audit.blocked_reason) == (0, None)
    assert audit.frames_scanned == load(demo_job / "job.json", Job).frames
    assert probe_streams(demo_job / "redacted.mp4") == ["video:h264", "audio:aac"]
    assert verify_chain([load(demo_job / "receipt.json", Receipt)])
    assert (demo_job / "receipt.html").is_file()


def test_e3_ground_truth_thresholds(demo_job: Path) -> None:
    job = load(demo_job / "job.json", Job)
    labels = load_labels(Path(MANIFEST["truth"]), width=job.width, height=job.height, frames=job.frames)
    scores = score(load(demo_job / "plan.json", Plan), labels.boxes(), labels.should_hide, width=job.width,
                   height=job.height)  # fmt: skip
    hide = {k: s for k, s in scores.items() if s.should_hide}
    keep = {k: s for k, s in scores.items() if not s.should_hide}
    assert hide, "the demo job has should-hide objects"
    assert keep, "the demo job has participants to keep"
    for entity, s in hide.items():
        assert s.share >= 0.99, (entity, labels.categories[entity], s.exposed[:10])
        assert s.bursts == 0, (entity, s.exposed[:10])
    for entity, s in keep.items():
        assert s.share <= 0.10, (entity, s.hits, s.frames)
    assert passes_e3(scores)
