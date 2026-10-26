# HANDOFF: SAFECUT-WP6 (web app), for a successor with only the repo

## Goal, deadline, PR
- Build WP6 (`docs/work-packages/WP6.md`) to winning quality. Spec detail lives in PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges: `git show origin/pre-b-product:docs/UI-SPEC.md`). Official rules: `docs/OFFICIAL-GUIDE.md`.
- Internal deadline 2026-11-04T18:00Z; official deadline 2026-11-05 02:00 UTC.
- Branch `wp6-web`, which is pushed. **No PR is open yet.** Open exactly ONE PR wp6-web → main.
- Done = `bash .agent/win-gate.sh SAFECUT-WP6` prints `GATE: PASS` on the pushed HEAD. The gate has not been run yet.

## State (2026-10-26 ~20:30Z)
- PR #4 open, body current. Branch pushed (HEAD 56a4aec or later). LEASE active.
- Audit rounds 1 and 2 are fixed: 38 findings, including 1 critical and 4 high. Record: `reaudit.md`. Cache Components is now OFF (Activity state preservation caused round-2 #2, #6 and #7).
- Local results: 689 tests and e2e 66/66 on 05481aa.

## In flight
- Audit round 3 (a Sonnet subagent) on 05481aa. A FUZZ_RUNS=100000 agreement soak on 05481aa (log at scratchpad soak4.log; it's lost if the container restarts, so rerun it).

## Next steps, in order
1. Fix round-2 findings, push, then run full audits until two in a row find nothing (CLEAN_AUDITS_IN_A_ROW: 2).
2. Keep break-it.md's TESTED_COMMIT current: rerun the fresh-clone `checks.sh` after the last code change.
3. Gate until `GATE: PASS` on the pushed HEAD, then post the final status comment on PR #4 (put the gate's last line in it).
4. Raise the bar if time remains: compare against past winners. Candidates: a live demo deployment once the owner sets up Vercel, a GIF of the review flow, Safari/Firefox runs.

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
- Subagents: every Agent/Task launch sets model "sonnet" and effort "high" (auditors, reviewers, fixers, researchers, soak/log watchers). Integration, self-review, deciding which findings are real, and the gate stay in the main session; verify any subagent finding before fixing it, never drop one unchecked.
- Pushing: push when a substantial task is complete and green (audit findings fixed and tested, a feature slice working, a soak/break-it pass recorded, the gate run). No timer. Squashed, meaningful commits only (no empty/format-only/wip). Exactly one PR.
- Never idle and never end a turn to wait: while a subagent, audit, soak or build runs, work on the next item and collect results when they arrive. Only two reasons to stop: the API usage limit, or the /goal being met.

## Owner-only blockers
See `.agent/win/SAFECUT-WP6/BLOCKED.md`: the Vercel project and domain, hero footage with releases, making the repo public, Baseten credits, and the demo video.
