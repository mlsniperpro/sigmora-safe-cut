"""Data contracts: one pydantic model per JSON file in a job directory (ARCHITECTURE.md §3).

Every stage reads and writes these files, so a change here is a contract change (AGENTS rule 3):
update ARCHITECTURE §3 in the same PR. Coordinates are pixels of the prepared clip; boxes are
half-open ``[x1, y1, x2, y2)`` ints; frames are 0-based prepared-clip indices. Per-file rules are
model validators; rules that need two files (box bounds, mask sizes, ID links, receipt totals) live in
:func:`validate_job_dir`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    RootModel,
    StrictBool,
    ValidationError,
    model_validator,
)

from safecut.config import CapKind, CodeKind, Provider

# ---------------------------------------------------------------------------
# Shared field types
# ---------------------------------------------------------------------------


def _box(value: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = value
    if x1 < 0 or y1 < 0:
        raise ValueError(f"box {list(value)} has a negative corner")
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"box {list(value)} is empty (half-open boxes need x2 > x1 and y2 > y1)")
    return value


Box = Annotated[tuple[int, int, int, int], AfterValidator(_box)]
"""Half-open pixel box ``[x1, y1, x2, y2)`` in prepared-clip pixels."""


def _rel_path(value: str) -> str:
    if not value:
        raise ValueError("path is empty")
    if "\x00" in value:
        raise ValueError("path contains a NUL byte")
    if "\\" in value:
        raise ValueError(f"path {value!r} contains a backslash (paths use '/')")
    if value.startswith("/") or (len(value) > 1 and value[1] == ":" and value[0].isalpha()):
        raise ValueError(f"path {value!r} is absolute (job-relative paths only)")
    if ".." in value.split("/"):
        raise ValueError(f"path {value!r} has a '..' segment (it would leave the job directory)")
    return value


RelPath = Annotated[str, AfterValidator(_rel_path)]
"""A path inside the job directory: not empty, relative, forward slashes, no ``..`` segment, no NUL."""


def _source_name(value: str) -> str:
    if not value:
        raise ValueError("source is empty")
    if "\x00" in value:
        raise ValueError("source contains a NUL byte")
    if ".." in value.replace("\\", "/").split("/"):
        raise ValueError(f"source {value!r} has a '..' segment")
    return value


SourceName = Annotated[str, AfterValidator(_source_name)]
"""The original upload's name (or the path or URL it was read from): never a job-dir path, so only
NUL and ``..`` traversal are rejected."""

Frame = NonNegativeInt
Role = Literal["participant", "bystander", "child", "unsure"]
StageStatus = Literal["ok", "failed", "skipped"]
SPEAKER_PATTERN = r"^[SU][1-9][0-9]*$"
TRACK_ID_PATTERN = r"^[^:]+:[0-9]+$"
FILE_ID_PATTERN = r"^file[-_][A-Za-z0-9_-]+$"
#: A Responses ID is joined into a DELETE path, so it may hold no ``/``, ``?``, ``#`` or ``..``.
RESPONSE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must carry a timezone (ISO 8601 UTC, '…Z')")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_utc_datetime)]


class Contract(BaseModel):
    """Base for every contract model: unknown keys are an error, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)


class Rle(Contract):
    """A frame-sized COCO compressed RLE mask (``size`` = the prepared clip's ``[H, W]``)."""

    size: tuple[PositiveInt, PositiveInt]
    counts: str = Field(min_length=1)


class Point(Contract):
    x: NonNegativeInt
    y: NonNegativeInt


# ---------------------------------------------------------------------------
# 3.1 job.json
# ---------------------------------------------------------------------------


class Job(Contract):
    job_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    source: SourceName
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    prepared: RelPath
    fps: int = Field(ge=1, le=30)
    width: PositiveInt
    height: PositiveInt
    frames: PositiveInt
    times: list[Annotated[float, Field(ge=0)]]
    audio: bool
    created_at: UtcDatetime
    #: Gates the open-weight second opinion (PRE-A §3.8): true only for owner/recording codes (WP5) or the
    #: hero/dev eval splits; missing means false (fail closed).
    consented: StrictBool = False
    #: The open-weight second opinion runs at most once per job, across audit re-runs (PRE-A §12, WP4).
    open_weight_attempted: StrictBool = False

    @model_validator(mode="after")
    def _times(self) -> Job:
        if len(self.times) != self.frames:
            raise ValueError(f"times has {len(self.times)} entries for {self.frames} frames")
        if any(b < a for a, b in zip(self.times, self.times[1:], strict=False)):
            raise ValueError("times must be non-decreasing (a gap repeats a frame)")
        return self


# ---------------------------------------------------------------------------
# 3.2 tracks.json
# ---------------------------------------------------------------------------


class SamObject(Contract):
    request: NonNegativeInt
    object_id: str = Field(pattern=r"^[0-9]+$")


class Track(Contract):
    track_id: str = Field(pattern=TRACK_ID_PATTERN)
    concept: str = Field(min_length=1)
    first: Frame
    last: Frame
    boxes: dict[Frame, Box]
    masks: dict[Frame, Rle] = Field(default_factory=dict[int, Rle])
    reentry_of: str | None = None
    source: str | None
    prompt: str
    origin: Literal["sam", "static"] = "sam"
    sam_object: SamObject | None = None
    child_phrase: bool = False
    conf: dict[Frame, Annotated[float, Field(ge=0, le=1)]] = Field(default_factory=dict[int, float])

    @model_validator(mode="after")
    def _consistent(self) -> Track:
        if self.track_id.rsplit(":", 1)[0] != self.concept:
            raise ValueError(f"track_id {self.track_id!r} must start with its concept {self.concept!r}")
        if self.last < self.first:
            raise ValueError(f"track {self.track_id}: last < first")
        if not self.boxes:
            raise ValueError(f"track {self.track_id} has no boxes")
        for name, frames in (("boxes", self.boxes), ("masks", self.masks), ("conf", self.conf)):
            outside = [f for f in frames if not self.first <= f <= self.last]
            if outside:
                raise ValueError(f"track {self.track_id}: {name} frame {outside[0]} outside [first, last]")
        if self.origin == "static" and (self.masks or self.source is not None or self.sam_object):
            raise ValueError(f"static track {self.track_id} must have no masks, source or sam_object")
        return self


class SamRequest(Contract):
    kind: Literal["phrase", "object_prompt"]
    concept: str | None
    file_id: str = Field(pattern=FILE_ID_PATTERN)
    fps: float = Field(gt=0)
    frames_billed: NonNegativeInt
    matches: NonNegativeInt
    usd: float = Field(ge=0)

    @model_validator(mode="after")
    def _concept(self) -> SamRequest:
        if (self.concept is None) != (self.kind == "object_prompt"):
            raise ValueError("requests[].concept is null exactly when kind is object_prompt")
        return self


