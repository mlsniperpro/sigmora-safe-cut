"""Miss-loop post-processing (``miss-loop.md`` steps 1–5 and its failure handling; vectors M1–M13). Pure.

Muse names what SAM missed; each validated item always gets a point prompt, recurring kinds also a phrase sweep,
and an item that never gets a SAM result gets a static hidden box. A reported miss is never silently dropped.
"""

from __future__ import annotations

import math
import string
from collections.abc import Sequence
from dataclasses import dataclass, field

from safecut.contracts import Box, Track
from safecut.scout import grid

MAX_ITEMS = 8
MAX_PHRASE_SWEEPS = 3
MAX_PHRASE_WORDS = 3
MAX_LOOPS = 2
#: ``temporal.extend``'s floor (ARCHITECTURE §3.7): a static box spans ± max(this, round(job.fps)) frames.
TEMPORAL_EXTEND = 8
#: A static box around a lone point is a square of this share of min(W, H) (43 px at 1280×720).
POINT_BOX_SHARE = 0.06
#: Misses from different votes merge when their points are this share of the frame diagonal apart or closer.
MERGE_SHARE = 0.05
BLOCKLIST = frozenset({"thing", "object", "stuff", "private", "sensitive", "item"})
SINGULAR = {
    "children": "child",
    "kids": "kid",
    "babies": "baby",
    "men": "man",
    "women": "woman",
    "people": "person",
    "teens": "teen",
    "passersby": "passerby",
    "schoolchildren": "schoolchild",
    "ladies": "lady",
    "minors": "minor",
    "faces": "face",
    "childrens": "child",
    "mens": "man",
    "womens": "woman",
    "peoples": "person",
}
CHILD_SET = frozenset(
    {
        "child",
        "kid",
        "baby",
        "infant",
        "toddler",
        "boy",
        "girl",
        "teen",
        "teenager",
        "student",
        "schoolchild",
        "minor",
        # Beyond miss-loop.md's list (stricter only: any of these locks the track hidden as a child).
        "schoolgirl",
        "schoolboy",
        "newborn",
        "pupil",
        "youngster",
        "preteen",
        "tween",
        "kiddo",
    }
)
PERSON_SET = (
    frozenset(
        {
            "person",
            "man",
            "woman",
            "adult",
            "guy",
            "lady",
            "reflection",
            "silhouette",
            "crowd",
            "pedestrian",
            "passerby",
            "driver",
            "face",
        }
    )
    | CHILD_SET
)
_DELETE = str.maketrans("", "", string.punctuation + "‘’“”–—…")


def normalise(phrase: str) -> str:
    """Lowercase, delete punctuation (no space inserted: ``passers-by`` → ``passersby``), collapse spaces."""
    return " ".join(phrase.lower().translate(_DELETE).split())


def singular(token: str) -> str:
    if token in SINGULAR:
        return SINGULAR[token]
    if token.endswith("s") and token[:-1] in PERSON_SET:
        return token[:-1]
    return token


@dataclass(frozen=True)
class Concept:
    concept: str
    child_phrase: bool


#: An object concept is at most 40 characters, cut at a word boundary.
CONCEPT_CHARS = 40


def concept_for(phrase: str) -> Concept:
    """A normalised phrase → its track concept (M12, M13): any child-set token → ``person`` + ``child_phrase``;
    a person-set head noun → ``person`` (``face`` for a face); anything else is an object named by the phrase."""
    tokens = [singular(t) for t in phrase.split()]
    if not tokens:
        raise ValueError("an empty phrase has no concept")
    if any(t in CHILD_SET for t in tokens):
        return Concept("person", child_phrase=True)
    if tokens[-1] in PERSON_SET:
        return Concept("face" if tokens[-1] == "face" else "person", child_phrase=False)
    # A model-written phrase names the track (labels, Set-of-Mark tags): bounded like a sweep's phrase.
    short = phrase if len(phrase) <= CONCEPT_CHARS else phrase[: CONCEPT_CHARS + 1].rsplit(" ", 1)[0]
    return Concept(short[:CONCEPT_CHARS].strip(), child_phrase=False)


@dataclass(frozen=True)
class RawMiss:
    """One ``missed`` entry as a vote returned it (0–1000 grid on the sent image)."""

    what: str
    sam_phrase: str
    frame: int
    point: tuple[int, int]
    box: tuple[int, int, int, int] | None
    recurs: bool


@dataclass
class Miss:
    """A validated miss in prepared-clip pixels, with what the loop plans for it."""

    what: str
    phrase: str
    frame: int
    point: tuple[int, int]
    box: Box | None
    recurs: bool
    concept: Concept
    sweep: bool = False
    notes: list[str] = field(default_factory=list[str])
    track_ids: list[str] = field(default_factory=list[str])


