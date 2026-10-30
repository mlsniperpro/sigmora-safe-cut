TESTED_COMMIT: 3807d13

# Break-it log: SAFECUT-WP6

Everything below ran against the code at TESTED_COMMIT (no code changed after it). Run on 2026-10-30; audit rounds 45 and 46 found the same code clean.

## Fresh clone, the way a judge runs it
`git clone --branch wp6-web` into an empty directory, checked out at 3807d13, then `bash .agent/win/SAFECUT-WP6/checks.sh`. The steps:
1. install (frozen lockfile)
2. lint (0 warnings)
3. typecheck (with `next typegen`)
4. **893 vitest tests in 33 files**
5. production build
6. Playwright e2e **145/145**

Exit 0 in 234 s.

Earlier fresh-clone runs are what found three shipping bugs (all fixed):
1. `pnpm typecheck` failed before any build (route types). Fixed with `next typegen && tsc` (f7efd29).
2. The sample `.mp4` clips were git-ignored, so there was no hero or review video (898e116).
3. The `/jobs` routes were git-ignored, so the review and result pages 404'd (b2e384c). `checks.sh` now fails if any source file is ignored.

## Replay / mock e2e (real browser)
`pnpm e2e` (`web/e2e/replay-e2e.mjs`) runs on the production build at 1280×900 and 390×844, plus a landscape 844×390 and two desktop sizes for the sticky player. It covers:
- **Landing:** CSP header, hero video, Raw toggle, no horizontal scroll, and reduced motion (no autoplay; Play demo hands focus to the player and shows only while paused).
- **/try:**
  - empty and wrong codes refused;
  - the real sample MP4's duration read; rights tick;
  - refusals that disable Start take focus;
  - the expired code says it expired on any date.
- **Upload, then progress.**
- **Review:**
  - the overlay pixel over the hidden plate is opaque on its frame;
  - Hide + toast + Undo, and re-entry merge with focus following the chip to its tab;
  - the Why drawer ring on the Set-of-Mark keyframe, Esc to close, and focus kept in the sheet and on ◀/▶ at the ends.
- **Result:** Approve & render, the audit summary, no Publish outside Sigmora, then Delete everything now.
- **Other pages:** every job-state route, the demo banner, the 404 page and its title, a job page's state title, a cut-off percent-escape (404, not 500), the region rewrite, /privacy, and a failed job's Try again keeping focus.

Also covered:
- **Forced colours:** selection cues and the accent buttons, the Why sheet handle, and the toast focus ring at ≥ 3:1.
- **200% default text:**
  - the review layout gates step aside on phones, and the desktop query agrees with Tailwind's `lg:` at 125% on 1100 px;
  - the ⋯ menu stays on screen, including after a resize;
  - the Why sheet scrolls whole on short screens, and its title, failed keyframe and frame row fit at 320 px;
  - the header and landing reflow.
- **Long API tokens:** they wrap on six pages, in the Why drawer and in the merge dialog, without splitting control labels.
- **Layout and focus:**
  - every chip's ⋯ menu opens on screen with all items above the bar;
  - focus survives crossing the desktop breakpoint and is left alone after a click away;
  - a failed job's Try again keeps focus while the retry is out;
  - a 320 px chip reason shows in full.
- **Other:** tab titles follow the state, and a cut-off percent-escape gets the 404 page.

Two checks run on every screen:
- **44 px targets:** every control on mobile measured on landing, /try, review with the toast open, both Why drawers, result and privacy.
- **axe WCAG 2.2 AA:** 0 violations.

**145/145.**

## Fuzz and soak
- **Model-based agreement fuzz** (`src/lib/review/agreement.test.ts`): random sequences of keep/hide/remove/confirm/cancel/merge/cover/undo, with interleaved acks and injected rejects, go through the reducer and the mock server. Once nothing is pending, the client's view must equal the server's, and a child is never kept.
  - `FUZZ_RUNS=100000` on TESTED_COMMIT 3807d13, in the same fresh clone: 3 properties × 100,000 = 300,000 sequences. **Pass** (403 s).
  - Earlier: `FUZZ_RUNS=200000` on 4a36a77 (600,000 sequences, pass).
- **Property tests** (fast-check, in the normal suite):
  - frame mapping;
  - display times and timeline checks;
  - rewrite rules;
  - upload rounding;
  - thumbnail crop geometry;
  - a reducer invariant run (no duplicate requests, children never kept, no merge chains, pending edits never overlap).
- **Clock sweep:** the whole vitest suite passes with the wall clock moved −1, 0, +0.6, +10, +40 and +400 days. The mock fixtures shift by whole UTC days so their moment falls on today, so the demo behaves as written on any date, including judging.
- **Contracts:** WP0's own `j_example` fixtures (wp0-foundation 9003bad) parse through the client's schemas (`contracts.wp0.test.ts`), with ARCHITECTURE §3.8's audit example verbatim.

## Failure injection
- **Mock refusals:** `MockBackend.inject()` and scripted access codes drive every refusal through the real client and components:
  - 401: wrong, expired, not yet active, revoked at start.
  - 413, 409 `upload_incomplete` and 422 `job_cap`.
  - 429: `daily_cap`, `code_cap`, `pilot_pool_cap`, and `rate_limited` with Retry-After.
  - 500 on review edits: the edit reverts, Try again resends the same `edit_id`, and focus follows the chip, including on mobile tabs.
  - 500 on DELETE: the page keeps its state.
  - 503 `auditor_unavailable` and `billing`.
  - Spec-shaped answers with no IDs the spec doesn't give: `/result` without `job_id`, `captions_url`, `status` or `frames` (the page loads, with captions from the job's transcript), 202 acks without `job_id`, review acks without `edit_id`, the demo without `hero_id`.
  - 5xx on the demo: one retry.
- **API client tests:** timeouts (15 s), network errors with 2/4/8 s backoff on GETs only, malformed JSON and schema violations.
- **Independent audits:** rounds 3–44 also drove a live-mode build against a fake https API with fault injection: signed-URL expiry and refresh, hangs, dropped connections and every status code. See `reaudit.md`.

## Not covered
- **The live API:** WP5 doesn't exist yet. The client is schema-validated, so a contract mismatch shows up as a typed error page, not a broken render.
- **Safari and Firefox:** not run here (Chromium only). The rAF fallback for browsers without rVFC is labelled in the UI and unit-tested through the same frame formula.
