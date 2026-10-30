"""Speech (WP2 step 1): Muse Voice Transcribe → ``transcript.json``, with the Muse Spark 1.2 fallback."""

from __future__ import annotations

from pathlib import Path


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The ``transcribe`` stage (see :mod:`safecut.speech.stage`)."""
    from safecut.speech.stage import run as run_stage  # noqa: PLC0415 -- lazy: the stage pulls in the Meta client

    return run_stage(job_dir, replay=replay)
