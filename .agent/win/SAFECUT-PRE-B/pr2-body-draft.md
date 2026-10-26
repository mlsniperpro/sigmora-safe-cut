The PRE-B work package: docs only, before kickoff (`date -u` when this session took over: Sun Oct 25 08:09 UTC 2026; kickoff is Oct 26 16:00 UTC). Every file is Markdown in the paths PRE-B owns, plus `docs/BLOCKED-PRE-B.md`, `docs/WIN-CHECKLIST-PRE-B.md` and `docs/HANDOFF-PRE-B.md`. No code, config or scaffolding. Branch `pre-b-product`, as the WP names. **Budget used: $0**, with no API calls.

`.agent/win/SAFECUT-PRE-B/LEASE` is session hand-off state that the owner's PICK UP instruction requires (PRE-A keeps the same kind of file). It's not a deliverable: **remove `.agent/` before this PR merges.**

## What's in it

| File | What |
|---|---|
| `docs/labeling/LABELING-GUIDE.md` | The `should_hide` question, 9 categories (child = may be under 18), who counts as a participant, box conventions, which tools may draw ground-truth boxes, **31 worked edge cases**, difficulty tags, the two-labeller agreement procedure, resolving disputes (A and B together, no deciding vote), privacy rules (real-public clips only in the owner's custody) |
| `docs/labeling/CVAT-SETUP.md` | Self-hosted CVAT v2.80.0: the build box (owner custody; test clips labelled in person, never tunnelled), projects per split, track/interpolation workflow, MOT 1.1 export behaviour answered from v2.80.0's source (§7.1) |
| `docs/labeling/LABEL-FORMAT.md` | Label JSON field by field (EVAL.md §1 schema), four file kinds (resolved, A, B, A2 for plan R3), the two-clock time model from PRE-A §5b (with step 4's exact `Fraction` arithmetic), MOT conventions, a validator spec (LBL001–LBL045 incl. LBL035), valid/invalid vectors V1–V7 (+V6b) and X1–X30, test vectors (M, R, O, K1–K5), a fully worked 10 s example |
| `docs/labeling/SCHEDULE.md` | Hours per clip, the 12 test / 3 dev / 3 hero split (binding for WP0/WP7), the test split's mean clip ≤ 30 s, dev tuning inside WP2's $15, people time ≈ 25 h, fallback plans R1–R4 (default R4 → R1) |
| `docs/UI-SPEC.md` | Every WP6 screen with desktop/mobile wireframes, the full copy deck, the two refusal patterns (§2.6.1), states, the review bar (§3.5), keyboard and WCAG 2.2 behaviour, the field map to ARCHITECTURE §3, fixtures, the reducer, and **23 requests to other WPs** |
| `docs/STORYBOARD.md` | 20 shots timed to 2:50, placeholders that each trace to a committed `metrics.json`, the Nov 3 screen recordings and their $12 recording-code budget, pre-export checks |
| `docs/PILOTS.md` | Target profiles, outreach drafts (DM 106 words, email 113, placeholders as one word), consent and data note, the timed protocol, the $6-per-code / $20 caps, how results are reported (anonymous-only credits with ≤ 2 pilots) |
| `docs/RULES-CHECKLIST.md` | Rule areas with an action for every answer, plus cut plans down to 2:00 |
| `docs/BLOCKED-PRE-B.md` | Only what the owner must physically do, each with a default, a date, and the exact secret entries (codes without dates: each kind's window applies) |
| `docs/WIN-CHECKLIST-PRE-B.md` | Every judging criterion, deliverable and audit finding (#1–#598) mapped to evidence; 0 unchecked lines |

## State of the art: the core choices and why

**Ground truth: manual keyframes every 15 frames with linear interpolation, in self-hosted CVAT.** CVAT's "Segment Anything 2 Tracker" is rejected for ground truth: CVAT's docs list it only for CVAT Online/Enterprise or a separate agent, it tracks polygons and masks rather than rectangles, and, most importantly, Safe Cut is built on SAM 3.1, so SAM-drawn ground truth would inherit exactly the late starts and dropped masks the exposure metric has to catch. CVAT's OpenCV TrackerMIL (not a Meta model) is allowed as a draft aid.

**Agreement:** raw percent, Cohen's κ and the 2×2 counts, reported together, because κ alone is low under skewed prevalence (Feinstein & Cicchetti 1990). Under plan R3, a blind second pass is reported as intra-rater agreement, never as κ between labellers.

**Review overlay:** `requestVideoFrameCallback`, with `mediaTime` mapped to a prepared frame by `floor(mediaTime × fps + ¼)` on the constant-frame-rate prepared clock (PRE-A §5b), falling back to `requestAnimationFrame` with a visible note.

**Accessibility:** WCAG 2.2 AA, including SC 2.5.8 (24×24 minimum; we use 44 px on mobile, 32 px on desktop), 2.4.11, 2.5.7 and 2.1.4.

Sources (read 2026-10-24 from GitHub copies; the canonical sites don't resolve from the sandbox): [`cvat-ai/cvat`](https://github.com/cvat-ai/cvat/tree/develop/site/content/en/docs) docs and [`v2.80.0`](https://github.com/cvat-ai/cvat/tree/v2.80.0/cvat/apps/dataset_manager) source (`formats/mot.py`, `bindings.py`, `annotation.py`), [`cvat-ai/datumaro` @ `335fc3e`](https://github.com/cvat-ai/datumaro/blob/335fc3e55fe699b9401091f6af11f10c3b0e08cb/src/datumaro/plugins/data_formats/mot.py), [`w3c/wcag`](https://github.com/w3c/wcag) SC sources, [`WICG/video-rvfc`](https://github.com/WICG/video-rvfc) and [`mdn/browser-compat-data`](https://github.com/mdn/browser-compat-data) (Chrome 83, Safari 15.4, Firefox 132), scikit-learn's `cohen_kappa_score`. Feinstein & Cicchetti (J Clin Epidemiol 43(6), 1990) is cited from knowledge, not fetched.

## Decisions

1. **Footage: plan as if nothing has been filmed.** Default track R4 → R1. *Rejected:* planning around the 18-clip ideal.
2. **Labeller B: plan with B; if B isn't recruited and free to calibrate on hero 1 by Oct 26 08:00 EAT, switch to R3** (single labeller, "not measured"). *Changed this session:* the old Oct 25 09:00 EAT trigger came before hero 1 could exist, so R3 always fired.
3. **CVAT machine:** one the owner controls; a borrowed machine only for consented clips, or in the owner's physical custody for test clips. Test clips are labelled in person, never over a tunnel or screen share; backups go to an encrypted local drive, never a cloud. *Rejected:* a cloud VM, and "plus a private bucket" for real-public clips (SHOTLIST line 15, superseded; request below).
4. **Splits: 12 test / 3 dev + 3 hero**, test mean ≤ 30 s (PRE-A prices the $43.20 test line at 30 s).
5. **Pilot money: $6 per code, $20 shared pool** (PRE-A's request), enforced by WP5. The pool isn't refilled, so a `pilot_pool_cap` refusal disables the action.
6. **Pilot timing:** the "usual way" step is capped at 30 minutes; capped results are "≥ 30 min".
7. **Deletion promises** only after Claude checks the live cleanup, Meta file deletion and `store: false`.
8. **Pilot credit:** anonymous by default; with ≤ 2 pilots, anonymous only (format + country) across the whole submission, and no timing in the video. **Publication:** anonymous per-pilot timings are published; withdrawal until Nov 3 12:00 UTC (collection), results committed only after that.
9. **Café menu laptop:** Needs you, then kept clear with one tap (supersedes DEMO.md beat 5's "clear").
10. **Home-tour TV:** a fabricated video call with a consenting actor.
11. **"Remove person"** covers fully; no cutting in v1.
12. **VO:** the owner's own voice.
13. **Disputed labels:** `should_hide: true`, marked "disputed:".
14. **Every number in the video traces to a committed `metrics.json`**, committed by Nov 3 18:00 EAT (hero recordings Nov 3 morning, live runs by 16:00 EAT; script by 20:00; VO after, with Nov 4 morning as a VO-only buffer). **Creator time** is H1A and H1B (n = 2): manual masking vs upload to approved render, the only hero clips PRE-A's $12 line renders; EVAL's "3 clips" is a request. Pilot medians appear only with 3+ pilots. No literature number on the chart (supersedes DEMO.md beat 7's "ceiling line").
15. **Time model is PRE-A's §5b:** constant-frame-rate prepared clip, `times` in source seconds computed with `Fraction` arithmetic; no trim in v1.
16. **Leak count shown = distinct `patched_item`s;** `sample_step = round(job.fps)` (PRE-A §12).
17. **Access codes (PRE-A @ `565eee3`, adopted):** every code kind has a default window (judge/public Nov 5 00:00 – Nov 10 23:59 UTC; recording to Nov 3 23:59; pilot to Nov 2 23:59; owner to Nov 10 23:59); entries may only narrow it; the window is checked on every paid request for every kind; `code_valid_until` hides retries that would land after it. The recording code is $12, raisable to at most $15.00 (PRE-A's $3.00 headroom). *Replaced:* this session's earlier "`valid_until` required", "creation-only gating" and Nov 3 11:59 UTC pilot end, superseded when PRE-A changed in parallel.
18. **Refusals:** Continue checks the code (`POST /v1/codes/check`, request 21). On `/try` a refusal disables Start and deletes any half-made job; on a job page the UI never deletes automatically and the page, not the request, decides the copy (UI-SPEC §2.6.1, incl. one expiry rule and a download-or-delete rule). `POST /start` answers `422 job_cap` (never fits) or `429` with the caller cap's reason; `POST /v1/jobs` refuses below the $1.12 floor; `503 auditor_unavailable` when EgoBlur can't load.
19. **Rules day:** the demo stays live with judge codes from Nov 5 00:00 to Nov 10 23:59 UTC; after that, replay only.

## Reconciliation with PRE-A (PR #1)

Checked against `origin/pre-a-research` @ `715b977`. PRE-A changed in parallel during a wind-down, working from this PR at `22283eb`, so PRE-B adopted PRE-A's API and cost facts where the two had diverged (#331): `422 job_cap`, the $3.00 headroom and $15.00 bound, per-kind code windows, the `owner` kind, `code_valid_until`, `failure.reason: "code_not_active"`, `503 auditor_unavailable`, 60 s costs $2.02–2.09 ($2.34 no-cache). Every item in PRE-A §12's "Requests to PRE-B" is now in PRE-B's text (#332: hold and static Why rows, union-box `cover_spot` with `origin`/`audit_label`, object rulings for `other`, `child_phrase` → child, "Voice S1" speaker labels, stage-file `status` in mocks), and since `02c605e` also #409–#415 (scene `introduced_in_turn`/`introduction_quote` in every mock, service keys `401` outside the judge window, an auditor name rule for the YuNet fallback, `503 billing` copy, the prompt-cache sentence and receipt check in the consent note, `…T23:59:59Z` window ends), and PRE-A's three `[P]` rows in its WIN-CHECKLIST §4 are satisfied here; PRE-A can mark them `[x]`. Labels and pilots stay PRE-B's; API and cost facts stay PRE-A's.

## Self-review

- **This session:** full audit rounds 24–48 (and continuing until two consecutive rounds are clean), each with three independent fresh auditors in parallel (cross-package facts; UI-SPEC internals; labels, pilots and storyboard), each on a fixed commit. Findings #204–#598 were all fixed (or, for #257, answered). Many later findings were regressions of earlier fixes, so every round re-reads the latest diff and its neighbouring rules first.
- **Known limits:** hours per clip are estimates until two clips are timed; UI copy hasn't been seen by a user; the API field names in UI-SPEC §8 are proposals until WP5 exists; Feinstein & Cicchetti is cited, not fetched.

## Evidence

(See the final status comment for the audit outputs and gate commands of the last round.)

## What needs the owner

`docs/BLOCKED-PRE-B.md`: a checklist with a default for each item (filming, labeller B, the CVAT machine, sending pilot messages, code secrets, account steps).

## Requests for other WPs (not changed here)

- **WP8:** the README opens with the "Built during the event" paragraph (RULES-CHECKLIST §0: first product-code commit, each clip's real filming and labelling dates from the owner, the Sigmora split only if shown), names the auditors by UI-SPEC's §1.3 rule with the Muse Spark Open scope note, and links `/privacy`.

- **MAXXING (owner):** §1 judging dates → Nov 5–8 / finals Nov 9; §4 → live to Nov 10 23:59 UTC, demo-only from Nov 11; O7 → repo public before submitting, after the owner's OK; §1 bonus list → the guide's five bonuses, no Modal credit figure (OFFICIAL-GUIDE; PRE-A request).
- **ARCHITECTURE (owner):** §1/§5 assume a public repo from Oct 26 and Actions CI; while private there is no runner, so PRE-A recommends flipping early.

- **WP1:** PRE-A §5b exactly (constant-rate prepared clip, `times` by step 4's `Fraction` rule, `job.frames` read back).
- **WP2:** Set-of-Mark labels from track IDs; `matches_participant`, `suggested_role`, `escalation_evidence`/`escalation_frames`; `roles.missed[].track_ids`; `transcript.source_kind`; transcript times on the prepared clock.
- **WP3:** `reason` ≤ 90 chars, lowercase-first; edits `keep`, `hide`, `merge`, `remove_person`, `cover_spot`, `undo`; `removed_by_creator`; kinds per UI-SPEC §0.
- **WP4/WP5:** `blocked_reason` + `audit_budget_cause`; `POST /v1/jobs/{id}/audit` with the auto-patch loop and receipt; `leaks[].unresolved`, `sample_step`, `spots[]`.
- **WP5:** the UI-SPEC §8 fields; `422 job_cap` and `429` caller caps on `POST /start`, the $1.12 floor on `POST /v1/jobs`, `503 auditor_unavailable`; `POST /v1/codes/check` (request 21); `SAFECUT_ACCESS_CODES` with `kind` (incl. `owner`), `cap_usd`, optional narrowing `valid_from`/`valid_until`, PRE-A's per-kind windows checked on every paid request, `code_valid_until` on every job; pilot, recording and owner caps; `GET /v1/demo/{hero_id}`; `deletes_at`; daily reset at 00:00 UTC.
- **WP0 and WP7:** the 12/3 split, test mean ≤ 30 s, within their own WP caps and PRE-A §9.2's lines (the $20 pilot cap covers pilot codes only); WP7: the validator incl. LBL035 and A2 files, percent + κ + 2×2 + B-added counts, the `creator-time-<date>` and `pilots-<date>` results directories.
- **WP8:** form fields from RULES-CHECKLIST; STORYBOARD placeholders only from committed `metrics.json`.
- **WP7 (also):** `n_clips`, `n_public`, `n_staged` in the test run's `metrics.json` (UI-SPEC request 22); `eval/results/pilots-<date>/quotes.json` (permitted quotes and credits only).
- **EVAL.md's owner:** §1's split sizes → 12 test / 3 dev for this event; §2 "Creator time" → 2 clips (H1A, H1B) for this event, measured as summed parts (stage timings plus a stopwatch-timed review) rather than wall-clock.
- **SHOTLIST.md's owner:** line 15 → "they live only in `~/SafeCutEval/` on the owner's machines, never in a bucket".
- **DEMO.md's owner:** beat 5 "clear" → Needs you then kept clear; beat 7 drop the literature "ceiling line".
- **ARCHITECTURE §4's owner:** add `SAFECUT_ACCESS_CODES` (JSON) and `SAFECUT_PILOT_POOL_USD`.

PRE-B changes no contract file itself: ARCHITECTURE.md §3 is untouched and the label JSON is EVAL.md §1 as written. The contract additions the UI needs are requests (UI-SPEC §8 requests 9 and 18, adopted by PRE-A §12), for WP0 to implement with `contracts.py` (AGENTS rule 3).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01Tjy33tfkpth8jMhhnhhcYL
