"""Copy the live probe responses into the per-model fixture folders as ``live-*`` twins.

Run after ``scripts/probes/probes.py``. Only responses to synthetic clips exist under
``fixtures/probes/`` (the probes never send anything else), so the copies are safe to publish.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: (source under fixtures/probes, destination under fixtures)
COPIES: tuple[tuple[str, str], ...] = (
    ("b/sam-red_square.events.json", "sam/live-red_square.events.json"),
    ("b/sam-face.events.json", "sam/live-face_zero_match.events.json"),
    ("d/asr.response.json", "asr/live-tone.json"),
)


def trim(root: Path = ROOT) -> list[str]:
    copied: list[str] = []
    for src_rel, dst_rel in COPIES:
        src = root / "fixtures" / "probes" / src_rel
        if src.exists():
            json.loads(src.read_text())  # refuse to copy anything that isn't valid JSON
            dst = root / "fixtures" / dst_rel
            shutil.copyfile(src, dst)
            copied.append(dst_rel)
    scene = sorted((root / "fixtures" / "probes" / "c").glob("probe_c-*.response.json"))
    if scene:
        events = [{"type": "response.completed", "response": json.loads(scene[0].read_text())}]
        dst = root / "fixtures" / "muse" / "live-scene.events.json"
        dst.write_text(json.dumps(events, indent=1) + "\n")
        copied.append("muse/live-scene.events.json")
    return copied


if __name__ == "__main__":
    done = trim()
    print("\n".join(done) if done else "no live probe responses yet (run scripts/probes/probes.py first)")
    sys.exit(0)
