"""The audit's pure rules (``docs/prompts/redteam.md`` "Leak decision", API-NOTES §5 and §12; vectors L1–L14, G1–G14).

* **Exclusion:** a finding is not a leak only when it overlaps (IoU > 0.3) a *kept* track of the matching concept on
  that frame: a face only a kept ``face:`` track, a person only a kept ``person:`` track, text or a screen only a
  kept object track, a plate only a kept ``license plate:`` track; misaligned redactions and "other" never. An
  EgoBlur face is never excused by a kept ``person:`` box (L12).
* **Read-through:** red-team text, screen or plate findings on a hidden item's planned region are leaks flagged
  ``redaction_too_weak``; the item covering the largest share of the finding is the ``through_item`` and is
  re-rendered solid (L7, L14).
* **Patches:** every other leak becomes an audit patch: a static box held ``f ± (ceil(sample_step / 2) + extend)``
  (no back-fill). Leaks of one pass that touch in space and lie within a sample step of each other share one patch
  (an EgoBlur run on a moving face), boxed by their union.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from safecut.contracts import DecisionItem, Decisions, Leak, LeakKind, Plan, Spot, Track, Tracks, boxes_overlap
from safecut.decide.geometry import BoxT, box_at, clamp, intersection, iou, union
from safecut.decide.review import PATCH_REASON

#: redteam.md: a finding overlapping a kept item's visible region by more than this IoU is that item.
EXCLUDE_IOU = 0.3
#: API-NOTES §5: a red-team box under 2 px becomes a 32 px box (fail closed: it still gets patched).
MIN_SIDE = 2
DEGENERATE_SIDE = 32


def concept_matches(kind: LeakKind, concept: str) -> bool:
    """redteam.md: a finding's kind matches only its own track concept (no looser mapping)."""
    match kind:
        case "face" | "person":
            return concept == kind
        case "text" | "screen":
            return concept not in {"face", "person"}
        case "plate":
            return concept == "license plate"
        case _:
            return False


def excluded_by(
    kind: LeakKind, box: BoxT, frame: int, decisions: Decisions, by_track: Mapping[str, Track]
) -> str | None:
    """The kept item that excuses a finding on ``frame``, or None (then it's a leak)."""
    for item in decisions.items:
        if item.decision != "keep":
            continue
        for track_id in item.track_ids:
            track = by_track.get(track_id)
            if track is None or not concept_matches(kind, track.concept):
                continue
            kept = box_at(track, frame)
            if kept is not None and iou(kept, box) > EXCLUDE_IOU:
                return item.item_id
    return None


def through_item(box: BoxT, frame: int, decisions: Decisions, plan: Plan) -> str | None:
    """The hidden decision item whose planned region covers the largest share of ``box`` on ``frame`` (any positive
    overlap counts), or None. Audit patches don't count: they are fixes, not redactions read through."""
    hidden = {i.item_id for i in decisions.items if i.decision in ("hide", "needs_you") and i.origin != "audit_patch"}
    best: tuple[int, str] | None = None
    for entry in plan.frames.get(frame, []):
        if entry.item_id not in hidden or not boxes_overlap(entry.box, box):
            continue
        share = intersection(entry.box, box)
        if best is None or share > best[0] or (share == best[0] and entry.item_id < best[1]):
            best = (share, entry.item_id)
    return best[1] if best is not None else None


# ---------------------------------------------------------------------------------------------------- grid


def round_half_up(z: float) -> int:
    return math.floor(z + 0.5)


def bar_height(height: int) -> int:
    """The frame-number bar added above each sent image: 40 px at 720 p (API-NOTES §11.2), never under 24 px."""
    return max(24, round(height / 18))


def grid_box(raw: Sequence[int], *, width: int, height: int, bar: int) -> BoxT | Literal["in_bar"] | None:
    """A red-team ``[x1, y1, x2, y2]`` on the 0–1000 grid of the sent image (bar on top) → a frame box.

    Returns ``"in_bar"`` for a box entirely inside the bar (the caller decides: our own label is dropped, anything
    else becomes a whole-frame leak), and None for a malformed box (not 4 integers: also a whole-frame leak).
    """
    if len(raw) != 4:
        return None
    vx1, vy1, vx2, vy2 = (min(1000, max(0, v)) for v in raw)
    vx1, vx2 = min(vx1, vx2), max(vx1, vx2)
    vy1, vy2 = min(vy1, vy2), max(vy1, vy2)
    sent_h = height + bar
    x1, x2 = round_half_up(vx1 * width / 1000), round_half_up(vx2 * width / 1000)
    y1, y2 = round_half_up(vy1 * sent_h / 1000), round_half_up(vy2 * sent_h / 1000)
    if y2 <= bar:
        return "in_bar"
    x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
    y1, y2 = max(0, min(height, y1 - bar)), max(0, min(height, y2 - bar))
    if x2 - x1 < MIN_SIDE or y2 - y1 < MIN_SIDE:
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        half = DEGENERATE_SIDE / 2
        boxed = clamp((cx - half, cy - half, cx + half, cy + half), width, height)
        return boxed if boxed is not None else (0, 0, width, height)
    return (x1, y1, x2, y2)


