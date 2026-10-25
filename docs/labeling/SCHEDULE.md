# Labelling schedule (Oct 24 → kickoff, and the fallbacks)

Status: **v1, written 2026-10-24 12:45 EAT (PRE-B).** Times are EAT. The original plan in [EVAL.md](../EVAL.md) §6 (dev split labelled Oct 20–21, test Oct 22–23, frozen Oct 24) has slipped: on Oct 20 [MAXXING.md](../MAXXING.md) §5 recorded that `~/SafeCutEval/` didn't exist and the Oct 17–18 filming looked undone. This file replans from today.

**Decision: plan as if nothing has been filmed yet.** The last written evidence ([MAXXING.md](../MAXXING.md) §5, Oct 20) says the footage didn't exist, and planning for less footage is the safe side: if more exists, labelling just starts earlier. So the **default track is R4 → R1** (§4): hero clip 1 is filmed and labelled first, then the rest. The 18-clip plan in §3 is what happens if filming is done by Oct 24 evening. Filming is the owner's hands-on step, in [`BLOCKED-PRE-B.md`](../BLOCKED-PRE-B.md).

How to label: [LABELING-GUIDE.md](LABELING-GUIDE.md). Tool: [CVAT-SETUP.md](CVAT-SETUP.md). Files: [LABEL-FORMAT.md](LABEL-FORMAT.md).

## 1. What actually has to be done by when

| Deadline | What | Why |
|---|---|---|
| **Oct 26 19:00** (kickoff) | Hero clip 1 labelled and in the private bucket | WP7's loader and metric tests, WP0's probes and every Wave B package use it |
| Oct 27 (Wave B starts) | Hero clips 2–3 and at least 3 dev clips labelled | WP7 dev runs; WP2/WP3 tuning |
| **Oct 29 23:59** | Test split labelled by two labellers, disagreements resolved, **frozen** (WP7 writes `eval/splits/test.sha256`) | The first test-split run is Oct 30 ([MAXXING.md](../MAXXING.md) §4); EVAL.md requires a freeze before it |

So "about 18 clips by Oct 26" is the **target**; the hard line is hero clip 1 by kickoff and a frozen test split by Oct 29. Note the owner's other deadlines on Oct 27 (Build With AI 00:00, OpenCV 09:45, GitLab 16:00): Oct 26 daytime is the riskiest labelling day.

## 2. Hours per clip (estimates; measure on the first two clips)

These are our estimates for a **30 s handheld clip at 30 fps** (900 frames), keying every 15 frames as the guide asks. A handheld camera makes even "static" things move, so participants who are on screen the whole clip are the expensive part (about 60 keyframes each). They are **not measured yet**: labeller A times the first two clips and replaces this table.

| Cat ([SHOTLIST.md](../SHOTLIST.md)) | Typical entities | Labeller A (boxes + JSON) | Labeller B (roles only) |
|---|---|---|---|
| A street interview | 2 participants, 3–4 bystanders, 0–1 plate | 60–75 min | 10 min |
| B walk-and-talk | host, 6–10 passing faces | 70–90 min | 12 min |
| C screens | 2 participants at a table, 3 screens | 35–45 min | 8 min |
| D plates | 4–8 plates, a few drivers | 35–50 min | 8 min |
| E documents | presenter, 3 objects | 25–35 min | 6 min |
| F home tour | presenter, 4–6 objects | 45–60 min | 8 min |
| G re-entry | host, 1–2 actors with gaps | 40–50 min | 8 min |
| H group interview | 3 participants, 1 watcher | 60–75 min | 12 min |
| I crowd | 20+ people | 2–3 h | 20 min |
| J negatives | 1 talking head | 15–20 min | 3 min |

Fixed costs: CVAT install and project setup about 2 h (once); a calibration session where A and B label hero clip 1 together and read the guide's cases about 1 h (once); resolving disagreements about 5 min per clip.

## 3. The plan for ~18 clips by Oct 26 (if footage exists by Oct 24 evening)

