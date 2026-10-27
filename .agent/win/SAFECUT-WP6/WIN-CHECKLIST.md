# WIN-CHECKLIST: SAFECUT-WP6 (web app)

Legend: `- [x]` done with evidence · `- [P]` waits on an owner input (BLOCKED.md) · `- [-]` not applicable, why · `- [ ]` open.

## Official guide reconciliation (docs/OFFICIAL-GUIDE.md, captured 2026-10-26 16:25Z)

- [x] Rubric weights match: Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25 (guide Stage 2 = AGENTS.md); deadline Wed Nov 4 21:00 ET = 2026-11-05 02:00 UTC matches MAXXING §1 (05:00 EAT); internal deadline stays 2026-11-04T18:00Z
- [x] Theme fit: "Build for Your World" (creators publishing street footage without exposing bystanders); not on the anti-project list (no medical advice; not a simple image analyzer: a multi-model video pipeline with tracking, role rulings, review and audit)
- [x] Stage 1 pass/fail made visible: How it works names Muse Spark, SAM 3.1, Muse Voice Transcribe, EgoBlur; the Why drawer shows the SAM keyframe, Muse Spark votes and transcript; Details lists the models (`src/components/landing/HeroAndSteps.tsx`, `src/lib/why/model.ts`)
- [x] "New work only": footer on every page states "New work: Safe Cut was built during the hackathon (Oct 26 – Nov 4, 2026)… Sigmora is the existing product" (`src/components/Footer.tsx`); repo history starts at kickoff
- [x] Copy never frames Safe Cut as an image analyzer or face recognition: copy deck words only (`src/lib/copy.ts`, components); grep for "recogni" finds only the audit's "read or recognise anything" sentence from the UI-SPEC deck
- [x] Best Agentic Use-Case bonus: "The loop, on every clip" figure on the landing (5 steps SAM→Muse→miss loop→render→audit) and per-item evidence in the Why drawer
- [x] Most Viral bonus: Open Graph + `summary_large_image` X card with the Safe Cut still (`src/app/layout.tsx`, metadataBase from `NEXT_PUBLIC_SITE_URL`)
- [P] Best Build on Meta Open-Weight Models bonus (Muse Spark Open via Baseten `meta-models/muse-spark-open-1026`): pipeline-side (WP2) and needs Baseten credits; the web shows whichever models `receipt.models` reports, so no web change is needed. Requested in the PR's "Requests for other WPs"
- [P] Live product + public repo at submission: needs the owner's Vercel project/domain and the repo made public (BLOCKED.md)
- [P] 3-minute demo video: owner records; the web side is the demo-mode screens (STORYBOARD)

## Judging criteria (Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25; Startup track: holds up in production)

- [x] Demo 25%: every screen works end to end against the mocks; e2e 60/60 on desktop and mobile (`web/e2e/replay-e2e.mjs`)
- [x] Meta tooling 25%: Why drawer with geometry-checked ring on the Set-of-Mark keyframe, vote marks vs majority, escalation text, transcript lines with speaker link (`src/components/review/WhyDrawer.tsx`, `src/lib/why/*`, tests `src/lib/why/model.test.ts`)
- [x] Impact 30%: results table component with placeholder until WP8 (never a typed number), blur-every-face vs Safe Cut stills, 3-step story (`src/app/page.tsx`, `src/components/landing/ResultsTable.tsx`)
- [x] Technical depth 20%: rVFC overlay with `floor(t·fps+0.25)` and the §3.6 timeline checks (`src/lib/time.ts`, `src/components/review/VideoPane.tsx`); optimistic reducer R1–R33 with undo/idempotent edit_ids and a client/server agreement fuzz (`src/lib/review/*.test.ts`)
- [x] Production: zod-validated responses, 15 s timeouts, GET-only 2/4/8 s retries, typed ApiError, edit_id idempotency, copy mapped per §10.3 (`src/lib/api.ts`, `src/lib/copy.ts`, `src/lib/api.test.ts`)
- [x] Production: CSP (frame-ancestors, object-src none), HSTS, nosniff, Permissions-Policy, noindex on job pages (`web/next.config.ts`; e2e checks the CSP header); only NEXT_PUBLIC_ values in the bundle, access codes never logged

## WP6 brief