def is_frame_label(text: str | None) -> bool:
    """Our own bar label (``F`` plus digits, spaces ignored), which a red-team text finding may read."""
    squashed = (text or "").replace(" ", "")
    return len(squashed) > 1 and squashed[0] == "F" and squashed[1:].isdigit()


# ---------------------------------------------------------------------------------------------------- sampling


def sample_frames(frames: int, fps: int, tracks: Tracks, plan: Plan, extra: Iterable[int] = ()) -> list[int]:
    """redteam.md inputs: 1 per second, 4 per track just outside its covered span (``first − backfill − 8``,
    ``first − backfill − 1``, ``last + extend + 1``, ``last + extend + 8``), the middle of every gap longer than
    ``gap_hold_s``, and every ``extra`` frame (those the detector flagged), clamped and de-duplicated."""
    chosen = set(range(0, frames, fps))
    backfill, extend = plan.temporal.backfill, plan.temporal.extend
    hold = plan.temporal.gap_hold_s * fps
    for t in tracks.tracks:
        for f in (t.first - backfill - 8, t.first - backfill - 1, t.last + extend + 1, t.last + extend + 8):
            chosen.add(min(frames - 1, max(0, f)))
        keys = sorted(t.boxes)
        for a, b in itertools.pairwise(keys):
            if b - a - 1 > hold:
                chosen.add((a + b) // 2)
    chosen.update(f for f in extra if 0 <= f < frames)
    return sorted(chosen)


# ---------------------------------------------------------------------------------------------------- patches


def patch_kind(kinds: Iterable[LeakKind]) -> Literal["person", "plate", "other"]:
    """API-NOTES §12: ``face``/``person`` → person, ``plate`` → plate, anything else → other."""
    found = set(kinds)
    if found & {"face", "person"}:
        return "person"
    return "plate" if "plate" in found else "other"


@dataclass
class Group:
    """Leaks that share one patch (or one spot): touching boxes within a sample step of each other."""

    leaks: list[Leak] = field(default_factory=list[Leak])

    @property
    def first(self) -> int:
        return min(leak.frame for leak in self.leaks)

    @property
    def last(self) -> int:
        return max(leak.frame for leak in self.leaks)

    @property
    def box(self) -> BoxT:
        return union([leak.box for leak in self.leaks])


def group_leaks(leaks: Sequence[Leak], step: int) -> list[Group]:
    """Group leaks in frame order: a leak joins a group with a leak no more than ``step`` frames earlier whose box
    overlaps its own; otherwise it starts a group."""
    groups: list[Group] = []
    for leak in sorted(leaks, key=lambda x: (x.frame, x.box)):
        home = next(
            (
                g
                for g in groups
                if any(leak.frame - other.frame <= step and boxes_overlap(other.box, leak.box) for other in g.leaks)
            ),
            None,
        )
        if home is None:
            groups.append(Group([leak]))
        else:
            home.leaks.append(leak)
    return sorted(groups, key=lambda g: (g.first, g.box))


def next_numbers(decisions: Decisions) -> tuple[int, int]:
    """The next free ``p_<n>`` and ``A<n>`` (labels never change once given; a new one takes the next free)."""
    patches = [int(i.item_id[2:]) for i in decisions.items if i.item_id.startswith("p_")]
    labels = [int(i.audit_label[1:]) for i in decisions.items if i.audit_label]
    return max(patches, default=0) + 1, max(labels, default=0) + 1


def make_patch(group: Group, number: int, label: int, *, frames: int, sample_step: int, extend: int) -> DecisionItem:
    half = math.ceil(sample_step / 2)
    return DecisionItem(
        item_id=f"p_{number}",
        track_ids=[],
        kind=patch_kind(leak.kind for leak in group.leaks),
        decision="hide",
        reason=PATCH_REASON,
        evidence_frames=[group.first],
        style="solid",
        decided_by="policy",
        locked=True,
        origin="audit_patch",
        audit_label=f"A{label}",
        box=group.box,
        first=max(0, group.first - half - extend),
        last=min(frames - 1, group.last + half + extend),
    )


def make_spots(unresolved: Sequence[Leak], step: int) -> list[Spot]:
    """PR #2's "Unfixed spot" chips: unresolved leaks grouped the patch way, numbered s1, s2 … by first frame."""
    spots: list[Spot] = []
    for n, group in enumerate(group_leaks(unresolved, step), start=1):
        boxes: dict[int, BoxT] = {}
        for leak in group.leaks:
            boxes[leak.frame] = union([boxes[leak.frame], leak.box]) if leak.frame in boxes else leak.box
        spots.append(Spot(spot_id=f"s{n}", first=group.first, last=group.last, boxes=boxes))
    return spots
