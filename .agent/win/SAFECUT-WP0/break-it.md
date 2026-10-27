TESTED_COMMIT: ee0fc9a

# Break-it log (every run below is at ee0fc9a, the current code)

- **Soak** (`HYPOTHESIS_PROFILE=soak uv run pytest -m "not live" -q`, 20,000 examples per property): **460 passed in 44 min 37 s**, no failure. Started 14:45 UTC, finished ~15:30 UTC on 2026-10-27. Covers:
  - the chaos property (random failure sequences keep the ledger equal to Σ cost.jsonl);
  - the fuzz properties: the SSE decoder; the SSE line splitter against a reference splitter over random chunkings; the error classifier; contract loaders and models; meters; Retry-After;
  - every example-based test below.
- **Fresh clone**: clone, `uv sync --locked`, ruff, pyright strict (0 errors), `pytest -m "not live"` → 460 passed in 75 s, 105 s from clone to green on 4 CPUs (two read-only auditors were running alongside).
- **Clip determinism**: `make_synthetic_clips.py` on all CPUs and under `taskset -c 0` gives identical sha256 for every file, and matches the committed `fixtures/clips/` byte for byte.
- **Replay e2e**: probes a–h run against mocked Meta and Baseten APIs (`tests/test_probes_replay.py`, `tests/test_audit9/12/14/16.py`):
  - the replay server mints a unique SAM response id per call, and the tests assert every created response is deleted, on success and failure paths;
  - probe c's 60 s / 180 s length check runs;
  - probe h's 8/9-image limit check runs.
- **Failure injection** (tests/test_audit5–16.py):
  - lost ledger acks; ledger faults on a retry; a saturated executor during cancelled settles; repeated cancels;
  - cancels and disk faults around uploads; fast 5xx and late-landing upload copies; orphan reconciliation; the ledger down during cleanup;
  - queued calls under a tight cap; proxy refusals; failing multipart factories;
  - unreadable or unwritable response logs; open SAM streams during a delete sweep;
  - malformed and missing model boxes; failed open-weight batches;
  - parser errors and status outages inside probes.
- **Independent stress harnesses** run by auditors #14–#17: 150 to 750 seeds each, with 2–14 concurrent jobs sharing a ledger and a breaker, random 5xx/429/504/eof/timeout/connect outcomes, and single and double cancels. In every seed the ledger equalled Σ cost.jsonl, no reservation stayed open, and no breaker trial slot or semaphore leaked (scripts in the session scratchpad; results in reaudit.md).
