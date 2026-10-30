"""Stand-in stages for API, pipeline and eval tests: each copies its contract file from the cross-checked example
job (``fixtures/contracts/j_example``), except ``decide``, which runs the real WP3 stage on those inputs. They test
the orchestration around the stages, never the stages themselves."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from safecut.decide import run as decide
from safecut.stages import Stage

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "fixtures" / "contracts" / "j_example"
CLIP = ROOT / "fixtures" / "clips" / "counter_24fps.mp4"


def fake_runner(stage: Stage) -> Callable[..., Path]:
    def run(job_dir: Path, *, replay: bool = False) -> Path:
        out = job_dir / stage.output
        if stage.name == "prepare":
            data = json.loads((EXAMPLE / "job.json").read_text())
            data["job_id"] = job_dir.name
            out.write_text(json.dumps(data))
            shutil.copyfile(CLIP, job_dir / data["prepared"])
        elif stage.name == "render":
            shutil.copyfile(CLIP, out)
        elif stage.name == "decide":
            return decide(job_dir, replay=replay)
        else:
            shutil.copyfile(EXAMPLE / stage.output, out)
            if stage.name == "receipt":
                (job_dir / "receipt.html").write_text("<!doctype html><title>receipt</title>")
        return out

    return run
