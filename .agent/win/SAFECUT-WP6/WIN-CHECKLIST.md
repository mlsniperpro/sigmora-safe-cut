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

Round 4 (fixes in the round-4 commit; details in `reaudit.md`):

- [x] R4-1 (high) mock /try jobs survive a reload and the copied link (localStorage until `deletes_at`): `mock-backend.test.ts`
- [x] R4-2 (med) result-page Try again works: ResultPage tests
- [x] R4-3 (med) /try hands a failed poll to the job page: TryFlow test
- [x] R4-4 (med) timed-out start resumes polling (§10.3): TryFlow tests
- [x] R4-5 (med) open-weight line in the §5.3 detail and the results footnote: copy + landing tests
- [x] R4-6 (low) media refresh re-arms after a successful load: ResultPage/JobPage/landing tests
- [x] R4-7 (low) mock `deletes_at` is now + 24 h: `mock-backend.test.ts`
- [x] R4-8 (low) ⋯ trigger closes its menu: JobPage test
- [x] R4-9 (low) Enter help text matches §3.8
- [x] R4-10 (low) discarded GETs still hand over fresh URLs: `withFreshUrls` test
- [x] R4-11 (low) paused job pages refresh signed URLs; downloads open a new tab: useJob test
- [x] R4-12 (low) one `<h1>` on every job state: JobPage tests
- [x] R4-13 (low) copy result announced, label resets: ProgressView test
- [x] R4-14 (low) review URL wraps: ProgressView test
- [x] R4-15 (low) hero poster while loading and on failure: landing test
- [x] R4-16 (low) dev CSP allows a local API (`connect-src` only)
- [x] R4-17 (low) screenshots refreshed; root README change requested from its owner WP in the PR
- [x] R4-18 (low) mock mode says the picked clip isn't analysed: TryFlow test

Round 5 (fixes in the round-5 commit; details in `reaudit.md`):

- [x] R5-1 (med) polls keep on-screen signed URLs; the player latches its source: useJob + JobPage tests
- [x] R5-2 (low) quiet URL refresh survives a hidden tab: useJob test
- [x] R5-3 (low) captions load under StrictMode: `useCaptions.test.ts`
- [x] R5-4 (low) no start after a confirmed delete: TryFlow slow-DELETE test
- [x] R5-5 (low) a past refusal time re-enables Start; no 0 s poll loop: TryFlow test
- [x] R5-6 (low) mock storage keeps only scripted codes: `mock-backend.test.ts`
- [x] R5-7 (low) sample receipt copy follows the data-handling copy notes
- [x] R5-8 (low) h1 on error, 404 and Deleted: `pages.test.tsx`, TryFlow test
- [x] R5-9 (low) README says where UI-SPEC lives until PRE-B merges
- [-] R5-10 (low) "Sent to Sigmora" without a delivery receipt: spec copy; a confirmation needs Sigmora's reply (PR "Requests for other WPs")

Round 6 (fixes in the round-6 commit; details in `reaudit.md`):

- [x] R6-1 (med) a failed DELETE leaves /try working (upload, start, navigation): TryFlow tests
- [x] R6-2 (med) the bottom bar never covers the footer: e2e desktop + mobile
- [x] R6-3 (low) text-field border ≥ 3:1 in both themes
- [x] R6-4 (low) the demo banner shows from the create response: TryFlow test
- [x] R6-5 (low) κ rounded down: landing test
- [x] R6-6 (low) masked covers drawn in the mask's shape: `rle.test.ts`, overlay tests

Round 7 (fixes in the round-7 commit; details in `reaudit.md`):

- [x] R7-1 (high) desktop player no longer sticky over the chips: e2e 1280×720 and 1366×768
- [x] R7-2 (med) scroll padding follows what's really sticky; bar static on very short screens: e2e 320×400 and 480×270
- [x] R7-3 (low) rate-limited Try again and Delete wait out Retry-After: JobPage tests
- [x] R7-4 (low) first frame on step C: JobPage test
- [x] R7-n1 `reentry_of` defaults to null: contracts test
- [x] R7-n2 one delete at a time
- [-] R7-n3 "Keep Plate 1 clear" naming: kept "Keep clear Plate 1" for WCAG 2.5.3

Round 8 (fixes in the round-8 commit; details in `reaudit.md`):

- [x] R8-1 (med) §3.1 desktop layout: capped player with the switch beside it, chips on the first screen: e2e
- [x] R8-2 (low) the open tab is scrolled into its strip on narrow phones: e2e 320/390
- [x] R8-3 (low) a failed delete's error takes focus: JobPage test
- [x] R8-4 (low) stray debug screenshot removed and ignored

Round 9 (fixes in the round-9 commit; details in `reaudit.md`):

- [x] R9-1 (med) refused actions announced and focused: JobPage test
- [x] R9-2 (low) focus kept during an in-flight delete; test dialog polyfill matches browsers: JobPage test
- [x] R9-3 (low) the selected item always has a timeline row: `timeline.test.ts`
- [x] R9-4 (low) tab focus ring not clipped
- [x] R9-5 (low) footer and landing link targets 44/32 px

Round 10 (fixes in the round-10 commit; details in `reaudit.md`):

