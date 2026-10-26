# SAFECUT-WP0 handoff

Branch `wp0-foundation`, PR #3 (the only PR for this session). Gate: `bash .agent/win-gate.sh SAFECUT-WP0`.

## Commands
- Every subagent launched with the Agent tool sets model `sonnet` and effort `high` (owner rule). Integration, self-review, deciding which findings are real, and the gate stay in the main session; verify any subagent finding before acting on it.
- Push when a substantial task is complete and green (a set of audit findings fixed and tested, a feature slice working, a soak or break-it pass recorded, the gate run). Don't wait for any timer. Each push is a meaningful, squashed commit set: never empty, format-only or "wip". Exactly one PR.
- Never sit idle and never end a turn to wait. While a subagent, audit, soak or build runs, keep working on the next item below. The only reasons to stop: the API usage limit, or the /goal being met.
- Checks: `bash .agent/win/SAFECUT-WP0/checks.sh` (about 60 s). Soak: `HYPOTHESIS_PROFILE=soak uv run pytest -m "not live" -q` in the background; write its PID to `.agent/win/SAFECUT-WP0/pids` and clear it when done.
- Live probes, once `MODEL_API_KEY` exists: `uv run python -m scripts.probes.probes all`, then `uv run python -m scripts.probes.trim`, then update docs/API-NOTES-WP0.md §13.3 with the measured numbers and put the total from `fixtures/probes/cost.jsonl` in the PR. Hero clip: add `--clip=<path>` (probes b and d).

## State at WIND DOWN (2026-10-26 ~17:25 UTC, owner's order)
- The last commit is an **uncommitted-at-the-time fix set pushed as-is**, so nothing is lost. **The suite is RED at this head:** the transport's `guard_body` now requires `store: false` (audit #2 M5), and tests that send store-less bodies (tests/test_chaos.py, some tests in test_meta_client.py) still need `"store": False` added to their bodies. Fix those tests first, then run checks.sh.
- In this last commit (from audit #2 and the code-review skill, not yet tested):
  - files.py rewritten: per-name locks, re-read and write of the index under one lock, an orphan recorded on cancellation, cleanup calls skip the breaker;
  - the breaker's trial is tracked per call, and a cancel during backoff frees it;
  - streamed refusals are billed at their usage;
  - httpx non-transport errors are typed;
  - the count call is off the breaker;
  - dotted config params are classified;
  - one shared `ensure_standard_model`;
  - `trust_env=False`, and `base_url` is validated in `MetaClient`;
  - config: aware datetimes, no inf/nan, token models must be priced;
  - synthetic clips are regenerated with `-threads 1` (CPU-independent bytes).
- Still open from audit #2:
  - #6: probe f role calls from SoM keyframes are not implemented. Add them, or list them in BLOCKED.md and fix docs/API-NOTES-WP0.md 13.2 ("b, d and f" should be "b and d").
  - #8: the API-NOTES 13.4 line on HTTP errors should say a 504 or slow 5xx is charged.
  - #9: probes.run should catch Exception per probe; `_video_question` should catch MetaError around `output_text`; probe_d should unlink the WAV in a finally.
  - New tests are needed for each audit #2 / code-review fix.
- Then: record audit #2 plus the code-review findings in reaudit.md, run audit #3 and #4 (two clean in a row), redo the soak and break-it.md at the final head, update PR #3's status line, and get the gate to PASS.
- Blocked (owner): MODEL_API_KEY, clips bucket, repo public (also fixes CI: no runner), BASETEN_API_KEY. See BLOCKED.md.
- When PR #1 (PRE-A) merges: fold docs/API-NOTES-WP0.md into docs/API-NOTES.md as §13.
