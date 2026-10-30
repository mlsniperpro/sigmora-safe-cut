"""Build the synthetic demo job: a clip, its ground truth, and a recorded response for every SENSE call.

**Everything here is synthetic.** The clip is drawn shapes; every recorded response is generated from the
clip's ground truth by a responder, never by a model, and is labelled ``synthetic: true``. The responder stands
in for Meta while the real stages run (prepare → track → transcribe → scene → roles, the miss loop and escalation
included), so the recordings are exactly what those stages ask for and what replay reads back.

Writes (deterministic; ``tests/test_demo_job.py`` rebuilds and compares):

- ``fixtures/clips/SC-A-91-synthetic-20261030.mp4``: 12 s, 640×360, 30 fps, with a soundtrack;
- ``fixtures/jobs/demo/truth/SC-A-91.json`` + ``tracks/SC-A-91/e<n>.mot.txt``: EVAL §1 labels (LABEL-FORMAT);
- ``fixtures/jobs/demo/raw/``: the recordings and ``manifest.json`` (``demo: true``) the pipeline replays.

The scene: a host (Amina) talks to camera and introduces her friend Kev; a passer-by walks behind them, leaves
and comes back (a re-entry: a new track ID); a child crosses the middle; an email inbox is on a wall screen; a
parked car shows its plate; an addressed envelope lies on the table, which no base concept finds (the miss loop
does). Keep: host and guest. Hide: everything else.

Usage: ``uv run python -m scripts.make_demo_job [--out-root <dir>]``
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import imageio_ffmpeg
import numpy as np
from numpy.typing import NDArray

from safecut import prepare
from safecut.config import Settings
from safecut.contracts import Job, Track, Tracks, load
from safecut.meta import replay, sam
from safecut.scout import boxes as keyframe_boxes
from safecut.scout import grid, roles, scene
from safecut.speech import stage as speech
from safecut.track import stage as track_stage
from safecut.track.axes import from_proxy_table
from safecut.track.synthetic import events as sam_events
from safecut.track.synthetic import stream_text

ROOT = Path(__file__).resolve().parent.parent
CLIP_NAME = "SC-A-91-synthetic-20261030.mp4"
CLIP_ID = "SC-A-91"
JOB_ID = "demo"
W, H, FPS, FRAMES = 640, 360, 30, 360
SECONDS = FRAMES / FPS
SYNTHETIC_FILE = "file-synthetic"
Box = tuple[int, int, int, int]


# ---------------------------------------------------------------------------- the scene


@dataclass(frozen=True)
class Figure:
    """A drawn person: head circle + body, with its visible frames and a position per frame."""

    entity: str
    shirt: tuple[int, int, int]  # BGR
    head_r: int
    body_w: int
    body_h: int
    frames: tuple[range, ...]

    def visible(self, f: int) -> bool:
        return any(f in r for r in self.frames)


def _host(f: int) -> tuple[int, int]:
    return 140 + round(6 * math.sin(2 * math.pi * f / 90)), 95


def _guest(f: int) -> tuple[int, int]:
    return max(500, 680 - 6 * (f - 60)), 105


def _passerby(f: int) -> tuple[int, int]:
    if f < 200:
        return -20 + round(5.5 * (f - 20)), 186
    return 660 - round(5.5 * (f - 200)), 186


def _child(f: int) -> tuple[int, int]:
    return 250 + round(0.6 * (f - 90)), 238


FIGURES: dict[str, tuple[Figure, Any]] = {
    "e1": (Figure("e1", (40, 120, 235), 32, 110, 200, (range(FRAMES),)), _host),
    "e2": (Figure("e2", (60, 170, 60), 31, 104, 200, (range(60, 330),)), _guest),
    "e3": (Figure("e3", (180, 90, 40), 19, 64, 110, (range(20, 140), range(200, 290))), _passerby),
    "e4": (Figure("e4", (160, 40, 150), 15, 42, 70, (range(90, 210),)), _child),
}
#: Objects: entity → (box, frames, category).
SCREEN: Box = (250, 18, 392, 102)
PLATE: Box = (540, 14, 616, 38)
ENVELOPE: Box = (360, 300, 432, 342)
OBJECTS: dict[str, tuple[Box, range]] = {
    "e5": (SCREEN, range(FRAMES)),
    "e6": (PLATE, range(150, 260)),
    "e7": (ENVELOPE, range(240, 336)),
}


def face_box(entity: str, f: int) -> Box | None:
    figure, at = FIGURES[entity]
    if not figure.visible(f):
        return None
    cx, cy = at(f)
    r = figure.head_r
    return _clip((cx - r, cy - r, cx + r + 1, cy + r + 1))


def person_box(entity: str, f: int) -> Box | None:
    figure, at = FIGURES[entity]
    if not figure.visible(f):
        return None
    cx, cy = at(f)
    r = figure.head_r
    return _clip((cx - figure.body_w // 2, cy - r, cx + figure.body_w // 2 + 1, cy + r + figure.body_h))


def object_box(entity: str, f: int) -> Box | None:
    box, frames = OBJECTS[entity]
    return box if f in frames else None


def truth_box(entity: str, f: int) -> Box | None:
    """The labelled box: the face for people (EVAL §1: head or face), the whole object otherwise."""
    return face_box(entity, f) if entity in FIGURES else object_box(entity, f)


def _clip(box: Box) -> Box | None:
    x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])
    return (x1, y1, x2, y2) if x2 - x1 >= 2 and y2 - y1 >= 2 else None


def draw(f: int) -> NDArray[np.uint8]:
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = np.linspace(150, 205, H, dtype=np.uint8)[:, None, None]  # a wall
    cv2.rectangle(img, (0, 290), (W, H), (90, 110, 130), -1)  # the floor and table edge
    x1, y1, x2, y2 = SCREEN
    cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), (35, 30, 30), -1)
    for k, line in enumerate(("Inbox", "Amina K. - Re: rent", "Bank: card 4417...")):
        cv2.putText(img, line, (x1 + 6, y1 + 22 + 24 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (240, 240, 240), 1,
                    cv2.LINE_AA)  # fmt: skip
    if f in OBJECTS["e6"][1]:
        cv2.rectangle(img, (500, 0), (636, 58), (70, 70, 160), -1)  # a parked car
        x1, y1, x2, y2 = PLATE
        cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), (250, 250, 250), -1)
        cv2.putText(img, "KDA 123X", (x1 + 4, y2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (10, 10, 10), 1, cv2.LINE_AA)
    order = ["e3", "e4", "e1", "e2"]  # the passer-by is furthest back
    for entity in order:
        figure, at = FIGURES[entity]
        if not figure.visible(f):
            continue
        cx, cy = at(f)
        r = figure.head_r
        cv2.rectangle(img, (cx - figure.body_w // 2, cy + r - 4), (cx + figure.body_w // 2, cy + r + figure.body_h),
                      figure.shirt, -1)  # fmt: skip
        cv2.circle(img, (cx, cy), r, (140, 180, 225), -1)
        cv2.circle(img, (cx - r // 3, cy - r // 6), max(2, r // 8), (30, 30, 30), -1)
        cv2.circle(img, (cx + r // 3, cy - r // 6), max(2, r // 8), (30, 30, 30), -1)
    if f in OBJECTS["e7"][1]:
        x1, y1, x2, y2 = ENVELOPE
        cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), (215, 235, 245), -1)
        cv2.putText(img, "K. Otieno", (x1 + 4, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (40, 40, 40), 1, cv2.LINE_AA)
        cv2.putText(img, "12 Moi Ave", (x1 + 4, y1 + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (40, 40, 40), 1, cv2.LINE_AA)
    return img


def soundtrack(path: Path) -> None:
    """Soft tones while someone speaks (the turns below), silence between: an audio stream to keep and mux."""
    rate = 24_000
    t = np.arange(int(SECONDS * rate)) / rate
    signal = np.zeros_like(t)
    for start, end, _, _ in TURNS:
        on = (t >= start) & (t < end)
        signal[on] = 0.2 * np.sin(2 * np.pi * 220 * t[on]) * np.sin(np.pi * (t[on] - start) / (end - start))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((signal * 32767).astype("<i2").tobytes())


def write_clip(path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "tone.wav"
        soundtrack(audio)
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-i", str(audio), "-c:a", "aac", "-b:a", "48k", "-shortest",
               "-threads", "1", "-c:v", "libx264", "-preset", "medium", "-crf", "26", "-pix_fmt", "yuv420p",
               "-g", str(FPS), "-bf", "0", "-movflags", "+faststart", "-map_metadata", "-1", "-fflags", "+bitexact",
               "-flags:v", "+bitexact", "-flags:a", "+bitexact", str(path)]  # fmt: skip
        raw = b"".join(draw(f).tobytes() for f in range(FRAMES))
        subprocess.run(cmd, input=raw, check=True)  # noqa: S603 -- fixed argv, bundled ffmpeg


# ---------------------------------------------------------------------------- ground truth (EVAL §1)

CATEGORY = {"e1": "participant", "e2": "participant", "e3": "bystander", "e4": "child", "e5": "screen",
            "e6": "plate", "e7": "document"}  # fmt: skip
DIFFICULTY = {"e3": ["reentry"], "e4": ["small"]}
REASON = {
    "e1": "the host: introduces herself as Amina and talks to camera",
    "e2": "the guest: introduced by the host as her friend Kev, answers her",
    "e3": "walks past behind them twice, never addressed",
    "e4": "a child crossing the middle of the frame",
    "e5": "a wall screen showing an email inbox with names",
    "e6": "a parked car's licence plate",
    "e7": "an addressed envelope on the table",
}


def write_truth(folder: Path) -> Path:
    tracks = folder / "tracks" / CLIP_ID
    tracks.mkdir(parents=True, exist_ok=True)
    entities: list[dict[str, Any]] = []
    for entity, category in CATEGORY.items():
        rows: list[str] = []
        visible = [f for f in range(FRAMES) if truth_box(entity, f) is not None]
        for f in visible:
            x1, y1, x2, y2 = cast(Box, truth_box(entity, f))
            rows.append(f"{f + 1},{entity[1:]},{x1},{y1},{x2 - x1},{y2 - y1},1,-1,-1,-1")
        (tracks / f"{entity}.mot.txt").write_text("\n".join(rows) + "\n")
        entities.append({
            "id": entity, "category": category, "should_hide": category not in ("participant",),
            "reason": REASON[entity], "difficulty": DIFFICULTY.get(entity, []),
            "frames": {"first": visible[0], "last": visible[-1]}, "boxes": f"tracks/{CLIP_ID}/{entity}.mot.txt",
        })  # fmt: skip
    label = {"clip": CLIP_NAME, "fps": FPS, "frames": FRAMES, "width": W, "height": H, "split": "dev",
             "entities": entities,
             "notes": "Synthetic clip drawn by scripts/make_demo_job.py; boxes are exact by construction."}  # fmt: skip
    path = folder / f"{CLIP_ID}.json"
    path.write_text(json.dumps(label, indent=1) + "\n")
    return path


# ---------------------------------------------------------------------------- the responder

TURNS: tuple[tuple[float, float, str, str], ...] = (
    (0.4, 2.8, "A", "Hi, I'm Amina, welcome back to the channel."),
    (2.9, 4.6, "A", "Today I'm at the market with my friend Kev."),
    (4.8, 6.4, "B", "Hey everyone, great to be here!"),
    (6.8, 9.2, "A", "Let's see what they have today."),
)
SCENE_ANSWER: dict[str, Any] = {
    "summary": "A street-market vlog: the host talks to camera and introduces her friend, who joins her.",
    "participants": [
        {"description": "woman in an orange top on the left, talking to camera", "evidence":
         "introduces herself: \"Hi, I'm Amina, welcome back to the channel\"", "speaker": "S1",
         "introduced_in_turn": 0, "introduction_quote": "I'm Amina", "is_creator": True},
        {"description": "man in a green top who joins from the right", "evidence":
         "introduced by the host as \"my friend Kev\" and greets the viewers", "speaker": "S2",
         "introduced_in_turn": 1, "introduction_quote": "my friend Kev", "is_creator": False},
    ],
    "children": [{"description": "a small figure in purple who crosses the middle"}],
    "others_present": "a passer-by in blue walks behind them",
    "candidate_objects": [
        {"what": "wall screen showing an email inbox", "approx_time": "throughout"},
        {"what": "a parked car's licence plate", "approx_time": "middle"},
        {"what": "an addressed envelope on the table", "approx_time": "end"},
    ],
}  # fmt: skip


def _responses_events(answer: Mapping[str, Any], response_id: str) -> list[dict[str, Any]]:
    text = json.dumps(answer, separators=(",", ":"))
    response = {
        "id": response_id, "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 0, "output_tokens": 0, "input_tokens_details": {"cached_tokens": 0}},
    }  # fmt: skip
    return [{"type": "response.created", "response": {"id": response_id, "status": "in_progress"}},
            {"type": "response.completed", "response": response}]  # fmt: skip


def iou(a: Sequence[int], b: Sequence[int]) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def entity_of(track: Track) -> str | None:
    """The ground-truth entity a track follows: best IoU against people's faces or bodies, or objects."""
    best: tuple[float, str | None] = (0.0, None)
    for f, box in track.boxes.items():
        for entity in [*FIGURES, *OBJECTS]:
            for truth in (
                (face_box(entity, f), person_box(entity, f)) if entity in FIGURES else (object_box(entity, f),)
            ):
                if truth is not None and (score := iou(box, truth)) > best[0]:
                    best = (score, entity)
        break
    return best[1] if best[0] >= 0.5 else None