- [x] Step 1: official create-next-app scaffold; vitest + Testing Library; lint/typecheck/test scripts (`web/package.json`)
- [x] Step 2: `web/src/lib/api.ts` + `client.ts` use the mock backend over `web/mocks/` when `NEXT_PUBLIC_SAFECUT_API` is unset
- [x] Screen 1 Landing `/` (e2e: hero loads, raw toggle, no horizontal scroll, axe clean; screenshots)
- [x] Screen 2 Upload `/try` (`src/components/try/TryFlow.tsx`; 11 tests in `TryFlow.test.tsx`; e2e uploads the real sample MP4)
- [x] Screen 3 Review `/jobs/[id]` (`src/components/review/*`; 20 integration tests in `src/components/job/JobPage.test.tsx`; e2e edit/undo/merge/drawer/overlay pixels)
- [x] Screen 4 Result `/jobs/[id]/result` (`src/components/job/ResultPage.tsx`; 6 tests; e2e)
- [x] Screen 5 Demo-mode banner on `mode: "replay"` (`src/components/mode.tsx`; test + e2e on `/jobs/job-replay`)
- [x] Step 3 Accessibility: axe WCAG 2.2 AA clean on every screen at desktop and mobile in the e2e; keyboard shortcuts, focus return, icon + word states, captions track
- [x] Step 4 Overlay synced to requestVideoFrameCallback with the §3.6 mapping; e2e reads the canvas pixel over the hidden plate
- [x] Step 5 `web/README.md` documents env vars, mock codes, checks and deployment
- [x] Tests: chips (toggle, lock, merge) in `JobPage.test.tsx`; reducer R1–R33 in `reducer.test.ts`; API client vs mocks in `api.test.ts`; frame↔time in `time.test.ts` (632 tests total)
- [x] Done-when: screenshots of every screen (desktop + mobile) produced by `pnpm e2e --shots <dir>` and attached to the PR
- [P] Done-when: switch to the live API after WP5 merges (client is contract-driven; needs WP5's deployed URL)

## Owner quality bar

- [x] State of the art: choices and sources recorded in the PR's Decisions section (Next 16 docs in node_modules, WICG rVFC, WCAG 2.2, zod 4)
- [x] Property-based tests: fast-check in time, rewrite, upload, keyframe, reducer and the agreement fuzz
- [x] Integration tests across client ↔ mock backend ↔ pages (`api.test.ts`, `JobPage.test.tsx`, `TryFlow.test.tsx`, `ResultPage.test.tsx`)
- [x] One end-to-end test in mock/replay mode in a real browser (`web/e2e/replay-e2e.mjs`, 60/60)
- [x] Failure paths covered: timeouts, network retries, schema violations, malformed JSON, 401/404/409/413/422/429/500/503, rejected edits, failed deletes
- [x] Strict TS (strict + noUncheckedIndexedAccess), ESLint `--max-warnings=0` clean
- [x] Self-review section in the PR with expected load and first breaking point (PR #4 body)

## Audit findings

Rounds 1–2 (38 findings) are tabled with their fixes in `reaudit.md`. Round 3:

- [x] R3-1 (med) signed URLs refetched for thumbnails, keyframes, download and receipt links (§10.7): `ReviewPanel` refreshKeyframes, `ResultPage` link refresh; JobPage + ResultPage tests
- [x] R3-2 (low) focus follows a covered spot to the server's item: JobPage "covers an unfixed spot"
- [x] R3-3 (low) ⌘Z undo on a Mac: JobPage "Cmd+Z undoes on a Mac"
- [x] R3-4 (low) drawer Keep on an object keeps focus on the confirm's Cancel: did not reproduce; pinned by a JobPage test
- [x] R3-5 (low) /try keeps polling a just-started `created` job: `useJob.test.tsx`
- [x] R3-6 (low) one 5xx while polling retries quietly: `useJob.test.tsx`
- [x] R3-7 (low) Copy link failure says so and selects the link: `ProgressView.test.tsx`
- [x] R3-8 (low) illustration captions on the drawn-shape stills: `app/page.tsx`
- [x] R3-9 (low) mock mode no longer contradicts itself: `mode.test.tsx`, TryFlow test
- [x] R3-10 (low) README facts (Cache Components off, routes, Node/pnpm, Playwright browser)
- [P] R3-11 (low) privacy contact email for `/privacy`: owner sets `NEXT_PUBLIC_PRIVACY_CONTACT` at deploy (BLOCKED.md)
