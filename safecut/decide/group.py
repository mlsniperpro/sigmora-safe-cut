"""Group a person's ``face:*`` and ``person:*`` tracks into one review item (WP3 step 2).

A face and a person track belong together when the face box lies inside the person box on at least 80 % of the
frames both have boxes on. "Inside" allows a sliver of hair over the person box's edge: 90 % of the face box's
area. Each face pairs with at most one person and the reverse; a Hungarian assignment settles faces inside two
people (one person behind another), the body a face fills most wins between bodies that hold it equally often (a
child's face inside both the child's body and the adult carrying them), and an exact tie pairs nothing. Grouping only
ever merges two hidden decisions or demands that both tracks qualify for a keep, so a wrong pair over-hides; a child's
face left unpaired locks every body that holds it (``policy.decide``).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from safecut.contracts import Track
from safecut.decide.geometry import area, assign, intersection

#: WP3 step 2: the face box is inside the person box on at least this share of their shared frames.
SHARED_FRAMES = 0.80
#: How much of the face box's area must fall inside the person box for it to count as inside.
FACE_INSIDE = 0.90
#: The fit's weight: a tie-break only, below any difference in shared frames (one frame in 10,000 frames).
TIE_BREAK = 1e-5


def inside_share(face: Track, person: Track) -> float:
    """The share of the frames both tracks have boxes on where the face lies inside the person (0 if none)."""
    shared = set(face.boxes) & set(person.boxes)
    if not shared:
        return 0.0
    inside = sum(intersection(face.boxes[f], person.boxes[f]) >= FACE_INSIDE * area(face.boxes[f]) for f in shared)
    return inside / len(shared)


def fit(face: Track, person: Track) -> float:
    """The face's mean share of the person box's area over their shared frames, in [0, 1]: larger is tighter."""
    shared = set(face.boxes) & set(person.boxes)
    if not shared:
        return 0.0
    return sum(min(1.0, area(face.boxes[f]) / max(1, area(person.boxes[f]))) for f in shared) / len(shared)


def group_tracks(tracks: Sequence[Track]) -> list[list[Track]]:
    """Every track in exactly one group (deny by default leaves nothing out), ordered by first frame then id."""
    faces = [t for t in tracks if t.concept == "face" and t.origin == "sam"]
    people = [t for t in tracks if t.concept == "person" and t.origin == "sam"]
    pairs: dict[str, str] = {}
    if faces and people:
        share = np.array([[inside_share(f, p) for p in people] for f in faces], dtype=np.float64)
        share[share < SHARED_FRAMES] = 0.0
        # Among bodies that hold a face equally often, the one it fills most is its own (a child's face inside both
        # the child's body and the adult carrying them): the fit breaks the tie without outweighing the share.
        share += (share > 0.0) * TIE_BREAK * np.array([[fit(f, p) for p in people] for f in faces], dtype=np.float64)
        for row, col in assign(share):
            best = share[row, col]
            if best <= 0.0:
                continue
            face_ties = int((share[row] == best).sum()) > 1
            person_ties = int((share[:, col] == best).sum()) > 1
            if not face_ties and not person_ties:
                pairs[faces[row].track_id] = people[col].track_id
    by_id = {t.track_id: t for t in tracks}
    paired = set(pairs) | set(pairs.values())
    groups = [[by_id[face], by_id[person]] for face, person in pairs.items()]
    groups += [[t] for t in tracks if t.track_id not in paired]
    return sorted(groups, key=lambda g: (min(t.first for t in g), min(t.track_id for t in g)))
