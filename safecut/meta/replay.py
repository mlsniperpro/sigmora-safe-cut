"""Recorded API calls: what a live run saves under ``<job>/raw/`` and what replay mode reads back.

One JSON file per call. Live runs record the response exactly as Meta sent it (stream events, or the JSON body),
plus a small descriptor of the request; replay feeds the same bytes to the same parsers and schemas, so a
replayed stage runs the code path a live one does. Synthetic recordings (generated from a synthetic clip's
ground truth, never from a model) carry ``synthetic: true`` and are never presented as model output.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from safecut.contracts import dump, load

RAW = "raw"
_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")


class ReplayMissing(FileNotFoundError):
    """Replay mode needs a recorded response that isn't in the job directory."""


class RawCall(BaseModel):
    """One recorded call. ``events`` for streamed Responses/SAM calls, ``response`` for plain JSON bodies."""

    model_config = ConfigDict(extra="forbid")

    synthetic: bool
    stage: str = Field(min_length=1)
    model: str = Field(min_length=1)
    request: dict[str, Any]
    events: list[dict[str, Any]] | None = None
    response: Any = None
    #: What the live call cost when it was recorded (0 for synthetic recordings); replay spends nothing.
    usd: float = Field(default=0.0, ge=0)

    def failure(self) -> tuple[str, str] | None:
        """``(kind, reason)`` for a recorded failure (``kind`` is ``budget`` for a budget stop), else ``None``."""
        response: object = self.response
        if not isinstance(response, dict):
            return None
        body = cast(dict[str, Any], response)
        kind = body.get("failed")
        return None if kind is None else (str(kind), str(body.get("reason") or kind))


def slug(text: str) -> str:
    """A file-name-safe key for a phrase: lowercase, runs of anything else to ``_``."""
    out = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return out[:80] or "x"


def path(job_dir: Path, stage: str, key: str) -> Path:
    if not _KEY.fullmatch(key) or not _KEY.fullmatch(stage):
        raise ValueError(f"bad recording key {stage}/{key}")
    return job_dir / RAW / stage / f"{key}.json"


def save(job_dir: Path, stage: str, key: str, call: RawCall) -> Path:
    target = path(job_dir, stage, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    return dump(call, target)


def load_call(job_dir: Path, stage: str, key: str) -> RawCall:
    target = path(job_dir, stage, key)
    if not target.exists():
        raise ReplayMissing(f"replay: no recorded response {target.relative_to(job_dir)}")
    return load(target, RawCall)


def exists(job_dir: Path, stage: str, key: str) -> bool:
    return path(job_dir, stage, key).exists()