class Tracks(Contract):
    concepts: list[str]
    sam_fps: int = Field(ge=1, le=30)
    sam_frames: PositiveInt
    tracks: list[Track]
    crowded_frames: list[Frame] = Field(default_factory=list[int])
    requests: list[SamRequest] = Field(default_factory=list[SamRequest])

    @model_validator(mode="after")
    def _unique(self) -> Tracks:
        ids = [t.track_id for t in self.tracks]
        if len(ids) != len(set(ids)):
            raise ValueError("track_id values must be unique")
        if self.crowded_frames != sorted(set(self.crowded_frames)):
            raise ValueError("crowded_frames must be sorted and unique")
        for track in self.tracks:
            if track.sam_object and track.sam_object.request >= len(self.requests):
                raise ValueError(f"track {track.track_id}: sam_object.request has no requests[] entry")
        return self


# ---------------------------------------------------------------------------
# 3.3 transcript.json
# ---------------------------------------------------------------------------


class Turn(Contract):
    speaker: str = Field(pattern=SPEAKER_PATTERN)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def _order(self) -> Turn:
        if self.end < self.start:
            raise ValueError("turn end must be >= start")
        return self


class Transcript(Contract):
    status: StageStatus
    source: str | None
    source_kind: Literal["primary", "fallback"] | None
    degraded: bool = False
    turns: list[Turn]

    @model_validator(mode="after")
    def _status(self) -> Transcript:
        if any(b.start < a.start for a, b in zip(self.turns, self.turns[1:], strict=False)):
            raise ValueError("turns must be sorted by start")
        if self.status != "ok":
            if self.turns or not self.degraded or self.source is not None or self.source_kind is not None:
                raise ValueError("a failed or skipped transcript has no turns, degraded=true, null source")
        elif (self.source is None) != (self.source_kind is None):
            raise ValueError("source and source_kind are both set (a model ran) or both null (no audio)")
        return self


# ---------------------------------------------------------------------------
# 3.4 scene.json
# ---------------------------------------------------------------------------


class Participant(Contract):
    description: str
    evidence: str
    speaker: str | None = Field(pattern=SPEAKER_PATTERN)
    is_creator: bool = False
    introduced_in_turn: NonNegativeInt | None
    introduction_quote: str | None

    @model_validator(mode="after")
    def _intro(self) -> Participant:
        if (self.introduced_in_turn is None) != (self.introduction_quote is None):
            raise ValueError("introduced_in_turn and introduction_quote are both set or both null")
        return self


class CandidateObject(Contract):
    what: str
    approx_time: Literal["beginning", "middle", "end", "throughout", "unknown"]


class SceneChild(Contract):
    description: str


class Scene(Contract):
    status: StageStatus
    model: str | None
    summary: str
    participants: list[Participant]
    candidate_objects: list[CandidateObject]
    children: list[SceneChild] = Field(default_factory=list[SceneChild])
    others_present: str = ""

    @model_validator(mode="after")
    def _model(self) -> Scene:
        if (self.status == "ok") != (self.model is not None):
            raise ValueError("scene.model is set exactly when status is ok")
        return self


# ---------------------------------------------------------------------------
# 3.5 roles.json
# ---------------------------------------------------------------------------


class RoleTrack(Contract):
    track_id: str = Field(pattern=TRACK_ID_PATTERN)
    role: Role
    votes: list[Role] = Field(min_length=1)
    escalated: bool
    evidence: str
    frames: list[Frame]
    failed_votes: int = Field(default=0, ge=0, le=3)
    matches_participant: NonNegativeInt | None = None
    suggested_role: Literal["participant", "bystander", "child"] | None = None
    escalation_evidence: str | None = None
    escalation_frames: list[Frame] | None = None

    @model_validator(mode="after")
    def _votes(self) -> RoleTrack:
        if self.failed_votes > len(self.votes):
            raise ValueError(f"track {self.track_id}: failed_votes exceeds the number of votes")
        if not self.escalated and (self.escalation_evidence is not None or self.escalation_frames is not None):
            raise ValueError(f"track {self.track_id}: escalation fields set without an escalation")
        return self


class RoleObject(Contract):
    track_id: str = Field(pattern=TRACK_ID_PATTERN)
    sensitive: bool
    content: str
    frames: list[Frame]


class Missed(Contract):
    what: str
    sam_phrase: str = Field(min_length=1)
    frame: Frame
    point: Point | None
    box: Box | None = None
    recurs: bool = False
    track_ids: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def _located(self) -> Missed:
        if self.point is None and self.box is None:
            raise ValueError("a missed item needs a point or a box")
        return self


class Roles(Contract):
    status: StageStatus
    model: str | None
    tracks: list[RoleTrack]
    objects: list[RoleObject] = Field(default_factory=list[RoleObject])
    missed: list[Missed] = Field(default_factory=list[Missed])
    keyframes: list[RelPath] = Field(default_factory=list[RelPath])

    @model_validator(mode="after")
    def _status(self) -> Roles:
        if (self.status == "ok") != (self.model is not None):
            raise ValueError("roles.model is set exactly when status is ok")
        if self.status != "ok" and any(t.role != "unsure" for t in self.tracks):
            raise ValueError("a failed or skipped role pass leaves every track unsure")
        return self


# ---------------------------------------------------------------------------
# 3.6 decisions.json
# ---------------------------------------------------------------------------

Hold = Literal["no_scene", "no_speech", "no_roles", "unmatched_child", "no_speech_link"]
Style = Literal["solid", "pixelate", "person_solid"]


class DecisionItem(Contract):
    item_id: str = Field(pattern=r"^[ip]_[0-9]+$")
    track_ids: list[str]
    kind: Literal["person", "child", "plate", "screen", "document", "other"]
    decision: Literal["hide", "keep", "needs_you"]
    reason: str = Field(min_length=1)
    evidence_frames: list[Frame]
    style: Style | None
    decided_by: Literal["policy", "model", "creator"]
    locked: bool
    hold: Hold | None = None
    origin: Literal["sam", "static", "audit_patch"] = "sam"
    audit_label: str | None = Field(default=None, pattern=r"^A[1-9][0-9]*$")
    box: Box | None = None
    first: Frame | None = None
    last: Frame | None = None

    @model_validator(mode="after")
    def _rules(self) -> DecisionItem:
        if (self.decision == "keep") != (self.style is None):
            raise ValueError(f"{self.item_id}: style is null exactly for keep items")
        if self.kind == "child" and (self.decision != "hide" or not self.locked):
            raise ValueError(f"{self.item_id}: children are always hidden and locked")
        if self.origin == "audit_patch":
            if self.box is None or self.first is None or self.last is None or self.last < self.first:
                raise ValueError(f"{self.item_id}: an audit patch needs box, first and last")
            if self.track_ids or self.decision != "hide" or not self.locked or self.audit_label is None:
                raise ValueError(f"{self.item_id}: an audit patch is a locked hide with no tracks and a label")
            # PRE-A §12: a policy decision, solid, with one evidence frame (the finding's) inside its span.
            if self.style != "solid" or self.decided_by != "policy":
                raise ValueError(f"{self.item_id}: an audit patch is solid and decided by policy")
            if len(self.evidence_frames) != 1 or not self.first <= self.evidence_frames[0] <= self.last:
                raise ValueError(f"{self.item_id}: an audit patch has one evidence frame inside first..last")
        else:
            if self.box is not None or self.first is not None or self.last is not None:
                raise ValueError(f"{self.item_id}: box/first/last are only for audit patches")
            if not self.track_ids:
                raise ValueError(f"{self.item_id}: a tracked item needs track_ids")
        return self


