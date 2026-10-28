"""Data contracts: one pydantic model per JSON file in a job directory (ARCHITECTURE.md §3).

Every stage reads and writes these files, so a change here is a contract change (AGENTS rule 3):
update ARCHITECTURE §3 in the same PR. Coordinates are pixels of the prepared clip; boxes are
half-open ``[x1, y1, x2, y2)`` ints; frames are 0-based prepared-clip indices. Per-file rules are
model validators; rules that need two files (box bounds, mask sizes, ID links, receipt totals) live in
:func:`validate_job_dir`.
"""

from __future__ import annotations

import bisect
import hashlib
import itertools
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast, overload

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

    @model_validator(mode="after")
    def _covers_the_frame(self) -> Rle:
        # A box-sized mask labelled frame-sized decodes silently into the top-left corner (pycocotools treats a
        # run deficit as background), leaving the item exposed: its runs must cover exactly H x W pixels.
        runs = rle_runs(self.counts)
        if any(r < 0 for r in runs) or sum(runs) != self.size[0] * self.size[1]:
            raise ValueError(f"mask runs cover {sum(runs)} pixels, not the {self.size[0]}x{self.size[1]} frame")
        return self


def rle_runs(counts: str) -> list[int]:
    """The run lengths of a COCO compressed RLE string (cocoapi ``rleFrString``)."""
    runs: list[int] = []
    p = 0
    while p < len(counts):
        x = k = 0
        more = True
        while more:
            if p >= len(counts):
                raise ValueError("mask counts end inside a run")
            c = ord(counts[p]) - 48
            if not 0 <= c < 64:
                raise ValueError("mask counts aren't COCO compressed RLE")
            if k > 12:  # a real run needs at most 4 groups; a runaway continuation is garbage (and slow)
                raise ValueError("mask counts aren't COCO compressed RLE")
            x |= (c & 0x1F) << (5 * k)
            more = bool(c & 0x20)
            p += 1
            k += 1
            if not more and c & 0x10:
                x |= -1 << (5 * k)
        if len(runs) > 2:
            x += runs[-2]
        runs.append(x)
    return runs


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
    votes: list[Role] = Field(min_length=3, max_length=3)  # role-pass.md step 7: missing votes are `unsure`
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
        if self.matches_participant is not None and (self.role != "participant" or set(self.votes) != {"participant"}):
            # role-pass.md step 7: set only for a unanimous participant, so the UI never links speech on a guess.
            raise ValueError(f"track {self.track_id}: matches_participant is only for a unanimous participant")
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
        if self.style == "pixelate" and self.kind not in ("person", "child"):
            # DESIGN §2.7 / WP3.md: text, screens, plates and documents are always solid (a fine mosaic on text
            # is legible, redteam.md case 1); pixelate is only for faces and people.
            raise ValueError(f"{self.item_id}: a {self.kind} item is always solid, never pixelate")
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
    """DESIGN §2.6 / WP3: faces 15 % + 8 px, others 8 % + 8 px; a guard may pad more, never less."""

    face: float = Field(ge=0.15, le=1)
    default: float = Field(ge=0.08, le=1)
    px: int = Field(ge=8)


class Temporal(Contract):
    extend: int = Field(ge=8)  # DESIGN §2.6: extend ±8 frames (more is allowed)
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

    @model_validator(mode="after")
    def _yunet_has_no_plates(self) -> EgoBlurSummary:
        if self.model == "yunet-face" and self.plates is not None:
            # PRE-A §12: YuNet detects faces only, so plates is null, never 0 (AGENTS rule 9: no misreport).
            raise ValueError("yunet-face detects no plates: plates is null")
        return self


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
            # redteam.md: each finding gets its own leak with detector "redteam" (an EgoBlur leak on the same face
            # isn't the red-team's record of it).
            if not any(
                leak.detector == "redteam" and leak.frame == hit.frame and boxes_overlap(leak.box, hit.box)
                for leak in self.leaks
            ):
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

    @model_validator(mode="after")
    def _detector_kinds(self) -> Audit:
        # The face detector reports faces and plates; YuNet faces only (PRE-A §12).
        allowed = {"face"} if self.egoblur.model == "yunet-face" else {"face", "plate"}
        for leak in self.leaks:
            if leak.detector == "egoblur" and leak.kind not in allowed:
                raise ValueError(f"leak at frame {leak.frame}: {self.egoblur.model} can't report a {leak.kind}")
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


