TESTED_COMMIT: 2012ed0

# Break-it log

Recorded at the wind-down (2026-10-27 ~03:40 UTC). Each line names the head it ran on. The successor must re-run the soak and a fresh clone at the final head before relying on this file.

- **Full suite at 2012ed0** (`bash .agent/win/SAFECUT-WP0/checks.sh`): ruff and ruff format clean, pyright strict 0 errors, `pytest -m "not live"` 432 passed. It includes:
  - the chaos property (random failure sequences keep the ledger equal to Σ cost.jsonl);
  - the fuzz properties: the SSE decoder; the SSE line splitter against a reference splitter over random chunkings (this caught a real `\r`/`\n` edge, now fixed); the error classifier; contract loaders; meters;
  - the replay e2e of probes a–h, where the replay server mints a unique SAM response id per call and the test asserts every created response is deleted;
  - failure injection for audits #5–#11: lost ledger acks; cancels and disk faults around uploads; orphan copies with failing deletes; a saturated executor during a cancelled settle; unreadable response logs; malformed model output; a failed open-weight batch.
- **Fresh clone at 5c72c49** (the code differs from 2012ed0 only in the audit #11 fixes): clone, `uv sync --locked`, ruff, pyright, then `pytest -m "not live"` → 425 passed in 49.5 s, 67 s from clone to green on 4 CPUs, with a soak running alongside.
- **Clip determinism at 5c72c49**: `make_synthetic_clips.py` on all CPUs and under `taskset -c 0` gave identical sha256 for every file, matching the committed `fixtures/clips/`. The clips were regenerated in 5c72c49 because the EgoBlur pin moves opencv to 4.14; truth.json is byte-identical.
- **Soak** (`HYPOTHESIS_PROFILE=soak`, 20,000 examples per property): every run in this session was stopped as stale when a new fix landed, the last at 5c72c49 after ~8 min with no failure. UNFINISHED: run it to completion (40+ min) at the final head.
