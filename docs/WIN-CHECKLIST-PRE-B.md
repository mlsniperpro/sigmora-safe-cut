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
- [x] **#25 (review 3)**: VFR drift between `times` and the player clock. Fix: Superseded by PRE-A §5b: the prepared MP4 carries `times` as its timestamps, so the player and `times` can't drift (UI-SPEC §3.6).
- [x] **#26 (review 3)**: Display time and transcript on the wrong clock. Fix: UI-SPEC §0, §4.6 now follow §5b.
- [x] **#27 (review 3)**: `bystander` row said "adult or teen". Fix: LABELING-GUIDE §2.1.
- [x] **#28 (review 3)**: Two CVAT line citations didn't support claims. Fix: CVAT-SETUP §7.1 (`include_empty=True` line 2101; `CommonData` default).
- [x] **#29 (review 3)**: $20 cap enforcer unnamed; EVAL.md split conflict. Fix: SCHEDULE §3 (WP5; request to EVAL.md's owner).
- [x] **#30 (review 3)**: Pilot estimate ignored clip length. Fix: PILOTS §5.
- [x] **#31 (win audit 1)**: PRE-A moved to §5b (no trim, `times[0] = 0`); pilot estimate now $8.70. Fix: UI-SPEC §3.6, LABEL-FORMAT §2, PILOTS §5, SCHEDULE §3.
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

## 4. Which builder reads what

| WP | Reads from PRE-B | For |
|---|---|---|
| WP0 | SCHEDULE §3 (split), BLOCKED-PRE-B (fixture fallbacks) | fixtures, probe clips |
| WP2 | UI-SPEC §8 requests 2, 3, 7 | SoM numbers, speaker links, transcript timeline |
| WP3 | UI-SPEC §3.4, §8 requests 4–5, §10.5 | reason strings, review edit names, reducer semantics |
| WP5 | UI-SPEC §8, §10.1–10.3; PILOTS §4–5 | API fields, error codes, idempotency, per-code cap, deletion |
| WP6 | UI-SPEC (all) | every screen |
| WP7 | LABEL-FORMAT (all), LABELING-GUIDE §5, SCHEDULE §3, PILOTS §6 | loader, validator, agreement, metrics test vectors, pilot results |
| WP8 | STORYBOARD, RULES-CHECKLIST §5–6, PILOTS §6 | video script, submission fields, launch |

## 5. Open risks to the win (ranked)

- [P] **Risk 1: Hero footage late** (effect: Demo 25%, Impact story). Mitigation: Default plan R4 → R1; synthetic-clip and mock paths keep code moving. Owner input: Film hero 1 by Oct 25 18:00 EAT.
- [P] **Risk 2: No labeller B** (effect: Weaker Impact evidence (no κ)). Mitigation: R3 with honest "not measured". Owner input: Recruit B.
- [P] **Risk 3: Fewer than 5 pilots** (effect: Weaker Impact). Mitigation: Report the real count; shot 8.3 is cut. Owner input: Send outreach Oct 27.
- [P] **Risk 4: Official rules differ from MAXXING** (effect: Any). Mitigation: RULES-CHECKLIST: an action for every answer. Owner input: Accept the rules at kickoff.
- [P] **Risk 5: API field names drift between WP5 and WP6** (effect: Demo breaks). Mitigation: UI-SPEC §10.1: mocks follow WP5's names. Owner input: —.