class Responder:
    """Answers every SENSE call from the scene's geometry and script, as Meta's models would ideally answer."""

    def __init__(self, job_dir: Path, settings: Settings) -> None:
        self.job_dir = job_dir
        self.settings = settings
        self.job = load(job_dir / "job.json", Job)

    def __call__(self, stage: str, key: str, info: Mapping[str, Any]) -> replay.RawCall:
        answer = {"sam": self.sam, "asr": self.asr, "scene": self.scene, "roles": self.vote,
                  "escalate": self.escalate, "boxes": self.boxes}[stage](key, info)  # fmt: skip
        model = {"sam": self.settings.sam_model, "asr": self.settings.asr_model, "scene": self.settings.scene_model,
                 "roles": self.settings.role_model, "escalate": self.settings.escalate_model,
                 "boxes": self.settings.role_model}[stage]  # fmt: skip
        request = {k: v for k, v in info.items() if k in ("kind", "concept", "text", "sam_frames", "vote", "frames")}
        if stage == "sam":
            request["file_id"] = SYNTHETIC_FILE
            if info.get("labels"):
                labels = cast(Mapping[str, Any], info["labels"])
                request["labels"] = {k: vars(v) for k, v in labels.items()}
            return replay.RawCall(synthetic=True, stage="track", model=model, request=request, events=answer)
        if stage == "asr":
            return replay.RawCall(synthetic=True, stage="speech", model=model, request=request, response=answer)
        return replay.RawCall(synthetic=True, stage=stage, model=model, request=request, events=answer)

    # -- SAM ------------------------------------------------------------------

    def _proxy(self) -> tuple[int, list[int]]:
        frames = int(prepare_proxy_frames(self.job_dir))
        return frames, from_proxy_table(self.job.frames, self.job.fps, min(self.settings.sam_fps, self.job.fps), frames)

    def sam(self, key: str, info: Mapping[str, Any]) -> Any:
        frames, table = self._proxy()
        objects: dict[str, dict[int, Box]] = {}
        shapes: dict[str, str] = {}
        if info["kind"] == "phrase":
            concept = cast(str, info["concept"])
            boxes_of = {"face": face_box, "person": person_box}.get(concept)
            if boxes_of is not None:
                for n, entity in enumerate(FIGURES):
                    objects[str(n)] = {j: b for j, f in enumerate(table) if (b := boxes_of(entity, f)) is not None}
                    shapes[str(n)] = "ellipse" if concept == "face" else "rect"
            entity = {"screen": "e5", "license plate": "e6"}.get(concept)
            if entity is not None:
                objects["0"] = {j: b for j, f in enumerate(table) if (b := object_box(entity, f)) is not None}
        else:
            for p in cast(Sequence[sam.ObjectPrompt], info["prompts"]):
                hit = next((e for e in OBJECTS if (b := object_box(e, table[p.frame])) is not None
                            and b[0] <= p.point[0] < b[2] and b[1] <= p.point[1] < b[3]), None)  # fmt: skip
                if hit is not None:
                    objects[str(p.object_id)] = {
                        j: b for j, f in enumerate(table) if (b := object_box(hit, f)) is not None
                    }
        text = stream_text(objects, (self.job.width, self.job.height), shapes=shapes)
        return sam_events(text, response_id=f"resp_synthetic_{key.replace('-', '_')}", frames_billed=frames)

    # -- speech, scene ----------------------------------------------------------

    def asr(self, _key: str, _info: Mapping[str, Any]) -> Any:
        turns = [{"turnId": i, "speaker": s, "startMs": round(a * 1000), "endMs": round(b * 1000), "transcript": t}
                 for i, (a, b, s, t) in enumerate(TURNS)]  # fmt: skip
        return {"sessionId": "synthetic", "transcript": " ".join(t for *_, t in TURNS),
                "audioDurationMs": round(SECONDS * 1000), "turns": turns}  # fmt: skip

    def scene(self, key: str, _info: Mapping[str, Any]) -> Any:
        return _responses_events(SCENE_ANSWER, f"resp_synthetic_{key}")

    # -- role votes and escalation ---------------------------------------------

    def _tracks(self) -> dict[str, Track]:
        return {t.track_id: t for t in load(self.job_dir / "tracks.json", Tracks).tracks}

    def vote(self, key: str, info: Mapping[str, Any]) -> Any:
        k = cast(int, info["vote"])
        per_frame = cast(Sequence[tuple[int, Sequence[str]]], info["labels_per_frame"])
        tracks = self._tracks()
        present: dict[str, list[int]] = {}
        for f, labels in per_frame:
            for label in labels:
                present.setdefault(label, []).append(f)
        answer: dict[str, Any] = {"tracks": [], "objects": [], "missed": []}
        for track_id, frames in present.items():
            track = tracks[track_id]
            entity = entity_of(track)
            cite = frames[:2]
            if track.concept in ("face", "person"):
                role, evidence, idx = self._person(entity, track, k)
                answer["tracks"].append({"track_id": track_id, "role": role, "evidence": evidence, "frames": cite,
                                         "matches_participant": idx})  # fmt: skip
            else:
                content = REASON.get(entity or "", "an object that may show private details")
                answer["objects"].append({"track_id": track_id, "sensitive": True, "content": content, "frames": cite})
        sent = cast(Sequence[int], info["frames"])
        if key.startswith("pass1-") and k in (1, 2):
            frame = next((f for f in sent if object_box("e7", f) is not None), None)
            if frame is not None:
                answer["missed"].append(self._missed(frame))
        return _responses_events(answer, f"resp_synthetic_{key.replace('-', '_')}")

    def _person(self, entity: str | None, track: Track, k: int) -> tuple[str, str, int | None]:
        if entity == "e1":
            return "participant", "The host: introduces herself as Amina (S1) and talks to camera.", 0
        if entity == "e2":
            return "participant", "Introduced by the host as her friend Kev; he answers her (S2).", 1
        if entity == "e4":
            return (
                ("child", "Looks like a child.", None)
                if k == 1
                else ("bystander", "Crosses behind, not addressed.", None)
            )
        if entity == "e3" and track.reentry_of is not None and k == 2:
            return "unsure", "Too small to tell who this is on these frames.", None
        return "bystander", "Walks past in the background; nobody addresses them.", None

    def gx(self, px: float) -> int:
        return round(px * grid.GRID / self.job.width)

    def gy(self, py: float) -> int:
        return round((py + grid.BAR_H) * grid.GRID / (self.job.height + grid.BAR_H))

    def grid_box(self, box: Box) -> list[int]:
        return [self.gx(box[0]), self.gy(box[1]), self.gx(box[2]), self.gy(box[3])]

    def _missed(self, frame: int) -> dict[str, Any]:
        x1, y1, x2, y2 = ENVELOPE
        return {"what": "an addressed envelope on the table", "sam_phrase": "envelope", "frame": frame,
                "point": {"x": self.gx((x1 + x2) / 2), "y": self.gy((y1 + y2) / 2)},
                "box": self.grid_box(ENVELOPE), "recurs": False}  # fmt: skip

    def boxes(self, key: str, info: Mapping[str, Any]) -> Any:
        """The muse_no_track baseline's detector: every visible object on each keyframe, as boxes."""
        frames: list[dict[str, Any]] = []
        for f in cast(Sequence[int], info["frames"]):
            objects: list[dict[str, Any]] = []
            for entity in FIGURES:
                for kind, box in (("face", face_box(entity, f)), ("person", person_box(entity, f))):
                    if box is not None:
                        objects.append({"kind": kind, "box": self.grid_box(box)})
            for entity, kind in (("e5", "screen"), ("e6", "license plate"), ("e7", "document")):
                if (box := object_box(entity, f)) is not None:
                    objects.append({"kind": kind, "box": self.grid_box(box)})
            frames.append({"frame": f, "objects": objects})
        return _responses_events({"frames": frames}, f"resp_synthetic_boxes_{key}")

    def escalate(self, key: str, info: Mapping[str, Any]) -> Any:
        tracks = self._tracks()
        sent = cast(Sequence[int], info["frames"])
        rulings: list[dict[str, Any]] = []
        for track_id in cast(Sequence[str], info["disputed"]):
            frames = [f for f in sent if f in tracks[track_id].boxes][:2]
            rulings.append({
                "track_id": track_id, "role": "bystander", "frames": frames,
                "evidence": "Walks past behind the host and guest; nobody addresses or introduces them.",
                "why_others_wrong": "The unsure judge relied on the figure's size, not on any exchange.",
            })  # fmt: skip
        return _responses_events({"rulings": rulings}, f"resp_synthetic_escalate_{key}")


