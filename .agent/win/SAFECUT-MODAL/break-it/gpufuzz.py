"""GPU fault fuzz: any sequence of GPU faults, the audit still completes and names exactly the detector that ran.

Hypothesis draws a sequence of per-call faults (none, timeout, error, stale Volume) and a weights or GPU problem,
injects a 3-frame leak half the time, and runs the real audit (and receipt) against the fake Modal call of
``tests/test_audit_gpu.py``. Invariants: ``validate_job_dir`` passes, ``unresolved == 0``, and EgoBlur is named
exactly when every scan of the final audit was answered by the GPU (``gpu.json`` agrees). Usage, from the repo root:
``EXAMPLES=300 uv run python .agent/win/SAFECUT-MODAL/break-it/gpufuzz.py``
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402 -- after the sys.path insert above, on purpose

from safecut.audit import GPU_RECORD, detectors  # noqa: E402 -- after the sys.path insert above, on purpose
from safecut.audit import run as audit_run  # noqa: E402 -- after the sys.path insert above, on purpose
from tests.test_audit_gpu import (  # noqa: E402 -- after the sys.path insert above, on purpose
    FACE,
    PLATE,
    FakeModal,
    audit_of,
    prepared,
    sealed,
    server,
    settings_for,
)
from tests.test_audit_loop import drop  # noqa: E402 -- after the sys.path insert above, on purpose

EXAMPLES = int(os.environ.get("EXAMPLES", "200"))
FAULTS = st.lists(st.sampled_from([None, None, "timeout", "error", "stale"]), max_size=6)


def need(ok: bool, what: object) -> None:
    """A broken invariant stops the run, naming it (``assert`` would vanish under ``python -O``)."""
    if not ok:
        raise SystemExit(f"BROKEN: {what}")


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck), derandomize=False)
@given(faults=FAULTS, problem=st.sampled_from(["none", "none", "no_weights", "altered", "no_gpu"]), leak=st.booleans())
def check(faults: list[str | None], problem: str, leak: bool) -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
        root = Path(tmp)
        weights = root / "models" / "egoblur"
        weights.mkdir(parents=True)
        import hashlib  # noqa: PLC0415 -- imported in the test that uses it

        pins = {}
        for name in (FACE, PLATE):
            (weights / name).write_bytes(name.encode())
            pins[name] = hashlib.sha256(name.encode()).hexdigest()
        mp.setattr(detectors, "EGOBLUR_GEN2_SHA256", pins)
        if problem == "altered":
            (weights / PLATE).write_bytes(b"truncated")
        folder = root / "empty" if problem == "no_weights" else weights
        job_dir = prepared(root)
        if leak:
            drop(job_dir, "i_2", {30, 31, 32})
        settings_ = settings_for(root)
        fake = FakeModal(server(job_dir, folder, gpu_name=None if problem == "no_gpu" else "NVIDIA L4"), faults)
        audit_run(job_dir, replay=True, settings=settings_, gpu_call=fake.call, gpu_commit=fake.commit)
        audit = audit_of(job_dir)
        record = json.loads((job_dir / GPU_RECORD).read_text())
        receipt = sealed(job_dir, settings_)  # validate_job_dir inside
        need(audit.unresolved == 0, "audit.unresolved == 0")
        need(
            record["ran"] == audit.egoblur.model == receipt.audit.auditor,
            'record["ran"] == audit.egoblur.model == receipt.audit.auditor',
        )
        need(
            receipt.audit.auditor_device == audit.egoblur.device, "receipt.audit.auditor_device == audit.egoblur.device"
        )
        if audit.egoblur.model == "egoblur-gen2":
            need(record["fallback"] is None, 'record["fallback"] is None')
            need(audit.egoblur.device == "cuda:NVIDIA L4", 'audit.egoblur.device == "cuda:NVIDIA L4"')
            need(problem == "none", 'problem == "none"')
        else:
            need(record["fallback"], 'record["fallback"]')
            need(
                (audit.egoblur.device, audit.egoblur.plates) == ("cpu", None),
                '(audit.egoblur.device, audit.egoblur.plates) == ("cpu", None)',
            )


if __name__ == "__main__":
    check()
    print(f"GPUFUZZ: PASS ({EXAMPLES} examples: every audit completed, named the detector that ran, receipts verify)")
