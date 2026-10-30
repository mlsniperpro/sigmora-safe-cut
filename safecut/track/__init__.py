"""SAM 3.1 tracking: the proxy clip, one sweep per concept, linking into tracks (WP1)."""

from __future__ import annotations

from pathlib import Path


def run(job_dir: Path, *, replay: bool = False) -> Path:
    """The ``track`` stage (see :mod:`safecut.track.stage`); imported lazily so ``prepare`` can use the axes."""
    from safecut.track.stage import run as run_stage  # noqa: PLC0415 -- lazy: the stage pulls in the Meta client

    return run_stage(job_dir, replay=replay)
