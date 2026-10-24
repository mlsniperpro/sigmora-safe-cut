# WIN-CHECKLIST (PRE-B): criteria → evidence

Status: **live, updated each audit round** (first version 2026-10-24 17:30 UTC). This maps every judging criterion, every PRE-B deliverable and every audit finding to the evidence that covers it. The file name carries `-PRE-B` so it can't collide with PRE-A's `docs/WIN-CHECKLIST-PRE-A.md`.

Judging facts are from [MAXXING.md](MAXXING.md) §1 and §3 (to be re-checked against the official rules on Oct 26, [RULES-CHECKLIST.md](RULES-CHECKLIST.md) §8).

**Marks:** `[x]` done, with the evidence named on the line · `[P]` the PRE-B part is done, and the rest depends on an owner input in [BLOCKED-PRE-B.md](BLOCKED-PRE-B.md) or on a later WP building from this spec · `[-]` superseded or not applicable, with the reason. No line is left unmarked.

## 1. Judging criteria

- [P] **Impact (30%)**: A real problem, real users, measured gains. Evidence: Labelled test set with a written ground-truth rule and 31 worked cases ([LABELING-GUIDE.md](labeling/LABELING-GUIDE.md) §1–3); human-agreement reporting (percent + κ + 2×2, §5); creator pilots with timed protocol and honest reporting of capped times ([PILOTS.md](PILOTS.md) §5–6). Builder: WP7 (numbers), owner (pilots). Waiting on: owner input: footage, labeller B, pilots
- [P] **Use of Meta AI tooling (25%)**: Meta models doing things only they can, used deeply. Evidence: The Why? drawer puts the loop on screen: SAM 3.1's numbered tracks, Muse Spark's 3 votes, escalation, Voice Transcribe lines ([UI-SPEC.md](UI-SPEC.md) §4); progress labels name each model's job (§2.5); storyboard beat 4 shows it ([STORYBOARD.md](STORYBOARD.md) 4.1–4.2). Builder: WP6, WP2 (mark numbers). Waiting on: build: WP6
- [P] **Technical depth (20%)**: Hard parts solved, not glued. Evidence: Ground truth that isn't SAM-derived (LABELING-GUIDE §2.4); MOT export behaviour answered from CVAT v2.80.0 source ([CVAT-SETUP.md](labeling/CVAT-SETUP.md) §7.1); exact label schema, validator codes and test vectors ([LABEL-FORMAT.md](labeling/LABEL-FORMAT.md) §6–9); frame-accurate overlay on PRE-A's time axes (UI-SPEC §3.6, §10.6). Builder: WP6, WP7. Waiting on: build: WP6, WP7
- [P] **Demo (25%)**: It works live and the video lands. Evidence: 20-shot storyboard at 2:50 with every number traced to a `metrics.json` (STORYBOARD §1–2); 11 named screen recordings (§3); demo-mode banner for replay (UI-SPEC §6); cut plans down to 2:00 and below (RULES-CHECKLIST §4). Builder: WP6, WP8, owner. Waiting on: owner input: hero footage, VO
- [P] **Startup: holds up in production**: A deployed, safe, observable service. Evidence: Every state, validation rule, error and retry policy (UI-SPEC §2.6, §3.7, §10.2–10.4); deletion promise tied to the live cleanup (PILOTS §4); receipt and audit wording that can't overstate (UI-SPEC §5, distinct `patched_item` count). Builder: WP5, WP6. Waiting on: build: WP5, WP6
- [x] **Bonus: community vote / most viral**: Shareable proof. Evidence: Rules-day actions for both bonus mechanics (RULES-CHECKLIST §6). Builder: WP8.

## 2. PRE-B deliverables ([PRE-B.md](work-packages/PRE-B.md))