class Decisions(Contract):
    items: list[DecisionItem]

    @model_validator(mode="after")
    def _unique(self) -> Decisions:
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item_id values must be unique")
        labels = [i.audit_label for i in self.items if i.audit_label]
        if len(labels) != len(set(labels)):
            raise ValueError("audit_label values must be unique")
        return self


# ---------------------------------------------------------------------------
# 3.7 plan.json
# ---------------------------------------------------------------------------


class Padding(Contract):
    face: float = Field(ge=0, le=1)
    default: float = Field(ge=0, le=1)
    px: NonNegativeInt


class Temporal(Contract):
    extend: NonNegativeInt
    backfill: NonNegativeInt
    gap_hold_s: float = Field(ge=0)


class PlanEntry(Contract):
    item_id: str = Field(pattern=r"^[ip]_[0-9]+$")
    shape: Literal["box", "mask"]
    box: Box
    mask: Rle | None
    style: Style
    grid: tuple[NonNegativeInt, NonNegativeInt, PositiveInt] | None
    source: Literal["decision", "audit_patch"] = "decision"

    @model_validator(mode="after")
    def _shape(self) -> PlanEntry:
        if (self.shape == "mask") != (self.mask is not None):
            raise ValueError("mask is set exactly when shape is mask")
        if (self.style == "pixelate") != (self.grid is not None):
            raise ValueError("grid is set exactly when style is pixelate")
        return self


class CrowdFill(Contract):
    frames: list[Frame] = Field(min_length=1)
    box: Box


class Plan(Contract):
    padding: Padding
    temporal: Temporal
    frames: dict[Frame, list[PlanEntry]]
    crowd_fills: list[CrowdFill] = Field(default_factory=list[CrowdFill])


# ---------------------------------------------------------------------------
# 3.8 audit.json
# ---------------------------------------------------------------------------

LeakKind = Literal["face", "person", "text", "plate", "screen", "misaligned_redaction", "other"]
BlockedReason = Literal["unresolved_leaks", "audit_failed", "over_budget"]


class EgoBlurSummary(Contract):
    model: Literal["egoblur-gen2", "egoblur-gen1", "yunet-face"]
    faces: NonNegativeInt | None
    plates: NonNegativeInt | None


class Leak(Contract):
    frame: Frame
    box: Box
    kind: LeakKind
    detector: Literal["egoblur", "redteam", "redteam_open"]
    patched_item: str | None
    flag: Literal["redaction_too_weak"] | None = None
    through_item: str | None = None
    unresolved: bool = False

    @model_validator(mode="after")
    def _links(self) -> Leak:
        if (self.flag is None) != (self.through_item is None):
            raise ValueError("through_item is set exactly on a flagged leak (the item it reads through)")
        if self.unresolved and self.patched_item is not None:
            raise ValueError("an unresolved leak has no patched_item")
        return self


class RedteamNone(Contract):
    frame: Frame
    finding: Literal["none"]


class RedteamHit(Contract):
    frame: Frame
    finding: Literal["hit"]
    kind: LeakKind
    text: str | None
    detail: str
    box: Box
    confidence: Literal["low", "medium", "high"]
    excluded_by: str | None = None


class OpenWeightSummary(Contract):
    """The open-weight second opinion (PRE-A §3.8): it can only add leaks and never blocks the job."""

    model: str | None = None
    status: Literal["ok", "failed", "off"] = "off"
    frames: NonNegativeInt = 0
    findings: NonNegativeInt = 0

    @model_validator(mode="after")
    def _consistent(self) -> OpenWeightSummary:
        if self.status == "off" and (self.model is not None or self.frames or self.findings):
            raise ValueError("an open-weight opinion that didn't run has no model, frames or findings")
        if self.status != "off" and self.model is None:
            raise ValueError("an open-weight opinion that ran names its model (the receipt and README quote it)")
        # "failed" may still carry findings and frames: batches that finished keep theirs (redteam.md).
        return self


class Spot(Contract):
    spot_id: str = Field(pattern=r"^s[1-9][0-9]*$")
    first: Frame
    last: Frame
    boxes: dict[Frame, Box] = Field(min_length=1)
    covered_by: str | None = None

    @model_validator(mode="after")
    def _span(self) -> Spot:
        if self.first > self.last:
            raise ValueError(f"spot {self.spot_id}: first {self.first} is after last {self.last}")
        outside = sorted(f for f in self.boxes if not self.first <= f <= self.last)
        if outside:
            raise ValueError(f"spot {self.spot_id}: boxes on frames {outside[:5]} outside {self.first}-{self.last}")
        return self


