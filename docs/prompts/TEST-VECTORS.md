# Test vectors for the prompt specs' deterministic rules

These cover the **pure** logic around each model call (aggregation, rulings, normalisation, leak decisions). WP2 (scout), WP3 (policy) and WP4 (audit) copy them into unit tests. Model calls are stubbed: the inputs below are what a stubbed call returns. Coordinates are prepared-clip pixels, half-open boxes (API-NOTES §5). IoU = intersection area / union area.

## 1. Role-pass vote aggregation (`role-pass.md`, "Self-consistency rules")
Setup: track `face:7` is present in keyframes F90, F120, F150, and all three were sent.

| # | Vote 1 | Vote 2 | Vote 3 | Cited frames (union, valid) | Expected `role` | Then |
|---|---|---|---|---|---|---|
| A1 | participant | participant | participant | F90, F120 | `participant` | policy may `keep` (if not a child) |
| A2 | participant | participant | participant | F90 only | `unsure` (fewer than 2 keyframes) | escalate |
| A3 | participant | participant | bystander | F90, F120 | `unsure` | escalate |
| A4 | participant | participant | child | any | `child`, `locked: true` | **no** escalation |
| A5 | bystander | bystander | bystander | F90 | `bystander` | hidden |
| A6 | participant | *(track missing from the output)* | participant | F90, F120 | `unsure` (missing counts as `unsure`) | escalate |
| A7 | participant | participant, citing **F95** (not sent) | participant | F90, F120 | `unsure` (vote 2 discarded) | escalate |
| A8 | participant | participant | *(call failed after retry)* | F90, F120 | `unsure`, `failed_votes: 1` | escalate (2 real votes remain); if escalation then fails or is skipped, `hold: "no_roles"` |
| A9 | unsure | unsure | unsure | — | `unsure` | escalate |
| A10 | participant ×3 for `face:99` | — | — | — | track dropped (not in the input list); hallucination count +1 | — |
| A11 | participant (F90, F120; idx 0) | participant (F120, F150; idx 0) | participant (F90; idx 0) | — | `participant`; `frames` [90, 120, 150]; `evidence` = vote 1's; `matches_participant` **0** | — |
| A12 | participant (idx 0) | participant (idx 1) | participant (idx 0) | F90, F120 | `participant`; `matches_participant` **null** (the votes disagree on who) | — |
| A13 | participant (F90, "speaks to host") | bystander (F120, "background") | participant (F150) | — | `unsure`; `frames` [90, 120, 150]; `evidence` "Judges disagreed: speaks to host" | escalate |
| A14 | w1 participant, w2 participant (idx 0) | w1 participant, w2 participant (idx 0) | w1 participant, w2 bystander | w1 F90, F120; w2 F1500, F1530 | `unsure` (window 2 isn't 3/3); `votes` [participant, participant, bystander] | escalate |
| A15 | w1 participant, w2 participant (idx 0) | w1 participant, w2 participant (idx 0) | w1 participant, w2 participant (idx 0) | w1 F90, F120; w2 F1500, F1530 | `participant`; `frames` [90, 120, 1500, 1530]; `matches_participant` **0** | policy may `keep` |
| A16 | w1 bystander, w2 bystander | w1 bystander, w2 bystander | w1 bystander, w2 bystander | w1 F90; w2 F1500 | `bystander` (bystander in every window) | hidden |

Objects (`screen:2`):
| # | Votes (`sensitive`) | Expected |
|---|---|---|
| B1 | false, false, false | `sensitive: false` → `needs_you` with the suggestion "keep clear" (DESIGN §2.5: the creator confirms) |
| B2 | true, false, false | `sensitive: true` → hidden |
| B3 | false, false, *(failed)* | `sensitive: true` (fail closed) → hidden |

## 2. Escalation rulings (`escalation.md`, ordered rules, first match wins)
| # | Role-pass votes | Escalation result | Expected |
|---|---|---|---|
| E1 | participant, participant, child | *(not called)* | `child`, locked |
| E2 | participant, participant, unsure | ruling `child` | `child`, locked; `escalated: true` |
| E3 | participant, participant, unsure | call failed | `unsure`, `needs_you`, `suggested_role: null`, `escalated: false`, `hold: "no_roles"` |
| E4 | participant, participant, unsure | ruling `participant`, frames F210, F240 (both sent, track present) | `unsure`, `needs_you`, `suggested_role: "participant"`, `escalation_frames: [210, 240]`, `escalated: true`. **Not kept.** |
| E5 | participant, bystander, bystander | ruling `bystander` | `unsure`, `needs_you`, `suggested_role: "bystander"` |
| E6 | participant, participant, unsure | ruling `participant`, citing F205 (not sent) | same as E3 (invalid citation) |
| E7 | participant, participant, unsure | ruling `unsure`, frames F210 (valid) | `unsure`, `needs_you`, `suggested_role: null`, `escalation_evidence: null`, `escalation_frames: null`, `escalated: true` (the drawer says the closer look couldn't settle it) |
| E8 | a track in 2 windows | window 1 ruling `participant`, window 2 ruling `child` | `child`, locked (any window's `child` wins); `escalated: true` |
| E9 | a track in 2 windows | window 1 `participant`, window 2 `bystander` | as E7: `suggested_role: null`, `escalated: true` |

The invariant tested over every row: **no escalation output ever yields `keep`.** WP3 property-tests it over random vote and ruling combinations with hypothesis.

## 3. Miss-loop post-processing (`miss-loop.md`, steps 1–5)
Swept so far: `face, person, license plate, screen, phone, document, name badge`.

| # | Model item | Expected |
|---|---|---|
| M1 | `sam_phrase "Envelope."`, `recurs: true`, frame F420 (sent) | phrase `envelope` → phrase sweep **and** point prompt |
| M2 | `sam_phrase "envelope"`, `recurs: false` | point prompt only |
| M3 | `sam_phrase "House Number"`, `recurs: true` | phrase `house number` → sweep + point |
| M4 | `sam_phrase "addressed envelope on table"` (4 words), `recurs: true` | **no phrase sweep** (over 3 words); point prompt only. Logged as `phrase_too_long` |
| M5 | `sam_phrase "face"`, `recurs: true` | no sweep (already swept); **point prompt runs** |
| M6 | `sam_phrase "thing"`, `recurs: true` | no sweep (blocklist); point prompt runs |
| M7 | frame F421 (not sent) | item **dropped** |
| M8 | 9 items | the first 8 get SAM prompts (in output order); item 9 gets a **static hidden box** ±`max(temporal.extend, round(job.fps))` (±30 at 30 fps), `needs_you`, logged `item_cap` |
| M9 | point (0, 0) on the 0–1000 grid (inside the bar) | point dropped. If the item has a valid `box`, its centre becomes the point; otherwise the item is dropped |
| M10 | the same `envelope` from votes 1 and 2, points 30 px apart on the same frame (a 1280×720 diagonal is 1,469 px, 5% = 73 px) | merged into one item |
| M11 | the role re-pass proposes `envelope` at F420 for loop 2, and the step-6 budget check stops before loop 2's request, or the batched object-prompt request fails after retries | no SAM result → **static hidden box** at F420 ±`max(temporal.extend, round(job.fps))` = F390–F450 at 30 fps (from `box`, else a square of side 6% of `min(W, H)`), `needs_you`. Never dropped |
| M12 | loop 2 proposes `sam_phrase "Kids"` at F600 and SAM tracks it, or it falls back to a static box | singularised `kid` → concept `person`, track `person:n` (next free), `child_phrase: true`; WP3: `kind: child`, `locked: true`, never escalated; it does **not** count toward the `scene.children` match |
| M13 | phrases `little girl`, `school kids`, `babies`, `schoolchildren`, `passers-by`, `old men` | tokens → `girl`, `kid`, `baby`, `schoolchild` (child set), `passerby`, `man` (person set): the first four are `person:n` with `child_phrase: true`; the last two are `person:n` |

## 4. Red-team leak decisions (`redteam.md`)
Frame 50 has one approved kept-clear item, `A` (a participant's face), visible at box [100, 100, 200, 200]. Frame 1280×720.

| # | Finding | Expected |
|---|---|---|
| L1 | `face` at [110, 110, 190, 190] | IoU with A = 6,400 / 10,000 = **0.64 > 0.3**, same kind → **not a leak** (logged in `redteam` only) |
| L2 | `face` at [180, 100, 280, 200] | IoU = 2,000 / 18,000 = **0.11** → **leak** |
| L3 | `text` "AMINA K." at [110, 110, 190, 190] | kind doesn't match A's (face) → **leak** |
| L4 | `face`, `confidence: low`, at [600, 300, 650, 360] | **leak** (confidence never filters) |
| L5 | a box with 3 integers | **leak**, with the whole-frame box [0, 0, 1280, 720] |
| L6 | frame 50 missing from the output; also missing after one re-send | `unresolved += 1` for frame 50 only; `blocked_reason: "audit_failed"` |
| L11 | `text` "TODAY'S SPECIALS" at [110, 110, 190, 190] on frame 50, where `B` is an approved non-sensitive `menu:1` track (a miss-loop concept) visible at [100, 100, 200, 200] | object concept, `text` finding, IoU 0.64 → **not a leak** (any approved non-sensitive object track matches `text`/`screen`) |
| L9 | a red-team pass over 40 frames is skipped because its estimate exceeds the job cap | `unresolved += 40`, `blocked_reason: "over_budget"`, `audit_budget_cause: "job_cap"`; publishing is off (invariant: `blocked_reason != null` ⇔ `unresolved > 0`) |
| L10 | EgoBlur reports `frames_scanned` 300 of `frames` 900 (any cause: a crash, a timeout) | the 600 unscanned frames count in `unresolved`, `blocked_reason: "audit_failed"`; publishing is off. There is no sampled EgoBlur mode |
| L7 | `text` read *through* a redaction (inside a hidden item's region) | **leak** + flag `redaction_too_weak` → that item is re-rendered as `solid` |
| L8 | no findings on any frame | `unresolved` unchanged; every frame logged `finding: "none"` |

Publishing is allowed only when `audit.json.unresolved == 0` after at most 3 passes (WP4.md step 2; ARCHITECTURE §3.8's `passes: 2` is only an example).

## 5. Policy gate for children (API-NOTES §12, `scene.children` and `decisions.items[].hold`)
Each row: a `person:` track with 3/3 `participant` votes on ≥ 2 keyframes (would be auto-kept).

| # | Scene pass | Child items (voted `child` by the role pass or escalation; `child_phrase` alone never counts) | Expected |
|---|---|---|---|
| P1 | **failed** (`status: "failed"`, `children: []`) | 0 | hidden, `needs_you`, `hold: "no_scene"` (a failure never turns the gate off) |
| P2 | ok, `children` has 1 entry | 0 | hidden, `needs_you`, `hold: "unmatched_child"` |
| P3 | ok, `children` has 1 entry (hero clip 1) | 1 (`face:4`, locked) | auto-kept as before, `hold: null` |
| P4 | ok, `children: []` | 0 | auto-kept, `hold: null` |
| P5 | ok, `children` has **2** entries | 1 child **item** made of `face:4` + `person:3` (both locked `child`) | hidden, `needs_you`, `hold: "unmatched_child"` (items are counted, not tracks: 1 < 2) |
| P10 | ok, `children` has 1 entry | 0 (the only child item is a `child_phrase` poster track, locked by rule 0) | hidden, `needs_you`, `hold: "unmatched_child"` |

Speech and introduction evidence (a transcript exists: `job.audio: true`, `status: "ok"`, `degraded: false`; each track 3/3 `participant` on ≥ 2 keyframes, no scene child):

| # | Track | Expected |
|---|---|---|
| P6 | `matches_participant: 0`, participant 0 "Amina" has `speaker: "S1"` with 3 turns | speech evidence → auto-kept |
| P7 | `matches_participant: 1`, participant 1 "Kev" has `speaker: null`, `introduced_in_turn: 2` (turn 2: "this is my mate Kev") | introduction evidence → auto-kept |
| P8 | `matches_participant: null` (votes named different participants) | no speech or introduction evidence → hidden, `needs_you`, `hold: "no_speech_link"` |
| P9 | any 3/3 participant; `job.audio: true`, but Voice Transcribe and the fallback both failed (`turns: []`, `degraded: true`) | hidden, `needs_you`, `hold: "no_speech"` (a speech failure never turns the check off) |
| P9b | any 3/3 participant; `job.audio: true`; the speech stage was skipped for budget (`transcript.json` `status: "skipped"`, `turns: []`, `degraded: true`) | hidden, `needs_you`, `hold: "no_speech"` |
| P9c | 3/3 participant, `matches_participant: null`; `job.audio: true`, transcript `status: "ok"`, `degraded: false`, `turns: []` | a transcript exists (empty) → no speech or introduction evidence → hidden, `needs_you`, `hold: "no_speech_link"` |
| P11 | `matches_participant: 0`, participant 0 has `speaker: null`, `introduced_in_turn: null` (with any transcript, including `turns: []`) | no evidence (`speaker == null` alone isn't an introduction) → hidden, `needs_you`, `hold: "no_speech_link"` |

