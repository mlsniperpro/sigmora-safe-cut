"""The synthetic clips are what truth.json says, and the generator reproduces them byte for byte."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from scripts.make_synthetic_clips import main as make_clips

CLIPS = Path(__file__).resolve().parent.parent / "fixtures" / "clips"


def _video_packets(path: Path) -> int:
    out = subprocess.run(  # noqa: S603 -- fixed argv, bundled ffmpeg
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sum(1 for line in out.splitlines() if line and not line.startswith("#"))


@pytest.mark.parametrize("name", ["counter_30fps_audio.mp4", "counter_24fps.mp4"])
def test_clip_matches_truth(name: str) -> None:
    truth = json.loads((CLIPS / "truth.json").read_text())[name]
    meta = next(imageio_ffmpeg.read_frames(str(CLIPS / name)))
    assert tuple(meta["size"]) == tuple(truth["size"])
    assert round(meta["fps"]) == truth["fps"]
    assert (meta.get("audio_codec") is not None) == truth["audio"]
    assert _video_packets(CLIPS / name) == truth["frames"]
    assert truth["frames"] / truth["fps"] <= 3.0
    assert (CLIPS / name).stat().st_size < 64_000


def test_generator_is_deterministic(tmp_path: Path) -> None:
    make_clips(tmp_path)
    for name in ("counter_30fps_audio.mp4", "counter_24fps.mp4", "truth.json"):
        assert (
            hashlib.sha256((tmp_path / name).read_bytes()).digest()
            == hashlib.sha256((CLIPS / name).read_bytes()).digest()
        )
