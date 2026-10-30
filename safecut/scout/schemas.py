"""Structured-output schemas (``text.format`` json_schema, ``strict: true``) and the pydantic models that check
every answer again (``docs/prompts/README.md`` rule 2): strict decoding guarantees the shape, not the meaning.

Strict mode needs ``additionalProperties: false`` and every property in ``required``, so optional values are
nullable; no ``maxItems``/``minItems`` (their strict support is unverified, a 400 would cost a call): the
models enforce those instead.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROLE_ENUM = ["participant", "bystander", "child", "unsure"]
NULLABLE_STRING: dict[str, Any] = {"type": ["string", "null"]}
FRAMES: dict[str, Any] = {"type": "array", "items": {"type": "integer"}}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


SCENE = _object(
    {
        "summary": {"type": "string"},
        "participants": {
            "type": "array",
            "items": _object(
                {
                    "description": {"type": "string"},
                    "evidence": {"type": "string"},
                    "speaker": NULLABLE_STRING,
                    "introduced_in_turn": {"type": ["integer", "null"]},
                    "introduction_quote": NULLABLE_STRING,
                    "is_creator": {"type": "boolean"},
                }
            ),
        },
        "children": {"type": "array", "items": _object({"description": {"type": "string"}})},
        "others_present": {"type": "string"},
        "candidate_objects": {
            "type": "array",
            "items": _object(
                {
                    "what": {"type": "string"},
                    "approx_time": {"type": "string", "enum": ["beginning", "middle", "end", "throughout", "unknown"]},
                }
            ),
        },
    }
)

MISSED_ITEM = _object(
    {
        "what": {"type": "string"},
        "sam_phrase": {"type": "string"},
        "frame": {"type": "integer"},
        "point": _object({"x": {"type": "integer"}, "y": {"type": "integer"}}),
        "box": {"type": ["array", "null"], "items": {"type": "integer"}},
        "recurs": {"type": "boolean"},
    }
)

ROLE_PASS = _object(
    {
        "tracks": {
            "type": "array",
            "items": _object(
                {
                    "track_id": {"type": "string"},
                    "role": {"type": "string", "enum": ROLE_ENUM},
                    "evidence": {"type": "string"},
                    "frames": FRAMES,
                    "matches_participant": {
                        "type": ["integer", "null"],
                        "description": "the bracketed participant number shown above, or null",
                    },
                }
            ),
        },
        "objects": {
            "type": "array",
            "items": _object(
                {
                    "track_id": {"type": "string"},
                    "sensitive": {"type": "boolean"},
                    "content": {"type": "string"},
                    "frames": FRAMES,
                }
            ),
        },
        "missed": {"type": "array", "items": MISSED_ITEM},
    }
)

ESCALATION = _object(
    {
        "rulings": {
            "type": "array",
            "items": _object(
                {
                    "track_id": {"type": "string"},
                    "role": {"type": "string", "enum": ROLE_ENUM},
                    "evidence": {"type": "string"},
                    "frames": FRAMES,
                    "why_others_wrong": {"type": "string"},
                }
            ),
        }
    }
)

SPEECH = _object(
    {
        "has_speech": {"type": "boolean"},
        "turns": {
            "type": "array",
            "items": _object(
                {
                    "speaker": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                    "self_intro": NULLABLE_STRING,
                    "addresses": NULLABLE_STRING,
                }
            ),
        },
    }
)


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


Role = Literal["participant", "bystander", "child", "unsure"]


class SceneParticipant(_Out):
    description: str
    evidence: str
    speaker: str | None
    introduced_in_turn: int | None
    introduction_quote: str | None
    is_creator: bool


class SceneChildOut(_Out):
    description: str


class SceneObject(_Out):
    what: str
    approx_time: Literal["beginning", "middle", "end", "throughout", "unknown"]


class SceneOut(_Out):
    summary: str
    participants: list[SceneParticipant]
    children: list[SceneChildOut]
    others_present: str
    candidate_objects: list[SceneObject]


class GridPoint(_Out):
    x: int
    y: int


class MissedOut(_Out):
    what: str
    sam_phrase: str
    frame: int
    point: GridPoint
    box: tuple[int, int, int, int] | None
    recurs: bool

    @field_validator("box", mode="before")
    @classmethod
    def _four_or_null(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        # miss-loop.md: a box that isn't exactly 4 integers becomes null (the point still counts).
        items = cast(list[object], value)
        if len(items) != 4 or not all(isinstance(v, int) and not isinstance(v, bool) for v in items):
            return None
        return items


class TrackOut(_Out):
    track_id: str
    role: Role
    evidence: str
    frames: list[int]
    matches_participant: int | None


class ObjectOut(_Out):
    track_id: str
    sensitive: bool
    content: str
    frames: list[int]


class RolePassOut(_Out):
    tracks: list[TrackOut]
    objects: list[ObjectOut]
    missed: list[MissedOut]


class RulingOut(_Out):
    track_id: str
    role: Role
    evidence: str
    frames: list[int]
    why_others_wrong: str


class EscalationOut(_Out):
    rulings: list[RulingOut]


class SpeechTurnOut(_Out):
    speaker: str
    start: float = Field(allow_inf_nan=False)
    end: float = Field(allow_inf_nan=False)
    text: str
    self_intro: str | None
    addresses: str | None


class SpeechOut(_Out):
    has_speech: bool
    turns: list[SpeechTurnOut]
