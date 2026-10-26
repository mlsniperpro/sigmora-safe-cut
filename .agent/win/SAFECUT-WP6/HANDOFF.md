# HANDOFF: SAFECUT-WP6 (web app), for a successor with only the repo

## Goal, deadline, PR
- Build WP6 (`docs/work-packages/WP6.md`) to winning quality. Spec detail lives in PRE-B's `docs/UI-SPEC.md` (on `origin/pre-b-product` until it merges: `git show origin/pre-b-product:docs/UI-SPEC.md`). Official rules: `docs/OFFICIAL-GUIDE.md`.
- Internal deadline 2026-11-04T18:00Z; official deadline 2026-11-05 02:00 UTC.
- Branch `wp6-web`, which is pushed. **No PR is open yet.** Open exactly ONE PR wp6-web → main.
- Done = `bash .agent/win-gate.sh SAFECUT-WP6` prints `GATE: PASS` on the pushed HEAD. The gate has not been run yet.

## Done (evidence)
- Scaffold: official create-next-app (Next 16.4.3, React 19.3, Tailwind 4, TS strict + noUncheckedIndexedAccess), vitest 5 + Testing Library + fast-check. Lives in `web/`.
- Contracts: `web/src/lib/contracts.ts` has zod schemas aligned with WP0's `safecut/contracts.py` on `origin/wp0-foundation`.
- API client: `web/src/lib/api.ts` has 15 s timeouts, GET-only retries at 2/4/8 s, a typed ApiError, and treats 404 on DELETE as success. The live transport (`transport-live.ts`) uses fetch, plus XHR for uploads with a 30 s stall check. `client.ts` picks mock vs live based on `NEXT_PUBLIC_SAFECUT_API`.
- Mock backend: `web/src/lib/mock-backend.ts`.
  - Every fixture is reachable at `/jobs/<fixture-name>`.
  - Jobs created through /try run a simulated pipeline.
  - Review edits follow WP3 semantics: idempotent edit_id, undo/reverts, merge, cover_spot.
  - `inject()` adds failure injection.
  - `MOCK_CODES` lists scripted access codes (wrong, not-yet, expired, no-budget, revoked, no-auditor, …).
- Fixtures: `web/scripts/gen-mocks.mjs` writes `web/mocks/*.json` (82 fixtures) and `mocks/index.ts`. `web/mocks/mocks.test.ts` checks every UI-SPEC §10.1 invariant and that the files match the generator.
- Synthetic sample scene: `web/scripts/sample-scene.mjs` and `gen-sample.mjs` render `web/public/sample/*` (drawn shapes, no real people). It needs ffmpeg.
- Pure logic, each with tests:
  - review reducer R1–R33 + property test: `src/lib/review/reducer.ts`
  - bar rows §3.5: `bar.ts`
  - chip view model: `view.ts`
  - Why drawer copy: `src/lib/why/`
  - copy deck: `copy.ts`
  - upload checks: `upload.ts`
  - overlay ops/drawing: `overlay.ts`
  - keyframe geometry: `keyframe.ts`
  - prepared-clock time: `time.ts`
  - polling rule: `polling.ts`
- Screens:
  - `/` (hero toggle, how it works + model loop, side-by-side, results table)
  - `/try`
  - `/jobs/[id]` (§10.4 state machine; review panel with rVFC overlay, tabs on mobile, keyboard shortcuts, toasts and undo, merge/remove/cover spot, Why drawer)
  - `/jobs/[id]/result`
  - not-found and error pages
- Security headers: CSP and others in `web/next.config.ts`.
- Last local results: 629 vitest tests passing; `pnpm lint` (max-warnings 0) and `pnpm typecheck` clean; `pnpm build` passed.

## In flight (exact state)
- `web/e2e/replay-e2e.mjs`: a Playwright end-to-end run of the production build in mock mode, covering every screen, axe WCAG 2.2 AA checks, overlay pixel checks and screenshots. Devdeps `playwright@1.63.0` and `axe-core` are added. It is committed but **has never completed a run**: the first run was killed by the wind-down. Expect some selector fixes.
- `.agent/win/SAFECUT-WP6/WIN-CHECKLIST.md` has items still `- [ ]`. Their evidence still needs filling in.
- `reaudit.md` and `break-it.md` don't exist yet. The gate fails without them.

## Next steps, in order
1. `cd web && pnpm install && pnpm build && pnpm e2e --shots /tmp/shots`, then fix any failures.
2. Write `web/README.md`: the env vars, the mock-code table, how to regenerate mocks and sample media, and deploy notes (Vercel; don't deploy from the sandbox).
3. Fill WIN-CHECKLIST with evidence. Run a full audit and write `reaudit.md` (AUDITED_COMMIT, OPEN_CRITICAL, OPEN_HIGH, CLEAN_AUDITS_IN_A_ROW). Write `break-it.md` (TESTED_COMMIT: fuzz/property runs, the e2e, a fresh-clone README run).
4. Run the gate and fix every FAIL.
5. Open the ONE PR. Put in it: screenshots of every screen, Decisions, Self-review, expected load, the gate's last line, and Requests for other WPs:
   - WP5: `eta_s`, `stage_reason`, the result/demo route shapes, `code_valid_until`, the publish postMessage contract (`{type:"safecut:publish", job_id, video_url, receipt_json_url}`, or a fallback to `<sigmora>/safecut/return?job_id=`)
   - WP0/WP3: `removed_by_creator` and `spot_id` on DecisionItem
   - WP2: Muse Spark Open via Baseten for the open-weight bonus

## Known gaps / open audit findings (not yet audited formally)
- With fixture URLs, mock mode substitutes sample media into hero fixtures. The video (240 frames) then disagrees with the fixture data (12 frames). This is cosmetic and limited to mock mode.
- The `<details>` Why-drawer Details section and the live-region behaviour are not covered by any test.
- There is no integration test for the broken-timeline error page. The logic itself is unit-tested in `time.test.ts`.
- `job.times` is used only for validation. The receipt's source-time column is rendered by WP4's receipt.html.

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
