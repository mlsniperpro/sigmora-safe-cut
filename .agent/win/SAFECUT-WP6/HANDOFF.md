# HANDOFF: SAFECUT-WP6 (web app), for a successor with only the repo

## Goal, deadline, PR
- Build WP6 (`docs/work-packages/WP6.md`) to winning quality. Spec detail lives in PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges: `git show origin/pre-b-product:docs/UI-SPEC.md`). Official rules: `docs/OFFICIAL-GUIDE.md`.
- Internal deadline 2026-11-04T18:00Z; official Devpost deadline 2026-11-05 02:00 UTC.
- **Owner milestone: the owner submits on Tue 2026-11-03, so the web app and its part of the submission must be final and pushed by 2026-11-03T12:00Z.**
- Branch `wp6-web`; its one PR is #4 (wp6-web → main).
- Done = `bash .agent/win-gate.sh SAFECUT-WP6` prints `GATE: PASS` on the pushed HEAD.

## Current state (2026-10-27, session_01PMv2tTJFHGsGC5rcjHFfL1 holds the lease)
- Audit round 3 (on 6d860ad): 1 medium and 10 low, fixed in 153fac4.
- Audit round 4 (on 153fac4): 1 high, 4 medium and 13 low, fixed in the round-4 commit. Highlights:
  - Mock /try jobs persist in localStorage until `deletes_at`.
  - Timed-out `/start` resumes polling.
  - Result-page "Try again" works.
  - Open-weight copy in §5.3 and the results footnote.
  - Paused job pages quietly refresh their signed URLs.
  - One h1 per page.
- The full table is in reaudit.md, with each finding mapped in WIN-CHECKLIST.md.
- On the round-4 commit: lint 0, typecheck, 779 vitest tests (23 files), build, e2e 71/71, `checks.sh` exit 0. Screenshots refreshed from that e2e run.
- FUZZ_RUNS=100000 passed on 153fac4 (300,000 sequences, 412 s). Round 4 didn't touch the reducer, only the mock's storage and `deletes_at`.
- Audit round 5 (on f56577e): 1 medium and 9 low. All fixed in the round-5 commit except #10, which stays as the spec's copy and is a request to Sigmora.
  - The medium: the review video reloaded on every URL re-sign. Polls now keep the on-screen URLs and the player latches its source.
- On the round-5 commit: 788 tests (25 files), e2e 71/71, `checks.sh` exit 0.
- Audit round 6 (on f690e1f): 2 medium and 4 low, all fixed in the round-6 commit. Highlights:
  - A failed delete no longer strands /try.
  - The footer clears the bottom bar.
  - Field border contrast, an earlier demo banner, κ rounding.
  - Mask-shaped covers.
- On the round-6 commit: 798 tests (26 files), e2e 73/73, `checks.sh` exit 0. Screenshots refreshed.
- Audit round 7 (on d4bb6a1): 1 high, 1 medium and 2 low, all fixed in the round-7 commit. Highlights:
  - The desktop player is no longer sticky over the chips.
  - Scroll padding follows what really sticks, and the bar is static under 480 px tall.
  - 429 cooldowns.
  - The first frame on step C.
- On the round-7 commit: 801 tests (27 files), e2e 81/81, `checks.sh` exit 0. Screenshots refreshed.
- The audit agent hit the usage limit once (19:5x to 23:20 UTC). It resumed with SendMessage, keeping its saved work.
- CLEAN_AUDITS_IN_A_ROW is 0. Two clean full audits are still needed, then a fresh break-it.md (fresh clone + FUZZ_RUNS=100000).

## Next steps, in order
1. Run full audit round 4 on HEAD. If it finds anything, fix it and reset CLEAN_AUDITS_IN_A_ROW to 0. Repeat until two consecutive audits find nothing. Then set AUDITED_COMMIT to the last code commit and CLEAN_AUDITS_IN_A_ROW to 2.
2. After the last code change, run the fresh-clone `checks.sh` (`git clone --branch wp6-web` into an empty dir) and the FUZZ_RUNS=100000 agreement soak. Rewrite break-it.md with TESTED_COMMIT set to that commit.
3. Run the gate until it prints `GATE: PASS` on the pushed HEAD. Then post the final status on PR #4, including the gate's last line.
4. If time remains: live deployment (owner sets up Vercel), Safari/Firefox runs.

## Key decisions (why)
- Overlay maps frames with `floor(mediaTime*fps+0.25)`, following UI-SPEC §3.6 (which supersedes WP6 step 4's "via job.times"). It uses requestVideoFrameCallback with a labelled rAF fallback.
- Solid covers with a frame-sized COCO RLE mask are filled in the mask's shape (§3.6, `lib/rle.ts`). A mask that doesn't decode or fit falls back to the box, so the preview never covers less than the plan.
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