def validate(raw: RawMiss, *, sent: frozenset[int], width: int, height: int, bar_h: int = grid.BAR_H) -> Miss | None:
    """Steps 1–2: the frame must have been sent (M7); the point must land in the picture, else the box's centre
    stands in for it (M9); an item with neither is dropped. An empty phrase is dropped too."""
    phrase = normalise(raw.sam_phrase)
    if raw.frame not in sent or not phrase:
        return None
    box = grid.box(raw.box, width, height, kind="miss", bar_h=bar_h) if raw.box is not None else None
    point = grid.point(raw.point[0], raw.point[1], width, height, bar_h)
    if point is None and box is not None:
        point = ((box[0] + box[2] - 1) // 2, (box[1] + box[3] - 1) // 2)
    if point is None:
        return None
    return Miss(what=raw.what, phrase=phrase, frame=raw.frame, point=point, box=box, recurs=raw.recurs,
                concept=concept_for(phrase))  # fmt: skip


#: A miss with its own box counts as tracked only if a same-concept track box covers this share of it.
TRACKED_SHARE = 0.5


def _covers(box: Box, miss: Miss) -> bool:
    x, y = miss.point
    if not (box[0] <= x < box[2] and box[1] <= y < box[3]):
        return False
    if miss.box is None:
        return True
    m = miss.box
    inter = max(0, min(box[2], m[2]) - max(box[0], m[0])) * max(0, min(box[3], m[3]) - max(box[1], m[1]))
    return inter >= TRACKED_SHARE * (m[2] - m[0]) * (m[3] - m[1])


def untracked(misses: Sequence[Miss], tracks: Sequence[Track]) -> list[Miss]:
    """Drop a miss already tracked (and hidden): a track of the same concept whose box on the miss's frame holds its
    point and, when the miss has a box, half of that box, e.g. loop 1's envelope re-reported by the re-pass.
    Another concept's box doesn't count: an unboxed face on a boxed screen is still a miss (``miss-loop.md`` tricky
    case 2). A child miss counts as tracked only by a ``child_phrase`` track: a child in front of an adult's person
    box is still a child to lock."""
    kept: list[Miss] = []
    for miss in misses:
        covered = any(
            t.concept == miss.concept.concept
            and (t.child_phrase or not miss.concept.child_phrase)
            and (box := t.boxes.get(miss.frame)) is not None
            and _covers(box, miss)
            for t in tracks
        )
        if not covered:
            kept.append(miss)
    return kept


def dedupe(misses: Sequence[Miss], width: int, height: int) -> list[Miss]:
    """Step 4: merge items with the same phrase on the same frame whose points are ≤ 5% of the diagonal apart
    (M10). The first keeps its place; ``recurs`` and a box carry over from the merged ones."""
    limit = MERGE_SHARE * math.hypot(width, height)
    kept: list[Miss] = []
    for miss in misses:
        twin = next(
            (
                k
                for k in kept
                if k.phrase == miss.phrase and k.frame == miss.frame and math.dist(k.point, miss.point) <= limit
            ),
            None,
        )
        if twin is None:
            kept.append(miss)
            continue
        twin.recurs = twin.recurs or miss.recurs
        twin.box = twin.box or miss.box
    return kept


@dataclass
class LoopPlan:
    prompts: list[Miss]
    sweeps: list[Miss]
    static: list[Miss]


def plan(misses: Sequence[Miss], *, swept: Sequence[str]) -> LoopPlan:
    """Step 3 and 5: the first 8 items get point prompts (the rest static boxes, ``item_cap``); a phrase sweep runs
    for at most 3 recurring, short, new, non-blocklisted phrases (``phrase_too_long``, ``phrase_budget``)."""
    done = {normalise(s) for s in swept}
    prompts = list(misses[:MAX_ITEMS])
    static = list(misses[MAX_ITEMS:])
    for miss in static:
        miss.notes.append("item_cap")
    sweeps: list[Miss] = []
    for miss in prompts:
        if not miss.recurs or miss.phrase in done or miss.phrase in BLOCKLIST:
            continue
        if len(miss.phrase.split()) > MAX_PHRASE_WORDS:
            miss.notes.append("phrase_too_long")
            continue
        if len(sweeps) >= MAX_PHRASE_SWEEPS:
            miss.notes.append("phrase_budget")
            continue
        miss.sweep = True
        done.add(miss.phrase)
        sweeps.append(miss)
    return LoopPlan(prompts=prompts, sweeps=sweeps, static=static)


def static_box(miss: Miss, width: int, height: int) -> Box:
    """The fallback box: the item's own box, else a square of 6% of ``min(W, H)`` centred on its point."""
    if miss.box is not None:
        return miss.box
    side = max(2, round(POINT_BOX_SHARE * min(width, height)))
    x, y = miss.point
    x1, y1 = max(0, x - side // 2), max(0, y - side // 2)
    return (x1, y1, min(width, x1 + side), min(height, y1 + side))


def static_track(miss: Miss, track_id: str, *, fps: int, frames: int, width: int, height: int) -> Track:
    """A hidden static box on ``frame ± max(extend, job.fps)`` (M8, M11): never role-passed, never auto-kept."""
    reach = max(TEMPORAL_EXTEND, fps)
    first, last = max(0, miss.frame - reach), min(frames - 1, miss.frame + reach)
    box = static_box(miss, width, height)
    return Track(
        track_id=track_id,
        concept=miss.concept.concept,
        first=first,
        last=last,
        boxes=dict.fromkeys(range(first, last + 1), box),
        source=None,
        prompt=miss.phrase,
        origin="static",
        child_phrase=miss.concept.child_phrase,
    )
