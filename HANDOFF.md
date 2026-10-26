# HANDOFF: SAFECUT-WP6 (web app)

Branch `wp6-web` (PR into `main`). Scope: `web/`, `.agent/win/SAFECUT-WP6/`, this file. Spec: `docs/work-packages/WP6.md` and PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges).

## Commands

- Checks: `bash .agent/win/SAFECUT-WP6/checks.sh` (install, lint, typecheck, test, build, replay e2e).
- Gate: `bash .agent/win-gate.sh SAFECUT-WP6`. Done = `GATE: PASS` on the pushed HEAD after the last code change, or past 2026-11-04T18:00Z.
- Subagents: every Agent/Task launch sets model `sonnet` and effort `high` (owner rule). Integration, self-review, deciding which findings are real, and the gate stay in the main session. Verify every subagent finding before acting on it.
- Pushing: push when a substantial task is complete and green (an audit-findings batch fixed and tested, a feature slice working, a soak/break-it pass recorded, the gate run). No timer. Squash first: no empty, format-only or "wip" commits. Exactly one PR.
- Never idle: while a subagent, audit, soak or build runs, work on the next item below. Never end a turn with "will push at HH:MM" or "waiting for X". The only reasons to stop: the API usage limit, or the /goal being met.
- Never edit `.agent/win-gate.sh`; never push to `main` (the one gate commit is done).

## Next items

See `.agent/win/SAFECUT-WP6/WIN-CHECKLIST.md` (every open `- [ ]` line).
