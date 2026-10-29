AUDITED_COMMIT: bb56bbe
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
