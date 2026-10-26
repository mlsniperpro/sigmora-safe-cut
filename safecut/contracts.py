"""Data contracts: one pydantic model per JSON file in a job directory (ARCHITECTURE.md §3).

Every stage reads and writes these files, so a change here is a contract change (AGENTS rule 3):
update ARCHITECTURE §3 in the same PR. Coordinates are pixels of the prepared clip; boxes are
half-open ``[x1, y1, x2, y2)`` ints; frames are 0-based prepared-clip indices. Per-file rules are
model validators; rules that need two files (box bounds, mask sizes) live in :func:`validate_job_dir`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
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

Frame = NonNegativeInt
Role = Literal["participant", "bystander", "child", "unsure"]
StageStatus = Literal["ok", "failed", "skipped"]
SPEAKER_PATTERN = r"^[SU][1-9][0-9]*$"
TRACK_ID_PATTERN = r"^[^:]+:[0-9]+$"
FILE_ID_PATTERN = r"^file[-_][A-Za-z0-9_-]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must carry a timezone (ISO 8601 UTC, '…Z')")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_utc_datetime)]


class Contract(BaseModel):
    """Base for every contract model: unknown keys are an error, so typos never pass silently."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    source: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    prepared: str = Field(min_length=1)
    fps: int = Field(ge=1, le=30)
    width: PositiveInt
    height: PositiveInt
    frames: PositiveInt
    times: list[float]
    audio: bool
    created_at: UtcDatetime
    #: Gates the open-weight second opinion (PRE-A §3.8): true only for owner/recording codes (WP5) or the
    #: hero/dev eval splits; missing means false (fail closed).
    consented: bool = False

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
    keyframes: list[str] = Field(default_factory=list[str])

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
        if self.flag is not None and self.through_item is None:
            raise ValueError("a flagged leak names the item it reads through (through_item)")
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


class Spot(Contract):
    spot_id: str = Field(pattern=r"^s[1-9][0-9]*$")
    first: Frame
    last: Frame
    boxes: dict[Frame, Box] = Field(min_length=1)
    covered_by: str | None = None


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
    thumbnail: str | None = None


class ReceiptAudit(Contract):
    auditor: str
    frames_scanned: NonNegativeInt
    leaks_found: NonNegativeInt
    leaks_patched: NonNegativeInt
    unresolved: NonNegativeInt
    passes: NonNegativeInt
    blocked_reason: BlockedReason | None


class DataHandling(Contract):
    mode: Literal["standard"]
    store: bool
    store_by_model: dict[str, bool]
    no_store_param: list[str]
    files_deleted: bool
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
        """``files_deleted: true`` needs every upload deleted and no orphan left (PRE-A §10.4)."""
        return all(e.deleted_at is not None and not e.orphan for e in self.root)

    def live(self, name: str) -> FileEntry | None:
        """The newest undeleted entry with a file ID for ``name``."""
        matches = [e for e in self.root if e.name == name and e.file_id and e.deleted_at is None]
        return max(matches, key=lambda e: e.created_at) if matches else None


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


def _check_plan(plan: Plan, job: Job) -> None:
    for frame, entries in plan.frames.items():
        _check_frame(frame, job, "plan.json frames")
        for e in entries:
            _check_box(e.box, job, f"plan.json frame {frame} {e.item_id}")
            if e.mask is not None:
                _check_rle(e.mask, job, f"plan.json frame {frame} {e.item_id}")
    for fill in plan.crowd_fills:
        _check_box(fill.box, job, "plan.json crowd_fills")
        for frame in fill.frames:
            _check_frame(frame, job, "plan.json crowd_fills")


def _check_decisions(decisions: Decisions, tracks: Tracks) -> None:
    known = {t.track_id for t in tracks.tracks}
    for item in decisions.items:
        missing = [tid for tid in item.track_ids if tid not in known]
        if missing:
            raise ContractError(f"decisions.json {item.item_id}: unknown track {missing[0]}")


def _check_audit(audit: Audit, job: Job) -> None:
    for leak in audit.leaks:
        _check_frame(leak.frame, job, "audit.json leaks")
        _check_box(leak.box, job, f"audit.json leak at frame {leak.frame}")


def validate_job_dir(job_dir: str | Path) -> dict[str, BaseModel]:
    """Load every contract file present in ``job_dir`` and run the cross-file checks.

    ``job.json`` is required; other files are checked only when present. Returns the loaded models
    keyed by file name, so callers validate once and reuse the result.
    """
    job_dir = Path(job_dir)
    job = load(job_dir / "job.json", Job)
    loaded: dict[str, BaseModel] = {"job.json": job}
    for name, model in JOB_FILES.items():
        if name != "job.json" and (job_dir / name).exists():
            loaded[name] = load(job_dir / name, model)
    tracks = loaded.get("tracks.json")
    if isinstance(tracks, Tracks):
        _check_tracks(tracks, job)
    transcript = loaded.get("transcript.json")
    if isinstance(transcript, Transcript):
        _check_transcript(transcript, job)
    plan = loaded.get("plan.json")
    if isinstance(plan, Plan):
        _check_plan(plan, job)
    decisions = loaded.get("decisions.json")
    if isinstance(decisions, Decisions) and isinstance(tracks, Tracks):
        _check_decisions(decisions, tracks)
    audit = loaded.get("audit.json")
    if isinstance(audit, Audit):
        _check_audit(audit, job)
    return loaded
