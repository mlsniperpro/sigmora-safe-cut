"""``prepare`` against ffmpeg's own output: every prepared frame is identified by the source frame it shows.

Each synthetic source frame paints its index in 8 black/white bars, so decoding the prepared clip tells which
source frame ffmpeg's ``fps`` filter kept in each slot; ``job.times`` must name exactly that frame's time.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import pytest

from safecut import config, prepare
from safecut.contracts import Intake, Job, dump, load
from safecut.track import media

W, H, BARS = 128, 64, 8


def _frame(index: int) -> bytes:
    img = np.zeros((H, W, 3), dtype=np.uint8)
    for bit in range(BARS):
        if index >> bit & 1:
            img[:, bit * (W // BARS) : (bit + 1) * (W // BARS)] = 255
    return img.tobytes()


def _decode_indices(path: Path) -> list[int]:
    gen = imageio_ffmpeg.read_frames(str(path))
    meta = next(gen)
    w, h = meta["size"]
    out: list[int] = []
    for raw in gen:
        img = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
        bar = w // BARS
        out.append(
            sum(1 << b for b in range(BARS) if img[:, b * bar + bar // 4 : (b + 1) * bar - bar // 4].mean() > 127)
        )
    return out


def make_clip(path: Path, times: list[float], *, audio_offset: float | None = None, video_offset: float = 0.0) -> Path:
    """A VFR H.264 MP4 whose frame ``k`` shows ``k`` and starts at ``video_offset + times[k]``."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    expr = "+".join(f"eq(N,{k})*{t + video_offset:.6f}" for k, t in enumerate(times))
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "1000",
           "-i", "-"]  # fmt: skip
    if audio_offset is not None:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={times[-1] + 0.5}"]
    cmd += ["-vf", f"setpts='({expr})/TB'", "-fps_mode", "passthrough", "-enc_time_base", "1/90000", "-map", "0:v"]
    if audio_offset is not None:
        cmd += ["-map", "1:a", "-c:a", "aac", "-af", f"adelay={audio_offset * 1000:.0f}:all=1"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p", "-g", "1",
            "-video_track_timescale", "90000", str(path)]  # fmt: skip
    subprocess.run(cmd, input=b"".join(_frame(k) for k in range(len(times))), check=True)  # noqa: S603
    return path


def _check(clip: Path, job_dir: Path) -> Job:
    job = load(prepare.prepare(clip, job_dir), Job)
    source = media.packets(clip)
    shown = _decode_indices(job_dir / prepare.PREPARED)
    assert len(shown) == job.frames == media.frame_count(job_dir / prepare.PREPARED)
    for n, k in enumerate(shown):
        assert job.times[n] == float(source.seconds(k)), (n, k)
    return job


def test_jittery_30fps_keeps_every_frame(tmp_path: Path) -> None:
    jitter = [0.0015 * ((k * 7) % 3 - 1) for k in range(45)]
    times = [max(0.0, k / 30 + j) for k, j in enumerate(jitter)]
    job = _check(make_clip(tmp_path / "jitter.mp4", times), tmp_path / "j_jitter")
    assert job.fps == 30
    # Every frame is kept (each rounds to its own tick); only the last may fall in a slot ffmpeg doesn't emit.
    assert set(range(44)) <= set(_decode_indices(tmp_path / "j_jitter" / prepare.PREPARED))


def test_60fps_halves_to_30(tmp_path: Path) -> None:
    job = _check(make_clip(tmp_path / "s60.mp4", [k / 60 for k in range(60)]), tmp_path / "j_60")
    assert job.fps == 30
    assert job.frames in (29, 30, 31)


def _packets(times: list[float]) -> media.Packets:
    return media.Packets(time_base=Fraction(1, 100), pts=tuple(round(t * 100) for t in times), last_duration=10)


@pytest.mark.parametrize(
    ("times", "want"),
    [
        ([0.0, 0.10, 0.26, 0.40], [0.0, 0.10, 0.10, 0.26]),  # T6a: 0.26 → slot 3, slot 2 repeats 0.10
        ([0.0, 0.10, 0.31, 0.40], [0.0, 0.10, 0.10, 0.31]),  # T6b
        ([0.0, 0.03, 0.04, 0.09, 0.10, 0.40], [0.04, 0.10, 0.10, 0.10]),  # T6c: slot 0 keeps its last frame
    ],
)
def test_t6_frame_times(times: list[float], want: list[float]) -> None:
    assert prepare.frame_times(_packets(times), 10, 4) == pytest.approx(want, abs=1e-12)