@overload
def load[M: BaseModel](path: str | Path, model: type[M]) -> M: ...
@overload
def load(path: str | Path) -> BaseModel: ...
def load(path: str | Path, model: type[BaseModel] | None = None) -> BaseModel:
    """Read ``path`` and validate it as ``model`` (by default, the job file its name says, ``JOB_FILES``); raise
    :class:`ContractError` with the file name."""
    path = Path(path)
    if model is None:
        if path.name not in JOB_FILES:
            raise ContractError(f"{path.name}: not a job file; pass the model to validate it as")
        model = JOB_FILES[path.name]
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


def _check_tracks(tracks: Tracks, job: Job, files: FilesIndex | None = None) -> None:
    if files is not None:
        _check_sam_requests(tracks, files)
    for frame in tracks.crowded_frames:
        _check_frame(frame, job, "tracks.json crowded_frames")
    by_id = {t.track_id: t for t in tracks.tracks}
    for t in tracks.tracks:
        _check_frame(t.last, job, f"tracks.json {t.track_id}")
        if t.reentry_of is not None:
            # A re-entry is a new ID for an object that left the frame: the original exists and ended first.
            original = by_id.get(t.reentry_of)
            if original is None or original.last >= t.first:
                raise ContractError(
                    f"tracks.json {t.track_id}: reentry_of {t.reentry_of} must be a track that ended before it starts"
                )
        for f, box in t.boxes.items():
            _check_box(box, job, f"tracks.json {t.track_id} frame {f}")
        for f, rle in t.masks.items():
            _check_rle(rle, job, f"tracks.json {t.track_id} frame {f}")


def _check_sam_requests(tracks: Tracks, files: FilesIndex) -> None:
    """PRE-A §10.6: SAM is sent the proxy (``sam_proxy.mp4``) by its ``files.json`` id; ``prepared.mp4`` would bill
    ``job.fps / sam_fps`` times the frames and break the frame indexing."""
    proxy = {e.file_id for e in files.root if e.name == "sam_proxy.mp4" and e.file_id is not None}
    for i, request in enumerate(tracks.requests):
        if request.file_id not in proxy:
            raise ContractError(f"tracks.json requests[{i}]: {request.file_id} isn't sam_proxy.mp4 in files.json")


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


def _check_decisions(decisions: Decisions, job: Job, tracks: Tracks | None, roles: Roles | None = None) -> None:
    known = None if tracks is None else {t.track_id for t in tracks.tracks}
    child_phrase: set[str] = set() if tracks is None else {t.track_id for t in tracks.tracks if t.child_phrase}
    # escalation.md rules 1-2: any child vote, or a child ruling, makes the track a child (locked, hidden).
    child_role: set[str] = (
        set() if roles is None else {t.track_id for t in roles.tracks if t.role == "child" or "child" in t.votes}
    )
    votes = {} if roles is None else {t.track_id: t for t in roles.tracks}
    concepts = None if tracks is None else {t.track_id: t.concept for t in tracks.tracks}
    for item in decisions.items:
        where = f"decisions.json {item.item_id}"
        if known is not None:
            missing = [tid for tid in item.track_ids if tid not in known]
            if missing:
                raise ContractError(f"{where}: unknown track {missing[0]}")
        # PRE-A §12 (WP3 rule 0): an item over a child_phrase track is a child (a locked hide), whatever any vote
        # says; and a track ruled a child is never kept (WP3.md).
        phrased = [tid for tid in item.track_ids if tid in child_phrase]
        if phrased and item.kind != "child":
            raise ContractError(f"{where}: track {phrased[0]} is a child_phrase track, so the item is kind child")
        if (
            item.style == "pixelate"
            and concepts is not None
            and "face" not in {concepts.get(t) for t in item.track_ids}
        ):
            # DESIGN §2.7 / WP3.md: pixelate is the face treatment, sized from the face; a person-only item is solid.
            raise ContractError(f"{where}: a pixelated item needs a face track")
        ruled = [tid for tid in item.track_ids if tid in child_role]
        if ruled and item.kind != "child":
            raise ContractError(f"{where}: track {ruled[0]} has a child vote or ruling, so the item is kind child")
        if item.decision == "keep" and item.decided_by != "creator" and roles is not None:
            # WP3: only a unanimous participant (a person) is kept by policy or model; a screen, a never-judged
            # track or any doubt needs the creator.
            if item.kind != "person":
                raise ContractError(f"{where}: a {item.kind} item is never kept without the creator")
            doubtful = [
                tid for tid in item.track_ids
                if tid not in votes or votes[tid].role != "participant" or votes[tid].votes != ["participant"] * 3
                or votes[tid].failed_votes
                or len(set(votes[tid].frames)) < 2  # WP3: consistent on ≥ 2 keyframes
            ]  # fmt: skip
            if doubtful:
                raise ContractError(
                    f"{where}: kept by {item.decided_by}, but {doubtful[0]} isn't a unanimous participant"
                )
        _check_item(item, job, where)
    if known is not None:
        # Deny by default: every track is in an item, so nothing found is left undecided (and unhidden).
        undecided = sorted(known - {tid for item in decisions.items for tid in item.track_ids})
        if undecided:
            raise ContractError(f"decisions.json: track {undecided[0]} is in no item")