- [x] **Step 1: `should_hide` rules, 15+ edge cases (all 8 named)**. Evidence: LABELING-GUIDE §1–3 (31 cases: named ones are #1, #2, #4, #6, #8–9, #10, #12, #14).
- [x] **Step 1: Box conventions, resolving disagreements**. Evidence: LABELING-GUIDE §2.3, §5.
- [x] **Step 1: CVAT on a build box (not the Intel Mac), project, labels, interpolation, MOT export, privacy**. Evidence: CVAT-SETUP §1–7.
- [x] **Step 1: Label JSON + MOT, fully worked 10 s example**. Evidence: LABEL-FORMAT §2–5 (plus schema §6, validator §7 with 29 codes incl. single-labeller LBL032–034, examples §8 with V1–V6 and X1–X29, test vectors §9).
- [x] **Step 1: Hours per clip; ~18-clip plan; reduced plan**. Evidence: [SCHEDULE.md](labeling/SCHEDULE.md) §2–4. Note: estimates until timed
- [x] **Step 2: Every WP6 screen: wireframes desktop + mobile, copy deck, states, keyboard/a11y, contract fields**. Evidence: UI-SPEC §1–9, build contract §10.
- [x] **Step 2: The Why? drawer in detail; progress-stage labels**. Evidence: UI-SPEC §4, §2.5.
- [x] **Step 3: Shot-by-shot 2:50 with frame, text, VO, duration, source; Nov 3 recordings; placeholders**. Evidence: STORYBOARD §1–3.
- [x] **Step 4: Pilot profile, 15 candidates by channel type, 2 drafts < 120 words, consent note, protocol, results policy**. Evidence: PILOTS §1–6 (DM 103 words, email 110).
- [x] **Step 5: Rules checklist with an action for every answer**. Evidence: RULES-CHECKLIST §1–12.
- [x] **Step Done: Cross-links to DESIGN, EVAL, DEMO; no executable code**. Evidence: Verified by the docs check in the PR evidence.
- [x] **Step Owner: Owner-only inputs with defaults and stub paths**. Evidence: BLOCKED-PRE-B.

## 3. Audit findings

Every finding from every round, with its fix. "Round" names the review that found it.

- [x] **#1 (review 1)**: Video numbers not traced to `metrics.json`. Fix: STORYBOARD §2: every placeholder → a committed results dir.
- [x] **#2 (review 1)**: Hook called staged actors non-consenting. Fix: STORYBOARD 1.1–1.2 wording + on-screen "Staged with actors".
- [x] **#3 (review 1)**: Outreach promised 24 h deletion before WP5 exists. Fix: PILOTS §4 two-stage promise.
- [x] **#4 (review 1)**: 2:00 cut plan only reached 2:22. Fix: RULES-CHECKLIST §4 stage A/B (verified 142 s → 120 s).
- [x] **#5 (review 1)**: Results table dropped EVAL's "Muse without tracking". Fix: UI-SPEC §1 rows.
- [x] **#6 (review 1)**: Tooltips changed metric units. Fix: UI-SPEC §1.3 restated with EVAL units.
- [x] **#7 (review 1)**: κ procedure biased upward. Fix: LABELING-GUIDE §5 (percent + κ + 2×2 + detection count).
- [x] **#8 (review 1)**: R2 test split contradicted the split rule. Fix: LABELING-GUIDE §6, SCHEDULE §4.
- [x] **#9 (review 1)**: Pilot "30 minutes" unrealistic. Fix: PILOTS §5 30-min cap, "up to an hour".
- [x] **#10 (review 1)**: Chip actions unreachable by keyboard. Fix: UI-SPEC §3.8.
- [x] **#11 (review 2)**: Edge-case table broken at case 9. Fix: LABELING-GUIDE §3.
- [x] **#12 (review 2)**: Hero 1 filming default missing cast. Fix: BLOCKED-PRE-B, SCHEDULE R4.
- [x] **#13 (review 2)**: SCHEDULE still left the split to the owner. Fix: SCHEDULE §3.
- [x] **#14 (review 2)**: Intel Mac named as CVAT fallback. Fix: CVAT-SETUP §2.
- [x] **#15 (review 2)**: Eval-clip due dates wrong. Fix: BLOCKED-PRE-B.
- [x] **#16 (review 2)**: `job.times` meant different things in two docs. Fix: Now one definition: PRE-A API-NOTES §5b (LABEL-FORMAT §2, UI-SPEC §3.6).
- [x] **#17 (review 2)**: Capped pilot times could show as a median. Fix: STORYBOARD 8.3.
- [x] **#18 (review 2)**: Leak count = rows, not leaks. Fix: UI-SPEC §5.6 (distinct `patched_item`).
- [x] **#19 (review 2)**: Hard-coded "30 s clip"; `{speedup}` unsourced. Fix: STORYBOARD 2.1, §2.
- [x] **#20 (review 2)**: AI-voice row and company status left open. Fix: RULES-CHECKLIST §4, §7.
- [x] **#21 (owner audit)**: Reconcile with PRE-A (child < 18, times, cost, split). Fix: LABELING-GUIDE §2.1; LABEL-FORMAT §2; PILOTS §5; SCHEDULE §3.
- [x] **#22 (owner audit)**: 3 CVAT export questions open. Fix: CVAT-SETUP §7.1 from v2.80.0 source.
- [x] **#23 (owner audit)**: WP0/WP7 bound to 12/3 and $20. Fix: SCHEDULE §3.
- [x] **#24 (owner audit)**: Root BLOCKED.md conflicts with PRE-A. Fix: moved to docs/BLOCKED-PRE-B.md.
- [x] **#25 (review 3)**: VFR drift between `times` and the player clock. Fix: the overlay maps the player on the prepared clock (`clamp(floor(mediaTime × fps + 0.25), 0, frames − 1)`), never through `times`, per PRE-A §5b at `3d33e5f` (UI-SPEC §3.6). This replaces an interim fix (`times` as the MP4's own timestamps) that PRE-A later rejected.
- [x] **#26 (review 3)**: Display time and transcript on the wrong clock. Fix: UI-SPEC §0, §4.6 now follow §5b.
- [x] **#27 (review 3)**: `bystander` row said "adult or teen". Fix: LABELING-GUIDE §2.1.
- [x] **#28 (review 3)**: Two CVAT line citations didn't support claims. Fix: CVAT-SETUP §7.1 (`include_empty=True` line 2101; `CommonData` default).
- [x] **#29 (review 3)**: $20 cap enforcer unnamed; EVAL.md split conflict. Fix: SCHEDULE §3 (WP5; request to EVAL.md's owner).
- [x] **#30 (review 3)**: Pilot estimate ignored clip length. Fix: PILOTS §5.
- [x] **#31 (win audit 1)**: PRE-A moved the time-axis definition into §5b (its interim draft said no trim and `times[0] = 0`; the current `3d33e5f` text has two clocks and lets `times[0]` exceed 0); pilot estimate now $8.70. Fix: UI-SPEC §3.6, LABEL-FORMAT §2, PILOTS §5, SCHEDULE §3.
- [x] **#32 (win audit 1)**: Builders had no exact schema, validator codes, examples or test vectors. Fix: LABEL-FORMAT §6–9.
- [x] **#33 (win audit 1)**: Builders had no mocks list, validation rules, error map, state machine, reducer tests. Fix: UI-SPEC §10.
- [x] **#34 (win audit 1)**: Owner inputs had no stub path. Fix: BLOCKED-PRE-B "Until it arrives" lines.
- [x] **#35 (win audit 2)**: Main review mock broke the spec's own `times` check; §10.6 used a 61 s time. Fix: UI-SPEC §10.1 mock, §10.6.
- [x] **#36 (win audit 2)**: Plates sent through the screen keep-confirm; §4.3 said plates are always hidden. Fix: UI-SPEC §4.3, §10.5 R1–R2; café mock added.
- [x] **#37 (win audit 2)**: BLOCKED promised a café mock that didn't exist. Fix: UI-SPEC §10.1 `job-review-cafe`; BLOCKED-PRE-B.
- [x] **#38 (win audit 2)**: κ vector K1 disagreed with IEEE float arithmetic. Fix: LABEL-FORMAT §9 tolerance and rounding rule.
- [x] **#39 (win audit 2)**: No validator path for a missing labeller-B file (plan R3). Fix: LABEL-FORMAT §7 warning code + cases.
- [x] **#40 (win audit 2)**: Several §8.3 expected codes didn't follow from §7. Fix: LABEL-FORMAT §7 stop rules, §8.3.
- [x] **#41 (win audit 2)**: State machine contradicted §5.4 and §10.3; missing states. Fix: UI-SPEC §10.4.
- [x] **#42 (win audit 2)**: Reducer guards, CONFIRM_KEEP, MERGE precedence and UNDO undefined. Fix: UI-SPEC §10.5, §8 request 5.
- [x] **#43 (win audit 2)**: 404 on a job route mapped to two different pages. Fix: UI-SPEC §7, §10.3, §10.4.
- [x] **#44 (win audit 2)**: SoM mark given per item, needed per track. Fix: UI-SPEC §0, §8 request 2, §10.1 mock.
- [x] **#45 (win audit 3)**: Chips showed numeric SoM marks; PRE-A burns `<concept>:<n>` labels on keyframes. Fix: UI-SPEC §0, mocks, copy; STORYBOARD 4.1/4.3.
- [x] **#46 (win audit 3)**: "Back to review" from a done job bounced back to the result page. Fix: UI-SPEC §5, §10.4 (`?view=review`).
- [x] **#47 (win audit 3)**: Pilot spend would hit PRE-A's $3/day public cap. Fix: PILOTS §5 (pilot codes outside the daily cap; WP5 request).
- [x] **#48 (win audit 3)**: κ vector K1 sat on a rounding tie. Fix: LABEL-FORMAT §9.2 K1 = 11/26; tie rule.
- [x] **#49 (win audit 3)**: Escalation `suggested_role` not shown; impossible "Hidden, unsure" row; scene link already in PRE-A. Fix: UI-SPEC §4.3, §4.6, §8.
- [x] **#50 (win audit 3)**: Mock evidence frames had no keyframe or box. Fix: UI-SPEC §10.1 mocks.
- [x] **#51 (win audit 3)**: Re-entry bystander offered a merge into a non-participant. Fix: UI-SPEC §3.3–3.4, §10.5.
- [x] **#52 (win audit 3)**: Merged items' counts, overlay and later edits undefined. Fix: UI-SPEC §10.5.
- [x] **#53 (win audit 3)**: Limit messages could show the limit itself (floor rounding). Fix: UI-SPEC §2.6, §10.2.
- [x] **#54 (win audit 3)**: No single-labeller copy for the landing results footnote. Fix: UI-SPEC §1.3–1.4.
- [x] **#55 (win audit 4)**: Time axes followed PRE-A's rejected draft; PRE-A @3d33e5f uses a constant-rate prepared clock and non-decreasing source-second `times`. Fix: UI-SPEC §0, §3.3, §3.6, §4.6, §8, §10.1, §10.6.
- [x] **#56 (win audit 4)**: Label → prepared mapping was "nearest frame"; PRE-A decided prepared → label at `times[i]`. Fix: LABEL-FORMAT §2, §9.1.
- [x] **#57 (win audit 4)**: No UI state for PRE-A's `retry_later` job status. Fix: UI-SPEC §10.4, copy, mock.
- [x] **#58 (win audit 4)**: Drawer said Muse Spark isn't asked about plates; PRE-A's role pass judges them. Fix: UI-SPEC §4.3–4.4, hero mock.
- [x] **#59 (win audit 4)**: Muse evidence quoted raw frame numbers into the drawer. Fix: UI-SPEC §4.3 frame → m:ss transform + tests.
- [x] **#60 (win audit 4)**: Landing footnote showed κ without the 2×2 counts; no K3 variant. Fix: UI-SPEC §1.3–1.4.
- [x] **#61 (win audit 4)**: `removed` flag had no contract field. Fix: UI-SPEC §8 request (`removed_by_creator`), reducer.
- [x] **#62 (win audit 4)**: X8's expected codes didn't follow stop rule 4. Fix: LABEL-FORMAT §7 stop rule 4, §8.3.
- [x] **#63 (win audit 4)**: Mock `scene` lacked PRE-A's required fields. Fix: UI-SPEC §10.1 mocks, field list.
- [x] **#64 (win audit 4)**: Shots 1.2 and 8.3 ran above 150 wpm. Fix: STORYBOARD 1.2, 8.3, rule 6 (now 265 words, max ≤150 wpm per shot).
- [x] **#65 (win audit 5)**: Every `failed` job got one generic retry; no failure reason, pilot code cap or daily-cap reset defined. Fix: UI-SPEC §2.6, §10.3, `failure: {stage, reason}`, `code_cap`, requests 1 and 10.
- [x] **#66 (win audit 5)**: Ground-truth matching needed unrounded `times`; nothing required it. Fix: LABEL-FORMAT §2 (WP1 request), vector M8.
- [x] **#67 (win audit 5)**: Escalation ruling had no field of its own; `escalated` undefined on failure. Fix: UI-SPEC §4.3, §4.6, §8 request 3 (`escalation_evidence`, `escalation_frames`).
- [x] **#68 (win audit 5)**: No copy for PRE-A's "audit couldn't run" / "over budget" cases. Fix: UI-SPEC §5.3–5.6, `redteam_status`, request 11, mocks.
- [x] **#69 (win audit 5)**: Frame-reference rewrite missed lists and bare ranges. Fix: UI-SPEC §4.3 rules + 7 more cases (incl. ARCHITECTURE §3.5's example).
- [x] **#70 (win audit 5)**: Undo reused the idempotency key; reducer cases had no fixture. Fix: UI-SPEC §10.3, §10.5, `reducer-state.json`.
- [x] **#71 (win audit 5)**: Label header: upper-case extensions, hero naming, rotated clips. Fix: LABEL-FORMAT §1, §2, §6.1, V7, portrait vector.
- [x] **#72 (win audit 5)**: Unsupported claims shown to users ("doesn't train on it", "storage off", "every frame"). Fix: UI-SPEC §1.3, §2, §5; PILOTS §4; STORYBOARD 6.2.
- [x] **#73 (win audit 5)**: Thumbnail used `track_ids[0]`, not the primary track. Fix: UI-SPEC §3.3.
- [x] **#74 (win audit 5)**: Stale cross-doc statements (WIN #25/#31, SCHEDULE 4-clip subset, WP6 step 4; PRE-A's BLOCKED-PRE-A line 3 and WIN row 56). Fix: PRE-B side fixed (WIN #25/#31, SCHEDULE §3, UI-SPEC request 12). PRE-A side resolved by PRE-A itself at `948b678`: its BLOCKED pointer now names `docs/BLOCKED-PRE-B.md` (PRE-A WIN row 66), and its shared-facts list (§4) marks the time axes and UI fields as matching.
- [x] **#75 (win audit 6)**: Clip ID = "first 7 characters" broke hero IDs. Fix: LABEL-FORMAT §1, §6.1, §7 (one regex).
- [x] **#76 (win audit 6)**: Ring and thumbnail ignored the keyframe's 40 px frame-number bar. Fix: UI-SPEC §4.3 geometry, `keyframe_geometry`, request 13.
- [x] **#77 (win audit 6)**: Removed person kept clear still counted as removed. Fix: UI-SPEC §3.4, §10.5 R13b.
- [x] **#78 (win audit 6)**: Degraded or fallback transcript shown as "no speech" with exact times. Fix: UI-SPEC §4.3–4.6, mocks.
- [x] **#79 (win audit 6)**: Over-blur had no per-frame definition or test vectors. Fix: LABEL-FORMAT §9.3 (≥ 0.50; O1–O4).
- [x] **#80 (win audit 6)**: Harmless non-screen objects got the wrong drawer sentence; concept→kind unmapped. Fix: UI-SPEC §0, §3.4, §4.3, request 14.
- [x] **#81 (win audit 6)**: Mock and §10.6 times were rounded (fails M8). Fix: UI-SPEC §10.1, §10.6.
- [x] **#82 (win audit 6)**: Consent note promised per-call data handling the receipt doesn't record. Fix: PILOTS §4.
- [x] **#83 (win audit 6)**: Cut plans kept VO that breaks 150 wpm. Fix: RULES-CHECKLIST §4 cut-version VO table.
- [x] **#84 (win audit 6)**: Person size threshold ambiguous for 4K and portrait. Fix: LABELING-GUIDE §2, §4; LABEL-FORMAT LBL020, X20.
- [x] **#85 (win audit 7)**: Server rule for clearing `removed_by_creator` on a later keep was missing. Fix: UI-SPEC request 9, request 5, §3.4.
- [x] **#86 (win audit 7)**: Keyframe-mismatch fixture couldn't produce its state. Fix: UI-SPEC §4.3 checks, `keyframe_geometry` fields, stubbed image loading.
- [x] **#87 (win audit 7)**: No "Hidden by you" sentence. Fix: UI-SPEC §4.3 table and precedence.
- [x] **#88 (win audit 7)**: Over-blur counted Needs-you harmless objects as hidden with no stated rule. Fix: LABEL-FORMAT §9.3: two labelled rows (as shipped; suggestions accepted).
- [x] **#89 (win audit 7)**: Kind `other` items (second-look finds) had no drawer path. Fix: UI-SPEC §4.3, request 15.
- [x] **#90 (win audit 7)**: Speech-fallback fixture couldn't detect a missing ±1.5 s window. Fix: UI-SPEC §10.1 `job-review-speech-fallback.json`.
- [x] **#91 (win audit 7)**: Limited-speech check keyed on a hard-coded model ID. Fix: UI-SPEC `source_kind` (request 16), AGENTS rule 8.
- [x] **#92 (win audit 7)**: Reducer `confirm` still described as screen/document only. Fix: UI-SPEC §10.5.
- [x] **#93 (win audit 7)**: Hero clip numbers limited to 1–3; SHOTLIST allows 3–4. Fix: LABEL-FORMAT §1, §6.1 (1–9).
- [x] **#94 (win audit 7)**: LBL020 message had no number format. Fix: LABEL-FORMAT §7 (1 decimal).
- [x] **#95 (win audit 8)**: `budget` failure copy wrong when the daily cap (not the job cap) ran out. Fix: UI-SPEC §2.6, §10.3 (`job_cap` vs `daily_cap`), request 1.
- [x] **#96 (win audit 8)**: Publish could be enabled when the red-team check never ran. Fix: UI-SPEC §5.6 (`redteam_status == "ok"`).
- [x] **#97 (win audit 8)**: 3/3 participant on one keyframe shown as "checks didn't agree". Fix: UI-SPEC §4.3 sentence; marks vs majority vote.
- [x] **#98 (win audit 8)**: Landing said all test clips were filmed in public. Fix: UI-SPEC §1.3 footnotes (`n_public` / `n_staged`).
- [x] **#99 (win audit 8)**: Results table had no row for over-blur with suggestions accepted. Fix: UI-SPEC §1 table; STORYBOARD §2 placeholder note.
- [x] **#100 (win audit 8)**: 7.2 VO described over-blur as people only. Fix: STORYBOARD 7.2.
- [x] **#101 (win audit 8)**: No mocks for budget, code-cap or deterministic failures. Fix: UI-SPEC §10.1 (5 mocks).
- [x] **#102 (win audit 8)**: Sunday labelling hours didn't follow the table. Fix: SCHEDULE §3 (≈ 8 h).
- [x] **#103 (win audit 8)**: Remove person: person-only in one place, person and child in another. Fix: UI-SPEC §3.1 overflow menu.
- [x] **#104 (win audit 8)**: Result wireframe dropped the "of {frames}" denominator. Fix: UI-SPEC §5.1–5.2.
- [x] **#105 (win audit 9)**: One-keyframe row missing from the drawer's precedence list. Fix: UI-SPEC §4.3.
- [x] **#106 (win audit 9)**: Escalation sentence said "checks disagreed" for a unanimous one-keyframe case. Fix: UI-SPEC §4.3.
- [x] **#107 (win audit 9)**: Too-long or broken clips found after upload had no failure reason; client and server limits differed. Fix: UI-SPEC §2.6, §10.2, §10.3 (`too_long`/`too_large`/`bad_media`; one 60.05 s rule), request 17.
- [x] **#108 (win audit 9)**: Nov 3 recordings would exceed the $3/day public cap. Fix: STORYBOARD §3 (owner recording code, $6 cap).
- [x] **#109 (win audit 9)**: "Review them" for unresolved audit spots led to a panel with nothing to fix. Fix: UI-SPEC §3.3 "Unfixed spot" chips, `cover_spot`, request 18.
- [x] **#110 (win audit 9)**: Pilot clip spec didn't mention the 150 MB limit. Fix: PILOTS §5.
- [x] **#111 (win audit 9)**: `{h1a_seconds}` sourced from a run without a `job.json`. Fix: STORYBOARD §2 (hero-live run).
- [x] **#112 (win audit 9)**: No state for a job created but never uploaded. Fix: UI-SPEC §10.4 `created`.
- [x] **#113 (win audit 9)**: Labelling guide would fork into two master copies at kickoff. Fix: LABELING-GUIDE header (single master; WP7 links).
- [x] **#114 (win audit 10)**: Over-budget audit path contradicted PRE-A (it adds to `unresolved`). Fix: UI-SPEC §5 mocks, PRE-A invariant.
- [x] **#115 (win audit 10)**: Invented `redteam_status`; PRE-A already defines `blocked_reason` and "Run the audit again". Fix: UI-SPEC §5, request 11 (PRE-A's fields).
- [x] **#116 (win audit 10)**: Audit failure modelled as `done`; PRE-A sends it to job status `needs_you`. Fix: UI-SPEC §10.4 `needs_you` row, banner.
- [x] **#117 (win audit 10)**: Pilot caps used withdrawn PRE-A figures; PRE-A asked for $6 per code. Fix: PILOTS §5 ($6 per code, $20 total; $1.12 / $11.20), BLOCKED-PRE-B.
- [x] **#118 (win audit 10)**: Bottom bar called uncovered leaks "hidden". Fix: UI-SPEC §3.5 (disabled until covered).
- [x] **#119 (win audit 10)**: `cover_spot` had no reducer action; audit missing from the job response. Fix: UI-SPEC §10.5 COVER_SPOT, R19–R22, §8.
- [x] **#120 (win audit 10)**: A-labels collided between audit items and unfixed spots. Fix: UI-SPEC §0, §3.3 (U1… for spots).
- [x] **#121 (win audit 10)**: Duration rule still described a 422 path. Fix: UI-SPEC §10.2 (`failure.duration_s`, fallback copy).
- [x] **#122 (win audit 10)**: Landing hero job would be deleted after 24 h and needs a code. Fix: UI-SPEC §1.6, request 19 (`GET /v1/demo/{hero_id}`, pinned).
- [x] **#123 (win audit 10)**: Recording budget used withdrawn costs and undercounted runs. Fix: STORYBOARD §3 ($10 owner code from PRE-A's hero line).
- [x] **#124 (win audit 11)**: Pilot estimate's margin ignored 60 s clips. Fix: PILOTS §5 (clips 15–45 s; ≈ $15–17 for 10 clips).
- [-] **#125 (win audit 11)**: Early pilots could use up the shared $20 before later ones ran. Fix: PILOTS §5 (≤ 2 jobs per code), UI-SPEC request 20. **Superseded by #135:** the per-code job count was removed in round 13; the $6 code cap and the $20 pool bound spend instead.
- [x] **#126 (win audit 11)**: Running out of the shared pilot total pointed pilots to a new code. Fix: UI-SPEC §2.6 `pilot_pool_cap` copy.
- [x] **#127 (win audit 11)**: Owner recording code existed only in STORYBOARD. Fix: UI-SPEC §8 request 20, BLOCKED-PRE-B Nov 3 step, WIN §4 WP5 row.
- [x] **#128 (win audit 11)**: Recording budget priced hero runs at the 30 s rate. Fix: STORYBOARD §3 (45 s ≈ $1.5–1.7; $12 code).
- [x] **#129 (win audit 12)**: `pilot_pool_cap` missing from the reason list, error table and mocks. Fix: UI-SPEC request 1, §10.3, §10.1.
- [-] **#130 (win audit 12)**: Third job on a pilot code had no error; failed uploads used up jobs. Fix: UI-SPEC `code_job_limit`, request 20 (jobs count only past prepare). **Superseded by #135:** the per-code job count was removed in round 13; the $6 code cap and the $20 pool bound spend instead.
- [x] **#131 (win audit 12)**: Recording code described as resetting daily. Fix: STORYBOARD §3, BLOCKED-PRE-B (a total; owner raises it).
- [x] **#132 (win audit 12)**: Over-budget audit button stayed enabled when a code or pool cap was the cause. Fix: UI-SPEC §5.3 banner by `audit_budget_cause`, mocks, request 20.
- [-] **#133 (win audit 12)**: Pilot cap sized for 2 clips while the protocol runs 1. Fix: PILOTS §5 (one clip, 2 jobs allowed; estimate ≈ $8). **Superseded by #135:** the per-code job count was removed in round 13; the $6 code cap and the $20 pool bound spend instead.
- [x] **#134 (win audit 12)**: Daily-cap reasoning still cited 60 s pilot clips. Fix: PILOTS §5.
- [x] **#135 (win audit 13)**: `code_job_limit` placed on two different endpoints. Fix: Simplified away: no job count; the $6 code cap and the $20 pool bound spend (UI-SPEC request 20, PILOTS §5).
- [x] **#136 (win audit 13)**: Job limit couldn't be checked before prepare. Fix: Same simplification.
- [x] **#137 (win audit 13)**: `audit_budget_cause` and `retry_at` missing from the audit request. Fix: UI-SPEC request 11 (PRE-B's one addition).
- [x] **#138 (win audit 13)**: State machine always showed [Run the audit again]; §5.3 hid it for some causes. Fix: UI-SPEC §5.3: always shown, disabled only before `retry_at`.
- [x] **#139 (win audit 13)**: A cap raised by the owner could never re-enable the audit; pool cap blamed the code. Fix: UI-SPEC §5.3 cause lines, mock.
- [x] **#140 (win audit 13)**: "Hero line has room" was false at 45 s clip costs. Fix: STORYBOARD §3 (overrun noted; re-pricing request to PRE-A).
- [x] **#141 (win audit 13)**: [Try again tomorrow] always restarted the whole pipeline. Fix: UI-SPEC §2.6, §10.3 (same stage routing as [Try again]).
- [x] **#142 (win audit 14)**: SR-01 would show the access code in the public video. Fix: UI-SPEC §10.2 masked field; STORYBOARD SR-01 and §4 checklist; BLOCKED-PRE-B revoke step.
- [x] **#143 (win audit 14)**: Code-kind caps requested only of WP5; the budget guard lives in WP0's client. Fix: UI-SPEC request 20 (WP0 + `cost.jsonl` code fields; request to PRE-A).
- [-] **#144 (win audit 14)**: Edits in the `needs_you` state could be lost by re-running only the audit. Fix: UI-SPEC §3.5 (an edit switches to Approve & render). **Superseded by #157:** `needs_you` is now read-only, and edits go through an explicit reopen.
- [x] **#145 (win audit 14)**: `job_cap` audit offered an endless re-run. Fix: UI-SPEC §5.3 (no button; shorter clip).
- [x] **#146 (win audit 14)**: `daily_cap` retry button described two ways. Fix: UI-SPEC §10.3 aligned with §2.6.
- [x] **#147 (win audit 14)**: Superseded job-count fixes still marked [x]. Fix: WIN #125, #130, #133 → [-].
- [-] **#148 (win audit 15)**: An edit in `needs_you` didn't change the server state. Fix: UI-SPEC request 5, §3.5, §10.4 transitions, R24. **Superseded by #157:** `needs_you` is now read-only, and edits go through an explicit reopen.
- [x] **#149 (win audit 15)**: `job_cap` in `needs_you` left the bar empty or allowed a doomed re-render. Fix: UI-SPEC §3.3, §3.5, §5.3–5.4, §10.4, mock, R23.
- [x] **#150 (win audit 15)**: `job_cap` exception missing from three other sections and mocks. Fix: Same propagation as #149.
- [x] **#151 (win audit 15)**: Code kinds and caps had no config home; risk of codes in the public repo. Fix: UI-SPEC request 20 (`SAFECUT_ACCESS_CODES` JSON secret, `SAFECUT_PILOT_POOL_USD`); BLOCKED-PRE-B, STORYBOARD.
- [x] **#152 (win audit 15)**: `type=password` would trigger Chrome's save prompt inside SR-01. Fix: UI-SPEC §10.2 text input with CSS masking.
- [x] **#153 (win audit 15)**: A stage failing on `code_cap` couldn't recover after the cap was raised. Fix: UI-SPEC §2.6, §10.3, mock.
- [x] **#154 (win audit 15)**: `retry_later` promised open-ended retries; PRE-A re-queues once. Fix: UI-SPEC §2.6, request 1, §10.3–10.4, `upstream` failure, mock.
- [x] **#155 (win audit 16)**: Read-only chips under `job_cap` had no reducer guard. Fix: UI-SPEC §10.5 `readOnly` (rendering, needs_you), R23, R25.
- [x] **#156 (win audit 16)**: Bar chosen by `blocked_reason` showed the wrong action after a reload. Fix: UI-SPEC §3.5 (by job status + cause).
- [x] **#157 (win audit 16)**: Approve & render after an edit could only fail on an exhausted cap. Fix: Simplified: `needs_you` is read-only; [Edit and render again] reopens with a budget confirm.
- [x] **#158 (win audit 16)**: 429 cap codes mapped only on POST /start. Fix: UI-SPEC §10.3 (one mapping for /start, /render, /audit, /reopen).
- [x] **#159 (win audit 16)**: [Run the audit again] had no endpoint. Fix: UI-SPEC request 11 (`POST /v1/jobs/{id}/audit`, `/reopen`), mocks.
- [x] **#160 (win audit 16)**: Download promised in `needs_you` had no URL or button. Fix: UI-SPEC request 1 (`result.video_url` on the job), §3.5.
- [x] **#161 (win audit 16)**: No fixture for the reload-after-edit state. Fix: UI-SPEC §10.1 `job-reopened-review.json`; R24 replaced.
- [x] **#162 (win audit 16)**: BLOCKED said WP5 issues the recording code. Fix: BLOCKED-PRE-B (the owner adds it to the deploy secret).
- [x] **#163 (win audit 16)**: /start code-cap copy left the pilot at a dead end. Fix: UI-SPEC §2.6 (Start stays enabled).

## 4. Which builder reads what

| WP | Reads from PRE-B | For |
|---|---|---|
| WP0 | SCHEDULE §3 (split), BLOCKED-PRE-B (fixture fallbacks) | fixtures, probe clips |
| WP2 | UI-SPEC §8 requests 2, 3, 7 | SoM numbers, speaker links, transcript timeline |
| WP3 | UI-SPEC §3.4, §8 requests 4–5, §10.5 | reason strings, review edit names, reducer semantics |
| WP5 | UI-SPEC §8 (incl. request 20: pilot and recording codes), §10.1–10.3; PILOTS §4–5; STORYBOARD §3 | API fields, error codes, idempotency, per-code cap, deletion |
| WP6 | UI-SPEC (all) | every screen |
| WP7 | LABEL-FORMAT (all), LABELING-GUIDE §5, SCHEDULE §3, PILOTS §6 | loader, validator, agreement, metrics test vectors, pilot results |
| WP8 | STORYBOARD, RULES-CHECKLIST §5–6, PILOTS §6 | video script, submission fields, launch |

## 5. Open risks to the win (ranked)

- [P] **Risk 1: Hero footage late** (effect: Demo 25%, Impact story). Mitigation: Default plan R4 → R1; synthetic-clip and mock paths keep code moving. Owner input: Film hero 1 by Oct 25 18:00 EAT.
- [P] **Risk 2: No labeller B** (effect: Weaker Impact evidence (no κ)). Mitigation: R3 with honest "not measured". Owner input: Recruit B.
- [P] **Risk 3: Fewer than 5 pilots** (effect: Weaker Impact). Mitigation: Report the real count; shot 8.3 is cut. Owner input: Send outreach Oct 27.
- [P] **Risk 4: Official rules differ from MAXXING** (effect: Any). Mitigation: RULES-CHECKLIST: an action for every answer. Owner input: Accept the rules at kickoff.
- [P] **Risk 5: API field names drift between WP5 and WP6** (effect: Demo breaks). Mitigation: UI-SPEC §10.1: mocks follow WP5's names. Owner input: —.
