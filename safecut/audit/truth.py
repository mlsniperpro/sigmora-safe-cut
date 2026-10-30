"""Ground-truth labels (EVAL.md §1, ``docs/labeling/LABEL-FORMAT.md``) read as boxes per prepared frame.

Used by the synthetic red-team (a synthetic job's ``raw/manifest.json`` names its truth file) and by E3's
coverage scoring. MOT rows are 1-based source frames with ``x, y, w, h`` in source pixels; boxes are scaled to the
prepared clip and rounded outward to half-open ints.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from safecut.audit.redteam import TruthObject
from safecut.contracts import LeakKind
from safecut.decide.geometry import BoxT, clamp

#: What a red-teamer would call each label category (LABELING-GUIDE §2.1).
KIND: dict[str, LeakKind] = {
    "participant": "face",
    "bystander": "face",
    "child": "face",
    "photo": "face",
    "plate": "plate",
    "screen": "screen",
    "document": "text",
    "address": "text",
    "other": "other",
}


@dataclass(frozen=True)
class Labels:
    frames: dict[int, list[TruthObject]]
    should_hide: dict[str, bool]
    categories: dict[str, str]

    def boxes(self) -> dict[int, dict[str, BoxT]]:
        """frame → entity → box, the shape ``render.coverage.score`` takes."""
        return {f: {o.label: o.box for o in objs} for f, objs in self.frames.items()}


def load_labels(path: Path, *, width: int, height: int, frames: int) -> Labels:
    data = json.loads(path.read_text(encoding="utf-8"))
    sx, sy = width / data["width"], height / data["height"]
    out: dict[int, list[TruthObject]] = {}
    hide: dict[str, bool] = {}
    categories: dict[str, str] = {}
    for entity in data["entities"]:
        eid, category = entity["id"], entity["category"]
        hide[eid] = bool(entity["should_hide"])
        categories[eid] = category
        if entity.get("boxes") is None:
            continue
        for row in (path.parent / entity["boxes"]).read_text(encoding="utf-8").splitlines():
            if not row.strip():
                continue
            k, _, x, y, w, h = (float(v) for v in row.split(",")[:6])
            frame = round(k) - 1
            box = clamp((math.floor(x * sx), math.floor(y * sy), math.ceil((x + w) * sx), math.ceil((y + h) * sy)),
                        width, height)  # fmt: skip
            if box is None or not 0 <= frame < frames:
                continue
            out.setdefault(frame, []).append(
                TruthObject(box=box, kind=KIND.get(category, "other"), should_hide=hide[eid], label=eid)
            )
    return Labels(frames=out, should_hide=hide, categories=categories)


def manifest_truth(job_dir: Path) -> Path | None:
    """The truth file a **synthetic** recording's manifest names (repo-relative), when it exists."""
    manifest = job_dir / "raw" / "manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True or not isinstance(data.get("truth"), str):
        return None
    for root in (Path.cwd(), Path(__file__).resolve().parents[2]):
        candidate = root / data["truth"]
        if candidate.is_file():
            return candidate
    return None
