"""Synthetic job directories for the SAFETY lane's render/audit/receipt tests.

A clip of drawn faces (a static host and a bystander walking across), a static poster, and a 440 Hz tone, encoded
like a prepared clip (H.264 + AAC). YuNet detects these faces at ~0.9, so the audit's detector, the reversibility
check and the injected-leak test run on a real detector without any footage of real people (AGENTS rules 4-5).
Tracks are written from the drawing's geometry, the way SAM would report them. Everything here is synthetic.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from safecut.contracts import (
    Job,
    Participant,
    Roles,
    Scene,
    Track,
    Tracks,
    Transcript,
    Turn,
    dump,
)
from safecut.decide.geometry import BoxT, clamp

W, H, FPS = 320, 240, 30
SKIN = (140, 170, 210)


@dataclass(frozen=True)
class Actor:
    track_id: str
    start: tuple[int, int]
    step: tuple[float, float]
    size: int
    first: int
    last: int
    role: str  # participant | bystander | child
    skin: tuple[int, int, int] = SKIN

    def centre(self, frame: int) -> tuple[int, int]:
        d = frame - self.first
        return round(self.start[0] + self.step[0] * d), round(self.start[1] + self.step[1] * d)

    def box(self, frame: int) -> BoxT | None:
        cx, cy = self.centre(frame)
        s = self.size
        return clamp((cx - 0.45 * s, cy - 0.62 * s, cx + 0.45 * s, cy + 0.58 * s), W, H)


@dataclass
class Scenario:
    frames: int = 60
    actors: list[Actor] = field(
        default_factory=lambda: [
            Actor("face:1", (90, 120), (0.0, 0.0), 70, 0, 59, "participant"),
            Actor("face:2", (300, 110), (-3.0, 0.0), 50, 10, 59, "bystander", (120, 150, 190)),
        ]
    )
    audio: bool = True


def draw_face(img: np.ndarray, cx: int, cy: int, s: int, skin: tuple[int, int, int]) -> None:
    cv2.ellipse(img, (cx, cy), (int(s * 0.42), int(s * 0.55)), 0, 0, 360, skin, -1, cv2.LINE_AA)
    cv2.ellipse(img, (cx, cy - int(s * 0.3)), (int(s * 0.45), int(s * 0.3)), 0, 180, 360, (30, 30, 40), -1, cv2.LINE_AA)
    for dx in (-1, 1):
        ex, ey = cx + dx * int(s * 0.16), cy - int(s * 0.05)
        cv2.ellipse(img, (ex, ey), (int(s * 0.08), int(s * 0.045)), 0, 0, 360, (250, 250, 250), -1, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), int(s * 0.035), (40, 30, 20), -1, cv2.LINE_AA)
        cv2.ellipse(img, (ex, ey - int(s * 0.09)), (int(s * 0.09), int(s * 0.025)), 0, 180, 360, (40, 40, 50), 2,
                    cv2.LINE_AA)  # fmt: skip
    nose = np.array([[cx, cy], [cx - int(s * 0.05), cy + int(s * 0.15)], [cx + int(s * 0.05), cy + int(s * 0.15)]])
    cv2.polylines(img, [nose], False, (100, 120, 170), 2, cv2.LINE_AA)
    cv2.ellipse(
        img, (cx, cy + int(s * 0.27)), (int(s * 0.14), int(s * 0.05)), 0, 0, 180, (60, 60, 170), -1, cv2.LINE_AA
    )


POSTER: BoxT = (180, 170, 300, 230)


def frame_image(scenario: Scenario, index: int) -> np.ndarray:
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (90, 110, 80)
    img[:, :, 0] = np.linspace(70, 120, W, dtype=np.uint8)[None, :]
    cv2.rectangle(img, POSTER[:2], (POSTER[2] - 1, POSTER[3] - 1), (200, 200, 230), -1)
    cv2.putText(img, "SAFE CUT", (POSTER[0] + 8, POSTER[1] + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 40), 2)
    for actor in scenario.actors:
        if actor.first <= index <= actor.last:
            cx, cy = actor.centre(index)
            draw_face(img, cx, cy, actor.size, actor.skin)
    return cv2.GaussianBlur(img, (3, 3), 0)


def write_clip(path: Path, scenario: Scenario) -> None:
    raw = b"".join(frame_image(scenario, i).tobytes() for i in range(scenario.frames))
    argv = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]  # fmt: skip
    if scenario.audio:
        argv += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={scenario.frames / FPS}", "-c:a", "aac"]
    argv += ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
    subprocess.run(argv, input=raw, check=True)  # noqa: S603 -- fixed argv, bundled ffmpeg


def tracks_for(scenario: Scenario) -> Tracks:
    out: list[Track] = []
    for actor in scenario.actors:
        boxes = {f: b for f in range(actor.first, actor.last + 1) if (b := actor.box(f)) is not None}
        out.append(Track(track_id=actor.track_id, concept="face", first=min(boxes), last=max(boxes), boxes=boxes,
                         source="sam-3.1", prompt="face"))  # fmt: skip
    return Tracks(concepts=["face"], sam_fps=8, sam_frames=16, tracks=out)


def make_job(root: Path, scenario: Scenario | None = None, job_id: str = "j_synth") -> Path:
    """A job directory through ``tracks``/``roles``/``scene``/``transcript``, ready for decide → guard → render."""
    scenario = scenario or Scenario()
    job_dir = root / job_id
    job_dir.mkdir(parents=True)
    write_clip(job_dir / "prepared.mp4", scenario)
    dump(
        Job.model_validate({
            "job_id": job_id, "source": "synthetic.mp4", "source_sha256": "0" * 64, "prepared": "prepared.mp4",
            "fps": FPS, "width": W, "height": H, "frames": scenario.frames,
            "times": [i / FPS for i in range(scenario.frames)], "audio": scenario.audio,
            "created_at": "2026-10-30T12:00:00Z",
        }),
        job_dir / "job.json",
    )  # fmt: skip
    tracks = tracks_for(scenario)
    dump(tracks, job_dir / "tracks.json")
    rows = []
    for actor in scenario.actors:
        votes = [actor.role] * 3
        t = next(t for t in tracks.tracks if t.track_id == actor.track_id)
        rows.append({
            "track_id": actor.track_id, "role": actor.role, "votes": votes, "escalated": False,
            "evidence": f"synthetic {actor.role}", "frames": sorted({t.first, t.last}),
            "matches_participant": 0 if actor.role == "participant" else None,
        })  # fmt: skip
    dump(Roles.model_validate({"status": "ok", "model": "muse-spark-1.3", "tracks": rows}), job_dir / "roles.json")
    host = Participant(description="host", evidence="synthetic", speaker="S1", introduced_in_turn=None,
                       introduction_quote=None)  # fmt: skip
    dump(Scene(status="ok", model="muse-spark-1.3", summary="synthetic", participants=[host], candidate_objects=[]),
         job_dir / "scene.json")  # fmt: skip
    turns = [Turn(speaker="S1", start=0.0, end=1.0, text="Hi, I'm the host")] if scenario.audio else []
    transcript = (
        Transcript(status="ok", source="muse-voice-transcribe-1.0", source_kind="primary", turns=turns)
        if scenario.audio
        else Transcript(status="ok", source=None, source_kind=None, turns=[])
    )
    dump(transcript, job_dir / "transcript.json")
    (job_dir / "synthetic.json").write_text(json.dumps({"synthetic": True, "scenario": "tests/safety_jobs.py"}))
    return job_dir
