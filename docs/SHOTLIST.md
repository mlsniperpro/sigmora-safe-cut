> Imported unchanged from `sigmora-platform/docs/meta-hackathon/SHOTLIST.md` on 2026-10-20 (pre-event design). Where file paths or the Oct 14 model choices differ, [ARCHITECTURE.md](ARCHITECTURE.md) and [MAXXING.md](MAXXING.md) take precedence: this repo is standalone, and it adds Muse Voice Transcribe and an optional Muse Wonder escalation.

# Safe Cut: footage shot list (film BEFORE Oct 26)

Purpose: one footage set serves three jobs.
1. **Eval set** (private): about 30 labelled clips to measure what Safe Cut catches and what it misses.
2. **Demo footage** (public): 3–4 staged hero clips for the submission video and the live demo.
3. **Day-1 probes**: 3 clips to run through SAM 3.1 and Muse Spark the moment API access opens.

Filming is prep, not building, so it's safe before the event (see README "Rules of engagement").

## Ground rules (privacy is the product, so the dataset can't be a privacy problem)

- **Public footage = staged actors only.** Anyone who appears unblurred in the demo, the video, the repo or the README has signed a release (template at the bottom). The waiver says nothing we submit is confidential, so assume every published frame is public forever.
- **Real-public eval clips stay private.** Clips with genuine passers-by never leave our storage unredacted. They're used only for metrics (numbers, not frames) and deleted after judging (target 2026-12-01). They're never committed to any repo, including private ones; they live in `~/SafeCutEval/` plus a private bucket.
- **Children: consent or nothing.** Only children whose parent or guardian has signed for them. Never film other people's children on purpose. If one appears by chance, the clip goes in the private set only.
- **Meta API in Standard mode, never Contributor mode** (Contributor mode may train on inputs). Real-public clips go to the API only in Standard mode.
- **Fake data on screens.** Phone and laptop "PII" must be fabricated: a fake bank statement, a fake WhatsApp chat, a fake address. Prepare these in advance (props list below).
- **Kenya filming:** short handheld clips in ordinary public streets are fine for personal or creator use. Avoid government buildings, police, military, airports and malls with no-filming signs. If anyone objects, stop and delete on the spot.

## Camera settings

- DJI Osmo Pocket (primary) plus a phone (second look). **1080p, 30 fps, H.264, MP4.** SAM 3.1 takes MP4/MOV H.264/H.265, up to 15,000 frames per request (about 8 min at 30 fps). Muse Spark video input is MP4.
- Clips **15–45 s** each. Long enough for people to enter, exit and come back; short enough to stay cheap (SAM costs $0.0002 per frame, so a 30 s clip costs $0.18 per prompt at 30 fps, or $0.05 at 8 fps).
- Record audio, because Muse Spark uses speech to tell participants from bystanders ("Hi, I'm Amina, and…").
- Name files `SC-<cat>-<nn>-<location>-<yyyymmdd>.mp4`, e.g. `SC-A-01-cbd-20261018.mp4`.

## The list (about 34 clips)

| Cat | Scenario | # | What must happen in frame | Ground truth tests |
|---|---|---|---|---|
| **A** | **Street interview**, 1 guest | 6 | Host and guest talk to camera; 3+ passers-by cross behind, at least one close to the lens | Guest and host stay CLEAR; passers-by HIDDEN |
| **B** | **Walk-and-talk vlog** (host only) | 4 | Host walks a busy street or market; faces pass at several distances | Host clear; everyone else hidden; small and far faces |
| **C** | **Screens with PII** (staged props) | 4 | Café/desk: laptop with a fake inbox, phone with a fake chat, and one screen with a harmless menu or map | PII screens HIDDEN; harmless screen CLEAR (the context test) |
| **D** | **Number plates** | 4 | Parked and moving cars, matatu/boda plates, one plate partly occluded | All plates hidden, including moving ones |
| **E** | **Documents & addresses** | 3 | Parcel label with an address, ID-like card (FAKE), house number on a gate | Hidden |
| **F** | **Home / property tour** | 3 | Walk-through with family photos on a wall, mail on a table, a TV showing a person | Photos and mail hidden; the presenter clear |
| **G** | **Occlusion & re-entry** (actors) | 3 | Bystander walks behind a pillar or van and reappears; leaves frame and returns | Re-acquired person stays HIDDEN (blur-by-default) |
| **H** | **Group interview** | 2 | 2–3 participants introduced on camera, plus 1 bystander who stops to watch | All participants clear; the watcher hidden. Hardest role call |
| **I** | **Crowd stress** | 2 | 20+ people in frame (bus stage, market) | Tests SAM's 16-objects-per-frame limit; measures leaks |
| **J** | **Negatives** (no bystanders) | 3 | Talking head only. Reuse `edit_*` footage plus one new clip | Nothing hidden (over-blur test) |

**Hero demo clips (staged, all actors signed), film 2 takes each:**
1. **"The street interview":** guest (actor 1) clear; passing "child" (consented family member) hidden; parked car plate hidden; actor 2 walks past holding a phone showing a fake text with a phone number, hidden. One take where actor 2 ducks behind a parked van and reappears (shows the re-entry guarantee).
2. **"The café":** host interviews a founder at a table; laptop A shows a fake email inbox (hidden), laptop B shows a menu (clear). Shows the model reads content, not just "screen".
3. **"The walk-through":** a home tour with family photos and an addressed envelope (both hidden), the presenter clear.

## Props checklist

- [ ] 2 laptops plus 2 phones; fake inbox, fake bank statement, fake chat with a fake phone number, a harmless menu and a map (all mock-ups, no real accounts).
- [ ] A fake ID-style card (clearly marked SAMPLE in small print, invented details).
- [ ] An envelope or parcel with an invented address.
- [ ] Framed photos (actors' own, with their consent).
- [ ] Release forms (printed) plus a pen; a phone to photograph signed forms.
- [ ] 3–5 actors: a guest, 2 passers-by, and a "watcher" for H.

## Release form (short)

> I, ________, agree that AlgoCracked / Sigmora may record me on ____ (date) at ________ and use the footage, **unblurred**, in a public demo, video, website and hackathon submission for "Sigmora Safe Cut". I understand it may be shared with Meta and Cerebral Valley and published online. Signature ________ Date ____ (Parent/guardian for a minor: ________)

## Schedule

- **Sat Oct 17 – Sun Oct 18:** hero clips (actors), then categories A–H in the CBD, a market and a café.
- **Mon Oct 19 – Tue Oct 20:** top-up: I (crowd), D (plates), plus reshoots.
- **Oct 20–24:** labelling (EVAL.md).
