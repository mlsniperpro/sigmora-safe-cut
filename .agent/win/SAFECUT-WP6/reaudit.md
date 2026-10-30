AUDITED_COMMIT: c83e97a
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

## Round 3 (audited 7c03da4 / code 6d860ad by a Sonnet reviewer; every finding traced here before fixing; fixes in the next commit)

0 critical, 0 high, 1 medium, 10 low. The region proxy, /privacy, consent links and security surface were checked and found clean. None of the round 1–2 fixes regressed.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | Only `<video>` refetched on an expired signed URL; thumbnails, the Why keyframe, the download links and the receipt iframe didn't (UI-SPEC §10.7) | fixed: a failed thumbnail or keyframe refetches the job once (at most once a minute, however many fail together), and a fresh URL gets a new try; the result page refreshes its download/receipt links every 10 min (URLs live 15) without reloading the playing video or a loaded receipt; a receipt that doesn't load refetches once before "didn't load"; a failed background refresh keeps the page. Tests: JobPage (one refetch for many failing thumbnails), ResultPage ×4 with a fake clock and per-fetch signed URLs |
| 2 | low | Focus fell to `<body>` when the server acked "Cover it" (the optimistic chip remounts under its real ID) | fixed: focus follows the spot to the server's item; JobPage test |
| 3 | low | Cmd+Z did nothing on a Mac | fixed: Ctrl+Z or ⌘Z undo (works with single-key shortcuts off); help lists both; test |
| 4 | low | Mobile drawer "Keep clear" on an object: drawer close would steal focus from the confirm's Cancel | does not reproduce: the drawer is keyed by item, so closing unmounts the dialog without a `close` event. A JobPage test now pins focus on Cancel after three frames |
| 5 | low | /try poller stopped for good if the first GET after `/start` still said `created` | fixed: /try's poller (`useJob(id, {pollCreated: true})`) polls `created` like `processing`; job pages unchanged; hook test |
| 6 | low | A single 5xx on a poll replaced the whole page with the error page | fixed: with a job on screen, one 5xx retries after 2 s; a second in a row shows the §7 page; a first-load 5xx isn't retried; hook tests ×3 |
| 7 | low | Copy link: clipboard failure silent, rejection unhandled | fixed: "Couldn't copy. The link is selected: copy it from there." and the link is selected; tests for a refusal and for no Clipboard API |
| 8 | low | Side-by-side stills are drawn shapes but unlabelled once an API is configured | fixed: both captions say "Illustration with drawn shapes, not a measured result." Real stills wait on owner footage (BLOCKED.md) |
| 9 | low | Mock mode contradicted itself: "nothing leaves your browser" next to "It's sent to Meta"; the replay banner claimed a real run on a synthetic fixture | fixed: in mock mode the data bullets open with "In this preview nothing is uploaded … On the live service:", and the demo banner adds that its saved results are sample data (the §6 banner itself stays previewable); tests |
| 10 | low | README: "Cache Components" (it's off), missing /privacy, /unavailable, proxy; no Node/pnpm versions; no Playwright browser install | fixed |
| 11 | low | Privacy contact falls back to GitHub issues when `NEXT_PUBLIC_PRIVACY_CONTACT` is unset | owner input: already in BLOCKED.md (deploy env) |

## Round 4 (audited 153fac4 by a Sonnet reviewer; each finding traced here; fixes in the next commit)

0 critical, 1 high, 4 medium, 13 low. The round-3 changes held: no refetch loop, stale-ref or retry leak.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | high | Mock mode kept /try jobs only in memory: F5 or the copied review link gave "We couldn't find that clip" while the page said "You can leave this page" | fixed: `/try` jobs (data, edits, timeline) are stored in localStorage until their `deletes_at` (unreadable or full storage is ignored); fixture jobs still reset on reload; the review-link line says the preview link only works in this browser. `mock-backend.test.ts` ×4, ProgressView test |
| 2 | med | Result page "Try again" after a failed result load or two video errors did nothing | fixed: it refetches the result and restores the one-time retries; ResultPage tests ×2 |
| 3 | med | /try progress froze with no message once polling failed for good | fixed: the poller hands over to `/jobs/{id}`, whose §7 page offers Try again; TryFlow test |
| 4 | med | A timed-out `POST /start` dropped the job; §10.3 says polling resumes | fixed: the message shows, Start stays enabled, and a GET follows the job into progress if the server took it; a 409 on a re-pressed Start follows it as running; TryFlow tests ×2 |
| 5 | med | Open-weight (Baseten) line missing from the §5.3 audit detail and the results footnote; round 2 #11's rejection was wrong | fixed: `openWeightSentence` feeds step 3 and the §5.3 detail; the footnote adds the test-split clause once the hero's audit says the second opinion ran (`ResultsSection`). The spec's "where `audit.open_weight.status` is `ok`" is the condition, not copy. copy + landing tests |
| 6 | low | Signed-URL refresh was one-shot for the page's life (result video, review video, hero) | fixed: a source that loads re-arms its refresh; ResultPage, JobPage and landing tests |
| 7 | low | Mock jobs showed a fixed past `deletes_at` | fixed: now + 24 h for /try and fixture jobs and result fixtures; test |
| 8 | low | The ⋯ trigger couldn't close its own menu | fixed (blur to the trigger no longer closes first); test |
| 9 | low | Shortcut help said Enter opens Why? | fixed: "Select the focused chip (seek, pause and outline it)" (§3.8) |
| 10 | low | A keyframe refresh whose GET overlapped an edit was dropped | fixed: a GET discarded for a newer patch still hands over its signed URLs (`withFreshUrls`); test |
| 11 | low | "Download this version" (review bar, failed job) went stale; cross-origin `download` navigates away | fixed: a paused or stopped job page refetches quietly every 10 min (and on return to a tab after that long; a failed quiet refresh keeps the page); download links open a new tab; useJob test |
| 12 | low | No `<h1>` on job pages | fixed: review (visually hidden), progress, failed and message pages; tests assert exactly one per state |
| 13 | low | Copy-link outcome not reliably announced; "Copied" never reset | fixed: always-mounted status region, label resets after 2 s; test |
| 14 | low | Review URL couldn't wrap on narrow screens | fixed (`break-all`); test |
| 15 | low | Hero loading/failed states had no poster (§1.4) | fixed: poster while loading (mock knows it up front) and under the failure message; test |
| 16 | low | CSP blocked a plain-http local API in dev | fixed for `connect-src` only (dev builds); the README never claimed localhost, and media URLs must be https by schema anyway |
| 17 | low | Root README says "design docs only"; screenshots predate round 3 copy | screenshots refreshed from this commit's e2e run; the root README is outside WP6's paths: listed under "Requests for other WPs" in the PR |
| 18 | low | Mock mode ignores the picked clip without saying so | fixed: the data bullet says the clip isn't analysed and a built-in sample scene is reviewed; test |

## Round 5 (audited f56577e by a Sonnet reviewer; axe on 13 routes in light and dark at 320/390/desktop: 0 violations; each finding traced here; fixes in the next commit)

0 critical, 0 high, 1 medium, 9 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | The review video reloaded from 0:00 whenever a refetch re-signed `prepared_url` (every poll while rendering, any URL refresh); captions, thumbnails and the drawer keyframe churned too | fixed: polls keep the signed URLs on screen; only `refreshUrls` (a media or thumbnail error) and the 10-min quiet refresh take fresh ones. The player latches its source and switches only on an error, using a fresher URL already in hand before asking for one. useJob tests (signed per response), JobPage latch test |
| 2 | low | After a tab hide/show, the 10-min quiet refresh never ran again | fixed: showing the tab re-arms it for what's left of the interval; test |
| 3 | low | Captions never loaded under `pnpm dev` (StrictMode revoked the blob URL) | fixed: one blob URL per captions text, kept for the page's life; test |
| 4 | low | `POST /start` could still go out after Delete was confirmed during the upload (slow DELETE) | fixed: the confirm itself stops the upload and any start or navigation; deterministic test with a slow DELETE |
| 5 | low | A refusal whose `until` had already passed kept Start disabled for good; `Retry-After: 0` while polling could loop | fixed: a past time re-enables at once; polling waits at least one fast poll; test |
| 6 | low | Mock mode stored the typed access code in localStorage | fixed: only scripted mock codes are stored; test |
| 7 | low | Sample receipt said "Standard mode, store: false" and invented model versions | fixed in `receipt.html` and its generator: "requested with Standard model IDs only (never a Contributor model ID)", no versions |
| 8 | low | No h1 on the error, 404 and /try "Deleted" pages | fixed; tests |
| 9 | low | README cites `docs/UI-SPEC.md`, which isn't on this branch yet | fixed: README says where to read it until PRE-B merges |
| 10 | low | "Sent to Sigmora" shows without a delivery confirmation | kept: it's the spec's copy (§5.2), and `postMessage` has no receipt. A confirmation needs Sigmora to reply; listed under "Requests for other WPs" in the PR |

## Round 6 (audited f690e1f by a Sonnet reviewer; each finding traced here; fixes in the next commit)

0 critical, 0 high, 2 medium, 4 low. The round-5 changes held, except #1, which was a regression from round-5 #4.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | A DELETE that failed after the confirm stranded /try: navigation was suppressed for good, or the aborted upload froze on "Uploading" (regression from round-5 #4) | fixed: a confirmed delete only pauses things until it answers. Nothing is aborted or blocked for good unless it succeeds. If it fails, the upload carries on, `/start` goes out and a navigation held meanwhile is followed (§10.3 Delete row). TryFlow tests for both cases, which fail on the previous code |
| 2 | med | The review page's fixed bottom bar covered the footer (Privacy link) at the end of the page (WCAG 2.4.11, §7.1) | fixed: `body` is padded by the measured bar height (`--sticky-bottom`). e2e checks that the Privacy link clears the bar at full scroll on desktop and mobile (gap 32 px) |
| 3 | low | Access-code input border was about 1.5:1 (WCAG 1.4.11) | fixed: a `--field-border` token at 3.66:1 (light, on white) and 4.9:1 (dark) |
| 4 | low | The demo banner waited for the first poll instead of the `POST /v1/jobs` answer (§6) | fixed: the create response's `mode` is reported at once; test |
| 5 | low | κ shown with `toFixed(2)` could round up (AGENTS rule 9) | fixed: rounded down; test |
| 6 | low | The preview drew every cover as its box, though §3.6 says solid covers take the mask's shape | fixed: COCO RLE decoding (`rle.ts`, cached), solid/person_solid regions with a frame-sized mask fill run by run. A mask that doesn't decode or doesn't fit the frame falls back to the box, so the preview never covers less than the plan. Property test against an independent pycocotools-style encoder (2,000 masks), overlay tests |

## Round 7 (audited d4bb6a1 by a Sonnet reviewer, with real-browser probes; RLE decoder cross-checked against pycocotools 2.0.11 on 318 masks plus WP0's fixture, 0 mismatches; each finding traced here; fixes in the next commit)

0 critical, 1 high, 1 medium, 2 low, plus three of its notes acted on.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | high | On desktop the 750 px player was `sticky` (the `min-height` variant outranked `lg:static`) and covered the chip columns: at 1280×720 no chip could be hit and 30/30 focus stops were hidden. This dated from round 2 | fixed: sticky only below `lg` (`max-lg:` variants). e2e at 1280×720 and 1366×768: the player is static and 0 of 12 focused chip buttons are covered |
| 2 | med | `--sticky-top` padded scrolling by the player's height even when it wasn't sticky (short or zoomed screens), parking focus under the bottom bar | fixed: the player's and the bar's real computed position is measured, and re-measured on height breakpoint changes. On very short screens (< 480 px tall, 400% zoom) the bottom bar is no longer fixed: it sits at the end of the panel. e2e at 320×400 and 480×270: no top padding, 0 of 8 focused chips covered |
| 3 | low | A 429 on Try again (failed job) or on Delete (progress, failed, result) left the control enabled (§10.3) | fixed: a shared `useCooldown` holds the control until `Retry-After` (or 60 s); Try again uses the page's existing until-timer. JobPage tests |
| 4 | low | /try step C lacked the first frame (§2.3, §2.9) | fixed: the prepared clip's first frame, with no overlay, shows once `prepared_url` exists (/try and the job page); test |
| note | — | `reentry_of` was required but WP0's Track defaults it to None and may omit it, so a whole job could fail to parse | fixed: defaults to null; contracts test |
| note | — | A double-confirmed Delete could race; nothing showed while a DELETE was pending | fixed: Cancel and delete is disabled until the DELETE answers |
| note | — | §3.8's example name "Keep Plate 1 clear" | kept "Keep clear Plate 1": the accessible name must contain the visible label "Keep clear" (WCAG 2.5.3 Label in Name), which the spec's wording would break |
| note | — | "This version hasn't been fully checked." sits in the §5.3 banner rather than the bar | kept: it shows once, directly under the §5.3 message as the row says; the bar repeats it only when no audit banner exists |

## Round 8 (audited a847826 by a Sonnet reviewer; real-browser probes at 17 viewports including live resizes; each finding traced here; fixes in the next commit)

0 critical, 0 high, 1 medium, 3 low. The round-7 layout changes held: no horizontal scroll, footer reachable and focus never hidden at any probed size.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | On desktop the static player was full container width (about 750 px tall at 1280×720), so no chip showed on the first screen and the preview scrolled away while editing (§3.1) | fixed: the §3.1 layout. The player is on the left, at most 40% of the viewport tall; the Raw/Safe Cut switch and note sit beside it; the decorative timeline is capped at 24 rows. e2e at 1280×720 and 1366×768: the first chip row starts on screen (top 568 and 587) and the player stays in view with a chip focused |
| 2 | low | On narrow phones the open tab ("Needs you", the last) was clipped and focusing it didn't scroll it in | fixed: the strip scrolls sideways so the open or focused tab, focus ring included, is fully in it (never the page). e2e at 320 and 390 px |
| 3 | low | After a rate-limited or failed delete the trigger was disabled and focus fell to `<body>` (WCAG 2.4.3) | fixed: the delete error (`ActionError`) takes focus when it appears, on progress, failed, result and review. JobPage test |
| 4 | low | A stray `web/e2e-failure.png` from a debug run was committed | removed and git-ignored |

## Round 9 (audited da3d5da by a Sonnet reviewer; mock build and a live-API build against a faked https API; tabbed 45–70 stops per page at 11 viewports; axe on 28 pages, light and dark, 0 violations; about 1,200 random UI actions with 0 page errors; each finding traced here; fixes in the next commit)

0 critical, 0 high, 1 medium, 4 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | A refused Approve & render or Run the audit again (429, 401) was silent: the bar's text wasn't in a live region, and the disabled button dropped focus to `<body>`. A failed job's Try again lost focus too (WCAG 4.1.3, 2.4.3) | fixed: refusals, the cap line and action errors render as `ActionError` (`role=alert`, takes focus; `tone="plain"` for refusals). On a failed job the answers sit before the buttons, so Tab moves on from an answer to its button. JobPage test |
| 2 | low | While a confirmed delete was in flight on the progress page, focus sat on `<body>` (the opener was disabled before the dialog returned focus) | fixed: in flight the button is `aria-disabled` (looks disabled, ignores presses, keeps focus). The test setup's `dialog.close()` polyfill now fires `close` from a queued task as browsers do; it was synchronous, so focus return was never exercised in unit tests. JobPage test |
| 3 | low | The 24-row timeline cap dropped the selected item's bars past row 24 (§3.3) | fixed: the selection always gets a row (`timelineRows`); test |
| 4 | low | The top of a mobile tab's focus ring was clipped by the scrolling strip | fixed: the strip has top padding |
| 5 | low | Footer and landing bottom links were 20–24 px tall; §3.8/§9 ask 44 px on mobile, 32 px on desktop | fixed: `min-h-11 lg:min-h-8` |

## Round 10 (audited 663f6df by a Sonnet reviewer; fresh `git archive` build; 48 routes × 5 viewports × light/dark with axe: 0 violations, no overflow, one h1 each, no page errors; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low. The round-9 focus changes held: nothing steals focus on load, polls, re-renders, edits or resizes.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A second identical delete error (failed, progress, result) or code-cap line didn't remount, so it wasn't re-announced and focus fell to `<body>` | fixed: delete errors clear when an attempt starts; the bar's refusal and cap alerts are keyed by the press. JobPage tests for a repeated delete error and a repeated code-cap answer |
| 2 | low | Pressing Approve & render or Run the audit again disabled the focused button while busy, and focus never came back, even on success | fixed: busy buttons are `aria-disabled` (keep focus, ignore presses); once the render's progress shows, focus moves to it, unless the creator has moved elsewhere. JobPage test, stable over repeated runs |
| 3 | low | README-listed `/jobs/result-*/result` URLs showed a dead player and a blank receipt in mock mode (the fixtures' `example.invalid` URLs) | fixed: with sample media, result fixtures answer with the sample's video and receipt; mock-backend test |

## Round 11 (audited 7edc297 by a Sonnet reviewer; fresh archive build; live build against a faked https API end to end; axe on key routes in light and dark: 0 violations; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | On /try, Continue and Start were `disabled` while their request was out, so a refusal that keeps the step (429, 503, 5xx, 413, timeout) dropped focus to `<body>` (WCAG 2.4.3, §10.2) | fixed: busy Continue/Start are `aria-disabled` and ignore presses. e2e: a refused Continue keeps focus (this check fails on the previous build and passes now; jsdom doesn't blur a focused element when it's disabled, so the unit test alone can't tell) |
| 2 | low | Mock result fixtures played the 240-frame sample but said "12 of 12 frames checked" | fixed: in mock mode the result answer takes the sample's frame count; any gap the fixture's audit left unchecked stays unchecked. mock-backend test |
| 3 | low | The code-cap alert was re-keyed on the press, so a second press refocused and re-announced the old alert while the request was out | fixed: the alerts' key moves when an answer arrives. JobPage test: the button keeps focus while the second press is out, then the new answer takes it |

## Round 12 (audited 128d23b by a Sonnet reviewer; fresh archive build; 44 routes × 8 viewports × light/dark with axe (WCAG + best practice): 0 WCAG violations, no overflow, one h1 each; live build against a faked https API; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | Regression from round 11 #2: mock `/jobs/result-*/result` said "240 of 12 frames checked" (the result's frames came from the sample, the job's from the 12-frame hero fixture) | fixed at the source: with sample media, result fixtures' jobs are built on the sample job, so job, result and media are one clip (and "Back to review" lands on it). mock-backend test checks both |
| 2 | low | A refusal that disables Start on /try (401 on create, 429 daily cap or rate limit) still dropped focus to `<body>` | fixed: such a refusal takes focus itself (its alert box, which holds its actions). e2e with the `expired` mock code |
| note | — | README's mock-code table lacked `open-weight` | added |

## Round 13 (audited cd7913a by a Sonnet reviewer; fresh archive build; live build against a faked https API end to end; axe sweeps light and dark at 8 viewport sizes: 0 WCAG violations; each finding traced here; fixes in the next commit)

0 critical, 0 high, 1 medium, 3 low. Round-12 fixes held: the refusal box doesn't re-fire on re-render and wins over the step effect's target only for blocking refusals.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | med | In a live build, hero and result captions on the storage host never loaded: a cross-origin `<track>` needs a `crossorigin` video (WCAG 1.2.2, §1.5) | fixed without making the videos depend on CORS: `useRemoteCaptions` fetches the WebVTT and attaches it as a blob URL, and same-origin paths are used as they are. A 403, non-WebVTT body or CORS failure leaves the video playing without captions. README notes the bucket needs CORS GET (WP5). Hook tests |
| 2 | low | "Try again" after a failed upload unmounted its button, and a refused retry (non-blocking) left focus on `<body>` | fixed: focus moves to Start once the refusal clears. TryFlow test (fails without the fix) |
| 3 | low | Mock mode put the 8 s sample video under fixtures with a different clip (12-frame plans), so the overlay covered the wrong places | fixed: the sample is swapped in only for a fixture with the sample's frame count; others keep their unreachable URL, so the player honestly says the video didn't load. README calls the fixtures state viewers whose dates are their own |
| 4 | low | The landing "Try it" link was 39 px wide (§9 44×44) | fixed (`min-w-11`) |
| note | — | `mediaUrl` accepted "/\t/evil.com", protocol-relative once the browser strips the tab | hardened: whitespace and control characters are rejected; api test |

## Round 14 (audited 0381440 by a Sonnet reviewer; about 75 routes × 5 viewports × light/dark with axe: 0 WCAG violations, no overflow, one h1 each; live build against a faked https API, including an instrumented copy for the refresh race; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low. The round-13 changes held: cross-origin captions load as blobs with no CSP errors, failures leave the video playing, and no legitimate signed-URL shape is rejected.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A fresh-URL refetch cut short by another tick (a second refresh a frame later, or a poll) lost its "fresh" request, so the new signed URLs were dropped and the player stayed dead (reproduced 5 of 6 runs in an instrumented build) | fixed: an unanswered GET's fresh/quiet request passes on to the next one. useJob test (fails without the fix) |
| 2 | low | When a refetch gave back the same URL (mock fixtures, or a re-sign inside the same second), the video stayed a blank player with no message | fixed: the review player says the video didn't load if no fresh URL arrives within 10 s of asking; hero and result say so as soon as the refetch returns the failed URL. Tests for all three |
| 3 | low | /privacy contact link (20 px) and the demo banner's "What's demo mode?" (32 px) were under §9's 44 px on mobile | fixed (`min-h-11 lg:min-h-8`) |
| note | — | The result page's 10-min link refresh dropped and remounted the captions track, switching captions back on | fixed: the caption blob stays on show while a re-signed URL loads; identical text keeps the same blob. Hook test |

## Round 15 (audited 79b9b19 by a Sonnet reviewer; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low. Two were regressions from round 14's fixes.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A fresh URL that arrived after the review player's 10 s wait had given up (a slow refetch) was switched in but left the "didn't load" message over it | fixed: a late fresh URL clears the failure and gets its try. JobPage test (fails without the fix) |
| 2 | low | Round 14's carry-over let a quiet refresh cut short by an action's GET (resume) make that GET quiet too, so its failure was swallowed instead of retried and reported | fixed: the quiet flag carries over only while nothing polls, and resume clears it. useJob test (fails without the fix) |
| 3 | low | With reduced motion, the hero's "Play demo" button stayed over the video while it played, covering the controls | fixed: it shows only while the clip is paused, and pressing it moves focus to the player. Landing test (fails without the fix) and e2e checks for focus and visibility in Chromium |

## Round 16 (audited c57b904 by a Sonnet reviewer: about 60 routes at 320/390/1280 in light and dark with axe, every control measured with the drawer, toast, menu and dialogs open, a live build against a faked https API, URL edge cases and a 3×6×70-action random fuzz; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 6 low. The round-15 fixes and the c57b904 fixture-time shift held. Three findings (3–5) came from that shift.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A rejected review edit put the chip back in its old column and unmounted the one focus had followed, so focus fell to `<body>` (and on mobile the tab stayed on the column the chip had left) | fixed: on a failed edit, if focus was lost it goes back to the chip, or to its spot for a refused cover, and on mobile that chip's tab opens. JobPage test (fails without the fix) |
| 2 | low | Toast Undo (36 px) and the Why drawer's evidence ◀/▶ (39 px) were under 44 px wide on mobile | fixed with `min-w-11` (also the toast's other actions and the frame numbers). Root cause of a finding that recurred in rounds 9, 13 and 14: e2e now measures every control on mobile on landing, /try, review with the toast open, both Why drawers, result and privacy (fails on the old code with the auditor's exact sizes) |
| 3 | low | The shift kept the `expired` mock code's `valid_until` (Nov 3) ahead of now forever, so it could never say "expired" | fixed: expired codes end before the fixtures' moment (gen-mocks), and an e2e check reads "This code has expired." |
| 4 | low | Minute-rounded shifting turned day-boundary times into arbitrary clock times ("Nov 6, 10:24 AM") | fixed: the shift is whole days, rounded up, so midnights stay midnights and the cap's retry is always the next midnight ahead. mock-backend tests at five times of day; the suite passes with the clock moved −1, 0, +0.6, +10, +40 and +400 days |
| 5 | low | README still said fixture dates are the fixtures' own | fixed |
| 6 | low | A job link cut off mid-escape (`/jobs/abc%E0`) gave a bare 500 from Next's param decoding | fixed: `proxy.ts` sends an undecodable path to the not-found page (404). e2e check (fails on the old proxy with 500) |

## Round 17 (audited bb56bbe by a Sonnet reviewer: 87 routes × 320/390/1280 × light/dark with axe and target sizes, overlays open on six review fixtures, every /try code with 15 s hangs, a live build against a faked https API, the proxy and region rewrite, about 960 seeded random actions; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 5 low. #1 was a regression from round 16's fix, and #5 shows round 16's "always the next midnight ahead" was wrong for most of each day.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | On mobile, Try again on a rejected edit left the tab on the column round 16's refocus had opened, while the chip moved on out of sight; focus fell to `<body>` | fixed: Try again replays the rejected edit through the same path as the first press, so the tab and focus follow the chip (a confirmed keep and an undo too). Mobile JobPage test (fails on bb56bbe) |
| 2 | low | On mobile, Hide or Keep clear in the Why sheet swapped the pressed button away and focus left the still-open modal | fixed: focus moves to the button that took its place (the sheet's heading if none). e2e (fails on the old drawer) |
| 3 | low | The Why drawer's ◀/▶ became `disabled` at the ends, dropping focus out of the modal | fixed: `aria-disabled`, and presses at the end are ignored. e2e (fails on the old drawer) |
| 4 | low | Dismiss on the failed toast dropped focus to `<body>` | fixed: focus goes back to the chip the edit was about. Same JobPage test (fails without it) |
| 5 | low | Rounding the day shift up put a daily cap's retry a day late for about 14 of every 24 UTC hours | fixed: the shift is whole UTC days that put the fixtures' moment on today, so the cap's retry is always the next UTC midnight. mock-backend test at six times of day (fails on bb56bbe); a past `retry_later` retry only means the usual busy polling |

## Round 18 (audited b7ab493 by a Sonnet reviewer: 70 routes × 320/390/1280 × light/dark with axe and target sizes, every overlay state at 320/390, and an instrumented mock that fails, delays or passes each review edit, checking retry, undo, merge, remove, confirm and cover sequences; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 4 low. The round-17 sequences all held. All four findings are about where focus goes.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | On mobile, about 1 in 8 rejected edits left focus on `<body>`: the rescue opened the chip's tab from an effect, and the one-frame focus could run before that tab committed | fixed at the root: a focus request waits for the commit that mounts its chip (tried after every commit and on the next frame, lapsing after 1 s), so every focus path is covered, not only this one. Mobile JobPage test with frames that run before React's commit (fails on b7ab493) |
| 2 | low | Undo of a covered spot targeted the covering item, which the undo removes, so focus fell to `<body>` (and the mobile tab stayed on Hidden) | fixed: an undo that removes the item it created focuses the spot that comes back. JobPage test (fails on b7ab493) |
| 3 | low | On mobile, closing the Why sheet after its edit was rejected focused a chip that wasn't in the open tab | fixed: closing the sheet follows the chip, opening its tab. JobPage regression test (jsdom doesn't make the page behind a modal inert, so this test passes on the old code too; the change is one call, `follow` instead of `focusChip`) |
| 4 | low | A failed job's successful Try again unmounted the focused button with the failed view | fixed: once the job leaves `failed`, focus moves to the new view's progress unless the viewer moved on. JobPage test (fails on b7ab493) |

## Round 19 (audited a743ea2 by a Sonnet reviewer: 67 routes × 320/390/1280 × light/dark with axe and target sizes; a live build against a fake https API with fault injection on every job, result, /try and review request, plus signed-URL expiry; every /try mock code; the region rewrite; seeded focus fuzz watching every focusin; each finding traced here; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low. The round-18 fixes held, except that a lapsed focus request could still fire (#2).

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | The result page never re-armed its 10-minute link refresh after one failed, so the download links went stale (403) | fixed: a failed refresh re-arms the next one. ResultPage test (fails on a743ea2) |
| 2 | low | A focus request older than its 1 s lapse still fired if its chip mounted before any other commit cleared it (a late cover ack, then a tab change) | fixed: the lapse is checked first. JobPage test (fails on a743ea2) |
| 3 | low | Tab titles didn't follow the state shown (WCAG 2.4.2): the 404 page had the landing title, and every job and result state kept one static title. Also, a single 5xx on the demo left the hero on "didn't load" | fixed: the 404 page has its own title; job, result and error pages take their tab title from the h1 they show. The hero retries the demo once, 2 s after a 5xx. JobPage tests, a landing test and two e2e checks (each fails on the old code) |

## Round 20 (audited d4976bf by a Sonnet reviewer): CLEAN

0 critical, 0 high, 0 medium, 0 low.
- **Round-19 fixes:** each checked in a real browser.
  - The link refresh was driven for 35 minutes on a fake clock against a live build with failing and hanging GETs: one GET per 10 minutes, no loop.
  - Focus lapse checked.
  - Titles across every job, result and error fixture and a full navigation loop.
  - The hero retry under one, two and repeated 5xx, a 404 and a hang.
- **Also covered:**
  - URL edge cases.
  - 64 routes × 320/390/1280 × light/dark with axe, overflow, one h1 per page and 44 px targets (0 issues).
  - A dev server in two time zones (no hydration errors).
  - A full live-mode flow, keyboard shortcuts behind the open Why drawer, and the skip and hash links.
- **Two design limits, noted and not counted (no change, so the audited code stays as it is):**
  - A receipt URL answering 403/404 still fires the iframe's `load`, so the error body shows in the frame. Only a hung receipt reaches the "didn't load" message; the 10-minute refresh keeps URLs from expiring in normal use.
  - Some failed-job tab titles are long (the whole first sentence of the §2.6 copy).

## Round 21 (audited d4976bf by a Sonnet reviewer, re-diffed against UI-SPEC, WP0 `contracts.py`, ARCHITECTURE §3 and PRE-A API-NOTES §12, with a live build against a fake https API; each finding traced here; fixes in the next commit)

0 critical, 1 high, 1 medium, 6 low. This resets the clean count to 0. Earlier rounds checked behaviour, and the repo's own fixtures never used these WP0 values. Checking the contract field by field found #1 and #2.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | high | `audit.open_weight.model` was required as a string, but WP0's default is `{"model": null, "status": "off", …}` (ARCHITECTURE §3.8). Any live audit with the second opinion off would have failed the demo, job and result pages | fixed: `model` nullable, status ok/failed/off, counts default 0; an open_weight that can't be read counts as absent (it never blocks a job). WP0's `j_example` fixtures are now copied in and parsed by a contract test, with the §3.8 example verbatim (fails on d4976bf) |
| 2 | medium | `roles.missed[].point: null` (a box-only miss, valid in WP0) failed the whole job parse | fixed: `point` and `box` nullable. Also `Spot.covered_by` may be absent (WP0 defaults it). Same contract test (fails on d4976bf) |
| 3 | low | The Why drawer for audit-added and static items said "The keyframe didn't load" and showed keyframe captions for a frame Muse Spark was never shown | fixed: items with no keyframe (origin `audit_patch`, a review-time cover, or `static`) show only their origin's §4.3 caption. Two JobPage tests (fail on d4976bf) |
| 4 | low | A long unbroken file name scrolled the page sideways at 320 px (/try, progress, review header) | fixed: the names wrap. e2e at 320 px (fails on the old TryFlow by 91 px) |
| 5 | low | Two unfixed spots starting on the same frame both took the later leak's kind | fixed: a spot's kind comes from the leak rows that overlap its own box within its span (`spotKind`). view test (fails on d4976bf) |
| 6 | low | Durations rounded to nearest, so 59.6 s read "1:00" | fixed: whole seconds round down (§0). Unit test |
| 7 | low | The toast's focus ring was 2.57:1 (light) and 1.65:1 (dark) on its inverse surface | fixed: inside the toast the ring takes the toast's text colour (15.9:1). e2e reached by Tab, requiring `:focus-visible` (fails on the old CSS with 2.57) |
| 8 | low | The chip's kind had no icon, and the placeholder tile drew the state icon (§3.3) | fixed: six kind icons beside the kind word and on the placeholder tile (a pending cover keeps the state icon). JobPage test (fails on d4976bf) |

## Round 22 (audited a706ad0 by a Sonnet reviewer: contracts.ts against WP0 contracts.py, ARCHITECTURE §3, API-NOTES §12 and UI-SPEC §8 field by field, a live build fed WP0-shaped responses including a cover-spot ack with no `spot_id`, 87 routes × 320/390/1280 × light/dark with axe; each finding traced here; fix in the next commit)

0 critical, 0 high, 0 medium, 1 low. The contract check found no mismatch that would fail a real page, and round 21's fixes held.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A tracked item with no evidence frames (the roles stage failed, so there were no votes or keyframes) got the static-item caption, wrongly saying SAM 3.1 couldn't follow it | fixed: the caption goes by origin only. Audit-added and static items keep their §4.3 captions, and anything else reads "There's no keyframe for this item." JobPage test (fails on a706ad0) |

## Round 23 (audited e78b343 by a Sonnet reviewer: about 75 routes × 320/390/1280 × light/dark with axe, text-spacing and 200% font, a live build against a fake https API with fault injection, the region rewrite, Tab sweeps of 90 stops, drag-and-drop validation, and the main components read in full; fix in the next commit)

0 critical, 0 high, 0 medium, 1 low. The e78b343 caption change was confirmed correct.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | In forced colours (Windows High Contrast) the open mobile tab, the checked Raw/Safe Cut radio, the selected chip and the evidence-frame number lost their selected cue, and the accent buttons lost their edge: all were drawn with background colour or shadow | fixed with Tailwind's `forced-colors:` variant: the selected tab, radio and frame number use the system Highlight colours, the selected chip gets a 3 px border, and the accent buttons get a ButtonText border. (Correction, round 26: I first thought the Tailwind build drops a plain `@media (forced-colors: active)` block in globals.css. A clean build keeps it, so that was the stale incremental build cache found in round 26, which `pnpm build` now clears. The variants are fine either way.) e2e in a `forcedColors: "active"` context (3 checks, all fail on e78b343) |

Noted, not counted: at 320×640 with a tall bottom bar the 6 s edit toast overlaps the bar text; Undo stays reachable (seen before in round 21).

## Round 24 (audited 9dc64d8 by a Sonnet reviewer: side-by-side screenshots of 9dc64d8 and e78b343 in light and dark (no change outside forced colours); 67 routes × 320/390/1280 × light/dark with axe and targets; overlays; a live build against a fake https API covering every edit, render, poll, /try and demo failure; text-spacing overrides; fix in the next commit)

0 critical, 0 high, 0 medium, 1 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | The chip reason was clamped to two lines, so at 320 px 5 of 7 reasons on the sample were cut off (and some at 1280 under a text-spacing override); the full text was only in a hover title, the accessible name and the Why drawer | fixed: the reason shows in full. Decision: UI-SPEC §3.3's "One or two lines" describes the reasons' length, not a licence to hide text (WCAG 1.4.10/1.4.12), so a longer reason makes the chip taller. e2e at 320 px counts clipped reasons across all tabs (5 on the old code, 0 now) |

## Round 25 (audited b42eb33 by a Sonnet reviewer: long-reason builds at 11 viewports with real-Tab sweeps sampling every focused element against the sticky player and bar; 47 routes × 320/390/1280 × light/dark with axe; a live build; region rewrite; fix in the next commit)

0 critical, 0 high, 0 medium, 1 low (a regression from round 24's fix).

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | With the clamp gone, one long unbroken token in a chip reason (a URL or an ID) widened the page on phones: 29 px for a realistic URL at 320 px | fixed: the reason and the line below it wrap anywhere (`overflow-wrap: anywhere`). An e2e check at 320 px puts a long URL into a chip reason (253 px of sideways scroll on b42eb33, 0 now) |

Noted, not counted: the edit toast can cover part of a just-moved chip at 320×640 for its 6 s (the known transient overlap, Undo reachable). At 320×640, a chip taller than the ~179 px between the sticky player and the bar is centred when focused (it existed before round 24).

## Round 26 (audited ae9fca4 by a Sonnet reviewer: 87 routes × 320/390/1280 × light/dark with axe, overflow, one h1 and targets; text-spacing on every route; a live build with long-token reasons; region proxy; fix in the next commit)

0 critical, 0 high, 0 medium, 1 low. This is the same class as round 25, on a surface that fix didn't cover.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A long unbroken token (URL or ID) in API text scrolled the Why drawer sideways at 320 px (reason, Muse Spark's words, escalation evidence, transcript lines) | fixed for the whole class: `body` has `overflow-wrap: anywhere`, so any API text wraps, and flex and grid items can shrink around it. A new e2e sweep appends a long URL to every text block on six pages and in the Why drawer at 320 px, and fails if the page or any panel scrolls sideways. On ae9fca4 it failed all seven (up to +863 px); 7/7 pass now, with axe and the 44 px targets unchanged |

Found while fixing: an incremental `next build` (Turbopack's cache, with the Tailwind loader) once served stale CSS after a globals.css edit. It didn't reproduce on demand, but it can make local evidence wrong and could ship stale CSS from a cached deploy. `pnpm build` now clears `.next/cache` first, so every build compiles the CSS from source.

## Round 27 (audited 98d7555 by a Sonnet reviewer: mid-word breaks diffed against `overflow-wrap: normal` on ~100 routes at 8 widths; interactive states at 5 widths; a live build with fault injection on edits, renders and deletes; 87 routes × 3 widths × light/dark with axe; text-spacing; fix in the next commit)

0 critical, 0 high, 0 medium, 3 low. All three were regressions from round 26's `body { overflow-wrap: anywhere }`.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | The failed-edit toast split "Dismiss" ("Dismis/s") and squeezed "Try again" on phones | fixed: buttons, links, tabs, radios and menu items keep `overflow-wrap: normal`, so a control can't shrink below its longest word, while API text still wraps anywhere |
| 2 | low | The Why drawer's Close split ("Clos/e") at 320 px when the title wraps | fixed (same rule). The long-token e2e sweep now also fails if any control's label is split inside a word, and opens the drawer on a chip whose title wraps. It catches "Close" with the rule removed |
| 3 | low | "Delete everything now" split beside a failed-delete message at 320 px | fixed (same rule). The failed toast and failed delete can't be produced in the mock production build, so the e2e covers the class through the drawer case and the six-page sweep |

Lesson: a global text rule needs a check that controls stay whole, not just that text wraps. The sweep now checks both.

## Round 28 (audited b01cfee by a Sonnet reviewer: a live build with failures injected through a fake https API, old vs new CSS diffed for mid-word breaks and overflow on ~55 routes at 8 widths with interaction states, 100 routes × 3 widths × light/dark with axe; fixes in the next commit)

0 critical, 0 high, 1 medium, 1 low. Round 27's three cases are fixed at every width.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | A chip's ⋯ menu opened off the left edge of the screen when its trigger wrapped onto its own line (Face 8 at 1280, a full Needs-you row at 320): the menu is right-anchored and the trigger landed on the left (pre-existing, missed by rounds 1–27) | fixed: the trigger's wrapper is `ml-auto`, so a wrapped trigger stays at the row's right and the 256 px menu fits inside the chip. e2e opens every visible ⋯ at 320 (cafe, Needs you) and 1280 (sample) and requires the menu on screen. It fails on b01cfee at x=−183 and x=−131 |
| 2 | low | Round 27's `overflow-wrap: normal` on controls also stopped API text inside a control from wrapping, so a long token in a merge target's description or label overflowed (needs a URL or ID in Muse Spark text) | fixed: the API part of those labels sits in a `data-api-text` span that wraps anywhere. The long-token sweep now fills those spans and also runs in the merge dialog. That check can't fail on the old code (it had no such span to fill); the menu-name check shows the labels keep their exact accessible names |

## Round 29 (audited 99cf743 by a Sonnet reviewer: 819 menu opens over 15 fixtures at 13 widths in both columns and all tabs, 477 chip action rows at 9 widths, 378 route×viewport×scheme axe runs, text-spacing, forced colours, a live build, region rewrite, all /try codes; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low. Round 28's menu fix held at every width.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | The merge button rendered "Same asFace 1…": in the inline-flex button, round 28's two text runs became two flex items and the space between them collapsed (the accessible name was right) | fixed: the whole label is one run inside the wrapping span. e2e checks the rendered text reads "Same as …" (fails on 99cf743) |
| 2 | low | The ⋯ menu opens downward, so near the bottom its second item sat under the fixed bottom bar (about 65 of 819 opens; keyboard could reach it, a mouse had to scroll) | fixed: the open menu scrolls into view with `block: "nearest"`, which honours the page's scroll-padding for the bar. The menu e2e also requires every item to be uncovered (fails on 99cf743 for Face 4 at 1280) |

## Round 30 (audited 140bac7 by a Sonnet reviewer: the ⋯ menu placed near the top, middle and bottom of the band at 12 widths with keyboard open/close, 93 routes × 3 widths × light/dark with axe, forced colours, text-spacing, a live build with fault injection, region rewrite, and large default text sizes; fix in the next commit)

0 critical, 0 high, 1 medium, 0 low. Round 29's two changes were clean.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | At a large default text size (a browser font setting, not zoom), the review page's sticky player and fixed bar left no room on a phone: at 200% on 390×844 the free band was −48 px and no chip could be reached (WCAG 1.4.4). The px height gates (640/480 px) didn't grow with the rem-sized layers | fixed: the gates are in em (40em/30em) in the classes and in the matchMedia that measures them, so they rise with the text size. At 100% text nothing changes. e2e launches Chromium at 200% default text: the band and tab checks fail on 140bac7 (−48 px) and pass now (844 px free). A positive check keeps the phone's player sticky at 100% |

Noted, not counted: at 320 px with 200% text the header scrolls 8 px sideways (no content lost).

## Round 31 (audited 6ad7c81 by a Sonnet reviewer: the em gates at 5 text sizes × ~17 viewports including the exact boundaries and live resizes, real-Tab sweeps of 81 configs against both layers, 855 menu opens over 4 fixtures × 5 text sizes × 9 viewports, axe on 77 routes × 3 widths × light/dark, text-spacing, forced colours, a stateful live build, region proxy, copy against the spec; fixes in the next commit)

0 critical, 0 high, 1 medium, 1 low. Round 30's em gates were verified: the measured offsets match what is sticky and fixed at every size.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | At 125–200% default text the ⋯ menu's rem width (w-64) grew past the room left of its right-anchored trigger, so it ran off the left edge and cut its labels (phones, and the left column on desktop) | fixed: on open, the menu's max-width is capped to the room left of its trigger (minus 8 px). Its items already wrap. e2e at 200% text opens every ⋯ on a phone and requires the menu on screen (fails on 6ad7c81 at x=−179, w=512) |
| 2 | low | On short screens (landscape phones, 400% zoom, large text) the Why sheet's fixed header and footer left its scrolling body a 32–64 px sliver | fixed: below 36em of height the whole sheet scrolls and the body flows. e2e at 200% text on 844×390 checks the body isn't squeezed (the check relies on a new hook, so on the old code it errors rather than failing) |

Also: the e2e check "reduced motion: Play demo leaves while the clip plays" failed once in about ten runs, because it read the button the moment the video fired `playing`, before React re-rendered. It now waits up to 5 s for the button to go. It still fails if the button stays.

Noted, not counted: at 320 px with 200% text the landing figure scrolls 31 px sideways (the same family as round 30's header note). The toasts overlap the bar's 17 px top padding (no text hidden).

## Round 32 (audited 234db94 by a Sonnet reviewer: the Why sheet at 4 text sizes × 6 viewports with trap, Escape and scroll checks; 450 menu opens over 3 fixtures × 5 text sizes × 10 viewports; axe on 77 routes × 3 widths × light/dark; text-spacing; forced colours; a live build; region proxy; fixes in the next commit)

0 critical, 0 high, 1 medium, 2 low. Round 31's two changes held.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | At 125%+ default text on a 1024–1535 px screen, the JS layout query (px) picked the three columns while Tailwind's `lg:` (rem) kept their headings hidden and no tabs showed: three unnamed columns | fixed: one `DESKTOP_QUERY = "(min-width: 64em)"` (em, like `lg:`) for the review panel and the Why sheet, so JS and CSS switch together. e2e at 125% text and 1100 px requires named columns (fails on 234db94: no tabs, no visible headings) |
| 2 | low | The Why sheet's Expand/Collapse handle was invisible in forced colours | fixed: `forced-colors:bg-[CanvasText]` on the handle. e2e in forced colours (fails on 234db94) |
| 3 | low | A ⋯ menu left open while the screen turned kept its old width cap and ran off screen | fixed: the cap is recomputed on resize while open, and the listener is removed when the menu closes. e2e at 200% text turns the screen with a menu open (fails on 234db94 at x=−179) |

## Round 33 (audited 89e6512 by a Sonnet reviewer: JS vs `lg:` agreement at 5 text sizes × 18 widths including every 64em boundary ±1 (0 mismatches), live resizes across the breakpoint, 76 routes × 6 configs with axe, text-spacing with the drawer, region proxy over 16 path variants, a live build; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low. Round 32's three changes held.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | Crossing the desktop breakpoint (a tablet turning, a window resized) swapped tabs and columns and remounted every chip, dropping keyboard focus to the page | fixed: the panel remembers the last focused chip and, after the layout flips, gives it focus back in its tab (unless focus moved elsewhere). e2e focuses a chip at 800 px and resizes to 1280 and back (fails on 89e6512: focus to null) |
| 2 | low | At 175–200% text on a ≤360 px phone, a failed keyframe's message was cut off by its aspect-ratio box, and the Why sheet's title was squeezed to ~65–98 px beside Close ("Scr/een") | fixed: a failed keyframe drops the aspect ratio so the message sizes the box, and the sheet header wraps so Close goes below a long title. e2e at 200% text and 320 px (both fail on 89e6512: cut off; title 69 px) |

## Round 34 (audited f01e64d by a Sonnet reviewer: breakpoint refocus with chips, menus, the drawer and dialogs open; the sheet header at 5 text sizes × 320–1600 px; failed keyframes against a fake live API; 66 routes × 3 widths × light/dark with axe; Tab sweeps on 13 routes incl. forced colours; live /try failures; region rewrite; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | Round 33's breakpoint refocus kept a stale chip after the viewer clicked blank page (no focusin fires there), so a later flip pulled focus and scroll back to it | fixed: a pointerdown outside any chip forgets the remembered chip. e2e clicks away and flips the layout (fails on f01e64d: focus back on i_5) |
| 2 | low | At 200% text on a 320 px phone, the Why sheet's ◀ frames ▶ row overflowed by 22 px | fixed: the row wraps. e2e at 200% text and 320 px (fails on f01e64d: 22 px) |

## Round 35 (audited b2c083d by a Sonnet reviewer): CLEAN

0 critical, 0 high, 0 medium, 0 low.
- **Changes since round 34:** the header and landing at 100% text across 14–20 widths (320–1920) in light and dark, plus the mobile menu at 3 text sizes and 4 widths. The radiogroup's arrow keys (also in a live build). A read of the pointerdown refocus.
- **The rest of the app:**
  - repo e2e 142/142;
  - axe WCAG 2.2 A/AA on 53 routes × 320/390/1280 × light/dark (0 violations, one h1, no overflow, no target under 44 px);
  - text-spacing on 20 routes;
  - large default text (125–300%) on the landing, `?from=sigmora` and /try;
  - a live build covering /try and code-check faults, and copy against UI-SPEC §1.

Noted, not counted:
- With `?from=sigmora` at 320–326 px, "Back to Sigmora" wraps to a second header row (clean, better than squeezing).
- At 300% text (beyond 1.4.4's 200%) on 320 px, `/` and `/try` scroll 13–35 px sideways.
- The radiogroup has no Home/End (the arrow keys work).

## Round 36 (audited b2c083d by a Sonnet reviewer, with emphasis on what recent rounds covered least: copy against UI-SPEC §2.5–§10.4 line by line, the /try upload flow against a fake https API with slow, killed, stalled and 403 uploads, cancel and delete, the result page, keyboard, regions, 85 routes with axe, text-spacing, forced colours and 150/200% text; fixes in the next commit)

0 critical, 0 high, 0 medium, 3 low. This resets the clean count to 0 after round 35's clean.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | "You can leave this page" and the review link showed while the upload was still running; opening the link (or reloading) killed the upload and the job stayed `created` (§2.3 shows the note only after "✓ Uploading") | fixed: while uploading, the page says "Keep this page open until the upload finishes. Leaving now stops it.", the link comes once the upload is done, and the browser asks before a reload or close. ProgressView test (fails on b2c083d) |
| 2 | low | A 429 on Continue (code check) left Continue enabled; §10.3 holds the button until Retry-After (60 s without) for any POST but /review | fixed: Continue is aria-disabled for the cooldown (useCooldown) and ignores presses. The TryFlow test that expected an immediate retry encoded the bug; it now asserts the hold. The e2e checks the hold too |
| 3 | low | §2.7 calls for a "progress bar with percent" while uploading; only the percent text was shown | fixed: a `<progress>` (labelled "Upload progress") under the uploading row, with the percent kept. ProgressView test (fails on b2c083d) |

## Round 37 (audited b5ed253 by a Sonnet reviewer: the spec read line by line against the code, a fresh archive build in Chromium, and one live-mode build against a small fake https API; fixes in the next commit)

0 critical, 0 high, 1 medium, 4 low. CLEAN_AUDITS_IN_A_ROW stays 0. No regressions from round 36.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | The result video had captions only from a `captions_url` that no spec table defines; §5.5 and §9 want captions from the transcript whenever the source had speech | fixed: the result page builds them from the job's transcript (as the review page does) whenever no captions file is given or until it loads. ResultPage test with a `/result` stripped of `captions_url` (fails on b5ed253) |
| 2 | low | `resultResponseSchema` required top-level `status` and `frames`, which §8/§5.6 don't give `/result`, so a spec-shaped answer showed the error page | fixed: both optional; the frame count falls back to the job's, then to `frames_scanned`, as the review banner already does. Same ResultPage test (fails on b5ed253) |
| 3 | low | `?from=sigmora` and `?demo=1` were dropped moving from `/try` to `/jobs/{id}`, and "Review them" / "Back to review" dropped `demo` (§10.4) | fixed: `/try` appends `keptQuery` at navigation time (read from `location`, so `/try` stays static), and the result links use it. TryFlow and ResultPage tests (fail on b5ed253) |
| 4 | low | The Why drawer said "No speech is linked to {label}." for a linked speaker whose lines fell outside the first four overlapping turns or outside the window (§4.3) | fixed: the footer shows only when no speaker is linked, and within the four-line cap the linked speaker's lines are picked first, then shown in time order. Three speechSection tests (fail on b5ed253) |
| 5 | low | Unfixed-spot (U) chips had no ⋯ menu, so no "Jump to first appearance" (§3.1, §3.8) | fixed: spot chips get the menu with Jump only. view test (fails on b5ed253) |

Every new test was run against b5ed253's code (fixes stashed) and fails there: 7 tests. On the fix commit: `checks.sh` exit 0, 867 tests, e2e 143/143.

## Round 38 (audited 4a5bb7c by a Sonnet reviewer: a live-mode build against a fake https API answering every request with only the spec-named fields, every navigation and redirect for `from`/`demo`, and round 37's changes; fixes in the next commit)

0 critical, 0 high, 4 medium, 1 low. CLEAN_AUDITS_IN_A_ROW stays 0. No regressions from round 37. The four mediums are one class, which round 37 fixed only for `/result`'s `status` and `frames`: a schema demanding a field the spec never gives that response. I checked every response schema for the same thing.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | `actionAckSchema` required `job_id`; the 202 ack is `status` and `stage` (render-ack.json, audit-ack.json, ACTION_ACK), so Start, Approve & render, Run the audit again and a failed job's Try again showed the error page against a spec-shaped server | fixed: optional (nothing reads it). contracts test (fails on 4a5bb7c) |
| 2 | medium | `reviewAckSchema` required `edit_id`; §8 Edits gives the ack `items`, `plan`, `status`, `has_render` and `audit.spots`, so every edit was rejected and reverted | fixed: optional; the page matches acks by the request's own `edit_id`. contracts test (fails on 4a5bb7c) |
| 3 | medium | `demoResponseSchema` required `hero_id`, which request 19 doesn't give, so the landing hero showed "The demo video didn't load" | fixed: removed (nothing read it). contracts test (fails on 4a5bb7c) |
| 4 | medium | `resultResponseSchema` still required `job_id` | fixed: optional; Publish to Sigmora sends the route's job ID, like every request. contracts and ResultPage tests (fail on 4a5bb7c); the publish test now expects the route's ID |
| 5 | low | Without a `models` map the Why drawer's Details listed a fixed "Muse Spark 1.3 · SAM 3.1 · Muse Voice Transcribe", even when the job's passes named other models (§4.3: the receipt-style list) | fixed: the list comes from `models`, else from `roles.model`, `scene.model`, SAM 3.1 when there are tracks (§4.3's copy names it) and `transcript.source`; the line is left out when none is named. model test (fails on 4a5bb7c) |

Also fixed, from the auditor's "noted, not counted" list: "Try another clip" and "Upload again" (expired, not found, deleted, created, failed and the `job_cap` bar) now keep `from` and `demo`, so a Sigmora user keeps "Back to Sigmora" (§0). JobPage tests (fail on 4a5bb7c).

Noted, not counted (no spec field to build from, or by design): in live mode the hero poster and hero captions come only from the non-spec `poster_url`/`captions_url` (a WP8 static asset or a first-frame poster is the fix, listed for WP5/WP8); `POST /v1/jobs` sends `file_name`, which request 17 doesn't list; `eta_s` isn't defined in the spec, so "~N s left" shows only when WP5 adds it (already requested); a linked speaker with no overlapping turns shows the heading with no lines (the spec is silent); the mobile tab strip scrolls by design.

On the fix commit: `checks.sh` exit 0, 875 tests, e2e 143/143.

## Round 39 (audited 867bece by a Sonnet reviewer: round 38's spec-shaped live flow end to end, an error-body matrix for every request against the §2.6/§10.3 tables, signed-URL expiry in live mode, and §2, §5, §7 and §9 copy line by line; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low. CLEAN_AUDITS_IN_A_ROW stays 0. No regressions from round 38.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | Time-gated buttons on the failed-job page (Try again after a 429 `Retry-After`, Try again tomorrow until `retry_at`) and the needs_you "Run the audit again" (`daily_cap` until `retry_at`) re-enabled up to 15 s late: `useNow(15_000)` only ticked every 15 s (§10.3 "disabled until `Retry-After`", §2.6 "disabled until `retry_at`") | fixed: `useNow` also wakes right at each deadline it is given; FailedJob passes `retry_at` and the Retry-After time, ReviewPanel passes `retry_at`. useNow test with fake timers (fails on 867bece) |
| 2 | low | A failed job's Try again stayed on screen, disabled for good, when a retry got `429 daily_cap` under the §2.6.1 expiry rule ("hidden with the job-page cap line expiry string") | fixed: hidden in that case, with the expiry line (which takes focus). JobPage test (fails on 867bece) |

On the fix commit: `checks.sh` exit 0, 878 tests, e2e 143/143.

## Round 40 (audited 9c46081 by a Sonnet reviewer: cover-spot, merge and remove-person end to end in live mode with spec-correct acks, every timer and time gate, keyboard-only and screen-reader passes, and every mock access code; fixes in the next commit)

0 critical, 0 high, 0 medium, 1 low. CLEAN_AUDITS_IN_A_ROW stays 0. No regressions from round 39.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A failed job's Try again after `429` with `Retry-After: 0` (or a past HTTP-date) stayed disabled until the next 15 s tick: `useNow` dropped deadlines already due instead of waking (§10.3) | fixed: a due deadline wakes at once. useNow test (fails on 9c46081) |

Also fixed, from the "noted, not counted" list: the audit-added chip's accessible name read "…covered it.." (the reason already ends a sentence); chip names and the Why drawer's reason now add a full stop only when the text has none. view test (fails on 9c46081).

Also fixed in a follow-up commit: ←/→ on the Why drawer's keyframe changed the frame without an announcement; the "Frame at …" caption is now a polite live region. JobPage test (fails without it).

Noted, not counted: WP5 must send `Access-Control-Expose-Headers: Retry-After` for the UI to read it cross-origin (without it the UI holds the 60 s default, which §10.3 allows).

On the fix commits: `checks.sh` exit 0, 881 tests, e2e 143/143.

## Round 41 (audited 3c5f1ea by a Sonnet reviewer: the landing page end to end at 320–1280 px in light, dark and reduced motion, the README and docs from a fresh archive, and the review panel on the mock hero and sample jobs as a first-time user; fixes in the next commit)

0 critical, 0 high, 1 medium, 1 low. CLEAN_AUDITS_IN_A_ROW stays 0. No regressions from round 40; the app code, README and docs were clean. Both findings are in the synthetic sample scene's generated media and plan.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | medium | The landing hero's "Safe Cut" video and the side-by-side "Safe Cut" still showed the passer-by's face clearly, against §1.3's "the plate and the passer-by are hidden": `samplePlan` took the pixelate cell from the face's first box, clipped at the frame edge where the passer-by enters, so cells were 4 px on a 78 px face | fixed: the cell follows the item's largest box (22 px for the passer-by); `redacted.mp4`, `safe-cut.jpg` and `job-review-sample.json` regenerated, and the screenshots in `web/docs/screenshots/` re-shot from the e2e (the old landing shot showed the face). view test: every pixelate cell is at least an eighth of its box on every frame (fails on 3c5f1ea's mock); frames checked by eye |
| 2 | low | Frames 140–175 drew the passer-by larger and higher (crossing in front of the guest) while the tracks and plan kept the small head, so the face showed beside its cover, against the README's "boxes, plan and pixels agree" | fixed: `entitiesAt` returns the in-front geometry for those frames and `gen-sample.mjs` draws from it, so the tracks, plan and render follow the drawn head. view test on face:3's boxes (fails on 3c5f1ea's mock) |

Noted, not counted: toggling Raw / Safe Cut on a paused hero resumes playback (§1.5 only says switching keeps the time). `public/sample/` isn't drift-checked the way the mocks are (`gen-sample.mjs` needs ffmpeg); its plan is, through `job-review-sample.json`.

On the fix commit: `checks.sh` exit 0, 883 tests, e2e 143/143.

## Round 42 (audited f76be71 by a Sonnet reviewer: all 240 frames of `redacted.mp4` against `prepared.mp4` and the plan, every still, keyframe and screenshot against its caption, and the review overlay read back every 3 frames at three player sizes; fixes in the next commit)

0 critical, 0 high, 0 medium, 2 low. CLEAN_AUDITS_IN_A_ROW stays 0. Round 41's media fixes hold: every hidden head lies inside its cover on every frame, the guest stays clear, and the overlay lines up at every size.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | After a paused seek (Enter or a click on a chip, a scrub) a pixelate cover could stay drawn solid until playback or the toggle: the seek's frame callback can fire while `readyState` is 1, when the overlay can't sample the frame, and nothing redrew on `seeked` (§3.6: covers take the render's style). Same area covered, so nothing leaks | fixed: the player redraws on `seeked` and `loadeddata`. VideoPane test (fails on f76be71). The new e2e check of a mosaic after a chip seek passes on both commits in this sandbox (the auditor's timing didn't reproduce here), so it stays as a regression guard only |
| 2 | low | The Set-of-Mark keyframes' person labels overprinted the face labels at the same corner ("pface:3 2", "peface:8"), also in the chip thumbnails (§4.3's burned-in track IDs) | fixed: person labels sit at the bottom of their box; `som/*.jpg` regenerated and the screenshots re-shot. Checked by eye on frames 75 and 195 |

On the fix commit: `checks.sh` exit 0, 884 tests, e2e 144/144.

## Round 43 (audited c83e97a by a Sonnet reviewer: the whole app in mock mode and against a spec-shaped fake https API, round 42's changes, every fixture route, keyboard shortcuts, axe on 9 routes at 2 widths, the frame-reference rewrite and the RLE decoder; fixes in the next commit)

0 critical, 0 high, 0 medium, 1 low. CLEAN_AUDITS_IN_A_ROW stays 0. The rest of the app was clean.

| # | Sev | Finding | Status |
|---|---|---|---|
| 1 | low | A regression from round 42: the `seeked` redraw mapped the frame from `currentTime`, so a paused scrub landing in the last quarter of a frame drew the next frame's covers (§3.6 maps the presented frame's `mediaTime`). The same cause, already present before round 42, also hit the paused redraws on the Raw/Safe Cut toggle, an edit, the selection and a resize. Preview only; the render is unaffected | fixed: the player remembers the presented frame's `mediaTime` from the frame callback (cleared when a seek starts) and every paused redraw maps that, with `currentTime` only before a frame is presented or without rVFC. VideoPane test (fails on c83e97a with frame 203 for 202) and an e2e check at 0.8 into frame 202, after the seek and after the toggle (fails on c83e97a's build after the toggle); the e2e ran green three times |

Noted, not counted: the auditor suspected that an ack for a later edit arriving before an earlier edit's ack could revert the later one, but did not reproduce it; the model-based agreement fuzz (interleaved acks and rejects over pending edits) finds client and server state agreeing.

On the fix commit: `checks.sh` exit 0, 885 tests, e2e 145/145.
