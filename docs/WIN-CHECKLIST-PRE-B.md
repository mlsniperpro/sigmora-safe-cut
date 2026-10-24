# WIN-CHECKLIST (PRE-B): criteria → evidence

Status: **live, updated each audit round** (first version 2026-10-24 17:30 UTC). This maps every judging criterion, every PRE-B deliverable and every audit finding to the evidence that covers it. The file name carries `-PRE-B` so it can't collide with PRE-A's equivalent (the same reason the BLOCKED file is `docs/BLOCKED-PRE-B.md`).

Judging facts are from [MAXXING.md](MAXXING.md) §1 and §3 (to be re-checked against the official rules on Oct 26, [RULES-CHECKLIST.md](RULES-CHECKLIST.md) §8).

Legend: ✅ covered by a committed doc section · 🟡 covered, but depends on an input in [BLOCKED-PRE-B.md](BLOCKED-PRE-B.md) · ⏳ built later by the named WP from this spec.

## 1. Judging criteria

| Criterion (weight) | What a judge must see | PRE-B evidence | Status | Builder |
|---|---|---|---|---|
| **Impact (30%)** | A real problem, real users, measured gains | Labelled test set with a written ground-truth rule and 31 worked cases ([LABELING-GUIDE.md](labeling/LABELING-GUIDE.md) §1–3); human-agreement reporting (percent + κ + 2×2, §5); creator pilots with timed protocol and honest reporting of capped times ([PILOTS.md](PILOTS.md) §5–6) | 🟡 footage, labeller B, pilots | WP7 (numbers), owner (pilots) |
| **Use of Meta AI tooling (25%)** | Meta models doing things only they can, used deeply | The Why? drawer puts the loop on screen: SAM 3.1's numbered tracks, Muse Spark's 3 votes, escalation, Voice Transcribe lines ([UI-SPEC.md](UI-SPEC.md) §4); progress labels name each model's job (§2.5); storyboard beat 4 shows it ([STORYBOARD.md](STORYBOARD.md) 4.1–4.2) | ✅ spec · ⏳ WP6 | WP6, WP2 (mark numbers) |
| **Technical depth (20%)** | Hard parts solved, not glued | Ground truth that isn't SAM-derived (LABELING-GUIDE §2.4); MOT export behaviour answered from CVAT v2.80.0 source ([CVAT-SETUP.md](labeling/CVAT-SETUP.md) §7.1); exact label schema, validator codes and test vectors ([LABEL-FORMAT.md](labeling/LABEL-FORMAT.md) §6–9); frame-accurate overlay on PRE-A's time axes (UI-SPEC §3.6, §10.6) | ✅ spec · ⏳ WP6, WP7 | WP6, WP7 |
| **Demo (25%)** | It works live and the video lands | 20-shot storyboard at 2:50 with every number traced to a `metrics.json` (STORYBOARD §1–2); 11 named screen recordings (§3); demo-mode banner for replay (UI-SPEC §6); cut plans down to 2:00 and below (RULES-CHECKLIST §4) | 🟡 hero footage, VO | WP6, WP8, owner |
| **Startup: holds up in production** | A deployed, safe, observable service | Every state, validation rule, error and retry policy (UI-SPEC §2.6, §3.7, §10.2–10.4); deletion promise tied to the live cleanup (PILOTS §4); receipt and audit wording that can't overstate (UI-SPEC §5, distinct `patched_item` count) | ✅ spec · ⏳ WP5, WP6 | WP5, WP6 |
| Bonus: community vote / most viral | Shareable proof | Rules-day actions for both bonus mechanics (RULES-CHECKLIST §6) | ✅ | WP8 |

## 2. PRE-B deliverables ([PRE-B.md](work-packages/PRE-B.md))

