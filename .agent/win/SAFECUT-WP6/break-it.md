TESTED_COMMIT: b2e384c

# Break-it log: SAFECUT-WP6

Everything below ran against the code at TESTED_COMMIT (no code changed after it).

## Fresh clone, the way a judge runs it
`git clone --branch wp6-web` into an empty directory, then `bash .agent/win/SAFECUT-WP6/checks.sh`:
install (frozen lockfile) → lint (0 warnings) → typecheck (with `next typegen`) → 640 vitest tests → production build → Playwright e2e **60/60**. Exit 0.

Earlier fresh-clone runs are what found the three shipping bugs (all fixed):
1. `pnpm typecheck` failed before any build (route types): fixed with `next typegen && tsc` (f7efd29).
2. The sample `.mp4` clips were git-ignored, so there was no hero or review video (898e116).
3. The `/jobs` routes were git-ignored, so the review and result pages 404'd (b2e384c). `checks.sh` now fails if any source file is ignored.

## Replay / mock e2e (real browser)
`pnpm e2e` (`web/e2e/replay-e2e.mjs`) on the production build, desktop 1280×900 and mobile 390×844:
landing (CSP header, hero video, Raw toggle, no horizontal scroll) → /try (empty and wrong code refused, the real sample MP4's duration read, rights tick) → upload → progress → review (the overlay pixel over the hidden plate is opaque on its frame, Hide + toast + Undo, re-entry merge, Why drawer ring on the Set-of-Mark keyframe, Esc closes) → Approve & render → result (audit summary, no Publish outside Sigmora) → Delete everything now. Plus /jobs/job-replay (demo banner), /jobs/result-audit-failed, /jobs/error-404-expired and an unknown route. axe WCAG 2.2 AA runs on every screen: 0 violations. **60/60.**

## Fuzz and soak
- **Model-based agreement fuzz** (`src/lib/review/agreement.test.ts`): random sequences of keep/hide/remove/confirm/cancel/merge/cover/undo with interleaved acks and injected rejects go through the reducer and the mock server; once nothing is pending, the client's view must equal the server's, and a child is never kept.
  - `FUZZ_RUNS=100000` on the round-1 code (eda2876, same reducer and mock as TESTED_COMMIT): 300,000 sequences, **pass** (332 s).
  - `FUZZ_RUNS=200000` on 4a36a77: 600,000 sequences, pass (637 s).
- **Property tests** (fast-check, in the normal suite): frame mapping (2,000 runs × 3 properties), display times, timeline checks, rewrite rules (3,000 random strings, never leaves a placeholder), upload rounding (3,000 runs × 3), thumbnail crop geometry (2,000), and a reducer invariant run (1,500 sequences: no duplicate requests, children never kept, no merge chains, pending edits never overlap).

## Failure injection
`MockBackend.inject()` and scripted access codes drive every refusal through the real client and components: 401 (wrong, expired, not yet active, revoked at start), 413, 409 `upload_incomplete`, 422 `job_cap`, 429 (`daily_cap`, `code_cap`, `pilot_pool_cap`, `rate_limited` with Retry-After), 500 on review edits (the edit reverts, then Try again resends the same `edit_id`), 500 on DELETE (the page keeps its state), 503 (`auditor_unavailable`, `billing`: Start stays enabled, no DELETE). The API client tests cover timeouts (15 s), network errors with 2/4/8 s backoff on GETs only, malformed JSON and schema violations.

## Not covered
- The live API (WP5 doesn't exist yet). The client is schema-validated, so a contract mismatch surfaces as a typed error page, not a broken render.
- Safari and Firefox weren't run here (Chromium only). The rAF fallback for browsers without rVFC is labelled in the UI and unit-tested through the same frame formula.
