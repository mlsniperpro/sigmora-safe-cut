TESTED_COMMIT: 538675a

# Break-it log (every run below is at 538675a, the current code)

- **Soak** (`HYPOTHESIS_PROFILE=soak uv run pytest -m "not live" -q`, 20,000 examples per property): **724 passed in 38 min 24 s**, no failure. Started 11:28 UTC, finished 12:07 UTC on 2026-10-29. Covers:
  - the chaos property (random failure sequences keep the ledger equal to Σ cost.jsonl);
  - the fuzz properties: the SSE decoder; the SSE line splitter against a reference splitter over random chunkings; the error classifier; contract loaders and models; meters; Retry-After;
  - every example-based test below.
- **Fresh clone** (2026-10-29): clone, `uv sync --locked`, ruff, pyright strict (0 errors), `pytest -m "not live"` → 724 passed in 79 s, 97 s from clone to green.
- **Clip determinism** (2026-10-29): `make_synthetic_clips.py` on all CPUs and under `taskset -c 0` gives identical sha256 for every file, and matches the committed `fixtures/clips/` byte for byte.
- **Auditors' harnesses at 538675a and the heads just before it** (audits #73–#79): the Meta client chaos run (900 seeds of 1–4 concurrent streams, every failure kind, absurd usage, cost.jsonl write faults) kept the ledger equal to Σ cost.jsonl with no open reservation. The Files chaos run (1,500 seeds) never returned `all_deleted` with a copy left. The SAM ResponseLog run (150 seeds) never left a stored response untracked. The probe-runner sequences (40 random runs, interrupts, kills and same-second stamps) never lost or misattributed a paid file. The PRE-A writer emulator and the pixel-coverage oracle found no false refusal and no exposure.
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
