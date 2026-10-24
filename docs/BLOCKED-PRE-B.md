# BLOCKED (PRE-B): inputs only the owner can provide

PRE-B's documents are complete. Everything Claude could decide is decided; the decisions are in the PRE-B PR and in the docs. Each item below needs the owner physically: filming, recruiting or messaging real people, setting up a machine, or account steps. Each one says **what's needed, by when, the default to follow, and what's ready for it**, so it can be done without coming back with questions. Nothing else waits on these: the docs already fall back when an input is late (e.g. [SCHEDULE.md](labeling/SCHEDULE.md) §4 plans R1–R4).

## Footage and labels

- [ ] **Film hero clip 1, both takes, with signed releases.** By **Oct 25 18:00 EAT** (it must be labelled before kickoff, Oct 26 19:00).
  - Default: a phone is fine. Film the full [SHOTLIST.md](SHOTLIST.md) hero 1 cast, every adult with a signed release: the host and the guest (both kept clear); a consented child (a family member, with the guardian's signature) passing behind the guest; actor 2 walking past with a phone showing a fabricated chat with a phone number; at least 2 more passers-by; and one actor who stops, looks at the camera and never speaks (the Needs-you case in STORYBOARD 3.3 and 4.3). A parked car with a visible plate. Take B: actor 2 ducks behind a van and reappears. Every one of these is a shot in [STORYBOARD.md](STORYBOARD.md) (1.2, 3.3, 4.1–4.3, 6.1).
  - If no consented child is available, film without one and cut the child shots (1.2 label, 4.1). Never film someone else's child.
  - Ready for it: [LABELING-GUIDE.md](labeling/LABELING-GUIDE.md) (the cases cover every element of this clip), and plan R4 in SCHEDULE.md.
- [ ] **Film hero clips 2 (café) and 3 (walk-through).** By Oct 26.
  - Default for the café: laptop A shows a fabricated inbox, laptop B a menu. It will appear under **Needs you** and then be kept clear with one tap ([STORYBOARD.md](STORYBOARD.md) rule 4).
  - Default for the home tour: the TV shows a fabricated video call with a consenting actor, not broadcast TV (LABELING-GUIDE.md case 9).
- [ ] **Film the eval clips** in this order: A × 4, C × 3, D × 3, G × 2, J × 3. By **Oct 24 evening** for the 18-clip plan (SCHEDULE.md §3); by **Oct 25** for plan R1; if they can't exist before Oct 28, plan R2 applies (an 8-clip test split, SCHEDULE.md §4).
  - Default split: SCHEDULE.md §3 (`dev` = C, G, J × 1 each, all staged; everything real-public goes to `test`).
- [ ] **Set up the CVAT machine.**
  - Default: a Linux or Windows/WSL2 machine the owner controls. If none is free, use labeller B's (or another trusted person's) local machine, with clips moved on an encrypted drive. **Never the Intel dev Mac** (PRE-B.md, EVAL.md §1) and **never a cloud VM** ([CVAT-SETUP.md](labeling/CVAT-SETUP.md) §2).
  - Ready for it: CVAT-SETUP.md §3–5, pinned to CVAT v2.80.0.
- [ ] **Recruit labeller B** for about 4 hours: a 1 h calibration session plus about 3 h labelling roles. By **Oct 25 09:00 EAT**.
  - Default if nobody has started by then: switch to single-labeller plan R3. Agreement is then reported as "not measured" (SCHEDULE.md §4).
- [ ] **Upload the consented clips** (hero and dev only) and their labels to the private bucket. This needs `SAFECUT_CLIPS_URL` and a read token as environment secrets (owner step O3).
  - Default: test-split clips and labels stay on the owner's Mac and its private backup. Only the split hash is committed.
- [ ] **Time yourself masking hero clip 1 by hand** in an ordinary editor, with an on-screen timer (screen recording `SR-10`). Before Nov 3.
  - The time is committed as `eval/results/creator-time-<date>/metrics.json` and fills `{manual_minutes}` in the video ([STORYBOARD.md](STORYBOARD.md) §2).

## Creator pilots (messages to real people)

- [ ] **Build the private list of 15 candidates** from the channel types in [PILOTS.md](PILOTS.md) §2. By Oct 26. The list stays out of this repo.
- [ ] **Personalise and send the outreach** (PILOTS.md §3: a 103-word DM and a 110-word email). On **Oct 27**.
  - Default: one follow-up after 3 days; no incentives.
- [ ] **Send the consent note, protocol and per-pilot access codes** (PILOTS.md §4–5), but only after Claude has posted that the live service passed its deletion and `store: false` check (Oct 29 or WP5's first live day).
  - Default caps: $4 per code, $20 in total.
- [ ] **Collect timings, answers and written permissions** by Nov 2 23:59 EAT.
  - Default credit: anonymous, by format and country, unless the pilot chooses otherwise.

## Kickoff and submission (account steps)

- [ ] **Oct 26 kickoff: accept the official rules.** Then Claude works through [RULES-CHECKLIST.md](RULES-CHECKLIST.md) the same evening and applies each row.
- [ ] **Get the Meta API key** with the hackathon credits and add `MODEL_API_KEY` to the cloud environment's secrets (O6). Create a separate low-limit key for agents if the console allows it.
- [ ] **Make this repo public** (O7), after Claude posts its check for secrets and footage.
  - If the rules require a repo created after kickoff, create the fresh repo instead (RULES-CHECKLIST.md §1/§3).
- [ ] **If the rules require them:** identity or age checks; the company's legal name and country (only if the Startup track requires a company entry; otherwise enter as an individual); tax or banking forms for prize payment (after judging).
- [ ] **Nov 3: record the VO** in your own voice (not the clone; STORYBOARD.md rule 6), plus screen recordings `SR-01` to `SR-11` on the deployed app (STORYBOARD.md §3).
- [ ] **Nov 4 by 23:00 EAT: submit on Cerebral Valley** and post the launch thread.
