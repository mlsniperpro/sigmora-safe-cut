"""Generate the tiny synthetic test clips in ``fixtures/clips/`` (deterministic, no real footage).

Each clip is ≤ 3 s of moving coloured boxes over a grey background, with the frame number burned into
a black bar at the top (``F 000042``), so a model's answer about "which number is visible" can be checked
against ground truth. ``counter_30fps_audio.mp4`` also carries a 440 Hz tone that beeps on frames 30-44
for the speech/ASR timing probes.

Usage: ``uv run python scripts/make_synthetic_clips.py [out_dir]``
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

WIDTH, HEIGHT = 320, 180
BAR_H = 24


def frame_image(index: int, fps: int) -> np.ndarray:
    img = np.full((HEIGHT, WIDTH, 3), 128, dtype=np.uint8)
    t = index / fps
    # A red box moving right, a blue box moving down; positions are exact functions of the frame index.
    rx = int(10 + 60 * t)
    cv2.rectangle(img, (rx, 60), (rx + 40, 100), (0, 0, 255), thickness=-1)
    by = int(BAR_H + 4 + 30 * t)
    cv2.rectangle(img, (220, by), (260, by + 40), (255, 0, 0), thickness=-1)
    cv2.rectangle(img, (0, 0), (WIDTH, BAR_H), (0, 0, 0), thickness=-1)
    cv2.putText(img, f"F {index:06d}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def boxes(index: int, fps: int) -> dict[str, list[int]]:
    t = index / fps
    rx = int(10 + 60 * t)
    by = int(BAR_H + 4 + 30 * t)
    return {"red": [rx, 60, rx + 41, 101], "blue": [220, by, 261, by + 41]}


def tone_wav(path: Path, *, seconds: float, fps: int, beep_frames: tuple[int, int]) -> None:
    rate = 24_000
    n = int(seconds * rate)
    t = np.arange(n) / rate
    signal = np.zeros(n)
    start, end = beep_frames[0] / fps, (beep_frames[1] + 1) / fps
    on = (t >= start) & (t < end)
    signal[on] = 0.4 * np.sin(2 * np.pi * 440 * t[on])
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((signal * 32767).astype("<i2").tobytes())


def write_clip(path: Path, *, fps: int, frames: int, audio: Path | None) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{WIDTH}x{HEIGHT}",
           "-r", str(fps), "-i", "-"]  # fmt: skip
    if audio is not None:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "48k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryslow", "-crf", "30", "-pix_fmt", "yuv420p", "-g", str(fps),
            "-bf", "0", "-movflags", "+faststart", "-map_metadata", "-1", "-fflags", "+bitexact",
            "-flags:v", "+bitexact", "-flags:a", "+bitexact", str(path)]  # fmt: skip
    raw = b"".join(frame_image(i, fps).tobytes() for i in range(frames))
    subprocess.run(cmd, input=raw, check=True)  # noqa: S603 -- fixed argv, bundled ffmpeg


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    truth: dict[str, object] = {}
    for name, fps, frames, with_audio in (
        ("counter_30fps_audio.mp4", 30, 90, True),
        ("counter_24fps.mp4", 24, 48, False),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            audio = None
            if with_audio:
                audio = Path(tmp) / "tone.wav"
                tone_wav(audio, seconds=frames / fps, fps=fps, beep_frames=(30, 44))
            write_clip(out_dir / name, fps=fps, frames=frames, audio=audio)
        truth[name] = {
            "fps": fps,
            "frames": frames,
            "size": [WIDTH, HEIGHT],
            "bar_h": BAR_H,
            "audio": with_audio,
            "beep_frames": [30, 44] if with_audio else None,
            "boxes_half_open": {str(i): boxes(i, fps) for i in range(frames)},
        }
    (out_dir / "truth.json").write_text(json.dumps(truth, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "fixtures" / "clips")
