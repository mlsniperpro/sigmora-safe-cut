"""Ground-truth labels (EVAL.md §1): one JSON file per clip, its entities, and their boxes in MOT format.

An entity's ``boxes`` is a path (relative to the label file) to a MOT text file, ``frame,id,x,y,w,h,1,-1,-1,-1``
with **1-based** frames (the MOT convention CVAT exports), keyed at 2 fps or denser and linearly interpolated
between keys, exactly as EVAL §1 describes. A clip's boxes may also be inline, ``{"<0-based frame>": [x1, y1, x2,
y2]}``, for synthetic clips. :func:`load_labels` validates everything it reads.
"""

from __future__ import annotations

import csv
import itertools
import json
from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

Category = Literal["participant", "bystander", "child", "plate", "screen", "document", "address", "photo", "other"]
Split = Literal["dev", "test", "hero", "public", "synthetic"]
Difficulty = Literal["small", "occluded", "reentry", "motion_blur", "crowd"]
Box = tuple[float, float, float, float]


class LabelError(ValueError):
    """A label file, or one of its MOT files, is malformed or inconsistent with its clip."""


class Span(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first: Annotated[int, Field(ge=0)]
    last: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _order(self) -> Span:
        if self.last < self.first:
            raise ValueError(f"frames.last {self.last} is before frames.first {self.first}")
        return self


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    category: Category
    should_hide: bool
    reason: str = ""
    difficulty: list[Difficulty] = Field(default_factory=list[Difficulty])
    frames: Span
    boxes: str | dict[str, tuple[float, float, float, float]]
    _dense: dict[int, Box] = PrivateAttr(default_factory=dict[int, Box])

    @property
    def dense(self) -> dict[int, Box]:
        """Half-open ``[x1, y1, x2, y2)`` per 0-based frame where the entity is visible."""
        return self._dense


class ClipLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip: str = Field(min_length=1)
    fps: Annotated[float, Field(gt=0, le=120)]
    frames: Annotated[int, Field(gt=0)]
    width: Annotated[int, Field(gt=0, le=8192)]
    height: Annotated[int, Field(gt=0, le=8192)]
    split: Split
    entities: list[Entity]
    notes: str = ""
    #: Who labelled it: two independent labellers for reported splits (EVAL §1); synthetic truth is generated.
    labellers: Annotated[int, Field(ge=1, le=2)] = 1

    @model_validator(mode="after")
    def _unique(self) -> ClipLabels:
        ids = [e.id for e in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("entity ids must be unique")
        return self

    @cached_property
    def by_id(self) -> dict[str, Entity]:
        return {e.id: e for e in self.entities}


def read_mot(path: Path) -> dict[int, Box]:
    """MOT rows → ``{0-based frame: (x1, y1, x2, y2)}``; one track per file, so the id column must be constant."""
    rows: dict[int, Box] = {}
    ids: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LabelError(f"{path.name}: unreadable ({type(exc).__name__})") from exc
    for number, row in enumerate(csv.reader(text.splitlines()), 1):
        if not row or not "".join(row).strip():
            continue
        if len(row) < 6:
            raise LabelError(f"{path.name}:{number}: a MOT row has at least 6 columns")
        try:
            frame = int(row[0])
            x, y, w, h = (float(v) for v in row[2:6])
        except ValueError as exc:
            raise LabelError(f"{path.name}:{number}: not a number") from exc
        if frame < 1:
            raise LabelError(f"{path.name}:{number}: MOT frames are 1-based")
        if w <= 0 or h <= 0:
            raise LabelError(f"{path.name}:{number}: width and height must be positive")
        if frame - 1 in rows:
            raise LabelError(f"{path.name}:{number}: frame {frame} appears twice")
        ids.add(row[1].strip())
        rows[frame - 1] = (x, y, x + w, y + h)
    if len(ids) > 1:
        raise LabelError(f"{path.name}: one entity per MOT file, found ids {sorted(ids)}")
    return rows


def interpolate(keys: dict[int, Box], first: int, last: int) -> dict[int, Box]:
    """Linear interpolation between keyed frames, inside ``first..last`` only (no extrapolation past a key)."""
    known = sorted(f for f in keys if first <= f <= last)
    dense: dict[int, Box] = {}
    for a, b in itertools.pairwise(known):
        ba, bb = keys[a], keys[b]
        for f in range(a, b):
            t = (f - a) / (b - a)
            dense[f] = (
                ba[0] + t * (bb[0] - ba[0]),
                ba[1] + t * (bb[1] - ba[1]),
                ba[2] + t * (bb[2] - ba[2]),
                ba[3] + t * (bb[3] - ba[3]),
            )
    if known:
        dense[known[-1]] = keys[known[-1]]
    return dense


def load_labels(path: Path) -> ClipLabels:
    """Load and validate one clip's labels, resolving every entity's boxes (dense, 0-based)."""
    try:
        labels = ClipLabels.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise LabelError(f"{path.name}: {exc}") from exc
    for entity in labels.entities:
        if isinstance(entity.boxes, str):
            mot = (path.parent / entity.boxes).resolve()
            if path.parent.resolve() not in mot.parents:
                raise LabelError(f"{path.name}: entity {entity.id}'s boxes must sit beside the label file")
            keys = read_mot(mot)
        else:
            try:
                keys = {int(f): box for f, box in entity.boxes.items()}
            except ValueError as exc:
                raise LabelError(f"{path.name}: entity {entity.id} has a non-integer frame key") from exc
        if entity.frames.last >= labels.frames:
            raise LabelError(f"{path.name}: entity {entity.id} ends after the clip's last frame")
        dense = interpolate(keys, entity.frames.first, entity.frames.last)
        if not dense:
            raise LabelError(f"{path.name}: entity {entity.id} has no box inside frames {entity.frames}")
        for frame, (x1, y1, x2, y2) in dense.items():
            if x2 <= x1 or y2 <= y1 or x1 < -1 or y1 < -1 or x2 > labels.width + 1 or y2 > labels.height + 1:
                raise LabelError(f"{path.name}: entity {entity.id} frame {frame}: box outside the frame")
        entity._dense = dense  # pyright: ignore[reportPrivateUsage] -- the loader fills the model's cache
    return labels


def dump_labels(labels: ClipLabels, path: Path) -> None:
    path.write_text(json.dumps(labels.model_dump(mode="json"), indent=1) + "\n", encoding="utf-8")
