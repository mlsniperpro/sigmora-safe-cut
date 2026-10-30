"""Builders and hypothesis strategies for the SAFETY lane's tests (decide, guard, render, audit, receipt)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import strategies as st

from safecut.contracts import (
    Job,
    Participant,
    Roles,
    RoleTrack,
    Scene,
    SceneChild,
    StageStatus,
    Track,
    Tracks,
    Transcript,
    Turn,
)

W, H, FPS, FRAMES = 320, 180, 30, 60


def job(frames: int = FRAMES, *, width: int = W, height: int = H, fps: int = FPS, audio: bool = True) -> Job:
    return Job(
        job_id="j_test",
        source="clip.mp4",
        source_sha256="a" * 64,
        prepared="prepared.mp4",
        fps=fps,
        width=width,
        height=height,
        frames=frames,
        times=[i / fps for i in range(frames)],
        audio=audio,
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
    )


def track(
    track_id: str,
    first: int,
    last: int,
    box: tuple[int, int, int, int] = (10, 10, 50, 50),
    *,
    step: tuple[int, int] = (0, 0),
    anchors: list[int] | None = None,
    **extra: Any,
) -> Track:
    """A track moving ``step`` px a frame from ``box`` at ``first``; boxes on ``anchors`` (default: every frame)."""
    frames = anchors if anchors is not None else list(range(first, last + 1))
    boxes = {
        f: (box[0] + step[0] * (f - first), box[1] + step[1] * (f - first), box[2] + step[0] * (f - first),
            box[3] + step[1] * (f - first))
        for f in frames
    }  # fmt: skip
    concept = track_id.rsplit(":", 1)[0]
    origin = extra.pop("origin", "sam")
    return Track(
        track_id=track_id,
        concept=concept,
        first=first,
        last=last,
        boxes=boxes,
        source=None if origin == "static" else "sam-3.1",
        prompt=concept,
        origin=origin,
        **extra,
    )


def tracks(*items: Track, sam_fps: int = 8, crowded: list[int] | None = None) -> Tracks:
    return Tracks(
        concepts=sorted({t.concept for t in items}),
        sam_fps=sam_fps,
        sam_frames=16,
        tracks=list(items),
        crowded_frames=crowded or [],
    )


def row(track_id: str, *votes: str, frames: tuple[int, ...] = (5, 15), **extra: Any) -> RoleTrack:
    """A roles.json row; the role follows role-pass.md (3/3 participant, any child, all bystander, else unsure)."""
    vs = list(votes)
    if "role" in extra:
        role = extra.pop("role")
    elif "child" in vs:
        role = "child"
    elif vs == ["participant"] * 3 and len(set(frames)) >= 2:
        role = "participant"
    elif vs == ["bystander"] * 3:
        role = "bystander"
    else:
        role = "unsure"
    return RoleTrack.model_validate(
        {
            "track_id": track_id,
            "role": role,
            "votes": vs,
            "escalated": extra.pop("escalated", role == "unsure"),
            "evidence": extra.pop("evidence", "seen talking to the camera"),
            "frames": list(frames),
            **extra,
        }
    )


def roles(*rows: RoleTrack, status: StageStatus = "ok", objects: list[dict[str, Any]] | None = None) -> Roles:
    return Roles.model_validate(
        {
            "status": status,
            "model": "muse-spark-1.3" if status == "ok" else None,
            "tracks": [r.model_dump() for r in rows],
            "objects": objects or [],
        }
    )


def scene(*, status: StageStatus = "ok", children: int = 0, participants: list[Participant] | None = None) -> Scene:
    return Scene(
        status=status,
        model="muse-spark-1.3" if status == "ok" else None,
        summary="synthetic",
        participants=participants
        if participants is not None
        else [
            Participant(
                description="host",
                evidence="introduced",
                speaker="S1",
                introduced_in_turn=None,
                introduction_quote=None,
            )
        ],
        candidate_objects=[],
        children=[SceneChild(description="a child") for _ in range(children)],
    )


def transcript(*, status: StageStatus = "ok", degraded: bool = False, turns: list[Turn] | None = None) -> Transcript:
    if status != "ok":
        return Transcript(status=status, source=None, source_kind=None, degraded=True, turns=[])
    return Transcript(
        status="ok",
        source="muse-voice-transcribe-1.0",
        source_kind="primary",
        degraded=degraded,
        turns=turns if turns is not None else [Turn(speaker="S1", start=0.0, end=1.0, text="Hi, I'm Amina")],
    )


# ---------------------------------------------------------------------------------------------------- strategies

CONCEPTS = ["face", "person", "license plate", "screen", "document", "menu"]
ROLES = ["participant", "bystander", "child", "unsure"]


@st.composite
def track_sets(draw: st.DrawFn, frames: int = FRAMES, max_tracks: int = 6) -> list[Track]:
    """Random valid tracks: densified or anchored, moving or still, re-entries, child phrases, static boxes."""
    n = draw(st.integers(1, max_tracks))
    counts: dict[str, int] = {}
    out: list[Track] = []
    for _ in range(n):
        concept = draw(st.sampled_from(CONCEPTS))
        counts[concept] = counts.get(concept, 0) + 1
        first = draw(st.integers(0, frames - 1))
        last = draw(st.integers(first, min(frames - 1, first + 40)))
        w, h = draw(st.integers(4, 80)), draw(st.integers(4, 90))
        x, y = draw(st.integers(0, W - w)), draw(st.integers(0, H - h))
        dx, dy = draw(st.integers(-1, 1)), draw(st.integers(-1, 1))
        span = last - first
        dx = dx if x + dx * span >= 0 and x + w + dx * span <= W else 0
        dy = dy if y + dy * span >= 0 and y + h + dy * span <= H else 0
        inner = list(range(first + 1, last))
        anchors = None
        if inner and draw(st.booleans()):
            anchors = sorted({first, last, *draw(st.lists(st.sampled_from(inner), max_size=4))})
        origin = "static" if draw(st.integers(0, 9)) == 0 else "sam"
        earlier = [t.track_id for t in out if t.concept == concept and t.last < first]
        reentry = draw(st.sampled_from([None, *earlier])) if earlier else None
        out.append(
            track(
                f"{concept}:{counts[concept]}",
                first,
                last,
                (x, y, x + w, y + h),
                step=(dx, dy),
                anchors=anchors,
                origin=origin,
                reentry_of=reentry,
                child_phrase=draw(st.integers(0, 7)) == 0,
            )
        )
    return out


@st.composite
def role_rows(draw: st.DrawFn, items: list[Track], status: StageStatus) -> list[RoleTrack]:
    rows: list[RoleTrack] = []
    for t in items:
        if draw(st.integers(0, 5)) == 0:
            continue  # a track the role pass never judged
        if status != "ok":
            rows.append(row(t.track_id, "unsure", "unsure", "unsure", role="unsure", escalated=False, failed_votes=3))
            continue
        votes = draw(st.lists(st.sampled_from(ROLES), min_size=3, max_size=3))
        if draw(st.booleans()):
            votes = ["participant"] * 3
        frames = tuple(draw(st.lists(st.integers(0, FRAMES - 1), min_size=0, max_size=3)))
        failed = draw(st.integers(0, 3)) if draw(st.integers(0, 4)) == 0 else 0
        r = row(t.track_id, *votes, frames=frames, failed_votes=failed)
        if r.role == "participant" and draw(st.booleans()):
            r = r.model_copy(update={"matches_participant": draw(st.integers(0, 1))})
        if r.role == "unsure" and draw(st.booleans()):
            r = r.model_copy(update={"escalated": False})
        elif r.role == "unsure":
            r = r.model_copy(update={"suggested_role": draw(st.sampled_from([None, "participant", "bystander"]))})
        rows.append(RoleTrack.model_validate(r.model_dump()))
    return rows
