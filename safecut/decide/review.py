"""Creator overrides (WP3 step 4): ``apply_review(decisions, edits)`` without re-tracking.

The review log is the list of edits the web app sends (UI-SPEC §8 request 5, ``web/src/lib/contracts.ts``
``ReviewEdit``): ``keep``, ``hide``, ``merge``, ``remove_person``, ``cover_spot`` and ``undo``. Applying it is a pure
fold over the policy's decisions, so an undo is just an edit that drops another from the fold, and replaying the
same log always gives the same decisions. Every edit the creator makes is ``decided_by: "creator"``.

What a creator can never do: keep a locked item (a child, or an audit patch), merge a locked item into a
participant, or merge into anything but a kept person. Children therefore stay hidden whatever the log says.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import Field, RootModel

from safecut.contracts import Audit, Contract, DecisionItem, Decisions, Leak, LeakKind, Style, boxes_overlap
from safecut.decide.geometry import union

EditId = Annotated[str, Field(min_length=1, max_length=128)]
ItemId = Annotated[str, Field(pattern=r"^[ip]_[0-9]+$")]

#: API-NOTES §12: an audit patch's reason, word for word (the UI shows it as "Added by the audit").
PATCH_REASON = "Added by the audit: the final check found this after rendering and covered it."


class KeepEdit(Contract):
    type: Literal["keep"]
    edit_id: EditId
    item_id: ItemId


class HideEdit(Contract):
    type: Literal["hide"]
    edit_id: EditId
    item_id: ItemId


class MergeEdit(Contract):
    type: Literal["merge"]
    edit_id: EditId
    item_id: ItemId
    into: ItemId


class RemovePersonEdit(Contract):
    type: Literal["remove_person"]
    edit_id: EditId
    item_id: ItemId


class CoverSpotEdit(Contract):
    type: Literal["cover_spot"]
    edit_id: EditId
    spot_id: str = Field(pattern=r"^s[1-9][0-9]*$")


class UndoEdit(Contract):
    type: Literal["undo"]
    edit_id: EditId
    reverts: EditId


ReviewEdit = Annotated[
    KeepEdit | HideEdit | MergeEdit | RemovePersonEdit | CoverSpotEdit | UndoEdit, Field(discriminator="type")
]


class ReviewLog(RootModel[list[ReviewEdit]]):
    """``review.json`` in the job directory: every edit in the order the creator made it."""


class ReviewError(ValueError):
    """An edit that can't apply. ``code`` is the API's error code; ``edit_id`` names the edit."""

    def __init__(self, code: str, edit_id: str, message: str) -> None:
        super().__init__(f"{edit_id}: {message}")
        self.code = code
        self.edit_id = edit_id


@dataclass(frozen=True)
class ReviewResult:
    decisions: Decisions
    #: The audit with covered spots marked (``covered_by``), or None when no audit was given.
    audit: Audit | None
    #: Earlier edits that no longer apply after an undo (e.g. a merge into an item no longer kept), skipped.
    skipped: list[str] = field(default_factory=list[str])


def effective(edits: Sequence[ReviewEdit]) -> list[ReviewEdit]:
    """The edits still in force: first copy of each ``edit_id`` only, minus every edit an effective undo reverts
    (an undo of an undo restores its target), in log order, without the undos themselves."""
    seen: set[str] = set()
    unique: list[ReviewEdit] = []
    for edit in edits:
        if edit.edit_id not in seen:
            seen.add(edit.edit_id)
            unique.append(edit)
    reverted: set[str] = set()
    for edit in reversed(unique):  # a later undo decides about an earlier edit, so walk back
        if isinstance(edit, UndoEdit) and edit.edit_id not in reverted:
            reverted.add(edit.reverts)
    return [e for e in unique if not isinstance(e, UndoEdit) and e.edit_id not in reverted]


def _default_style(item: DecisionItem) -> Style:
    """A kept item hidden again: a person with a face gets the mosaic (DESIGN §2.7), everything else solid."""
    has_face = any(t.startswith("face:") for t in item.track_ids)
    return "pixelate" if item.kind == "person" and has_face else "solid"


def _patch_kind(leaks: list[Leak]) -> Literal["person", "plate", "other"]:
    """API-NOTES §12: a covered spot is ``person`` if any of its leaks is a face or person, else ``plate`` if any is a
    plate, else ``other``."""
    kinds: set[LeakKind] = {leak.kind for leak in leaks}
    if kinds & {"face", "person"}:
        return "person"
    return "plate" if "plate" in kinds else "other"


class _Fold:
    def __init__(self, decisions: Decisions, audit: Audit | None, frames: int | None, extend: int) -> None:
        self.items = {item.item_id: item for item in decisions.items}
        self.order = [item.item_id for item in decisions.items]
        self.audit = audit
        self.frames = frames
        self.extend = extend

    def get(self, edit_id: str, item_id: str) -> DecisionItem:
        item = self.items.get(item_id)
        if item is None:
            raise ReviewError("unknown_item", edit_id, f"no item {item_id}")
        return item

    def put(self, item: DecisionItem) -> None:
        self.items[item.item_id] = DecisionItem.model_validate(item.model_dump())

    def apply(self, edit: ReviewEdit) -> None:
        match edit:
            case KeepEdit():
                item = self.get(edit.edit_id, edit.item_id)
                if item.locked:
                    raise ReviewError("locked", edit.edit_id, f"{item.item_id} is locked hidden ({item.kind})")
                self.put(
                    item.model_copy(
                        update={
                            "decision": "keep",
                            "style": None,
                            "decided_by": "creator",
                            "hold": None,
                            "removed_by_creator": False,
                        }
                    )
                )
            case HideEdit():
                item = self.get(edit.edit_id, edit.item_id)
                style = item.style or _default_style(item)
                self.put(item.model_copy(update={"decision": "hide", "style": style, "decided_by": "creator"}))
            case RemovePersonEdit():
                item = self.get(edit.edit_id, edit.item_id)
                if item.kind not in ("person", "child") or item.origin == "audit_patch":
                    raise ReviewError("invalid_edit", edit.edit_id, f"{item.item_id} is a {item.kind}, not a person")
                update = {"decision": "hide", "style": "person_solid", "decided_by": "creator", "hold": None}
                self.put(item.model_copy(update={**update, "removed_by_creator": True}))
            case MergeEdit():
                self._merge(edit)
            case CoverSpotEdit():
                self._cover(edit)
            case UndoEdit():  # effective() drops undos before the fold
                raise ReviewError("invalid_edit", edit.edit_id, "an undo is resolved before applying")

    def _merge(self, edit: MergeEdit) -> None:
        src, dst = self.get(edit.edit_id, edit.item_id), self.get(edit.edit_id, edit.into)
        if src.item_id == dst.item_id:
            raise ReviewError("invalid_edit", edit.edit_id, "an item can't merge into itself")
        if src.locked:
            raise ReviewError("locked", edit.edit_id, f"{src.item_id} is locked hidden ({src.kind})")
        if dst.decision != "keep" or dst.kind != "person" or src.kind != "person":
            raise ReviewError("invalid_edit", edit.edit_id, "only a person merges, and only into a kept person")
        frames = sorted({*dst.evidence_frames, *src.evidence_frames})
        update = {"track_ids": [*dst.track_ids, *src.track_ids], "evidence_frames": frames, "decided_by": "creator"}
        self.put(dst.model_copy(update=update))
        del self.items[src.item_id]
        self.order.remove(src.item_id)

    def _cover(self, edit: CoverSpotEdit) -> None:
        audit = self.audit
        if audit is None or self.frames is None:
            raise ReviewError("invalid_edit", edit.edit_id, "covering a spot needs the audit and the job")
        spot = next((s for s in audit.spots if s.spot_id == edit.spot_id), None)
        if spot is None or spot.covered_by is not None:
            raise ReviewError("invalid_spot", edit.edit_id, f"no uncovered spot {edit.spot_id}")
        labels = [int(i.audit_label[1:]) for i in self.items.values() if i.audit_label]
        patches = [int(i.item_id[2:]) for i in self.items.values() if i.item_id.startswith("p_")]
        label, number = max(labels, default=0) + 1, max(patches, default=0) + 1
        half = math.ceil(audit.sample_step / 2)
        leaks = [
            leak
            for leak in audit.leaks
            if leak.unresolved and leak.frame in spot.boxes and boxes_overlap(leak.box, spot.boxes[leak.frame])
        ]
        item = DecisionItem(
            item_id=f"p_{number}",
            track_ids=[],
            kind=_patch_kind(leaks),
            decision="hide",
            reason=PATCH_REASON,
            evidence_frames=[spot.first],
            style="solid",
            decided_by="policy",
            locked=True,
            origin="audit_patch",
            audit_label=f"A{label}",
            box=union(list(spot.boxes.values())),
            first=max(0, spot.first - half - self.extend),
            last=min(self.frames - 1, spot.last + half + self.extend),
        )
        self.items[item.item_id] = item
        self.order.append(item.item_id)
        spots = [
            {**s.model_dump(), "covered_by": item.item_id} if s.spot_id == spot.spot_id else s.model_dump()
            for s in audit.spots
        ]
        self.audit = Audit.model_validate({**audit.model_dump(), "spots": spots})

    def result(self) -> tuple[Decisions, Audit | None]:
        return Decisions(items=[self.items[i] for i in self.order]), self.audit


def apply_review(
    decisions: Decisions,
    edits: Sequence[ReviewEdit],
    *,
    audit: Audit | None = None,
    frames: int | None = None,
    extend: int = 8,
) -> ReviewResult:
    """Fold the review log over ``decisions`` (the policy's, plus any audit patches).

    ``frames`` (``job.frames``) and ``audit`` are needed only for ``cover_spot``; ``extend`` is the plan's
    ``temporal.extend``. An edit that can't apply raises :class:`ReviewError` when it is the last effective edit
    (the one just sent); an earlier one that an undo left inapplicable is skipped and listed in ``skipped``.
    """
    fold = _Fold(decisions, audit, frames, extend)
    active = effective(edits)
    skipped: list[str] = []
    for index, edit in enumerate(active):
        try:
            fold.apply(edit)
        except ReviewError:
            if index == len(active) - 1:
                raise
            skipped.append(edit.edit_id)
    decided, audited = fold.result()
    return ReviewResult(decisions=decided, audit=audited, skipped=skipped)