def _check_audit_reasons(audit: Audit, job: Job, *, unscanned: int, open_leaks: int) -> None:
    if audit.open_weight.status != "off" and not (job.consented and job.open_weight_attempted):
        # PRE-A §3.8 privacy gate: frames go to a third party only for a consented job, attempted once.
        raise ContractError("audit.json: an open-weight opinion ran on a job that isn't consented and attempted")
    # Precedence over_budget > audit_failed > unresolved_leaks: frames no pass ran on are never "leaks".
    if unscanned and audit.blocked_reason == "unresolved_leaks":
        raise ContractError("audit.json: unscanned frames block as audit_failed or over_budget, not unresolved_leaks")
    if audit.blocked_reason == "unresolved_leaks" and not open_leaks:
        raise ContractError("audit.json: blocked_reason unresolved_leaks needs an unresolved leak")


def _check_audit(audit: Audit, job: Job) -> None:
    # EgoBlur scans every output frame; a frame no pass ran on counts in `unresolved` (PRE-A §12, vector L10).
    if audit.egoblur.faces is None and audit.frames_scanned:
        # PRE-A §12: a detector that never ran reports `faces: null` and frames_scanned 0 (its frames unresolved).
        raise ContractError("audit.json: egoblur.faces is null (the detector never ran), so frames_scanned is 0")
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
    _check_audit_reasons(audit, job, unscanned=unscanned, open_leaks=open_leaks)
    if audit.unresolved == 0 and audit.passes == 0:
        raise ContractError("audit.json: a publishable audit ran no red-team pass")
    # redteam.md: one red-team entry per frame sent, at least 1 per second (sample_step frames), and frames are
    # never silently skipped. Whatever the sampling phase, that is at least frames // sample_step distinct frames.
    if audit.sample_step != job.fps:
        # PRE-A §12: sample_step = round(job.fps), the red-team's 1 fps step in output frames (fps is an int).
        raise ContractError(f"audit.json: sample_step {audit.sample_step} != the job's {job.fps} fps")
    # 1 per second, whatever the sampling phase: each whole second of the clip has a red-team entry.
    seconds = {entry.frame // job.fps for entry in audit.redteam}
    unsampled = [k for k in range(max(1, job.frames // job.fps)) if k not in seconds]
    if audit.unresolved == 0 and unsampled:
        raise ContractError(
            f"audit.json: a publishable audit has no red-team entry in seconds {unsampled[:5]} (1 per second)"
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


def _check_plan_styles(plan: Plan, decisions: Decisions, audit: Audit | None) -> None:
    """Each plan entry renders its decision's style (the guard doesn't restyle), except that an item a model read
    through (a flagged leak's ``through_item``, once re-planned) renders solid on every frame (redteam.md: a model
    that read through one mosaic can read through the next). An audit patch's entries are
    solid and marked ``source: "audit_patch"`` (PRE-A §12)."""
    if audit is not None:
        _check_read_through(audit, decisions, plan)
    by_id = {item.item_id: item for item in decisions.items}
    # A leak left unresolved after the last pass was found after the last re-plan: its item may still be soft.
    upgraded: set[str] = (
        {leak.through_item for leak in audit.leaks if leak.through_item is not None and not leak.unresolved}
        if audit is not None
        else set()
    )
    for frame, entries in sorted(plan.frames.items()):
        for entry in entries:
            item = by_id.get(entry.item_id)
            if item is None:
                continue  # an unknown id is reported by _check_plan
            want = "solid" if item.item_id in upgraded else item.style
            if entry.style != want:
                raise ContractError(
                    f"plan.json frame {frame}: {item.item_id} renders {entry.style}, but its decision says {want}"
                )
            if (entry.source == "audit_patch") != (item.origin == "audit_patch"):
                raise ContractError(f"plan.json frame {frame}: {item.item_id} source {entry.source} != its origin")


SAM_OBJECT_CAP = 16  # PRE-A §1.6: SAM returns at most 16 objects per concept per frame


def _check_crowd_fills(plan: Plan, tracks: Tracks, hidden: set[str]) -> None:
    for frame in sorted(set(tracks.crowded_frames)):
        # The cap is SAM's 16 objects per concept: where a concept hit it, the fill covers all its objects.
        present: dict[str, list[Track]] = {}
        for t in tracks.tracks:
            if t.first <= frame <= t.last:
                present.setdefault(t.concept, []).append(t)
        for concept, objects in present.items():
            if len(objects) < SAM_OBJECT_CAP:
                continue
            # Only what's hidden must be under a fill: a kept participant in the crowd stays visible.
            boxes = [b for t in objects if t.track_id in hidden and (b := _box_near(t, frame)) is not None]
            # Fills may be split into tiles (DESIGN §2.6): each object lies inside some fill on this frame.
            frame_fills = [fill.box for fill in plan.crowd_fills if frame in fill.frames]
            outside = [b for b in boxes if not any(_contains(fill, b) for fill in frame_fills)]
            if outside:
                raise ContractError(
                    f"plan.json frame {frame}: no crowd fill covers {len(outside)} of the {len(boxes)}"
                    f" {concept} objects"
                )


def _check_plan_geometry(plan: Plan, decisions: Decisions, tracks: Tracks, job: Job) -> None:
    """What the plan draws really hides each track (the guard pads outward and clamps, never shrinks): a track's
    box on a planned frame lies inside one of its item's box entries or a crowd fill (a mask entry must overlap
    it); a pixelate grid keeps the face ≤ 6 blocks across (DESIGN §2.7); every crowded frame has a crowd fill;
    and the back-fill is SAM's 15-frame hotstart in prepared frames (PRE-A §5b, T10)."""
    filled = {f for fill in plan.crowd_fills for f in fill.frames}
    unfilled = sorted(set(tracks.crowded_frames) - filled)
    if unfilled:
        raise ContractError(f"plan.json: crowded frames {unfilled[:5]} have no crowd fill")
    hidden = {tid for i in decisions.items if i.decision in ("hide", "needs_you") for tid in i.track_ids}
    _check_crowd_fills(plan, tracks, hidden)
    want = math.ceil(15 * job.fps / min(tracks.sam_fps, job.fps))
    if plan.temporal.backfill != want:
        raise ContractError(
            f"plan.json: temporal.backfill {plan.temporal.backfill} != ceil(15 x fps / sam_fps) = {want}"
        )
    by_track = {t.track_id: t for t in tracks.tracks}
    for item in decisions.items:
        if item.decision not in ("hide", "needs_you"):
            continue
        for track in (by_track[tid] for tid in item.track_ids if tid in by_track):
            for frame, box in sorted(track.boxes.items()):
                entries = [e for e in plan.frames.get(frame, []) if e.item_id == item.item_id]
                if not entries:
                    continue  # coverage is _check_plan_covers'
                fills = [fill.box for fill in plan.crowd_fills if frame in fill.frames]
                # The guard pads every box by at least `padding.px` (clamped to the frame) and a mask is SAM's own
                # outline of the object, so it spans the track box.
                if not _held(entries, fills, box, _grow(box, plan.padding.px, job)):
                    raise ContractError(
                        f"plan.json frame {frame}: {item.item_id} doesn't cover {track.track_id}'s box {list(box)}"
                    )
                if track.concept != "face":
                    continue  # DESIGN §2.7's ≤ 6 blocks is about the face
                for e in entries:
                    if e.grid is not None and _contains(e.box, box) and e.grid[2] * 6 < box[2] - box[0]:
                        raise ContractError(
                            f"plan.json frame {frame}: {item.item_id}'s {e.grid[2]} px grid leaves"
                            f" {track.track_id} more than 6 blocks across"
                        )
            _check_between_anchors(plan, item, track)
        # A shifting grid leaks detail across frames (DESIGN §2.7): one fixed grid per track of the item.
        grids = {e.grid for entries in plan.frames.values() for e in entries if e.item_id == item.item_id and e.grid}
        if len(grids) > max(1, len(item.track_ids)):
            raise ContractError(f"plan.json: {item.item_id}'s pixelate grid moves between frames ({len(grids)} grids)")


def _check_between_anchors(plan: Plan, item: DecisionItem, track: Track) -> None:
    """A track with boxes only on some frames (SAM anchors; gaps the guard holds through): on the frames in
    between, the item's entry must at least overlap the box interpolated between the neighbouring anchors. The
    guard's held or grown box may differ, so containment would refuse valid output; a box moved away won't pass."""
    keys = sorted(track.boxes)
    for before, after in itertools.pairwise(keys):
        a, b = track.boxes[before], track.boxes[after]
        for frame in range(before + 1, after):
            entries = [e for e in plan.frames.get(frame, []) if e.item_id == item.item_id]
            if not entries:
                continue  # coverage (and a crowd fill instead) is _check_plan_covers'
            w = (frame - before) / (after - before)
            box = cast(Box, tuple(round(a[i] + (b[i] - a[i]) * w) for i in range(4)))
            fills = [fill.box for fill in plan.crowd_fills if frame in fill.frames]
            # The guard may hold an anchor's box (growing it) through a gap, so either anchor also counts.
            near = (box, a, b)
            if not any(_near(e, n) for e in entries for n in near) and not any(_contains(f, box) for f in fills):
                raise ContractError(
                    f"plan.json frame {frame}: {item.item_id} is nowhere near {track.track_id} (about {list(box)})"
                )


def _near(entry: PlanEntry, box: Box) -> bool:
    """A box entry overlaps ``box``; a mask entry has foreground inside it (an empty mask hides nothing)."""
    if entry.shape == "mask":
        return entry.mask is not None and _mask_spans(entry.mask, box, share=0)
    return boxes_overlap(entry.box, box)


def _held(entries: list[PlanEntry], fills: list[Box], box: Box, padded: Box) -> bool:
    """A box entry contains ``padded``, a mask entry's foreground spans ``box``, or a crowd fill contains ``box``."""
    return any(
        _contains(e.box, padded) if e.shape == "box" else e.mask is not None and _mask_spans(e.mask, box)
        for e in entries
    ) or any(_contains(fill, box) for fill in fills)


def _grow(box: Box, px: int, job: Job) -> Box:
    return (max(0, box[0] - px), max(0, box[1] - px), min(job.width, box[2] + px), min(job.height, box[3] + px))


def _mask_spans(mask: Rle, box: Box, share: float = 0.8) -> bool:
    """Whether a COCO RLE mask (column-major, runs alternating background/foreground) has foreground inside
    ``box`` spanning at least ``share`` of its width and height: one stray pixel hides nothing."""
    height = mask.size[0]
    x1, y1, x2, y2 = box
    xs: list[int] = []
    ys: list[int] = []
    start = 0
    for i, run in enumerate(rle_runs(mask.counts)):
        if i % 2 and run:
            for col in range(max(start // height, x1), min((start + run - 1) // height, x2 - 1) + 1):
                lo = max(start, col * height + y1)
                hi = min(start + run, col * height + y2)
                if lo < hi:
                    xs.append(col)
                    ys += [lo - col * height, hi - 1 - col * height]
        start += run
    if not xs:
        return False
    return max(xs) - min(xs) + 1 >= share * (x2 - x1) and max(ys) - min(ys) + 1 >= share * (y2 - y1)


def _contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _check_plan_covers(plan: Plan, decisions: Decisions, tracks: Tracks | None, job: Job) -> None:
    """Every hidden item (``hide``, or ``needs_you``, which renders hidden) is planned on every frame of each of
    its tracks, widened by the guard's temporal padding (``first − backfill`` … ``last + extend``, DESIGN §2.6,
    clamped to the clip; a merged item's gap between tracks needs nothing beyond that), or on an audit patch's
    own ``first..last``. On a frame with no entry, crowd fills must contain every one of the item's track boxes."""
    by_track = {t.track_id: t for t in tracks.tracks} if tracks is not None else {}
    planned = {(frame, e.item_id) for frame, entries in plan.frames.items() for e in entries}
    fills: dict[int, list[Box]] = {}
    for fill in plan.crowd_fills:
        for f in fill.frames:
            fills.setdefault(f, []).append(fill.box)
    temporal = plan.temporal
    for item in decisions.items:
        if item.decision not in ("hide", "needs_you"):
            continue
        needed: dict[int, list[Track]] = {}
        if item.first is not None and item.last is not None:
            for f in range(item.first, min(job.frames, item.last + 1)):
                needed.setdefault(f, [])
        for track in (by_track[tid] for tid in item.track_ids if tid in by_track):
            for f in range(max(0, track.first - temporal.backfill), min(job.frames, track.last + temporal.extend + 1)):
                needed.setdefault(f, []).append(track)

        def filled(f: int, owners: list[Track]) -> bool:
            if not owners or f not in fills:
                return False  # an audit patch is always planned itself
            boxes = [_box_near(t, f) for t in owners]
            return all(b is not None and any(_contains(fill, b) for fill in fills[f]) for b in boxes)

        missing = [
            f for f, owners in sorted(needed.items()) if (f, item.item_id) not in planned and not filled(f, owners)
        ]
        if missing:
            raise ContractError(f"plan.json: hidden item {item.item_id} has no entry on frames {missing[:10]}")
        _check_held_boxes(plan, item, by_track, job)


def _check_held_boxes(plan: Plan, item: DecisionItem, by_track: Mapping[str, Track], job: Job) -> None:
    temporal = plan.temporal
    # Where the guard holds a box the tracks don't carry (back-fill and extend frames, which hold the edge box;
    # an audit patch's static box), the entry must still cover it: these frames are where leaks happen.
    held: dict[int, list[Box]] = {}
    if item.box is not None and item.first is not None and item.last is not None:
        for f in range(item.first, item.last + 1):
            held.setdefault(f, []).append(item.box)
    for track in (by_track[tid] for tid in item.track_ids if tid in by_track):
        edges = range(max(0, track.first - temporal.backfill), min(job.frames, track.last + temporal.extend + 1))
        for f in (f for f in edges if not track.first <= f <= track.last):
            box = _box_near(track, f)
            if box is not None:
                held.setdefault(f, []).append(box)
    for f, boxes in sorted(held.items()):
        if f >= job.frames:
            continue
        entries = [e for e in plan.frames.get(f, []) if e.item_id == item.item_id]
        fills = [fl.box for fl in plan.crowd_fills if f in fl.frames]
        for box in boxes:
            if not _held(entries, fills, box, _grow(box, plan.padding.px, job) if item.box is None else box):
                raise ContractError(f"plan.json frame {f}: {item.item_id} doesn't cover its held box {list(box)}")


def _box_near(track: Track, frame: int) -> Box | None:
    """The track's box on ``frame``, or at its nearest keyframe (the guard holds the edge box when padding)."""
    if frame in track.boxes:
        return track.boxes[frame]  # the common case for a densified track: no search
    if not track.boxes:
        return None
    keys = sorted(track.boxes)
    i = bisect.bisect_left(keys, frame)
    return track.boxes[min(keys[max(0, i - 1) : i + 1], key=lambda k: (abs(k - frame), k))]


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


def _check_patches(audit: Audit, decisions: Decisions, tracks: Tracks | None, plan: Plan | None) -> None:
    """A leak's ``patched_item`` and ``through_item``, and a spot's ``covered_by``, are hidden items that hide
    the leak's (or spot's) frames and region: an audit patch's box contains the leak's box; a track item's
    planned region on that frame overlaps it. ``excluded_by`` is a kept item present on the hit's frame."""
    by_id = {item.item_id: item for item in decisions.items}
    spans = {t.track_id: (t.first, t.last) for t in tracks.tracks} if tracks is not None else {}

    cache: dict[str, set[int] | None] = {}

    def hidden_of(item: DecisionItem) -> set[int] | None:
        if item.item_id not in cache:
            cache[item.item_id] = _hidden_frames(item, spans, plan)
        return cache[item.item_id]

    def check(
        item_id: str | None, boxes: Mapping[int, tuple[int, int, int, int]], where: str, *, contain: bool
    ) -> None:
        item = by_id.get(item_id or "")
        if item is None:
            return
        if item.decision == "keep":
            raise ContractError(f"audit.json {where}: {item.item_id} is a kept item")
        hidden = hidden_of(item)
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
    for spot in audit.spots:
        where = f"spot {spot.spot_id} cover"
        check(spot.covered_by, spot.boxes, where, contain=True)  # cover_spot's patch is the union of the boxes
        cover = by_id.get(spot.covered_by or "")
        hidden = hidden_of(cover) if cover is not None else None
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


def _check_read_through(audit: Audit, decisions: Decisions, plan: Plan) -> None:
    """redteam.md: a text finding on a redacted region (any overlap with a hidden item's planned region on that
    frame) is a leak *and* a `redaction_too_weak` flag, so the item is re-rendered solid. A writer that records it
    unflagged would leave the mosaic that was read through."""
    hidden = {i.item_id for i in decisions.items if i.decision in ("hide", "needs_you")}
    for hit in audit.redteam:
        if (
            not isinstance(hit, RedteamHit)
            or hit.excluded_by is not None
            or hit.kind not in ("text", "screen", "plate")
        ):
            continue
        regions = [e.box for e in plan.frames.get(hit.frame, []) if e.item_id in hidden]
        if not any(boxes_overlap(r, hit.box) for r in regions):
            continue
        if not any(
            leak.detector == "redteam" and leak.frame == hit.frame and boxes_overlap(leak.box, hit.box) and leak.flag
            for leak in audit.leaks
        ):
            raise ContractError(
                f"audit.json red-team {hit.kind} hit at frame {hit.frame} reads through a hidden region, so its leak"
                " carries flag redaction_too_weak"
            )


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
        _check_tracks(tracks, job, files)
    if isinstance(transcript, Transcript):
        _check_transcript(transcript, job)
    if isinstance(roles, Roles):
        _check_roles(roles, job, tracks)
    if decisions is not None:
        _check_decisions(decisions, job, tracks, roles if isinstance(roles, Roles) else None)
    if isinstance(plan, Plan):
        _check_plan(plan, job, decisions)
    if audit is not None:
        _check_audit(audit, job)
    if isinstance(plan, Plan) and decisions is not None:
        _check_plan_covers(plan, decisions, tracks, job)
        _check_plan_styles(plan, decisions, audit)
        if tracks is not None:
            _check_plan_geometry(plan, decisions, tracks, job)
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
    _check_auto_keeps(
        decisions,
        job,
        scene=scene if isinstance(scene, Scene) else None,
        roles=roles if isinstance(roles, Roles) else None,
        transcript=transcript if isinstance(transcript, Transcript) else None,
        tracks=tracks,
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
        _check_receipt_models(
            receipt,
            audit=audit,
            scene=scene if isinstance(scene, Scene) else None,
            roles=roles if isinstance(roles, Roles) else None,
            transcript=transcript if isinstance(transcript, Transcript) else None,
        )
    return loaded


def _normal_words(text: str) -> str:
    return " ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).split())


def _speech_evidence(k: int | None, scene: Scene, transcript: Transcript) -> bool:
    """PRE-A §12: participant ``k`` has a turn by its speaker, or an introduction quote (≥ 2 words) found in the
    introducing turn's text, both normalised."""
    if k is None or not 0 <= k < len(scene.participants):
        return False
    who = scene.participants[k]
    if who.speaker is not None and any(t.speaker == who.speaker for t in transcript.turns):
        return True
    i, quote = who.introduced_in_turn, _normal_words(who.introduction_quote or "")
    return (
        i is not None
        and i < len(transcript.turns)
        and len(quote.split()) >= 2
        and (quote in _normal_words(transcript.turns[i].text))
    )


def _check_auto_keeps(
    decisions: Decisions | None,
    job: Job,
    *,
    scene: Scene | None,
    roles: Roles | None,
    transcript: Transcript | None,
    tracks: Tracks | None,
) -> None:
    """PRE-A §12's holds: a person is kept without the creator only when the scene pass ran (`no_scene`), the clip's
    audio has a usable transcript (`no_speech`), every scene child is matched to a child item (`unmatched_child`)
    and, with a transcript, each kept track's participant has speech or introduction evidence (`no_speech_link`).
    A hold explains a `needs_you`, so a keep never carries one."""
    if decisions is None:
        return
    auto = [i for i in decisions.items if i.decision == "keep" and i.decided_by != "creator" and i.kind == "person"]
    if not auto:
        return
    held = [i for i in auto if i.hold is not None]
    if held:
        raise ContractError(f"decisions.json {held[0].item_id}: a keep carries hold {held[0].hold}")
    where = f"decisions.json {auto[0].item_id}: kept by {auto[0].decided_by}, but"
    if scene is not None and scene.status != "ok":
        raise ContractError(f"{where} the scene pass didn't run (no_scene)")
    usable = transcript is not None and transcript.status == "ok" and not transcript.degraded
    if job.audio and transcript is not None and not usable:
        raise ContractError(f"{where} the clip's audio has no usable transcript (no_speech)")
    if scene is not None and roles is not None:
        phrase: set[str] = set() if tracks is None else {t.track_id for t in tracks.tracks if t.child_phrase}
        reentry: set[str] = set() if tracks is None else {t.track_id for t in tracks.tracks if t.reentry_of}
        child_tracks = {
            t.track_id for t in roles.tracks
            if t.track_id not in phrase and ("child" in t.votes or (t.escalated and t.role == "child"))
        }  # fmt: skip
        children = [
            i for i in decisions.items
            if set(i.track_ids) & child_tracks and not set(i.track_ids) <= reentry
        ]  # fmt: skip
        if len(scene.children) > len(children):
            raise ContractError(f"{where} the scene has an unmatched child (unmatched_child)")
    if job.audio and usable and scene is not None and roles is not None and transcript is not None:
        votes = {t.track_id: t for t in roles.tracks}
        for item in auto:
            for tid in item.track_ids:
                if tid in votes and not _speech_evidence(votes[tid].matches_participant, scene, transcript):
                    raise ContractError(
                        f"decisions.json {item.item_id}: kept by {item.decided_by}, but {tid} has no speech or"
                        " introduction evidence (no_speech_link)"
                    )


def _check_receipt_models(
    receipt: Receipt, *, audit: Audit | None, scene: Scene | None, roles: Roles | None, transcript: Transcript | None
) -> None:
    """The receipt names the models that actually ran (AGENTS rule 9; PRE-A: a YuNet fallback is never sealed as
    EgoBlur): each stage's model in ``models`` and the audit's ``auditor`` match the job file that recorded it."""
    ran: dict[str, str | None] = {
        "scene": scene.model if scene is not None else None,
        "roles": roles.model if roles is not None else None,
        "auditor": audit.egoblur.model if audit is not None else None,
    }
    if transcript is not None and transcript.source is not None:
        ran["speech_fallback" if transcript.source_kind == "fallback" else "asr"] = transcript.source
    for stage, model in ran.items():
        if model is not None and receipt.models.get(stage) != model:
            raise ContractError(f"receipt.json models.{stage} {receipt.models.get(stage)!r} != the job's {model!r}")
    if audit is not None and receipt.audit.auditor != audit.egoblur.model:
        raise ContractError(
            f"receipt.json audit.auditor {receipt.audit.auditor!r} != audit.json {audit.egoblur.model!r}"
        )