| Step | Deliverable | Where | Status |
|---|---|---|---|
| 1 | `should_hide` rules, 15+ edge cases (all 8 named) | LABELING-GUIDE §1–3 (31 cases: named ones are #1, #2, #4, #6, #8–9, #10, #12, #14) | ✅ |
| 1 | Box conventions, resolving disagreements | LABELING-GUIDE §2.3, §5 | ✅ |
| 1 | CVAT on a build box (not the Intel Mac), project, labels, interpolation, MOT export, privacy | CVAT-SETUP §1–7 | ✅ |
| 1 | Label JSON + MOT, fully worked 10 s example | LABEL-FORMAT §2–5 (plus schema §6, validator §7, examples §8, test vectors §9) | ✅ |
| 1 | Hours per clip; ~18-clip plan; reduced plan | [SCHEDULE.md](labeling/SCHEDULE.md) §2–4 | ✅ (estimates until timed) |
| 2 | Every WP6 screen: wireframes desktop + mobile, copy deck, states, keyboard/a11y, contract fields | UI-SPEC §1–9, build contract §10 | ✅ |
| 2 | The Why? drawer in detail; progress-stage labels | UI-SPEC §4, §2.5 | ✅ |
| 3 | Shot-by-shot 2:50 with frame, text, VO, duration, source; Nov 3 recordings; placeholders | STORYBOARD §1–3 | ✅ |
| 4 | Pilot profile, 15 candidates by channel type, 2 drafts < 120 words, consent note, protocol, results policy | PILOTS §1–6 (DM 103 words, email 110) | ✅ |
| 5 | Rules checklist with an action for every answer | RULES-CHECKLIST §1–12 | ✅ |
| Done | Cross-links to DESIGN, EVAL, DEMO; no executable code | Verified by the docs check in the PR evidence | ✅ |
| Owner | Owner-only inputs with defaults and stub paths | BLOCKED-PRE-B | ✅ |

## 3. Audit findings

Every finding from every round, with its fix. "Round" = which review found it.

| # | Round | Finding | Fix (where) | Status |
|---|---|---|---|---|
| 1 | review 1 | Video numbers not traced to `metrics.json` | STORYBOARD §2: every placeholder → a committed results dir | ✅ |
| 2 | review 1 | Hook called staged actors non-consenting | STORYBOARD 1.1–1.2 wording + on-screen "Staged with actors" | ✅ |
| 3 | review 1 | Outreach promised 24 h deletion before WP5 exists | PILOTS §4 two-stage promise | ✅ |
| 4 | review 1 | 2:00 cut plan only reached 2:22 | RULES-CHECKLIST §4 stage A/B (verified 142 s → 120 s) | ✅ |
| 5 | review 1 | Results table dropped EVAL's "Muse without tracking" | UI-SPEC §1 rows | ✅ |
| 6 | review 1 | Tooltips changed metric units | UI-SPEC §1.3 restated with EVAL units | ✅ |
| 7 | review 1 | κ procedure biased upward | LABELING-GUIDE §5 (percent + κ + 2×2 + detection count) | ✅ |
| 8 | review 1 | R2 test split contradicted the split rule | LABELING-GUIDE §6, SCHEDULE §4 | ✅ |
| 9 | review 1 | Pilot "30 minutes" unrealistic | PILOTS §5 30-min cap, "up to an hour" | ✅ |
| 10 | review 1 | Chip actions unreachable by keyboard | UI-SPEC §3.8 | ✅ |
| 11 | review 2 | Edge-case table broken at case 9 | LABELING-GUIDE §3 | ✅ |
| 12 | review 2 | Hero 1 filming default missing cast | BLOCKED-PRE-B, SCHEDULE R4 | ✅ |
| 13 | review 2 | SCHEDULE still left the split to the owner | SCHEDULE §3 | ✅ |
| 14 | review 2 | Intel Mac named as CVAT fallback | CVAT-SETUP §2 | ✅ |
| 15 | review 2 | Eval-clip due dates wrong | BLOCKED-PRE-B | ✅ |
| 16 | review 2 | `job.times` meant different things in two docs | Now one definition: PRE-A API-NOTES §5b (LABEL-FORMAT §2, UI-SPEC §3.6) | ✅ |
| 17 | review 2 | Capped pilot times could show as a median | STORYBOARD 8.3 | ✅ |
| 18 | review 2 | Leak count = rows, not leaks | UI-SPEC §5.6 (distinct `patched_item`) | ✅ |
| 19 | review 2 | Hard-coded "30 s clip"; `{speedup}` unsourced | STORYBOARD 2.1, §2 | ✅ |
| 20 | review 2 | AI-voice row and company status left open | RULES-CHECKLIST §4, §7 | ✅ |
| 21 | owner audit | Reconcile with PRE-A (child < 18, times, cost, split) | LABELING-GUIDE §2.1; LABEL-FORMAT §2; PILOTS §5; SCHEDULE §3 | ✅ |
| 22 | owner audit | 3 CVAT export questions open | CVAT-SETUP §7.1 from v2.80.0 source | ✅ |
| 23 | owner audit | WP0/WP7 bound to 12/3 and $20 | SCHEDULE §3 | ✅ |
| 24 | owner audit | Root BLOCKED.md conflicts with PRE-A | moved to docs/BLOCKED-PRE-B.md | ✅ |
| 25 | review 3 | VFR drift between `times` and the player clock | Superseded by PRE-A §5b: the prepared MP4 carries `times` as its timestamps, so the player and `times` can't drift (UI-SPEC §3.6) | ✅ |
| 26 | review 3 | Display time and transcript on the wrong clock | UI-SPEC §0, §4.6 now follow §5b | ✅ |
| 27 | review 3 | `bystander` row said "adult or teen" | LABELING-GUIDE §2.1 | ✅ |
| 28 | review 3 | Two CVAT line citations didn't support claims | CVAT-SETUP §7.1 (`include_empty=True` line 2101; `CommonData` default) | ✅ |
| 29 | review 3 | $20 cap enforcer unnamed; EVAL.md split conflict | SCHEDULE §3 (WP5; request to EVAL.md's owner) | ✅ |
| 30 | review 3 | Pilot estimate ignored clip length | PILOTS §5 | ✅ |
| 31 | win audit 1 | PRE-A moved to §5b (no trim, `times[0] = 0`); pilot estimate now $8.70 | UI-SPEC §3.6, LABEL-FORMAT §2, PILOTS §5, SCHEDULE §3 | ✅ |
| 32 | win audit 1 | Builders had no exact schema, validator codes, examples or test vectors | LABEL-FORMAT §6–9 | ✅ |
| 33 | win audit 1 | Builders had no mocks list, validation rules, error map, state machine, reducer tests | UI-SPEC §10 | ✅ |
| 34 | win audit 1 | Owner inputs had no stub path | BLOCKED-PRE-B "Until it arrives" lines | ✅ |
| 35 | win audit 2 | Main review mock broke the spec's own `times` check; §10.6 used a 61 s time | UI-SPEC §10.1 mock, §10.6 | 🔧 in progress |
| 36 | win audit 2 | Plates sent through the screen keep-confirm; §4.3 said plates are always hidden | UI-SPEC §4.3, §10.5 R1–R2; café mock added | 🔧 in progress |
| 37 | win audit 2 | BLOCKED promised a café mock that didn't exist | UI-SPEC §10.1 `job-review-cafe`; BLOCKED-PRE-B | 🔧 in progress |
| 38 | win audit 2 | κ vector K1 disagreed with IEEE float arithmetic | LABEL-FORMAT §9 tolerance and rounding rule | 🔧 in progress |
| 39 | win audit 2 | No validator path for a missing labeller-B file (plan R3) | LABEL-FORMAT §7 warning code + cases | 🔧 in progress |
| 40 | win audit 2 | Several §8.3 expected codes didn't follow from §7 | LABEL-FORMAT §7 stop rules, §8.3 | 🔧 in progress |
| 41 | win audit 2 | State machine contradicted §5.4 and §10.3; missing states | UI-SPEC §10.4 | 🔧 in progress |
| 42 | win audit 2 | Reducer guards, CONFIRM_KEEP, MERGE precedence and UNDO undefined | UI-SPEC §10.5, §8 request 5 | 🔧 in progress |
| 43 | win audit 2 | 404 on a job route mapped to two different pages | UI-SPEC §7, §10.3, §10.4 | 🔧 in progress |
| 44 | win audit 2 | SoM mark given per item, needed per track | UI-SPEC §0, §8 request 2, §10.1 mock | 🔧 in progress |

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

| # | Risk | Effect on score | Mitigation in the docs | Owner input |
|---|---|---|---|---|
| 1 | Hero footage late | Demo 25%, Impact story | Default plan R4 → R1; synthetic-clip and mock paths keep code moving | Film hero 1 by Oct 25 18:00 EAT |
| 2 | No labeller B | Weaker Impact evidence (no κ) | R3 with honest "not measured" | Recruit B |
| 3 | Fewer than 5 pilots | Weaker Impact | Report the real count; shot 8.3 is cut | Send outreach Oct 27 |
| 4 | Official rules differ from MAXXING | Any | RULES-CHECKLIST: an action for every answer | Accept the rules at kickoff |
| 5 | API field names drift between WP5 and WP6 | Demo breaks | UI-SPEC §10.1: mocks follow WP5's names | — |
