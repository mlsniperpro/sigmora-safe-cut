AUDITED_COMMIT: eda2876
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# Re-audit log: SAFECUT-WP6

## Round 1 (audited 4a36a77 by a Sonnet reviewer, every finding verified here before fixing; fixes in eda2876)

0 critical, 2 high, 20 medium/low. All fixed except where noted.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | high | `content-visibility` on chips clipped the ⋯ menu | fixed: removed; JobPage test opens the menu |
| 2 | high | Rights tick / data bullets out of date with the current UI-SPEC | fixed: spec strings, territory link, Baseten line on `open_weight` codes; tests |
| 3 | med-high | RETRY of a rejected object keep was a no-op (R31c) | fixed in reducer; R31b/c/d tests |
| 4 | med-high | Cancel during upload was overwritten by "upload stopped" | fixed with a deleted-by-user ref; regression test |
| 5 | med | scroll-padding variables never reached `<html>` (WCAG 2.4.11) | fixed: measured and set on `:root` |
| 6 | med | Focus didn't follow the edited chip | fixed |
| 7 | med | Chip article not tabbable; Enter opened the drawer instead of selecting | fixed (tabindex 0, Enter selects) |
| 8 | med | No copy link / cancel and delete on /jobs/[id] while processing or retry_later | fixed: shared ProgressView |
| 9 | med | Visible-tab refetch ran in paused states; stale GET could overwrite an ack | fixed: polling flag + patch sequence guard |
| 10 | med | Missing "{n} of the 3 checks didn't run" rows | fixed; test |
| 11 | med | Mobile drawer Keep clear on an object did nothing visible | fixed: drawer closes to the in-chip confirm |
| 12 | med-low | /result showed a generic error for failed/created jobs | fixed |
| 13 | med-low | Drawer kept the previous item's frame index; missing "Frame at" caption | fixed (keyed per item; caption) |
| 14 | low-med | Render started at ?view=review stayed on the panel; Back to result dropped ?from=sigmora | fixed |
| 15 | low-med | Remove/merge dialogs lost focus | fixed |
| 16 | low-med | Object confirm autofocused the affirmative button | fixed (Cancel focused) |
| 17 | low | "need(s) you" plural | fixed; test |
| 18 | low | Copy drift (deleted, each is fixed, footer); daily-cap retry blocked forever | fixed |
| 19 | low | 36 px touch targets on mobile | fixed (44 px below 1024 px) |
| 20 | low | "Always hidden" help link didn't focus the explanation | fixed |
| 21 | low | Receipt iframe error state unreachable | fixed: load timeout |
| 22 | low | URLs from the API accepted any scheme; CSP allows any https host | fixed: zod requires https or same-origin. Accepted: CSP keeps `https:` for media/connect because the storage host isn't known until deploy (documented in the PR) |

Break-it (fresh clone) also found, after round 1:
- **critical** `web/src/app/jobs/**` (the review and result routes) was never committed: the root `.gitignore`'s `jobs/` rule (meant for pipeline job directories) matched it. Fixed in b2e384c by re-including it in `web/.gitignore`; `checks.sh` now fails on any ignored source file.
- **high** the synthetic sample clips (`*.mp4`) were ignored the same way, so a fresh clone had no video. Fixed in 898e116.

Fresh-clone README run also found: `pnpm typecheck` failed before any build (Next route types). Fixed in f7efd29 (`next typegen && tsc`).

## Round 2 (audited eda2876 by a Sonnet reviewer; each finding verified here; fixes in the next commit)

1 critical, 2 high, 5 medium, 8 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | critical | /try started polling at 100% upload, before `POST /start`; a "created" answer stopped polling for good, so a slow start hung on "Waiting to start" | fixed: polling starts only after `/start` resolves; regression test with a 300 ms start |
| 2 | high | Cache Components kept /try (and every page) mounted but hidden (Next 16 `<Activity>`): Back returned to a stale progress page that pushed forward again; "Try another clip" after a delete was a dead link | fixed: Cache Components turned off (flow pages gain nothing from it); "Try another clip" resets the page; e2e checks Back lands on a fresh /try |
| 3 | high | The demo-mode banner latched from the landing hero into live /try and job pages ("Nothing is sent to Meta right now" during a real upload) | fixed: demo mode belongs to the page that got the replay response; test |
| 4 | med | Focus lost after shortcut edits, undo, jump, cancel; on mobile the moved chip was in an unmounted tab | fixed: every edit goes through one `act()` that focuses the moved chip and opens its tab; test + e2e |
| 5 | med | Sticky player taller than a landscape phone / 200% zoom viewport | fixed: player capped at 40vh below 1024 px; sticky only when the viewport is ≥ 640 px tall; e2e at 844×390 |
| 6 | med | Video audio kept playing on hidden pages | fixed by #2 (pages unmount) |
| 7 | med | `renderedHere` survived under Activity; not set on the 409 path | fixed by #2; 409 path sets it |
| 8 | med | Expired signed media URLs not refetched | fixed: one refetch on a media error (review and result), then the §7 page |
| 9 | low | Raw/Safe Cut radio arrows didn't move focus | fixed |
| 10 | low | No captions on the review player | fixed: WebVTT built from the transcript (escaped; property test) |
| 11 | low | §5.3 audit detail missing "where possible … stops publishing" | fixed. Rejected: the claimed open-weight sentence in §5.3: the spec has it only in landing step 3 |
| 12 | low | No virtualisation above 100 chips | accepted: all chips stay in the DOM so Tab order and screen readers see every one; 200 chips render without jank; content-visibility was removed because it clipped the ⋯ menu (round 1 #1) |
| 13 | low | The miss-loop row disappeared after it ran | fixed: stays once seen |
| 14 | low | Shortcut help reachable only by `?` | fixed: visible "Keyboard shortcuts" button |
| 15 | low | `mediaUrl` accepted `/\evil.com` | fixed: no backslashes; same-origin paths must not start with `//`; test |
| 16 | low | Focus dropped to `<body>` on /try step changes | fixed: focus moves to the new step |