def prepare_proxy_frames(job_dir: Path) -> int:
    from safecut.track import media  # noqa: PLC0415 -- only the responder needs the proxy's count

    return media.frame_count(job_dir / track_stage.PROXY)


# ---------------------------------------------------------------------------- build


async def record(clip: Path, job_dir: Path) -> None:
    settings = Settings(sam_fps=8)
    (job_dir / "source").mkdir(parents=True)
    shutil.copyfile(clip, job_dir / "source" / clip.name)
    prepare.prepare(clip, job_dir)
    responder = Responder(job_dir, settings)
    await track_stage.run_async(job_dir, settings=settings, responder=responder)
    await speech.run_async(job_dir, settings=settings, responder=responder)
    await scene.run_async(job_dir, settings=settings, responder=responder)
    await roles.run_async(job_dir, settings=settings, responder=responder)


#: Baselines whose perception differs from the full pipeline, recorded under ``variants/<name>/raw/`` (EVAL §3).
#: ``blur_all`` and ``detector_only`` replay the main recordings' ``face``/``license plate``/``screen`` sweeps.
VARIANTS = ("muse_no_track",)


async def record_muse_no_track(clip: Path, job_dir: Path) -> None:
    """EVAL §3 row 3: Muse's per-keyframe boxes held between keyframes (no SAM, miss loop stubbed), then the scene
    pass, the role pass ×3 and escalation as in the full pipeline."""
    settings = Settings(sam_fps=8, miss_sam="stub")
    (job_dir / "source").mkdir(parents=True)
    shutil.copyfile(clip, job_dir / "source" / clip.name)
    prepare.prepare(clip, job_dir)
    responder = Responder(job_dir, settings)
    await keyframe_boxes.run_async(job_dir, settings=settings, responder=responder)
    await speech.run_async(job_dir, settings=settings, responder=responder)
    await scene.run_async(job_dir, settings=settings, responder=responder)
    await roles.run_async(job_dir, settings=settings, responder=responder)


