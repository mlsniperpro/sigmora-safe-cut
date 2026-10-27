# HANDOFF: SAFECUT-WP6 (web app), for a successor with only the repo

## Goal, deadline, PR
- Build WP6 (`docs/work-packages/WP6.md`) to winning quality. Spec detail lives in PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges: `git show origin/pre-b-product:docs/UI-SPEC.md`). Official rules: `docs/OFFICIAL-GUIDE.md`.
- Internal deadline 2026-11-04T18:00Z; official Devpost deadline 2026-11-05 02:00 UTC.
- **Owner milestone: the owner submits on Tue 2026-11-03, so the web app and its part of the submission must be final and pushed by 2026-11-03T12:00Z.**
- Branch `wp6-web`; its one PR is #4 (wp6-web → main).
- Done = `bash .agent/win-gate.sh SAFECUT-WP6` prints `GATE: PASS` on the pushed HEAD.

## Current state (2026-10-27, session_01PMv2tTJFHGsGC5rcjHFfL1 holds the lease)
- Audit round 3 (on 6d860ad) found 0 critical, 0 high, 1 medium and 10 low. All are fixed and tested in the round-3 fix commit, except #4 (does not reproduce; pinned by a test) and #11 (owner env, BLOCKED.md). The table is in reaudit.md.
- On the round-3 fix commit: lint 0 warnings, typecheck, 760 vitest tests (22 files), build, e2e 71/71 (`checks.sh` exit 0).
- The gate still needs two clean full audits in a row on the current code, then a fresh `break-it.md` (fresh clone + FUZZ_RUNS=100000 soak).

## Next steps, in order
1. Run full audit round 4 on HEAD. If it finds anything, fix it and reset CLEAN_AUDITS_IN_A_ROW to 0. Repeat until two consecutive audits find nothing. Then set AUDITED_COMMIT to the last code commit and CLEAN_AUDITS_IN_A_ROW to 2.
2. After the last code change, run the fresh-clone `checks.sh` (`git clone --branch wp6-web` into an empty dir) and the FUZZ_RUNS=100000 agreement soak. Rewrite break-it.md with TESTED_COMMIT set to that commit.
3. Run the gate until it prints `GATE: PASS` on the pushed HEAD. Then post the final status on PR #4, including the gate's last line.
4. If time remains: live deployment (owner sets up Vercel), Safari/Firefox runs.

## Key decisions (why)
- Overlay maps frames with `floor(mediaTime*fps+0.25)`, following UI-SPEC §3.6 (which supersedes WP6 step 4's "via job.times"). It uses requestVideoFrameCallback with a labelled rAF fallback.
- Masks are drawn as their plan box, a superset of the mask, so the preview never under-covers.
- Long chip lists use CSS `content-visibility:auto` rather than JS virtualisation. All 200 chips stay in the DOM, so Tab order holds.
- Results-table percentages round in the unflattering direction (AGENTS rule 9).
- In mock mode the sample hero does not trigger the "real run" demo banner (honesty). A separate sample-data note shows instead.
- Requests use the URL's job ID, never the body's.
- System fonts instead of next/font, so builds have no network dependency.
- `noUnusedLocals` is off in tsconfig because Next's generated `.next/dev/types` fail it. ESLint `no-unused-vars` at max-warnings 0 covers the same ground.

## Commands
- Install: `cd web && pnpm install --frozen-lockfile`
- Check: `pnpm lint && pnpm typecheck && pnpm test && pnpm build && pnpm e2e`. All of these are in `.agent/win/SAFECUT-WP6/checks.sh`.
- Run: `pnpm dev` runs in mock mode. Try `/jobs/job-review-sample`, `/try` (any code; see MOCK_CODES for scripted refusals), and `/jobs/<fixture>`.
- Regenerate: `node scripts/gen-mocks.mjs` and `node scripts/gen-sample.mjs` (needs ffmpeg).
- Gate: `bash .agent/win-gate.sh SAFECUT-WP6` from the repo root.
- Subagents: every subagent you launch must set model "sonnet" and effort "high" (auditors, reviewers, fixers, researchers, soak/log watchers). Keep integration, self-review, judging findings and the gate in this session. Integration, self-review, deciding which findings are real, and the gate stay in the main session; verify any subagent finding before fixing it, never drop one unchecked.
- Pushing: push when a substantial task is complete and green (audit findings fixed and tested, a feature slice working, a soak/break-it pass recorded, the gate run). No timer. Squashed, meaningful commits only (no empty/format-only/wip). Exactly one PR.
- Never idle and never end a turn to wait: while a subagent, audit, soak or build runs, work on the next item and collect results when they arrive. Only two reasons to stop: the API usage limit, or the /goal being met.

## Owner-only blockers
See `.agent/win/SAFECUT-WP6/BLOCKED.md`: the Vercel project and domain (plus `NEXT_PUBLIC_PRIVACY_CONTACT`), hero footage with releases, making the repo public, Baseten credits, and the demo video.