class Audit(Contract):
    frames_scanned: NonNegativeInt
    egoblur: EgoBlurSummary
    leaks: list[Leak]
    redteam: list[RedteamNone | RedteamHit]
    unresolved: NonNegativeInt
    passes: NonNegativeInt
    sample_step: PositiveInt
    spots: list[Spot] = Field(default_factory=list[Spot])
    blocked_reason: BlockedReason | None
    audit_budget_cause: Literal["job_cap", "daily_cap", "code_cap", "pilot_pool_cap"] | None = None
    open_weight: OpenWeightSummary = Field(default_factory=OpenWeightSummary)
    redteam_open: list[RedteamNone | RedteamHit] = Field(default_factory=list[RedteamNone | RedteamHit])

    @model_validator(mode="after")
    def _gate(self) -> Audit:
        # A failed opinion keeps the finished batches' entries and leaks (redteam.md); only one that never ran
        # ("off") has none.
        if self.open_weight.status == "off" and (
            self.redteam_open or any(leak.detector == "redteam_open" for leak in self.leaks)
        ):
            raise ValueError("redteam_open entries and leaks need an open-weight opinion that ran")
        for hit in self.redteam:
            # redteam.md: every red-team hit is a leak (on its own region, not just its frame) unless the
            # kept-clear rule excluded it. `redteam_open` stays advisory until the grid check passes.
            if not isinstance(hit, RedteamHit) or hit.excluded_by is not None:
                continue
            if not any(leak.frame == hit.frame and boxes_overlap(leak.box, hit.box) for leak in self.leaks):
                raise ValueError(f"red-team hit at frame {hit.frame} is neither excluded nor a leak on its box")
        open_leaks = sum(leak.unresolved for leak in self.leaks)
        if self.unresolved < open_leaks:
            # PRE-A §12: each unresolved leak counts 1 in `unresolved`, the one publish gate.
            raise ValueError(f"unresolved {self.unresolved} is less than the {open_leaks} unresolved leaks")
        for leak in self.leaks:
            # A flag says which item a model read through; only a patch (that item re-rendered solid, or an
            # audit patch) fixes the leak, so a leak with neither a patch nor `unresolved` is refused.
            if leak.patched_item is None and not leak.unresolved:
                raise ValueError(f"leak at frame {leak.frame} is neither patched nor unresolved")
        if self.open_weight.status != "off":
            frames = len({entry.frame for entry in self.redteam_open})
            hits = sum(isinstance(entry, RedteamHit) for entry in self.redteam_open)
            if (self.open_weight.frames, self.open_weight.findings) != (frames, hits):
                raise ValueError(
                    f"open_weight says {self.open_weight.frames} frames and {self.open_weight.findings} findings;"
                    f" redteam_open holds {frames} frames and {hits} findings"
                )
        if (self.blocked_reason is not None) != (self.unresolved > 0):
            raise ValueError("blocked_reason is set exactly when unresolved > 0 (the one publish gate)")
        if (self.audit_budget_cause is not None) != (self.blocked_reason == "over_budget"):
            raise ValueError("audit_budget_cause is set exactly when blocked_reason is over_budget")
        return self

    @property
    def publishable(self) -> bool:
        return self.unresolved == 0


# ---------------------------------------------------------------------------
# 3.9 receipt.json
# ---------------------------------------------------------------------------


class ReceiptItem(DecisionItem):
    thumbnail: RelPath | None = None


class ReceiptAudit(Contract):
    auditor: str
    frames_scanned: NonNegativeInt
    leaks_found: NonNegativeInt
    leaks_patched: NonNegativeInt
    unresolved: NonNegativeInt
    passes: NonNegativeInt
    #: PRE-A §10.3: the receipt stage also runs after [Run the audit again] on a blocked audit, so a receipt
    #: may carry unresolved > 0; publishing stays off through the one gate, unresolved == 0.
    blocked_reason: BlockedReason | None


class DataHandling(Contract):
    mode: Literal["standard"]
    store: bool
    store_by_model: dict[str, bool]
    no_store_param: list[str]
    files_deleted: bool
    #: SAM responses whose deletion was requested (``responses.json`` entries with ``requested_at`` set) when
    #: ``store: false`` can't be sent; 0 when none were needed. Meta soft-deletes, so it's "deletion requested".
    responses_delete_requested: NonNegativeInt
    notes: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def _store(self) -> DataHandling:
        if self.store != any(self.store_by_model.values()):
            raise ValueError("data_handling.store must equal any(store_by_model.values())")
        overlap = set(self.no_store_param) & set(self.store_by_model)
        if overlap:
            raise ValueError(f"{sorted(overlap)} cannot be in both store_by_model and no_store_param")
        return self


class ReceiptBody(Contract):
    """Everything in ``receipt.json`` except ``hash``: what the hash chain covers."""

    job_id: str = Field(min_length=1)
    items: list[ReceiptItem]
    audit: ReceiptAudit
    models: dict[str, str]
    data_handling: DataHandling
    approved_by: Literal["creator"]
    approved_at: UtcDatetime
    cost_usd: float = Field(ge=0)
    cost_usd_estimated: float = Field(default=0, ge=0)
    #: Baseten spend (``provider: "baseten"`` cost lines), shown apart from the Meta ``cost_usd`` (PRE-A §3.8).
    cost_usd_baseten: float = Field(default=0, ge=0)
    prev_hash: str | None = Field(pattern=SHA256_PATTERN)


class Receipt(ReceiptBody):
    hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _hash(self) -> Receipt:
        if self.hash != receipt_hash(self):
            raise ValueError("receipt hash does not match sha256(prev_hash + canonical_json(body))")
        return self

    @classmethod
    def seal(cls, body: ReceiptBody) -> Receipt:
        """Compute the hash for ``body`` and return the sealed receipt."""
        return cls.model_validate({**body.model_dump(mode="json"), "hash": receipt_hash(body)})


def boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """Half-open boxes share a positive area (redteam.md's "on")."""
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def canonical_json(data: Any) -> str:
    """Sorted keys, compact separators, UTF-8 (non-ASCII kept): the hash chain's byte form."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def receipt_hash(body: ReceiptBody) -> str:
    """``sha256(prev_hash + canonical_json(body))`` over the validated body without ``hash``.

    A first receipt (``prev_hash`` null) chains from the empty string. Hashing the validated model,
    not raw JSON, means defaults and timestamp formats are normalised before hashing.
    """
    data = ReceiptBody.model_validate(body.model_dump(include=set(ReceiptBody.model_fields))).model_dump(mode="json")
    prev = data.get("prev_hash") or ""
    return hashlib.sha256((prev + canonical_json(data)).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3.10 cost.jsonl and files.json
# ---------------------------------------------------------------------------


class CostLine(Contract):
    ts: UtcDatetime
    #: Every Meta cap sums only ``meta`` lines; Baseten credits are a separate pot (PRE-A §3.8).
    provider: Provider
    job_id: str | None
    stage: str = Field(min_length=1)
    model: str | None
    attempt: NonNegativeInt
    units: dict[str, float]
    usd: float = Field(ge=0)
    estimated: bool
    request_id: str | None
    cap: CapKind | None = None
    code_kind: CodeKind
    code_id: str | None

    @model_validator(mode="after")
    def _rules(self) -> CostLine:
        if (self.code_kind == "system") != (self.job_id is None):
            raise ValueError("job_id is null exactly on system lines (healthz, startup probe)")
        is_budget = self.stage.startswith("budget:")
        if is_budget != (self.cap is not None):
            raise ValueError("cap is set exactly on budget:<stage> lines")
        if is_budget and (self.usd != 0 or self.attempt != 0 or self.request_id is not None or self.estimated):
            raise ValueError("a budget line records a stop: usd 0, attempt 0, no request, not estimated")
        return self


class FileEntry(Contract):
    name: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    file_id: str | None = Field(pattern=FILE_ID_PATTERN)
    purpose: Literal["user_data"] = "user_data"
    created_at: UtcDatetime
    deleted_at: UtcDatetime | None = None
    orphan: bool = False

    @model_validator(mode="after")
    def _orphan(self) -> FileEntry:
        if self.orphan != (self.file_id is None):
            raise ValueError("an entry is an orphan exactly when its file_id never arrived")
        return self


class FilesIndex(RootModel[list[FileEntry]]):
    @property
    def all_deleted(self) -> bool:
        """``files_deleted: true`` needs every upload deleted and every orphan resolved (PRE-A §10.4).

        An orphan (an upload whose ID never arrived) is resolved, ``deleted_at`` set, only after a listing found
        and deleted every unrecorded copy of its name (``FileStore.reconcile_orphans``).
        """
        return all(e.deleted_at is not None for e in self.root)

    def live(self, name: str) -> FileEntry | None:
        """The newest undeleted entry with a file ID for ``name``."""
        matches = [e for e in self.root if e.name == name and e.file_id and e.deleted_at is None]
        return max(matches, key=lambda e: e.created_at) if matches else None


class ResponseEntry(Contract):
    """One SAM response kept at Meta because ``store: false`` couldn't be sent (PRE-A §10.4 "SAM responses")."""

    response_id: str = Field(pattern=RESPONSE_ID_PATTERN)
    requested_at: UtcDatetime | None = None