The 18: **3 hero clips**: hero 1 take A (`H1A`, whose labelled boxes STORYBOARD shot 1.2 shows) and the best take of hero 2 and 3; hero 1 take B (`H1B`, the re-entry case) is labelled only if time allows (about 1 h more) + **15 eval clips** in the priority order from [MAXXING.md](../MAXXING.md) §5 (A, C, D, G, J first). Splits ([LABELING-GUIDE.md](LABELING-GUIDE.md) §6): hero clips → `hero`; every real-public clip → `test`; staged clips go to `dev` or `test` so that both splits cover the categories. **Assignment:** `dev` = C × 1, G × 1, J × 1 (all staged: the 3 dev clips Wave B needs on Oct 27); `test` = A × 4 and D × 3 (real-public) plus C × 2, G × 1, J × 2 (staged), 12 clips in all.

| Clips | Count | Labeller A time (midpoint) |
|---|---|---|
| Hero 1 (street), 2 (café), 3 (walk-through) | 3 | 68 + 40 + 53 = 161 min |
| A street interview | 4 | 4 × 68 = 272 min |
| C screens | 3 | 3 × 40 = 120 min |
| D plates | 3 | 3 × 43 = 129 min |
| G re-entry | 2 | 2 × 45 = 90 min |
| J negatives | 3 | 3 × 18 = 54 min |
| **Total** | **18** | **≈ 14 h** of boxes, + 3 h setup and calibration = **≈ 17 h** |

Labeller B: about 1 h calibration + 3 h for all 18. Resolution: about 1.5 h, done by A and B together (LABELING-GUIDE §5). **Total people time ≈ 25 h** (A 18 h, i.e. the 17 h above plus 1 h fixing the boxes B flags; B 4 h; 1.5 h × 2 resolving) **over about 51 elapsed hours.** It's feasible only if A has two near-full days and B exists.

| When (EAT) | Labeller A | Labeller B | Owner |
|---|---|---|---|
| **Sat Oct 24, 14:00–23:00** | Install CVAT, create the 3 projects (2 h). Calibrate on hero 1's roles with B (1 h). Hero 1 boxes (≈ 1.1 h). Hero 2, hero 3 (≈ 1.5 h). Time each clip | Calibrate on hero 1; label hero 2–3 roles | Upload hero 1 + its labels to the private bucket |
| **Sun Oct 25, 09:00–20:00** | A × 4, C × 3, G × 2 (272 + 120 + 90 = 482 min ≈ 8 h) | Roles for those 9 | Apply the §3 split (dev = C, G, J × 1; the rest to test) |
| **Mon Oct 26, 08:00–17:00** | D × 3, J × 3 (≈ 3 h); fix boxes B flagged (1 h); resolve disagreements with B (1.5 h, LABELING-GUIDE §5); export + back up everything | Roles for D, J; 10% box spot-check; resolve disagreements with A (1.5 h) | Back up `~/SafeCutEval/labels/` to an encrypted local drive in the owner's custody (never a cloud backup) |
| Mon Oct 26, 19:00 | — | — | Kickoff. Hero + dev labels in the bucket; test labels stay local |

