# SAFECUT-WP0 handoff

Branch `wp0-foundation`, PR #3 (the only PR for this session). Gate: `bash .agent/win-gate.sh SAFECUT-WP0`.

## Commands
- Every subagent launched with the Agent tool sets model `sonnet` and effort `high` (owner rule). Integration, self-review, deciding which findings are real, and the gate stay in the main session; verify any subagent finding before acting on it.
- Push when a substantial task is complete and green (a set of audit findings fixed and tested, a feature slice working, a soak or break-it pass recorded, the gate run). Don't wait for any timer. Each push is a meaningful, squashed commit set: never empty, format-only or "wip". Exactly one PR.
- Never sit idle and never end a turn to wait. While a subagent, audit, soak or build runs, keep working on the next item below. The only reasons to stop: the API usage limit, or the /goal being met.
- Checks: `bash .agent/win/SAFECUT-WP0/checks.sh`.

## Next
See the open items in WIN-CHECKLIST.md.