def test_gappy_vfr_matches_ffmpeg(tmp_path: Path) -> None:
    times = [0.0, 0.03, 0.04, 0.09, 0.10, 0.26, 0.40, 0.50, 0.71, 0.80, 0.90, 1.0, 1.05, 1.31, 1.40]
    job = _check(make_clip(tmp_path / "gappy.mp4", times), tmp_path / "j_gappy")
    assert any(a == b for a, b in zip(job.times, job.times[1:], strict=False))  # a gap repeated a frame


def test_t9_late_video_start_is_normalised(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "t9.mp4", [k / 30 for k in range(30)], audio_offset=0.0, video_offset=0.1)
    job = _check(clip, tmp_path / "j_t9")
    assert job.audio
    video = media.packets(tmp_path / "j_t9" / prepare.PREPARED)
    assert video.start == 0
    assert abs(float(media.decoded_start(tmp_path / "j_t9" / prepare.PREPARED, "a:0"))) < 0.001  # one origin


def test_aac_priming_is_not_mistaken_for_an_audio_lead() -> None:
    """The fixture's first AAC packet sits at -1024 samples (priming the decoder drops): no trim is due."""
    found = prepare.probe(Path("fixtures/clips/counter_30fps_audio.mp4"))
    assert found.audio is not None
    assert found.audio.start < 0
    assert found.audio_start == 0
    assert prepare._audio_filter(found.video, found.audio_start) == "asetpts=PTS-STARTPTS"  # pyright: ignore[reportPrivateUsage] -- the filter is the unit