**Binding for other work packages (owner's decision, 2026-10-24):** WP0 (fixtures, probes) and WP7 (the split freezer, `eval/splits/test.sha256`, and the runner) **must use this split: 12 test clips and 3 dev clips** (plus the 3 hero clips), Their budgets are their own WP caps (WP0 ≤ $6, WP7 ≤ $12 on dev and hero data) and PRE-A `docs/API-NOTES.md` §9.2's lines (the test line's hard $43.20); the $20 pilot cap in [PILOTS.md](../PILOTS.md) §5 covers pilot access codes only, never eval spend. This replaces the "about 12 dev / about 18 test" sizes in [EVAL.md](../EVAL.md) §1 for this event; PRE-B doesn't own EVAL.md, so updating its §1 is a request to its owner (in the PRE-B PR). PRE-A's cost model now uses this split (`docs/API-NOTES.md` §9.2 at `origin/pre-a-research` `565eee3`: 12 test, 3 dev, 3 hero), and cost figures stay PRE-A's to own. **Clip length:** the test split's **mean clip length stays ≤ 30 s** (every clip 15–45 s, [SHOTLIST.md](../SHOTLIST.md)), because PRE-A prices the hard $43.20 test line at a 30 s mean (`docs/API-NOTES.md` §9.2 @ `565eee3`); the owner checks it when choosing the test clips, and WP7's split freezer refuses to freeze a test split whose mean is over 30 s (fail closed: a clip is swapped, never silently trimmed, so its labels stay valid). With only 3 dev clips, dev iterations run on all 3 (PRE-A `docs/API-NOTES.md` §9.2 plans 8 rounds × 3 clips × $0.59 = $14.16 inside WP2's $15 cap). Adding the 3 consented hero clips would double a round to $3.54, so it's allowed only by cutting rounds to stay within that cap (at most 4 rounds of 6 clips = $14.16), never beyond it. If the reduced plan R2 below is triggered, the 8-clip test split it defines replaces this one, and WP7 records which split it froze.

## 4. Reduced plans (pick the first one that fits)

**R1. Footage arrives a day late (filmed Oct 25).** Kickoff needs only hero 1, so label the three hero clips first on Oct 25–26, then the 3 dev clips (C, G, J × 1, §3) by Oct 27, which Wave B needs (§1), then the 12 test clips Oct 27–29 in the priority order, about 4 h a day around the Oct 27 deadlines. Freeze Oct 29 23:59 with whatever is double-labelled.

**R2. Eval footage won't exist before Oct 28.** The test split shrinks. Minimum viable test split: **8 clips**: A × 3 and D × 1 (real-public), plus C × 2, G × 1 and J × 1 (staged, allowed in `test` per [LABELING-GUIDE.md](LABELING-GUIDE.md) §6, so the re-entry and over-blur cases are still covered). About 6 h for A. Use SA-Co/VEval SmartGlasses (CC BY 4.0) for the tracking and leak-guard numbers ([MAXXING.md](../MAXXING.md) risk 1, [EVAL.md](../EVAL.md) §2). The README and video say exactly how many clips the test split has; never extrapolate ([AGENTS.md](../../AGENTS.md) rule 9).

**R3. Only one labeller.** Default rule: plan with labeller B (recruiting B is the owner's step, in [`BLOCKED-PRE-B.md`](../BLOCKED-PRE-B.md)); if no B is recruited and free to calibrate on hero 1 by **Oct 26 08:00 EAT** (hero 1 is filmed by Oct 25 18:00 EAT, so B can't start earlier), switch to R3 automatically, without waiting. Do everything above without B. κ is reported as "not measured (single labeller)". Labeller A re-labels `should_hide` on 5 clips at least a day later, without looking at the first pass; that's "intra-rater agreement" and must be named as such, not called κ between labellers. The second pass is saved as `<clip-id>.labeller-A2.json` ([LABEL-FORMAT.md](LABEL-FORMAT.md) §6), never as a labeller-B file, and reported as LABEL-FORMAT §9.2 K5 says.

**R4. Hero clips aren't filmed by Oct 25.** This blocks the demo (25%), not just eval. Film **hero clip 1 first**, on a phone if need be, with the full cast in [`BLOCKED-PRE-B.md`](../BLOCKED-PRE-B.md) (host, guest, consented child, actor 2 with the fabricated chat, 2+ passers-by, the actor who looks at the camera, a parked car that is a cast member's or carries a fake plate). Only the cast may be in frame; re-take if anyone else walks in. Do take A first; take B (the van re-entry) can follow. Everything else waits for it.

**Never in any plan:** labelling on a hosted service, inventing labels for clips nobody watched, or relabelling after seeing model output to make a number look better.

## 5. Priority order if time runs out mid-plan

hero 1 → hero 2 (the context test) → A → C → G → D → J → hero 3 → H → B → E → F → I.

I (crowd) is last because it costs 2–3 h per clip; if it's skipped, the README says crowd performance is untested on our set.
