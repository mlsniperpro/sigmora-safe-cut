"""The perception hook of the ``muse_no_track`` baseline for SHIP's eval harness (EVAL §3 row 3).

``muse_keyframe_boxes`` returns, for each 1 fps keyframe, Muse Spark's boxes for every sensitive thing it localises
(faces, plates, screens, documents, phones, name badges; person boxes are left out, since EVAL scores what gets
hidden). The harness holds each keyframe's boxes until the next keyframe and scores them: nothing follows motion in
between, and that leak is what the baseline shows. Replay reads ``raw/baseline_muse/*.json``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from safecut.config import Settings
from safecut.meta.replay import Responder
from safecut.scout import boxes, grid

#: What the detector reports that the baseline hides (everything it is asked for except a whole person).
SENSITIVE: frozenset[str] = frozenset(boxes.KINDS) - {"person"}


async def muse_keyframe_boxes_async(
    job_dir: Path, *, replay: bool, settings: Settings | None = None, responder: Responder | None = None
) -> dict[int, list[grid.Box]]:
    job, answers = await boxes.answers_for(job_dir, replay_mode=replay, settings=settings, responder=responder)
    found = boxes.keyframe_objects(job, answers)
    return {f: [box for kind, box in objects if kind in SENSITIVE] for f, objects in sorted(found.items())}


def muse_keyframe_boxes(job_dir: Path, *, replay: bool) -> dict[int, list[tuple[int, int, int, int]]]:
    """Keyframe index → half-open boxes in prepared-clip pixels (every sent keyframe has an entry, maybe empty).
    Raises ``boxes.BaselineError`` when a detector call failed and ``replay.ReplayMissing`` when a replay has no
    recording (never a silent empty baseline)."""
    return asyncio.run(muse_keyframe_boxes_async(job_dir, replay=replay))