class ResponsesIndex(RootModel[list[ResponseEntry]]):
    @property
    def requested(self) -> int:
        """The receipt's ``data_handling.responses_delete_requested``."""
        return sum(e.requested_at is not None for e in self.root)

    @property
    def pending(self) -> list[str]:
        return [e.response_id for e in self.root if e.requested_at is None]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

JOB_FILES: Mapping[str, type[BaseModel]] = {
    "job.json": Job,
    "tracks.json": Tracks,
    "transcript.json": Transcript,
    "scene.json": Scene,
    "roles.json": Roles,
    "decisions.json": Decisions,
    "plan.json": Plan,
    "audit.json": Audit,
    "receipt.json": Receipt,
    "files.json": FilesIndex,
    "responses.json": ResponsesIndex,
}


class ContractError(ValueError):
    """A job-directory file is missing, malformed, or inconsistent with another file."""


def load[M: BaseModel](path: str | Path, model: type[M]) -> M:
    """Read ``path`` and validate it as ``model``; raise :class:`ContractError` with the file name."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ContractError(f"{path.name}: missing") from None
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise ContractError(f"{path.name}: {exc.error_count()} error(s): {_summarise(exc)}") from exc


def dump(model: BaseModel, path: str | Path) -> Path:
    """Write ``model`` as JSON atomically (temp file + rename), so readers never see a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model.model_dump_json(indent=1).encode("utf-8") + b"\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def append_cost_line(line: CostLine, path: str | Path) -> None:
    """Append one line to ``cost.jsonl`` in a single write (``O_APPEND`` keeps lines whole)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = line.model_dump_json().encode("utf-8") + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def read_cost_lines(path: str | Path) -> Iterator[CostLine]:
    """Stream ``cost.jsonl`` line by line (never loads the whole file)."""
    path = Path(path)
    if not path.exists():
        return
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                yield CostLine.model_validate_json(raw)
            except ValidationError as exc:
                raise ContractError(f"{path.name} line {number}: {_summarise(exc)}") from exc


def measured_usd(lines: Iterator[CostLine] | list[CostLine], *, provider: Provider = "meta") -> tuple[float, float]:
    """``(measured, possibly_billed)`` for one provider: reported figures sum only ``estimated: false`` lines
    (AGENTS rule 9), and Meta and Baseten spend are always reported apart (PRE-A §3.8)."""
    measured = 0.0
    estimated = 0.0
    for line in lines:
        if line.provider != provider:
            continue
        if line.estimated:
            estimated += line.usd
        else:
            measured += line.usd
    return measured, estimated


def now_utc() -> datetime:
    return datetime.now(UTC)


def _summarise(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors(include_input=False)[:5]
    ]
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Cross-file checks
# ---------------------------------------------------------------------------


_COST_TOLERANCE = 1e-6


def _check_box(box: tuple[int, int, int, int], job: Job, where: str) -> None:
    if box[2] > job.width or box[3] > job.height:
        raise ContractError(f"{where}: box {list(box)} exceeds the {job.width}x{job.height} frame")


def _check_frame(frame: int, job: Job, where: str) -> None:
    if frame >= job.frames:
        raise ContractError(f"{where}: frame {frame} >= job.frames {job.frames}")


def _check_rle(rle: Rle, job: Job, where: str) -> None:
    if tuple(rle.size) != (job.height, job.width):
        raise ContractError(f"{where}: mask size {list(rle.size)} != frame [{job.height}, {job.width}]")


def _check_tracks(tracks: Tracks, job: Job) -> None:
    for frame in tracks.crowded_frames:
        _check_frame(frame, job, "tracks.json crowded_frames")
    for t in tracks.tracks:
        _check_frame(t.last, job, f"tracks.json {t.track_id}")
        for f, box in t.boxes.items():
            _check_box(box, job, f"tracks.json {t.track_id} frame {f}")
        for f, rle in t.masks.items():
            _check_rle(rle, job, f"tracks.json {t.track_id} frame {f}")


def _check_transcript(transcript: Transcript, job: Job) -> None:
    if not job.audio and (transcript.source_kind is not None or transcript.turns):
        raise ContractError("transcript.json: a clip without audio has no turns and no source_kind")
    if job.audio and transcript.status == "ok" and transcript.source_kind is None:
        raise ContractError("transcript.json: a successful transcript with audio needs source_kind")


def _check_plan(plan: Plan, job: Job, decisions: Decisions | None) -> None:
    known = None if decisions is None else {i.item_id for i in decisions.items}
    for frame, entries in plan.frames.items():
        _check_frame(frame, job, "plan.json frames")
        for e in entries:
            if known is not None and e.item_id not in known:
                raise ContractError(f"plan.json frame {frame}: unknown item {e.item_id} (not in decisions.json)")
            _check_box(e.box, job, f"plan.json frame {frame} {e.item_id}")
            if e.mask is not None:
                _check_rle(e.mask, job, f"plan.json frame {frame} {e.item_id}")
    for fill in plan.crowd_fills:
        _check_box(fill.box, job, "plan.json crowd_fills")
        for frame in fill.frames:
            _check_frame(frame, job, "plan.json crowd_fills")


def _check_roles(roles: Roles, job: Job, tracks: Tracks | None) -> None:
    known = None if tracks is None else {t.track_id for t in tracks.tracks}

    def check_track(track_id: str, where: str) -> None:
        if known is not None and track_id not in known:
            raise ContractError(f"{where}: unknown track {track_id} (not in tracks.json)")

    for t in roles.tracks:
        where = f"roles.json track {t.track_id}"
        check_track(t.track_id, where)
        for frame in [*t.frames, *(t.escalation_frames or [])]:
            _check_frame(frame, job, where)
    for obj in roles.objects:
        where = f"roles.json object {obj.track_id}"
        check_track(obj.track_id, where)
        for frame in obj.frames:
            _check_frame(frame, job, where)
    for m in roles.missed:
        where = f"roles.json missed {m.sam_phrase!r}"
        _check_frame(m.frame, job, where)
        if m.box is not None:
            _check_box(m.box, job, where)
        if m.point is not None and (m.point.x >= job.width or m.point.y >= job.height):
            raise ContractError(
                f"{where}: point ({m.point.x}, {m.point.y}) is outside the {job.width}x{job.height} frame"
            )
        for track_id in m.track_ids:
            check_track(track_id, where)


def _check_item(item: DecisionItem, job: Job, where: str) -> None:
    """Frame and box bounds of one decision item (a receipt item is a copy of one)."""
    for frame in item.evidence_frames:
        _check_frame(frame, job, f"{where} evidence_frames")
    if item.box is not None:
        _check_box(item.box, job, where)
    for frame in (item.first, item.last):
        if frame is not None:
            _check_frame(frame, job, where)


def _check_decisions(decisions: Decisions, job: Job, tracks: Tracks | None) -> None:
    known = None if tracks is None else {t.track_id for t in tracks.tracks}
    for item in decisions.items:
        where = f"decisions.json {item.item_id}"
        if known is not None:
            missing = [tid for tid in item.track_ids if tid not in known]
            if missing:
                raise ContractError(f"{where}: unknown track {missing[0]}")
        _check_item(item, job, where)


def _check_audit(audit: Audit, job: Job) -> None:
    # EgoBlur scans every output frame; a frame no pass ran on counts in `unresolved` (PRE-A §12, vector L10).
    if audit.frames_scanned > job.frames:
        raise ContractError(f"audit.json: frames_scanned {audit.frames_scanned} > the job's {job.frames} frames")
    unscanned = job.frames - audit.frames_scanned
    open_leaks = sum(leak.unresolved for leak in audit.leaks)
    if audit.unresolved < open_leaks + unscanned:
        # The counts add (PRE-A §12): each unresolved leak counts 1, and so does each frame no pass ran on.
        raise ContractError(
            f"audit.json: {unscanned} frames weren't scanned and {open_leaks} leaks are unresolved, but unresolved"
            f" is {audit.unresolved}"
        )
    if audit.unresolved == 0 and audit.passes == 0:
        raise ContractError("audit.json: a publishable audit ran no red-team pass")
    # redteam.md: one red-team entry per frame sent, at least 1 per second (sample_step frames), and frames are
    # never silently skipped. Whatever the sampling phase, that is at least frames // sample_step distinct frames.
    if audit.sample_step != job.fps:
        # PRE-A §12: sample_step = round(job.fps), the red-team's 1 fps step in output frames (fps is an int).
        raise ContractError(f"audit.json: sample_step {audit.sample_step} != the job's {job.fps} fps")
    sampled = len({entry.frame for entry in audit.redteam})
    floor = max(1, job.frames // job.fps)
    if audit.unresolved == 0 and sampled < floor:
        raise ContractError(
            f"audit.json: a publishable audit has red-team entries on {sampled} frames; 1 per second needs {floor}"
        )
    for spot in audit.spots:
        where = f"audit.json spot {spot.spot_id}"
        _check_frame(spot.first, job, where)
        _check_frame(spot.last, job, where)
        for frame, box in spot.boxes.items():
            _check_frame(frame, job, where)
            _check_box(box, job, f"{where} frame {frame}")
    for leak in audit.leaks:
        _check_frame(leak.frame, job, "audit.json leaks")
        _check_box(leak.box, job, f"audit.json leak at frame {leak.frame}")
    for name, entries in (("redteam", audit.redteam), ("redteam_open", audit.redteam_open)):
        for entry in entries:
            _check_frame(entry.frame, job, f"audit.json {name}")
            if isinstance(entry, RedteamHit):
                _check_box(entry.box, job, f"audit.json {name} at frame {entry.frame}")


def _check_receipt(
    receipt: Receipt,
    job: Job,
    *,
    decisions: Decisions | None,
    audit: Audit | None,
    files: FilesIndex | None,
    responses: ResponsesIndex | None,
    cost_path: Path,
) -> None:
    if receipt.job_id != job.job_id:
        raise ContractError(f"receipt.json: job_id {receipt.job_id!r} != job.json job_id {job.job_id!r}")
    for item in receipt.items:
        _check_item(item, job, f"receipt.json {item.item_id}")
    if decisions is not None:
        _check_receipt_items(receipt, decisions)
    if audit is not None:
        summary = receipt.audit
        for name, got, want in (
            ("frames_scanned", summary.frames_scanned, audit.frames_scanned),
            ("leaks_found", summary.leaks_found, len(audit.leaks)),
            ("leaks_patched", summary.leaks_patched, sum(leak.patched_item is not None for leak in audit.leaks)),
            ("unresolved", summary.unresolved, audit.unresolved),
            ("passes", summary.passes, audit.passes),
            ("blocked_reason", summary.blocked_reason, audit.blocked_reason),
        ):
            if got != want:
                raise ContractError(f"receipt.json audit.{name} {got!r} != audit.json {want!r}")
    if receipt.data_handling.files_deleted and files is not None and not files.all_deleted:
        raise ContractError("receipt.json: files_deleted is true but files.json has an undeleted or orphan upload")
    if responses is not None and receipt.data_handling.responses_delete_requested != responses.requested:
        raise ContractError(
            f"receipt.json: responses_delete_requested {receipt.data_handling.responses_delete_requested}"
            f" != {responses.requested} requested in responses.json"
        )
    if cost_path.exists():
        _check_receipt_cost(receipt, job, cost_path)


def _check_receipt_items(receipt: Receipt, decisions: Decisions) -> None:
    """Item IDs match as a multiset, then every field but ``thumbnail`` matches item by item."""
    receipt_ids = Counter(i.item_id for i in receipt.items)
    decision_ids = Counter(i.item_id for i in decisions.items)
    if receipt_ids != decision_ids:
        missing = sorted((decision_ids - receipt_ids).elements())
        extra = sorted((receipt_ids - decision_ids).elements())
        raise ContractError(f"receipt.json items do not match decisions.json: missing {missing}, unexpected {extra}")
    by_id = {d.item_id: d.model_dump() for d in decisions.items}
    for item in receipt.items:
        got = item.model_dump(exclude={"thumbnail"})
        want = by_id[item.item_id]
        differing = sorted(name for name in want if got[name] != want[name])
        if differing:
            raise ContractError(f"receipt.json {item.item_id} differs from decisions.json in {differing}")


def _check_receipt_cost(receipt: Receipt, job: Job, cost_path: Path) -> None:
    """Sum this job's ``cost.jsonl`` lines per provider and compare with the receipt.

    A line of another job, or a system line (``job_id`` null: healthz, startup probe), has no place in a
    job directory's ``cost.jsonl`` and is rejected rather than silently skipped.
    """
    lines = list(read_cost_lines(cost_path))
    for number, line in enumerate(lines, start=1):
        if line.job_id is None:
            raise ContractError(f"cost.jsonl line {number}: a system line in this job's cost.jsonl")
        if line.job_id != job.job_id:
            raise ContractError(
                f"cost.jsonl line {number}: another job's line in this job's cost.jsonl"
                f" ({line.job_id!r} != {job.job_id!r})"
            )
    meta, meta_estimated = measured_usd(lines, provider="meta")
    baseten, _ = measured_usd(lines, provider="baseten")
    for name, got, want, label in (
        ("cost_usd", receipt.cost_usd, meta, "Meta"),
        ("cost_usd_estimated", receipt.cost_usd_estimated, meta_estimated, "Meta"),
        ("cost_usd_baseten", receipt.cost_usd_baseten, baseten, "Baseten"),
    ):
        if abs(got - want) > _COST_TOLERANCE:
            raise ContractError(f"receipt.json {name} {got} != cost.jsonl {label} total {want}")


def _check_plan_covers(plan: Plan, decisions: Decisions, tracks: Tracks | None, job: Job) -> None:
    """Every hidden item (``hide``, or ``needs_you``, which renders hidden) has a plan entry on every frame its
    tracks are present (each track's own first..last, so a merged item's gap between tracks needs none), or
    on an audit patch's own first..last, clamped to the clip. Extend/backfill entries beyond that are fine."""
    spans = {t.track_id: (t.first, t.last) for t in tracks.tracks} if tracks is not None else {}
    planned = {(frame, e.item_id) for frame, entries in plan.frames.items() for e in entries}
    for item in decisions.items:
        if item.decision not in ("hide", "needs_you"):
            continue
        present = _present_frames(item, spans)
        missing = [f for f in sorted(present) if f < job.frames and (f, item.item_id) not in planned]
        if missing:
            raise ContractError(f"plan.json: hidden item {item.item_id} has no entry on frames {missing[:10]}")


