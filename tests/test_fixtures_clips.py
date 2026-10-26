"""The synthetic clips are what truth.json says, and the generator reproduces them: byte for byte from run to run,
and frame for frame against the committed clips (container bytes may differ across ffmpeg builds; pixels must not)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from scripts.make_synthetic_clips import main as make_clips

CLIPS = Path(__file__).resolve().parent.parent / "fixtures" / "clips"


def _framemd5(path: Path, *, decode: bool) -> list[str]:
    """One line per video frame: the packet's MD5 (``decode=False``) or the decoded picture's."""
    copy = [] if decode else ["-c", "copy"]
    out = subprocess.run(  # noqa: S603 -- fixed argv, bundled ffmpeg
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            *copy,
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line and not line.startswith("#")]


def _video_packets(path: Path) -> int:
    return len(_framemd5(path, decode=False))


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
    make_clips(tmp_path / "one")
    make_clips(tmp_path / "two")
    assert (tmp_path / "one" / "truth.json").read_bytes() == (CLIPS / "truth.json").read_bytes()
    for name in ("counter_30fps_audio.mp4", "counter_24fps.mp4"):
        one, two = (hashlib.sha256((tmp_path / d / name).read_bytes()).digest() for d in ("one", "two"))
        assert one == two
        assert _framemd5(tmp_path / "one" / name, decode=True) == _framemd5(CLIPS / name, decode=True)
