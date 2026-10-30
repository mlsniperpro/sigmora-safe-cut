"""Ground-truth coverage, scored on exactly the pixels the renderer changes (E3; shared with WP7's metrics).

For each labelled object on each frame it's visible on, the coverage is the share of its box under the plan's
regions and crowd fills on that frame (``draw.hidden_mask``, the renderer's own union, audit patches included).

* A **should-hide** object passes a frame at ≥ 95 % coverage; a frame below that is *exposed*. A **leak burst** is
  a run of ≥ 3 consecutive exposed frames (EVAL.md's leak-burst metric; E3 allows zero).
* A **should-keep** object is *hidden* on a frame when more than half of its box is covered (over-blur).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from safecut.contracts import Plan
from safecut.decide.geometry import BoxT, area
from safecut.render.draw import hidden_mask

#: E3: a should-hide object is covered when at least this share of its box is hidden.
COVERED = 0.95
#: E3 over-blur: a should-keep object counts as hidden when more than this share of its box is.
OVER_HIDDEN = 0.5
#: E3: this many consecutive exposed frames make a leak burst.
BURST = 3


@dataclass
class ObjectScore:
    object_id: str
    should_hide: bool
    frames: int = 0
    #: should-hide: frames at ≥ 95 % coverage; should-keep: frames more than half hidden.
    hits: int = 0
    exposed: list[int] = field(default_factory=list[int])
    bursts: int = 0

    @property
    def share(self) -> float:
        """Covered share (should-hide) or hidden share (should-keep) of the visible frames."""
        return self.hits / self.frames if self.frames else 1.0 if self.should_hide else 0.0


def coverage(plan: Plan, frame: int, box: BoxT, width: int, height: int) -> float:
    """The share of ``box`` the renderer hides on ``frame``."""
    fills = [f for f in plan.crowd_fills if frame in f.frames]
    mask = hidden_mask(plan.frames.get(frame, []), fills, height, width)
    x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3])
    total = area((x1, y1, x2, y2))
    return float(mask[y1:y2, x1:x2].sum()) / total if total else 1.0


def _bursts(frames: list[int]) -> int:
    count, run, previous = 0, 0, None
    for f in frames:
        run = run + 1 if previous is not None and f == previous + 1 else 1
        if run == BURST:
            count += 1
        previous = f
    return count


def score(
    plan: Plan,
    truth: Mapping[int, Mapping[str, BoxT]],
    should_hide: Mapping[str, bool],
    *,
    width: int,
    height: int,
) -> dict[str, ObjectScore]:
    """Score every labelled object; ``truth`` maps frame → object → box (objects absent from a frame aren't visible
    there)."""
    scores = {oid: ObjectScore(oid, hide) for oid, hide in should_hide.items()}
    for frame in sorted(truth):
        for oid, box in truth[frame].items():
            s = scores[oid]
            covered = coverage(plan, frame, box, width, height)
            s.frames += 1
            if s.should_hide:
                if covered >= COVERED:
                    s.hits += 1
                else:
                    s.exposed.append(frame)
            elif covered > OVER_HIDDEN:
                s.hits += 1
    for s in scores.values():
        s.bursts = _bursts(s.exposed)
    return scores


def passes_e3(scores: Mapping[str, ObjectScore]) -> bool:
    """E3: every should-hide object ≥ 95 % covered on ≥ 99 % of its visible frames, no should-keep object hidden on
    more than 10 % of its frames, and zero leak bursts."""
    hide_ok = all(s.share >= 0.99 and s.bursts == 0 for s in scores.values() if s.should_hide)
    keep_ok = all(s.share <= 0.10 for s in scores.values() if not s.should_hide)
    return hide_ok and keep_ok
