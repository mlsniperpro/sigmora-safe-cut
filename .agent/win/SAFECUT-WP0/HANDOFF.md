# SAFECUT-WP0 handoff

Branch `wp0-foundation`, PR #3 (the only PR for this session). Gate: `bash .agent/win-gate.sh SAFECUT-WP0`.

## Commands
- Every subagent launched with the Agent tool sets model `sonnet` and effort `high` (owner rule). Integration, self-review, deciding which findings are real, and the gate stay in the main session; verify any subagent finding before acting on it.
- Push when a substantial task is complete and green (a set of audit findings fixed and tested, a feature slice working, a soak or break-it pass recorded, the gate run). Don't wait for any timer. Each push is a meaningful, squashed commit set: never empty, format-only or "wip". Exactly one PR.
- Never sit idle and never end a turn to wait. While a subagent, audit, soak or build runs, keep working on the next item below. The only reasons to stop: the API usage limit, or the /goal being met.
- Checks: `bash .agent/win/SAFECUT-WP0/checks.sh` (about 60 s). Soak: `HYPOTHESIS_PROFILE=soak uv run pytest -m "not live" -q` in the background; write its PID to `.agent/win/SAFECUT-WP0/pids` and clear it when done.
- Live probes, once `MODEL_API_KEY` exists: `uv run python -m scripts.probes.probes all`, then `uv run python -m scripts.probes.trim`, then update docs/API-NOTES-WP0.md §13.3 with the measured numbers and put the total from `fixtures/probes/cost.jsonl` in the PR. Hero clip: add `--clip=<path>` (probes b and d).

## State (2026-10-26 ~17:10 UTC)
- Done: scaffold, config, contracts, Meta client (with audit #1 fixed), probes a–h with replay e2e, fixtures, API notes, ARCHITECTURE sync, official-guide reconciliation, fuzz and chaos property tests.
- Blocked (owner): MODEL_API_KEY, clips bucket, repo public (also fixes CI: no runner), BASETEN_API_KEY. See BLOCKED.md.
- Next: audit #2 → fix → audit #3 (two clean in a row), soak and break-it at the final head, code-review skill, gate PASS, PR status line.
- When PR #1 (PRE-A) merges: fold docs/API-NOTES-WP0.md into docs/API-NOTES.md as §13.
