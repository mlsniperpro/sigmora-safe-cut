"""Owner, 11-04: a judge who approves without touching anything must get a correct video. Any tie to the
conversation keeps an adult clear (a majority of the role checks, the speech link, the scene pass naming the
interviewer or host); a re-entry of a kept person comes back kept; children never; strangers stay hidden.

Fixtures: the live street job j_kcZk0aJHKa78Nyr0JbmGOw (the interviewer went to Needs you on every street run: in
profile with the mic up, no speech linked to her face) and the café job j_6cI3f1wVTo5pFPKB2yo0sw, both AI-generated
scenes with no real people, saved with the policy's inputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from safecut.contracts import Decisions, Job, Roles, Scene, Track, Tracks, Transcript
from safecut.decide.policy import Inputs, decide
from safecut.guard.plan import plan
from safecut.render.draw import hidden_mask

FIXTURES = Path(__file__).parent / "fixtures"


def inputs(name: str) -> Inputs:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    raw = data["job"]
    job = Job(job_id=data["job_id"], source="clip.mp4", source_sha256="0" * 64, prepared="prepared.mp4",
              fps=raw["fps"], width=raw["width"], height=raw["height"], frames=raw["frames"], times=raw["times"],
              audio=raw["audio"], created_at=raw["created_at"])  # fmt: skip
    tracks = [
        Track(
            track_id=t["track_id"],
            concept=t["concept"],
            first=t["first"],
            last=t["last"],
            boxes={int(k): tuple(v) for k, v in t["boxes"].items()},
            reentry_of=t.get("reentry_of"),
            source="sam-3.1",
            prompt=t["concept"],
            child_phrase=t.get("child_phrase", False),
        )
        for t in data["tracks"]
    ]
    return Inputs(
        job=job,
        tracks=Tracks(concepts=sorted({t.concept for t in tracks}), sam_fps=8, sam_frames=job.frames, tracks=tracks),
        roles=Roles.model_validate(data["roles"] | {"keyframes": []}),
        scene=Scene.model_validate(data["scene"]),
        transcript=Transcript.model_validate(data["transcript"]),
    )


def item_of(d: Decisions, track_id: str) -> Any:
    return next(i for i in d.items if track_id in i.track_ids)


def test_the_street_interviewer_guest_and_their_reentries_are_kept_with_no_human_action() -> None:
    i = inputs("live_street_policy_2026_11_04.json")
    d = decide(i)
    for track_id in ("face:1", "face:2", "face:5", "face:6"):  # interviewer, guest, and their re-entries
        assert item_of(d, track_id).decision == "keep", (track_id, item_of(d, track_id).reason)
    assert "in the conversation" in item_of(d, "face:1").reason
    assert all(item.decision != "keep" for item in d.items if item.kind == "child")
    hoodie = item_of(d, "face:7")  # the man in the gray hoodie interrupting with his phone: a bystander, hidden
    assert hoodie.decision == "hide"
    # Zero human edits: the plan keeps the interviewer's and guest's faces clear on every frame (no cover over 5 %
    # of a kept face box but a child's) and covers every child on every frame it is tracked.
    p = plan(i.job, i.tracks, d)
    by_id = {t.track_id: t for t in i.tracks.tracks}
    children = {item.item_id for item in d.items if item.kind == "child"}
    for item in (x for x in d.items if x.decision == "keep"):
        for t in (by_id[x] for x in item.track_ids if by_id[x].concept == "face"):
            for f, box in t.boxes.items():
                others = [e for e in p.frames.get(f, []) if e.item_id not in children]
                x1, y1, x2, y2 = box
                assert hidden_mask(others, [], i.job.height, i.job.width)[y1:y2, x1:x2].mean() <= 0.05, (
                    t.track_id, f)  # fmt: skip
    for item in (x for x in d.items if x.kind == "child"):
        for t in (by_id[x] for x in item.track_ids):
            for f, (x1, y1, x2, y2) in t.boxes.items():
                mask = hidden_mask(p.frames.get(f, []), [], i.job.height, i.job.width)
                assert float(np.mean(mask[y1:y2, x1:x2])) >= 0.95, (item.item_id, t.track_id, f)


def test_the_cafe_presenter_is_kept_and_nobody_waits_on_the_creator() -> None:
    d = decide(inputs("live_cafe_policy_2026_11_04.json"))
    assert item_of(d, "face:3").decision == "keep"  # the presenter
    for track_id in ("face:1", "face:2", "face:4", "face:6"):  # customers and bar staff
        assert item_of(d, track_id).decision == "hide", track_id
    assert [item.item_id for item in d.items if item.decision == "needs_you"] == []
