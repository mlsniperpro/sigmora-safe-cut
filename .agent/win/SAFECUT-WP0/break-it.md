TESTED_COMMIT: 8cc543c

# Break-it log

Recorded at wind-down (2026-10-26 ~20:05 UTC). Some runs below were at earlier heads, as each line says. The successor must re-run the soak and a fresh clone at the final head before relying on this file.

- **Full suite at 8cc543c** (`bash .agent/win/SAFECUT-WP0/checks.sh`): ruff and ruff format clean, pyright strict 0 errors, `pytest -m "not live"` 372 passed. Included in that run:
  - the chaos property (`tests/test_chaos.py`: random failure sequences keep the ledger equal to Σ cost.jsonl, within the attempt bounds);
  - the fuzz properties (`tests/test_fuzz.py`: SSE decoder, the error classifier, now including the 5xx retry classes, contract loaders, meters, Retry-After);
  - the replay e2e (`tests/test_probes_replay.py`: probes a–h against mocked Meta and Baseten);
  - failure injection for audit #5 (`tests/test_audit5.py`: a lost ledger ack, a cancel or disk fault between an upload and its record, a cost.jsonl write fault, orphan reconciliation, replay refusal, SAM response deletion with 200/404/400).
- **Fresh clone at 44a24e5**: clone, `uv sync --locked`, `pytest -m "not live"` → 293 passed in 48.9 s, 53 s from clone to green on 4 CPUs. NOT yet repeated at 8cc543c.
- **Clip determinism at 44a24e5**: `make_synthetic_clips.py` on all CPUs and under `taskset -c 0` gave identical sha256 for every file, matching `fixtures/clips/`. Since 8cc543c the test also compares the decoded-frame MD5s with the committed clips.
- **Soak (`HYPOTHESIS_PROFILE=soak`, 20,000 examples per property)**: started at 8cc543c and stopped at wind-down after about 5 minutes, with no failure seen. UNFINISHED: re-run it to completion (about 40+ min) at the final head.
