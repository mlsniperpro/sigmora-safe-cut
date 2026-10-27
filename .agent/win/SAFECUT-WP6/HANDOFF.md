# HANDOFF: SAFECUT-WP6 (web app), for a successor with only the repo

## Goal, deadline, PR
- Build WP6 (`docs/work-packages/WP6.md`) to winning quality. Spec detail lives in PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges: `git show origin/pre-b-product:docs/UI-SPEC.md`). Official rules: `docs/OFFICIAL-GUIDE.md`.
- Internal deadline 2026-11-04T18:00Z; official Devpost deadline 2026-11-05 02:00 UTC.
- **Owner milestone: the owner submits on Tue 2026-11-03, so the web app and its part of the submission must be final and pushed by 2026-11-03T12:00Z.**
- Branch `wp6-web`; its one PR is #4 (wp6-web → main).
- Done = `bash .agent/win-gate.sh SAFECUT-WP6` prints `GATE: PASS` on the pushed HEAD.

## State at wind-down (2026-10-26 ~19:10Z, head 6d860ad + this handoff commit)
- PR #4 (wp6-web → main) is open and its body is current. The branch is pushed. LEASE is released.
- Done, with evidence on 6d860ad:
  - lint 0 warnings, typecheck, 744 vitest tests (20 files) pass.
  - e2e 71/71 (`pnpm build && pnpm e2e`) ran on 545e1e3. 6d860ad changes only `lib/region.ts` and its test.
  - Agreement fuzz with FUZZ_RUNS=100000 (3 tests) passed on 4abd680; the reducer and mock are unchanged since.
- Adopted PRE-B's newest UI-SPEC (f51fcb6):
  - region proxy (`src/proxy.ts`, `lib/region.ts`). Next ignores a status on a rewrite, so restricted users get 200 with the /unavailable page and no upload form.
  - /privacy and the Footer link.
  - consent line with Meta Terms/AUP links.
  - open-weight-aware data bullets.
  - Ctrl+Z with single-key shortcuts off.
- 6d860ad: the `SAFECUT_BLOCKED_TERRITORIES` override is validated with zod; no RegExp is built from the country header.
- Gate on 6d860ad: `GATE: FAIL (3): only 0 clean full audit(s) in a row; two consecutive audits must find nothing new`. It also fails because reaudit.md (eda2876) and break-it.md (b2e384c) are stale. Every other gate check passes.

## Unfinished / stopped at wind-down (nothing partial is committed, nothing reverted)
- Audit round 3 (Sonnet subagent, started on 4abd680) was STOPPED before it reported. No findings were collected.
- A fresh-clone `checks.sh` run on 545e1e3 was stopped mid-e2e. It was green up to that point.
- A 5× repeat of the vitest suite was stopped after run 1 (744/744).

## Open audit findings
- None known open. Accepted (low): no chip-list virtualisation above 100 chips (reasoning in reaudit.md round 2 #12).

## Next steps, in order
1. Run a full audit (round 3) on HEAD. Fix what it finds, then repeat until two full audits in a row find nothing. Set reaudit.md AUDITED_COMMIT to HEAD and CLEAN_AUDITS_IN_A_ROW to 2.
2. After the last code change, rerun the fresh-clone `checks.sh` (`git clone --branch wp6-web` into an empty dir) and the FUZZ_RUNS=100000 agreement soak. Set break-it.md TESTED_COMMIT to that HEAD and update its numbers (744 tests, e2e 71).
3. Run the gate until `GATE: PASS` on the pushed HEAD. Then post the final status comment on PR #4, including the gate's last line.
4. If time remains: a live deployment (owner sets up Vercel), Safari/Firefox runs.

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