def _check_links(
    scene: Scene | None,
    transcript: Transcript | None,
    roles: Roles | None,
    decisions: Decisions | None,
    audit: Audit | None,
    *,
    tracks: Tracks | None = None,
    plan: Plan | None = None,
) -> None:
    """Indexes and IDs one file takes from another (WP3 indexes ``scene.participants[matches_participant]``)."""
    if scene is not None and roles is not None:
        for track in roles.tracks:
            index = track.matches_participant
            if index is not None and index >= len(scene.participants):
                raise ContractError(
                    f"roles.json {track.track_id}: matches_participant {index} but scene.json has"
                    f" {len(scene.participants)} participants"
                )
    if scene is not None and transcript is not None:
        for number, participant in enumerate(scene.participants):
            turn = participant.introduced_in_turn
            if turn is not None and turn >= len(transcript.turns):
                raise ContractError(
                    f"scene.json participant {number}: introduced_in_turn {turn} but transcript.json has"
                    f" {len(transcript.turns)} turns"
                )
    if decisions is not None and audit is not None:
        items = {item.item_id for item in decisions.items}
        refs: list[tuple[str, str | None]] = []
        for leak in audit.leaks:
            refs += [(f"leak at frame {leak.frame} patched_item", leak.patched_item)]
            refs += [(f"leak at frame {leak.frame} through_item", leak.through_item)]
        refs += [(f"spot {spot.spot_id} covered_by", spot.covered_by) for spot in audit.spots]
        for name, entries in (("redteam", audit.redteam), ("redteam_open", audit.redteam_open)):
            refs += [
                (f"{name} at frame {entry.frame} excluded_by", entry.excluded_by)
                for entry in entries
                if isinstance(entry, RedteamHit)
            ]
        for where, ref in refs:
            if ref is not None and ref not in items:
                raise ContractError(f"audit.json {where}: {ref!r} is not an item in decisions.json")
        _check_patches(audit, decisions, tracks, plan)


