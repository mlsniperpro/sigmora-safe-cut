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
| A8 | participant | participant | *(call failed after retry)* | F90, F120 | `unsure` | escalate |
| A9 | unsure | unsure | unsure | — | `unsure` | escalate |
| A10 | participant ×3 for `face:99` | — | — | — | track dropped (not in the input list); hallucination count +1 | — |
| A11 | participant (F90, F120; idx 0) | participant (F120, F150; idx 0) | participant (F90; idx 0) | — | `participant`; `frames` [90, 120, 150]; `evidence` = vote 1's; `matches_participant` **0** | — |
| A12 | participant (idx 0) | participant (idx 1) | participant (idx 0) | F90, F120 | `participant`; `matches_participant` **null** (the votes disagree on who) | — |
| A13 | participant (F90, "speaks to host") | bystander (F120, "background") | participant (F150) | — | `unsure`; `frames` [90, 120, 150]; `evidence` "Judges disagreed: speaks to host" | escalate |

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
| E2 | participant, participant, unsure | ruling `child` | `child`, locked |
| E3 | participant, participant, unsure | call failed | `unsure`, `needs_you`, `suggested_role: null`, `escalated: false` |
| E4 | participant, participant, unsure | ruling `participant`, frames F210, F240 (both sent, track present) | `unsure`, `needs_you`, `suggested_role: "participant"`, `escalation_frames: [210, 240]`, `escalated: true`. **Not kept.** |
| E5 | participant, bystander, bystander | ruling `bystander` | `unsure`, `needs_you`, `suggested_role: "bystander"` |
| E6 | participant, participant, unsure | ruling `participant`, citing F205 (not sent) | same as E3 (invalid citation) |
| E7 | participant, participant, unsure | ruling `unsure`, frames F210 (valid) | `unsure`, `needs_you`, `suggested_role: null`, `escalation_evidence: null`, `escalation_frames: null`, `escalated: true` (the drawer says the closer look couldn't settle it) |
| E8 | a track in 2 windows | window 1 ruling `participant`, window 2 ruling `child` | `child`, locked (any window's `child` wins) |
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
| M8 | 9 items | the first 8 get SAM prompts (in output order); item 9 gets a **static hidden box** ±`temporal.extend`, `needs_you`, logged `item_cap` |
| M9 | point (0, 0) on the 0–1000 grid (inside the bar) | point dropped. If the item has a valid `box`, its centre becomes the point; otherwise the item is dropped |
| M10 | the same `envelope` from votes 1 and 2, points 30 px apart on the same frame (a 1280×720 diagonal is 1,469 px, 5% = 73 px) | merged into one item |
| M11 | the role pass over loop 2's new tracks proposes `envelope` at F420 (no loop 3), or the step-6 budget check stops before its request, or the batched object-prompt request fails after retries | no SAM result → **static hidden box** at F420 ±`temporal.extend` (from `box`, else a 6% square), `needs_you`. Never dropped |

## 4. Red-team leak decisions (`redteam.md`)
Frame 50 has one approved kept-clear item, `A` (a participant's face), visible at box [100, 100, 200, 200]. Frame 1280×720.

| # | Finding | Expected |
|---|---|---|
| L1 | `face` at [110, 110, 190, 190] | IoU with A = 6,400 / 10,000 = **0.64 > 0.3**, same kind → **not a leak** (logged in `redteam` only) |
| L2 | `face` at [180, 100, 280, 200] | IoU = 2,000 / 18,000 = **0.11** → **leak** |
| L3 | `text` "AMINA K." at [110, 110, 190, 190] | kind doesn't match A's (face) → **leak** |
| L4 | `face`, `confidence: low`, at [600, 300, 650, 360] | **leak** (confidence never filters) |
| L5 | a box with 3 integers | **leak**, with the whole-frame box [0, 0, 1280, 720] |
| L6 | frame 50 missing from the output; also missing after one re-send | `unresolved += 1` for frame 50 only; `redteam_status: "failed"` |
| L9 | a red-team pass over 40 frames is skipped because its estimate exceeds the job cap | `unresolved += 40`, `redteam_status: "over_budget"`; publishing is off (invariant: `redteam_status != "ok"` ⇒ `unresolved > 0`) |
| L7 | `text` read *through* a redaction (inside a hidden item's region) | **leak** + flag `redaction_too_weak` → that item is re-rendered as `solid` |
| L8 | no findings on any frame | `unresolved` unchanged; every frame logged `finding: "none"` |

Publishing is allowed only when `audit.json.unresolved == 0` after at most 3 passes (WP4.md step 2; ARCHITECTURE §3.8's `passes: 2` is only an example).
