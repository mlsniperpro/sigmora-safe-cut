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

## State at wind-down (2026-10-26)

Done and committed: zod contracts aligned with WP0, SafeCutClient + MockBackend, gen-mocks.mjs (82 UI-SPEC fixtures, invariant test), synthetic sample scene + media (web/public/sample), review reducer R1–R33, bar selector, Why drawer model, copy/upload/overlay/polling libs, every screen (/, /try, /jobs/[id], /jobs/[id]/result, 404, error), CSP headers. 629 vitest tests green; lint and typecheck clean; `pnpm build` passed.

Unverified: `web/e2e/replay-e2e.mjs` (Playwright real-browser e2e + axe + screenshots; devDeps playwright@1.63.0 and axe-core). Its first run was cut off by the wind-down: run `cd web && pnpm build && pnpm e2e --shots <dir>` and fix whatever fails.

## Next items (in order)

1. Run the e2e above and fix any failures.
2. Write `web/README.md`: env vars (NEXT_PUBLIC_SAFECUT_API, NEXT_PUBLIC_SAFECUT_HERO_ID, NEXT_PUBLIC_SIGMORA_URL, NEXT_PUBLIC_REPO_URL, NEXT_PUBLIC_SITE_URL, NEXT_PUBLIC_EVAL_URL), the mock-code table (MOCK_CODES), and deploy notes.
3. Update WIN-CHECKLIST.md with evidence, write reaudit.md and break-it.md, and run the gate.
4. Open the ONE PR (wp6-web → main) with screenshots and these sections: Decisions, Self-review, and Requests for other WPs (WP5: eta_s, stage_reason, the result and demo route shapes, and the publish postMessage contract; WP0: removed_by_creator and spot_id on DecisionItem).
5. Run the audit loop per the owner's mandate.