def _present_frames(item: DecisionItem, spans: Mapping[str, tuple[int, int]]) -> set[int]:
    """Frames an item exists on: an audit patch's own first..last, else each of its tracks' first..last."""
    if item.first is not None and item.last is not None:
        return set(range(item.first, item.last + 1))
    return {f for t in item.track_ids if t in spans for f in range(spans[t][0], spans[t][1] + 1)}


def _hidden_frames(item: DecisionItem, spans: Mapping[str, tuple[int, int]], plan: Plan | None) -> set[int] | None:
    """Frames an item hides: where it exists, plus every frame the plan renders it on (the guard's extend and
    backfill reach past its tracks). ``None`` when neither tracks nor a plan say."""
    frames = _present_frames(item, spans)
    if plan is not None:
        frames |= {f for f, entries in plan.frames.items() if any(e.item_id == item.item_id for e in entries)}
    return frames or None


def _regions(item: DecisionItem, frame: int, plan: Plan | None) -> list[tuple[int, int, int, int]]:
    """Where an item hides on ``frame``: what the plan renders there (the guard pads an audit patch's box
    outward, so a valid plan's box contains it); an audit patch's own box only where no plan says."""
    planned = [e.box for e in plan.frames.get(frame, []) if e.item_id == item.item_id] if plan is not None else []
    return planned or ([item.box] if item.box is not None else [])


def _check_solid(through: DecisionItem | None, plan: Plan | None, where: str) -> None:
    """redteam.md: the item a model read through is re-rendered solid (the guard reads the flag on every
    re-plan), because a model that read through one mosaic can read through the next."""
    if through is None or plan is None:
        return
    soft = sorted(f for f, es in plan.frames.items() for e in es if e.item_id == through.item_id and e.style != "solid")
    if soft:
        raise ContractError(
            f"audit.json {where}: {through.item_id} was read through but isn't solid on frames {soft[:5]}"
        )


