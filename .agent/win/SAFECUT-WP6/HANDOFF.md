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
- Audit round 8 (on a847826): 1 medium and 3 low, all fixed in the round-8 commit. Highlights:
  - The §3.1 desktop layout, with the player capped and the chips on the first screen.
  - The tab strip reveals the open tab.
  - A delete error takes focus.
- On the round-8 commit: 801 tests, e2e 87/87, `checks.sh` exit 0. Screenshots refreshed.
- Audit round 9 (on da3d5da): 1 medium and 4 low, all fixed in the round-9 commit. Highlights:
  - Refused actions are announced and take focus.
  - An in-flight delete keeps focus.
  - The selected item always has a timeline row.
  - Bigger link targets.
- On the round-9 commit: 804 tests (28 files), e2e 87/87, `checks.sh` exit 0.
- Known stale asset: `web/docs/screenshots/review-flow.gif` predates the round-8 desktop layout; the JPG screenshots are current.
- Audit round 10 (on 663f6df): 3 low and nothing higher, all fixed in the round-10 commit. Findings are getting fewer and lower round by round.
- On the round-10 commit: 808 tests (28 files), e2e 87/87, `checks.sh` exit 0.
- Audit round 11 (on 7edc297): 3 low, all fixed in the round-11 commit (focus on /try refusals, mock frame counts, alert keying). On that commit: 809 tests, e2e 88/88.
- Lesson: jsdom keeps focus on a button that becomes `disabled`, while real browsers drop it to `<body>`. Focus-loss fixes need an e2e check, not only a unit test.
- Audit round 12 (on 128d23b): 2 low, fixed in the round-12 commit. On that commit: 809 tests, e2e 89/89.
- Audit round 13 (on cd7913a): 1 medium (cross-origin captions) and 3 low, all fixed in the round-13 commit. On that commit: 815 tests (29 files), e2e 89/89.
- Audit round 14 (on 0381440): 3 low, fixed in the round-14 commit (refresh race, dead player on a same-URL refetch, two touch targets). On that commit: 820 tests, e2e 89/89.
- Audit round 15 (on 79b9b19): 3 low (two were regressions from round 14), fixed in the round-15 commit (late fresh URL, quiet flag leaking into resume, reduced-motion Play demo button). On that commit: 823 tests, e2e 93/93, `checks.sh` exit 0.
- Self-found on 2026-10-28: the fixtures' absolute dates started to pass (a daily cap's `retry_at` of 2026-10-28T00:00Z made a JobPage test flaky; the "code isn't active yet" test would have flipped on Nov 5, and the mock demo would have done the same during judging). MockBackend now shifts every fixture timestamp by (now − 2026-10-27T10:00Z), so the fixtures behave as written on any date. The suite was run with the clock moved −1, +10, +40 and +400 days: all pass. 825 tests, e2e 93/93.
- Audit round 16 (on c57b904): 6 low, fixed in the round-16 commit (rejected-edit focus, two narrow buttons plus an e2e sweep of every mobile control, the shift now whole days with expired codes kept expired, README, a cut-off percent-escape 500). On that commit: 828 tests, e2e 102/102, `checks.sh` exit 0.
- Audit round 17 (on bb56bbe): 5 low (one a regression from round 16), fixed in the round-17 commit (retry follows the chip on mobile, focus kept in the Why sheet and on ◀/▶, Dismiss refocuses, cap retry on the next UTC midnight). On that commit: 829 tests, e2e 104/104, `checks.sh` exit 0.
- Lesson: focus findings keep coming from controls that unmount or disable under focus. Before pushing a UI change, check every button that can disappear or become disabled while focused.
- Self-found from that sweep: a failed job's Try again was `disabled` while its request was out, dropping focus in a real browser. Now aria-disabled, with an e2e check (fails on the old code). Every other `disabled` that changes under focus was checked: each is followed by an alert that takes focus. On that commit: 829 tests, e2e 105/105.
- Audit round 18 (on b7ab493): 4 low focus findings, fixed in the round-18 commit. Root cause of #1: the one-frame focus could run before the commit that mounts the chip; `focusChip` now waits for that commit. On that commit: 833 tests, e2e 105/105, `checks.sh` exit 0.
- Audit round 19 (on a743ea2): 3 low, fixed in the round-19 commit (the result link refresh re-arms after a failure, the focus lapse is checked first, tab titles follow the h1, the hero retries a 5xx once). On that commit: 840 tests, e2e 107/107, `checks.sh` exit 0.
- Audit round 20 (on d4976bf): CLEAN, the first.
- Audit round 21 (on d4976bf, re-diffed against WP0's contracts): 1 high, 1 medium and 6 low, all fixed in the round-21 commit. CLEAN_AUDITS_IN_A_ROW is back to 0. Lesson: the client's schemas are now tested against WP0's own `j_example` fixtures, so a contract mismatch fails `pnpm test`. On that commit: 857 tests, e2e 110/110, `checks.sh` exit 0. The break-it run on d4976bf (fresh clone and FUZZ_RUNS=100000, both passing) has to be redone on the final commit.
- Audit round 22 (on a706ad0): 1 low (the no-keyframe caption for a tracked item when the roles stage failed), fixed in the round-22 commit. The field-by-field contract check was clean. On that commit: 858 tests, e2e 110/110.
- Audit round 23 (on e78b343): 1 low (forced-colours selection cues), fixed in the round-23 commit with `forced-colors:` variants. (I first blamed Tailwind for dropping a plain forced-colors media block. A clean build keeps it: that was the stale build cache, see round 26.) On that commit: 858 tests, e2e 113/113.
- Audit round 24 (on 9dc64d8): 1 low (chip reasons clamped at 320 px), fixed in the round-24 commit. The reason now shows in full. On that commit: 858 tests, e2e 114/114.
- Audit round 25 (on b42eb33): 1 low (a long token in an unclamped reason widened the page), fixed in the round-25 commit with `overflow-wrap: anywhere`. On that commit: 858 tests, e2e 115/115.
- Audit round 26 (on ae9fca4): 1 low (the same long-token class, in the Why drawer). Fixed for the whole app in the round-26 commit (`body { overflow-wrap: anywhere }`), with an e2e sweep. Gotcha: an incremental build once served stale CSS, so `pnpm build` now clears `.next/cache`. On that commit: 858 tests, e2e 122/122.
- Audit round 27 (on 98d7555): 3 low, all from round 26's global wrap (button labels split mid-word in tight rows). Fixed in the round-27 commit: controls keep `overflow-wrap: normal`, and the e2e sweep checks for split labels. On that commit: 858 tests, e2e 122/122.
- Audit round 28 (on b01cfee): 1 medium (the chip ⋯ menu off screen when its trigger wraps, pre-existing) and 1 low (API text inside controls), fixed in the round-28 commit. On that commit: 858 tests, e2e 125/125.
- Audit round 29 (on 99cf743): 2 low (the merge label's space, menu items under the bar), fixed in the round-29 commit. On that commit: 858 tests, e2e 127/127.
- Audit round 30 (on 140bac7): 1 medium (at large default text, the sticky player and bar covered the phone screen), fixed in the round-30 commit with em media gates. On that commit: 858 tests, e2e 130/130.
- Audit round 31 (on 6ad7c81): 1 medium (the ⋯ menu off screen at large text) and 1 low (a squeezed Why sheet on short screens), fixed in the round-31 commit, with a flaky e2e wait fixed too. On that commit: 858 tests, e2e 132/132.
- Audit round 32 (on 234db94): 1 medium (the JS layout query in px against Tailwind's rem) and 2 low, fixed in the round-32 commit. All layout gates now follow the text size. On that commit: 858 tests, e2e 135/135.
- Audit round 33 (on 89e6512): 2 low (focus lost crossing the breakpoint; the Why sheet at 200% on 320 px), fixed in the round-33 commit. On that commit: 858 tests, e2e 138/138.
- Audit round 34 (on f01e64d): 2 low (a stale chip refocus after a click away; the frame row at 200%/320 px), fixed in the round-34 commit. On that commit: 858 tests, e2e 140/140.
- Self-sweep after round 34: I probed every page and every Why sheet at 200% text on 320 and 360 px. I fixed the header (8 px) and landing hero (31 px) overflows earlier rounds had only noted; the probe is now clean. On that commit: 858 tests, e2e 142/142.
- Audit round 35 (on b2c083d): CLEAN.
- Audit round 36 (on b2c083d): 3 low (the leave note during upload, a 429 on Continue, no upload progress bar), fixed in the round-36 commit. CLEAN_AUDITS_IN_A_ROW is back to 0. Break-it on b2c083d passed (fresh clone 858 tests + e2e 142/142; FUZZ_RUNS=100000, 300,000 sequences, 385 s) but has to be redone on the final commit. On the round-36 commit: 861 tests, e2e 143/143.
- Audit round 37 (on b5ed253): 1 medium (no result captions without a `captions_url`) and 4 low (a strict `/result` schema, `from`/`demo` dropped from /try to the job page, a false "No speech is linked" footer, no ⋯ on U chips), fixed in the round-37 commit. On that commit: 867 tests, e2e 143/143.
- Audit round 38 (on 4a5bb7c): 4 medium (response schemas demanding fields the spec doesn't give: the 202 ack's `job_id`, the review ack's `edit_id`, the demo's `hero_id`, `/result`'s `job_id`) and 1 low (a fixed model list in the Why drawer), fixed in the round-38 commit with the /try links' kept query. Break-it passed on 4a5bb7c but is void now. On the round-38 commit: 875 tests, e2e 143/143.
- Audit round 39 (on 867bece): 2 low (time-gated retry buttons up to 15 s late; a failed job's Try again not hidden under the expiry rule), fixed in the round-39 commit. Break-it passed on 867bece (875 tests, e2e 143/143; 300,000 fuzz sequences, 340 s) but is void now. On the round-39 commit: 878 tests, e2e 143/143.
- Audit round 40 (on 9c46081): 1 low (Retry-After: 0 held Try again until the next 15 s tick), fixed in the round-40 commit with a doubled full stop in chip names. Break-it passed on 9c46081 (878 tests, e2e 143/143; 300,000 fuzz sequences, 354 s) but is void now. On the round-40 commit: 880 tests, e2e 143/143.
- CLEAN_AUDITS_IN_A_ROW is 0. Two clean full audits are still needed, then a fresh break-it.md (fresh clone + FUZZ_RUNS=100000).

## Next steps, in order
1. Run the next full audit round on HEAD (round 41 is next). If it finds anything, fix it and reset CLEAN_AUDITS_IN_A_ROW to 0. Repeat until two consecutive audits find nothing. Then set AUDITED_COMMIT to the last code commit and CLEAN_AUDITS_IN_A_ROW to 2.
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