- [x] R10-1 (low) repeated identical answers re-announced and focused: JobPage tests
- [x] R10-2 (low) busy action buttons keep focus; focus follows to the render progress: JobPage test
- [x] R10-3 (low) result fixtures play the sample media in mock mode: mock-backend test

Round 11 (fixes in the round-11 commit; details in `reaudit.md`):

- [x] R11-1 (low) /try busy buttons keep focus on refusal: e2e (fails on the previous build)
- [x] R11-2 (low) mock result frame counts match the sample clip: mock-backend test
- [x] R11-3 (low) alerts re-keyed per answer, not per press: JobPage test

Round 12 (fixes in the round-12 commit; details in `reaudit.md`):

- [x] R12-1 (low) mock result job and result describe the same clip: mock-backend test
- [x] R12-2 (low) a refusal that disables Start takes focus: e2e

Round 13 (fixes in the round-13 commit; details in `reaudit.md`):

- [x] R13-1 (med) cross-origin captions load as blob URLs, videos never depend on CORS: `useRemoteCaptions.test.ts`
- [x] R13-2 (low) focus after a refused upload retry: TryFlow test
- [x] R13-3 (low) sample media only under fixtures for the same clip
- [x] R13-4 (low) landing Try it target 44 px wide
- [x] R13-n media URLs reject whitespace/control characters: api test

Round 14 (fixes in the round-14 commit; details in `reaudit.md`):

- [x] R14-1 (low) a cut-short fresh refetch hands its request on: useJob test
- [x] R14-2 (low) a refetch with the same URL ends in the "didn't load" message: JobPage, ResultPage, landing tests
- [x] R14-3 (low) privacy link and demo-banner button 44 px on mobile
- [x] R14-n captions survive the result page's link refresh: hook test
- [x] R15-1 (low) a late fresh URL brings the review player back: JobPage test
- [x] R15-2 (low) an action's GET isn't made quiet by a cut-short refresh: useJob test
- [x] Self-found: fixture dates shift with the clock, so the mock and the tests hold on any date: mock-backend tests, suite run at clock shifts up to +400 days
- [x] R28-1 (medium) chip ⋯ menu stays on screen when its trigger wraps: e2e at 320 and 1280
- [x] R28-2 (low) API text inside controls wraps: data-api-text spans + sweep in the merge dialog
- [x] R27-1..3 (low) control labels keep whole words beside long text: e2e split-word check
- [x] R26-1 (low) long tokens wrap everywhere (body overflow-wrap: anywhere): e2e sweep on 6 pages + Why drawer
- [x] Build clears .next/cache so CSS is never stale
- [x] R25-1 (low) long tokens in chip reasons wrap: e2e
- [x] R24-1 (low) chip reasons show in full at 320 px: e2e
- [x] R23-1 (low) selection and accent buttons visible in forced colours: e2e
- [x] R22-1 (low) no-keyframe caption by origin, neutral otherwise: JobPage test
- [x] R21-1 (high) open_weight with model null parses: WP0 j_example contract test + ARCHITECTURE §3.8 example
- [x] R21-2 (medium) a box-only miss (point null) and an absent covered_by parse: contract test
- [x] R21-3 (low) no-keyframe items show their origin caption only: JobPage tests
- [x] R21-4 (low) long file names wrap at 320 px: e2e
- [x] R21-5 (low) spot kind from its own leak rows: view test
- [x] R21-6 (low) durations round down: unit test
- [x] R21-7 (low) toast focus ring ≥ 3:1: e2e
- [x] R21-8 (low) kind icons: JobPage test
- [x] R19-1 (low) the result page's link refresh re-arms after a failure: ResultPage test
- [x] R19-2 (low) a lapsed focus request never fires: JobPage test
- [x] R19-3 (low) tab titles follow the shown state; the hero retries a 5xx once: JobPage, landing tests, e2e
- [x] R18-1 (low) focus waits for the commit that mounts its chip: JobPage test
- [x] R18-2 (low) undoing a cover focuses its spot: JobPage test
- [x] R18-3 (low) closing the Why sheet follows the chip's tab: JobPage test
- [x] R18-4 (low) a failed job's successful retry focuses the progress: JobPage test
- [x] Self-found after round 17: a failed job's Try again keeps focus while its retry is out (aria-disabled): e2e
- [x] R17-1 (low) Try again follows the chip to its tab on mobile: JobPage test
- [x] R17-2 (low) focus stays in the Why sheet after Hide/Keep clear: e2e
- [x] R17-3 (low) ◀/▶ keep focus at the ends (aria-disabled): e2e
- [x] R17-4 (low) Dismiss hands focus back to the chip: JobPage test
- [x] R17-5 (low) cap retry is always the next UTC midnight: mock-backend test
- [x] R16-1 (low) focus returns to a chip whose edit was rejected: JobPage test
- [x] R16-2 (low) 44 px wide toast and evidence-frame buttons; e2e measures every mobile control
- [x] R16-3 (low) the expired mock code says expired on any date: e2e
- [x] R16-4 (low) whole-day fixture shift keeps midnights: mock-backend tests, clock sweep
- [x] R16-5 (low) README fixture-date wording
- [x] R16-6 (low) a cut-off percent-escape gets the 404 page, not a 500: e2e
- [x] R15-3 (low) reduced-motion "Play demo" shows only while paused and hands focus to the player: landing test, e2e