def main(out_root: Path) -> Path:
    clip = out_root / "fixtures" / "clips" / CLIP_NAME
    clip.parent.mkdir(parents=True, exist_ok=True)
    write_clip(clip)
    demo = out_root / "fixtures" / "jobs" / JOB_ID
    if demo.exists():
        shutil.rmtree(demo)
    truth = write_truth(demo / "truth")
    with tempfile.TemporaryDirectory() as tmp:
        job_dir = Path(tmp) / JOB_ID
        asyncio.run(record(clip, job_dir))
        shutil.copytree(job_dir / replay.RAW, demo / replay.RAW)
    manifest = {
        "demo": True,
        "synthetic": True,
        "source": str(clip.relative_to(out_root)),
        "source_sha256": prepare.sha256_file(clip),
        "truth": str(truth.relative_to(out_root)),
        "note": "Synthetic: every response was generated from the clip's ground truth by scripts/make_demo_job.py "
        "(none is model output).",
    }
    (demo / replay.RAW / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    for variant in VARIANTS:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / JOB_ID
            asyncio.run(record_muse_no_track(clip, job_dir))
            target = demo / "variants" / variant / replay.RAW
            shutil.copytree(job_dir / replay.RAW, target)
        note = {
            "variant": variant,
            "synthetic": True,
            "source": manifest["source"],
            "source_sha256": manifest["source_sha256"],
            "settings": {"SAFECUT_MISS_SAM": "stub"},
            "note": f"Synthetic recordings for the {variant} baseline (EVAL §3), generated from ground truth.",
        }
        (target / "variant.json").write_text(json.dumps(note, indent=1) + "\n")
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the synthetic demo job (clip, truth, recordings).")
    parser.add_argument(
        "--out-root", type=Path, default=ROOT, help="repository root to write into (default: this repo)"
    )
    print(main(parser.parse_args().out_root))