def _check_patches(audit: Audit, decisions: Decisions, tracks: Tracks | None, plan: Plan | None) -> None:
    """A leak's ``patched_item`` and ``through_item``, and a spot's ``covered_by``, are hidden items that hide
    the leak's (or spot's) frames and region: an audit patch's box contains the leak's box; a track item's
    planned region on that frame overlaps it. ``excluded_by`` is a kept item present on the hit's frame."""
    by_id = {item.item_id: item for item in decisions.items}
    spans = {t.track_id: (t.first, t.last) for t in tracks.tracks} if tracks is not None else {}

    def check(
        item_id: str | None, boxes: Mapping[int, tuple[int, int, int, int]], where: str, *, contain: bool
    ) -> None:
        item = by_id.get(item_id or "")
        if item is None:
            return
        if item.decision == "keep":
            raise ContractError(f"audit.json {where}: {item.item_id} is a kept item")
        hidden = _hidden_frames(item, spans, plan)
        outside = [f for f in sorted(boxes) if hidden is not None and f not in hidden]
        if outside:
            raise ContractError(f"audit.json {where}: {item.item_id} doesn't hide frames {outside[:5]}")
        for frame, box in sorted(boxes.items()):
            regions = _regions(item, frame, plan)
            if not regions:
                continue
            # An audit patch drawn for this very finding contains it; a flag or a through_item only needs the item's
            # planned region "on" the finding (any positive-area overlap, PRE-A §12 through_item, redteam.md).
            covered = (
                any(r[0] <= box[0] and r[1] <= box[1] and box[2] <= r[2] and box[3] <= r[3] for r in regions)
                if contain and item.box is not None
                else any(boxes_overlap(r, box) for r in regions)
            )
            if not covered:
                raise ContractError(
                    f"audit.json {where}: {item.item_id} doesn't cover box {list(box)} on frame {frame}"
                )

    for leak in audit.leaks:
        where = f"leak at frame {leak.frame}"
        check(leak.patched_item, {leak.frame: leak.box}, f"{where} patch", contain=leak.flag is None)
        patch = by_id.get(leak.patched_item or "")
        # redteam.md / PRE-A §12: every leak becomes a new audit-patch item; only a flagged leak may instead be
        # fixed by re-rendering the item it was read through (solid).
        if patch is not None and patch.origin != "audit_patch" and patch.item_id != leak.through_item:
            raise ContractError(
                f"audit.json {where} patch: {patch.item_id} is neither an audit patch nor the flagged through_item"
            )
        check(leak.through_item, {leak.frame: leak.box}, f"{where} through_item", contain=False)
        if not leak.unresolved:
            _check_solid(by_id.get(leak.through_item or ""), plan, where)
    for spot in audit.spots:
        where = f"spot {spot.spot_id} cover"
        check(spot.covered_by, spot.boxes, where, contain=True)  # cover_spot's patch is the union of the boxes
        cover = by_id.get(spot.covered_by or "")
        hidden = _hidden_frames(cover, spans, plan) if cover is not None else None
        missing = [f for f in range(spot.first, spot.last + 1) if hidden is not None and f not in hidden]
        if missing:
            raise ContractError(f"audit.json {where}: {spot.covered_by} doesn't hide frames {missing[:5]}")
    for name, entries in (("redteam", audit.redteam), ("redteam_open", audit.redteam_open)):
        for entry in entries:
            if not isinstance(entry, RedteamHit) or entry.excluded_by is None:
                continue
            item = by_id.get(entry.excluded_by)
            if item is None:
                continue  # an unknown id is reported by _check_links
            if item.decision != "keep":
                raise ContractError(
                    f"audit.json {name} at frame {entry.frame}: excluded_by {item.item_id}, which isn't a kept item"
                )
            if spans and entry.frame not in _present_frames(item, spans):
                raise ContractError(
                    f"audit.json {name} at frame {entry.frame}: excluded_by {item.item_id}, absent on that frame"
                )
            if tracks is not None:
                _check_exclusion(entry, item, tracks, f"audit.json {name} at frame {entry.frame}")


def _excludes(kind: LeakKind, concept: str) -> bool:
    """redteam.md "Leak decision": a finding's kind matches only its own track concept (no looser mapping)."""
    match kind:
        case "face" | "person":
            return concept == kind
        case "text" | "screen":
            return concept not in {"face", "person"}
        case "plate":
            return concept == "license plate"
        case _:
            return False  # misaligned_redaction and other are never excluded


def _check_exclusion(hit: RedteamHit, item: DecisionItem, tracks: Tracks, where: str) -> None:
    """A kept item excludes a hit only through one of its tracks on that frame whose concept matches the hit's
    kind and whose box overlaps the hit's (IoU > 0.3 needs a positive overlap; the visible region is inside
    the track's box, so the IoU itself is WP4's to compute)."""
    present = [t for t in tracks.tracks if t.track_id in item.track_ids and t.first <= hit.frame <= t.last]
    matching = [t for t in present if _excludes(hit.kind, t.concept)]
    if not matching:
        concepts = sorted({t.concept for t in present})
        raise ContractError(f"{where}: a {hit.kind} finding can't be excluded by {item.item_id} ({concepts})")
    boxed = [t.boxes[hit.frame] for t in matching if hit.frame in t.boxes]
    if boxed and not any(boxes_overlap(box, hit.box) for box in boxed):
        raise ContractError(f"{where}: excluded_by {item.item_id}, whose box there doesn't overlap the finding")


def validate_job_dir(job_dir: str | Path) -> dict[str, BaseModel]:
    """Load every contract file present in ``job_dir`` and run the cross-file checks.

    ``job.json`` is required; other files are checked only when present. Returns the loaded models
    keyed by file name, so callers validate once and reuse the result.
    """
    job_dir = Path(job_dir)
    job = load(job_dir / "job.json", Job)
    dir_name = job_dir.resolve().name
    if job.job_id != dir_name:
        raise ContractError(f"job.json: job_id {job.job_id!r} != job directory name {dir_name!r}")
    loaded: dict[str, BaseModel] = {"job.json": job}
    for name, model in JOB_FILES.items():
        if name != "job.json" and (job_dir / name).exists():
            loaded[name] = load(job_dir / name, model)
    tracks = loaded.get("tracks.json")
    tracks = tracks if isinstance(tracks, Tracks) else None
    decisions = loaded.get("decisions.json")
    decisions = decisions if isinstance(decisions, Decisions) else None
    audit = loaded.get("audit.json")
    audit = audit if isinstance(audit, Audit) else None
    files = loaded.get("files.json")
    files = files if isinstance(files, FilesIndex) else None
    transcript = loaded.get("transcript.json")
    roles = loaded.get("roles.json")
    plan = loaded.get("plan.json")
    receipt = loaded.get("receipt.json")
    if tracks is not None:
        _check_tracks(tracks, job)
    if isinstance(transcript, Transcript):
        _check_transcript(transcript, job)
    if isinstance(roles, Roles):
        _check_roles(roles, job, tracks)
    if decisions is not None:
        _check_decisions(decisions, job, tracks)
    if isinstance(plan, Plan):
        _check_plan(plan, job, decisions)
    if audit is not None:
        _check_audit(audit, job)
    if isinstance(plan, Plan) and decisions is not None:
        _check_plan_covers(plan, decisions, tracks, job)
    scene = loaded.get("scene.json")
    _check_links(
        scene if isinstance(scene, Scene) else None,
        transcript if isinstance(transcript, Transcript) else None,
        roles if isinstance(roles, Roles) else None,
        decisions,
        audit,
        tracks=tracks,
        plan=plan if isinstance(plan, Plan) else None,
    )
    if isinstance(receipt, Receipt):
        responses = loaded.get("responses.json")
        _check_receipt(
            receipt,
            job,
            decisions=decisions,
            audit=audit,
            files=files,
            responses=responses if isinstance(responses, ResponsesIndex) else None,
            cost_path=job_dir / "cost.jsonl",
        )
    return loaded