def test_an_edit_list_trim_keeps_audio_on_the_first_shown_frame(tmp_path: Path) -> None:
    """A stream-copy trim (``-ss 0.5 -c copy``, as phones' trims do) keeps the GOP's earlier frames as hidden
    packets before the edit list's start. The clock starts at the first *decoded* frame, so nothing delays the
    audio and the hidden frames aren't counted (§5b steps 2–3)."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    whole = tmp_path / "whole.mp4"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30",
           "-i", "-", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p", "-g", "30", "-bf", "0",
           "-c:a", "aac", "-shortest", str(whole)]  # fmt: skip
    subprocess.run(cmd, input=b"".join(_frame(k) for k in range(90)), check=True)  # noqa: S603 -- fixed argv
    trimmed = tmp_path / "trimmed.mp4"
    trim = [ffmpeg, "-y", "-loglevel", "error", "-ss", "0.5", "-i", str(whole), "-c", "copy", str(trimmed)]
    subprocess.run(trim, check=True)  # noqa: S603 -- fixed argv
    assert media.packets(trimmed).count == 90  # the hidden packets are there...
    found = prepare.probe(trimmed)
    assert (found.video.count, found.video.start, found.fps) == (75, 0, 30)  # ...and not counted
    assert found.audio_start is not None
    assert prepare._audio_filter(found.video, found.audio_start) == "asetpts=PTS-STARTPTS"  # pyright: ignore[reportPrivateUsage] -- the filter is the unit
    job = load(prepare.prepare(trimmed, tmp_path / "j_trim"), Job)
    shown = _decode_indices(tmp_path / "j_trim" / prepare.PREPARED)
    assert job.frames == len(shown) == 75
    assert shown[0] == 15
    assert job.times == [n / 30 for n in range(75)]
    head = [ffmpeg, "-loglevel", "error", "-i", str(tmp_path / "j_trim" / prepare.PREPARED), "-map", "0:a:0",
            "-t", "0.2", "-f", "s16le", "-ac", "1", "-"]  # fmt: skip
    pcm = subprocess.run(head, capture_output=True, check=True).stdout  # noqa: S603 -- fixed argv
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    assert len(samples) > 0
    assert np.sqrt(np.mean(samples**2)) > 1000  # the tone plays from the first shown frame, not after 0.5 s of silence


def test_fixture_clips_and_keyframes(tmp_path: Path) -> None:
    truth = json.loads(Path("fixtures/clips/truth.json").read_text())
    for name, spec in truth.items():
        job_dir = tmp_path / name.removesuffix(".mp4")
        job = load(prepare.prepare(Path("fixtures/clips") / name, job_dir), Job)
        assert (job.fps, job.frames, job.audio) == (spec["fps"], spec["frames"], spec["audio"])
        assert (job.width, job.height) == tuple(spec["size"])
        assert job.source == name
        assert job.job_id == job_dir.name
        assert job.source_sha256 == prepare.sha256_file(Path("fixtures/clips") / name)
        keyframes = sorted(p.name for p in (job_dir / prepare.KEYFRAMES).iterdir())
        assert keyframes == [f"{f:06d}.jpg" for f in range(0, job.frames, job.fps)]


def test_long_edge_is_capped_and_even(tmp_path: Path) -> None:
    clip = tmp_path / "wide.mp4"
    media.run(["-y", "-f", "lavfi", "-i", "testsrc=size=1921x1081:rate=10:duration=1", "-c:v", "libx264",
               "-pix_fmt", "yuv444p", str(clip)])  # fmt: skip
    job = load(prepare.prepare(clip, tmp_path / "j_wide"), Job)
    assert job.width == 1280
    assert job.height % 2 == 0
    assert job.height == 720


def test_portrait_rotation_is_applied(tmp_path: Path) -> None:
    clip = tmp_path / "rot.mp4"
    media.run(["-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=1", "-c:v", "libx264",
               "-metadata:s:v:0", "rotate=90", str(clip)])  # fmt: skip
    job = load(prepare.prepare(clip, tmp_path / "j_rot"), Job)
    assert (job.width, job.height) in ((180, 320), (320, 180))


def test_too_large_is_refused_before_transcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(prepare.PrepareError) as err:
        prepare.prepare(Path("fixtures/clips/counter_24fps.mp4"), tmp_path / "j")
    assert err.value.reason == "too_large"
    assert err.value.size_bytes is not None
    assert not (tmp_path / "j" / prepare.PREPARED).exists()


def test_too_long_is_refused(tmp_path: Path) -> None:
    clip = tmp_path / "long.mp4"
    media.run(["-y", "-f", "lavfi", "-i", "color=size=16x16:rate=1:duration=61", "-c:v", "libx264", str(clip)])
    with pytest.raises(prepare.PrepareError) as err:
        prepare.prepare(clip, tmp_path / "j")
    assert err.value.reason == "too_long"
    assert err.value.duration_s is not None
    assert err.value.duration_s > 60


def test_exactly_sixty_seconds_is_allowed(tmp_path: Path) -> None:
    clip = tmp_path / "sixty.mp4"
    media.run(["-y", "-f", "lavfi", "-i", "color=size=16x16:rate=2:duration=60", "-c:v", "libx264", str(clip)])
    job = load(prepare.prepare(clip, tmp_path / "j"), Job)
    assert job.fps == 2


def test_unreadable_and_videoless_uploads(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video at all")
    with pytest.raises(prepare.PrepareError) as err:
        prepare.prepare(junk, tmp_path / "j1")
    assert err.value.reason == "bad_media"
    audio_only = tmp_path / "audio.m4a"
    media.run(["-y", "-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", str(audio_only)])
    with pytest.raises(prepare.PrepareError) as err:
        prepare.prepare(audio_only, tmp_path / "j2")
    assert err.value.reason == "bad_media"


def test_run_finds_the_one_upload(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_run"
    with pytest.raises(prepare.PrepareError) as err:
        prepare.run(job_dir)
    assert err.value.reason == "no_source"
    (job_dir / prepare.SOURCE_DIR).mkdir(parents=True)
    (job_dir / prepare.SOURCE_DIR / "clip.mp4").write_bytes(Path("fixtures/clips/counter_24fps.mp4").read_bytes())
    job = load(prepare.run(job_dir, replay=True), Job)
    assert job.source == "clip.mp4"
    assert job.consented is False


def test_run_copies_the_intake(tmp_path: Path) -> None:
    job_dir = tmp_path / "j_intake"
    (job_dir / prepare.SOURCE_DIR).mkdir(parents=True)
    (job_dir / prepare.SOURCE_DIR / "clip.mp4").write_bytes(Path("fixtures/clips/counter_24fps.mp4").read_bytes())
    when = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    dump(Intake(source="clip.mp4", created_at=when, consented=True), job_dir / prepare.INTAKE)
    job = load(prepare.run(job_dir), Job)
    assert (job.created_at, job.consented) == (when, True)
    dump(Intake(source="other.mp4", created_at=when), job_dir / prepare.INTAKE)
    with pytest.raises(prepare.PrepareError) as err:
        prepare.run(job_dir)
    assert err.value.reason == "no_source"


def test_job_fps_rounds_half_up() -> None:
    packets = media.Packets(time_base=Fraction(1, 1000), pts=tuple(range(0, 1000, 40)), last_duration=40)
    assert prepare.job_fps(packets) == 25
    fast = media.Packets(time_base=Fraction(1, 1000), pts=tuple(range(0, 1000, 8)), last_duration=8)
    assert prepare.job_fps(fast) == 30
    single = media.Packets(time_base=Fraction(1, 1000), pts=(0,), last_duration=0)
    assert prepare.job_fps(single) == 1
