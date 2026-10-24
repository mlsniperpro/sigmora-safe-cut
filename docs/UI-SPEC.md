# Safe Cut: UI spec (WP6 builds from this)

Status: **v1, 2026-10-24 (PRE-B, docs only).** For every screen in [WP6](work-packages/WP6.md): wireframes (desktop and mobile), the copy deck, the states, keyboard and accessibility behaviour, and which contract field ([ARCHITECTURE.md](ARCHITECTURE.md) §3) feeds each element. The product rules behind the screens are in [DESIGN.md](DESIGN.md) §2.5 (policy), §2.7–2.9 (styles, audit, receipt); the demo that films these screens is [DEMO.md](DEMO.md) and [STORYBOARD.md](STORYBOARD.md).

Contents: [0 Principles](#0-principles-and-shared-pieces) · [1 Landing](#1-landing-) · [2 Upload and progress](#2-upload-and-progress-try) · [3 Review panel](#3-review-panel-jobsid) · [4 The "Why?" drawer](#4-the-why-drawer) · [5 Result and receipt](#5-result-and-receipt-jobsidresult) · [6 Demo-mode banner](#6-demo-mode-banner) · [7 Errors and empty pages](#7-error-and-not-found-pages) · [8 Field map](#8-contract-field-map-and-requests-to-wp5) · [9 Accessibility checklist](#9-accessibility-checklist)

## 0. Principles and shared pieces

**Voice.** Plain, calm and specific. Say what happened and what the creator can do. No hype ("magic", "revolutionary"), no blame ("you uploaded the wrong file"), no exclamation marks. Never say "face recognition" or "identify": Safe Cut judges roles from behaviour and context and does no identity matching ([CREATOR-PROBLEMS.md](CREATOR-PROBLEMS.md), wording rule). Use "hide" and "keep clear", not "blur" (we don't blur; [DESIGN.md](DESIGN.md) §2.7).

**Shared vocabulary** (use these words everywhere, including the receipt):

| Concept | UI word | Never |
|---|---|---|
| `decision: hide` | **Hidden** | Blurred, censored |
| `decision: keep` | **Kept clear** | Allowed, whitelisted |
| `decision: needs_you` | **Needs you** | Flagged, error |
| role `participant` | **Part of the story** | Consented (we don't know that) |
| role `bystander` | **Not part of the story** | Stranger, intruder |
| role `child` | **Child** | Minor (too legal) |
| role `unsure` | **Not sure** | Unknown |
| `kind: person` / `child` / `plate` / `screen` / `document` / `other` | **Person** / **Child** / **Number plate** / **Screen** / **Document** / **Other item** | |
| `decided_by: policy` / `model` / `creator` | **Safe Cut's rules** / **Muse Spark** / **You** | "The AI" |
| `style: solid` / `pixelate` / `person_solid` | **Solid cover** / **Coarse pixels** / **Whole person covered** | Blur |

**Header (all pages).** Desktop: wordmark "Safe Cut" with "by Sigmora" in small text (links to `/`), then "How it works", "Results", "Try it", "GitHub". Mobile: wordmark + a "Menu" button that opens the same links in a sheet. When opened from Sigmora (`?from=sigmora`, see §5), the header shows "Back to Sigmora" instead of the nav.

**Footer (all pages).** "Built for the Meta Global AI Developer Hackathon with Muse Spark, SAM 3.1 and Muse Voice Transcribe on the Meta Model API." · "Uploads are deleted after 24 hours." · "MIT licence" · "Source on GitHub".

**Time display.** Every frame number shown to a person is converted to clip time `m:ss` (or `m:ss.s` in the Why drawer) as `job.times[frame]`, which is the same timeline as the player's scrubber: prepare doesn't trim, so `times[0] = 0` and the prepared MP4 is encoded with exactly these timestamps (PRE-A `docs/API-NOTES.md` §5b, which owns the time axes; [ARCHITECTURE.md](ARCHITECTURE.md) §3.1). `m:ss` floors to whole seconds (`times = 65.9` → `1:05`); `m:ss.s` floors to tenths (`1:05.9`). Never show raw frame numbers outside the Why drawer's details row.

**Item label.** One rule, so the chip and the keyframe always agree. SAM 3.1's keyframes carry each track's label `<concept>:<n>` (e.g. `face:7`, `person:2`, `license plate:1`), burned in exactly as PRE-A `docs/prompts/role-pass.md` specifies, and track IDs use the same form ([ARCHITECTURE.md](ARCHITECTURE.md) §3.2). An item's **display label** is its **primary track**'s label in plain words: the primary track is its `face:*` track if it has one, otherwise the first track in `track_ids`; the label is the concept word plus `n`. Concept words: `face` → Face, `person` → Person, `license plate` → Plate, `screen` → Screen, `phone` → Phone, `document` → Document, `name badge` → Badge; any other (Muse-proposed) concept → its phrase with the first letter capitalised. So `face:7` → "Face 7", `license plate:1` → "Plate 1". Labels are unique because each concept numbers its own tracks. The drawer shows the raw label too ("On the keyframe: face:7", plus "also person:2" for the item's other tracks), so the creator can find it in the image. Items added by the audit have no keyframe label and are labelled `A1, A2, …` in order of their first frame. The UI derives every label from track IDs; it never invents a number.

**Icons.** Every state has an icon *and* a word: Hidden = filled square, Kept clear = open eye, Needs you = question mark in a circle, Locked = padlock, Demo mode = play-in-circle. Colour is never the only signal.

---

## 1. Landing (`/`)

Goal: in 20 seconds a judge sees the product working on real footage, understands the three steps, and can try it.

### 1.1 Wireframe: desktop (≥ 1024 px)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Safe Cut by Sigmora                      How it works   Results   Try it   GitHub    │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  Publish real-world footage without exposing          ┌──────────────────────────────┐│
│  the people who never agreed to be in it.             │                              ││
│                                                       │      hero clip 1 (video)     ││
│  Safe Cut works out who's part of your story and      │                              ││
│  hides everyone and everything else: passers-by,      │   [CC]                       ││
│  children, number plates, private screens.            ├──────────────────────────────┤│
│  You approve every decision.                          │ ( Raw footage | ■ Safe Cut ) ││
│                                                       │ Staged demo. Everyone shown  ││
│  [ Try it with an access code ]   See the results ↓   │ signed a release.            ││
│                                                       └──────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────────────────────┤
│  How it works                                                                        │
│  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐ │
│  │ 1  Muse Spark decides  │  │ 2  SAM 3.1 keeps them  │  │ 3  An audit checks     │ │
│  │    who                 │  │    hidden              │  │    the render          │ │
│  │ ...                    │  │ ...                    │  │ ...                    │ │
│  └────────────────────────┘  └────────────────────────┘  └────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Blur every face  vs  Safe Cut                                                       │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────┐          │
│  │  same moment, "blur all faces"   │  │  same moment, Safe Cut           │          │
│  │  guest hidden, plate visible     │  │  guest clear, plate hidden       │          │
│  └──────────────────────────────────┘  └──────────────────────────────────┘          │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Results on our labelled test set                                                    │
│  ┌──────────────────┬──────────┬──────────┬─────────────┬───────────┐               │
│  │ Method           │ Recall   │ Exposure │ Leak bursts │ Over-blur │               │
│  ├──────────────────┼──────────┼──────────┼─────────────┼───────────┤               │
│  │ Blur every face  │ …        │ …        │ …           │ …         │               │
│  │ EgoBlur Gen 2    │ …        │ …        │ …           │ …         │               │
│  │ Detector only    │ …        │ …        │ …           │ …         │               │
│  │ Muse, no tracking│ …        │ …        │ …           │ …         │               │
│  │ Safe Cut         │ …        │ …        │ …           │ …         │               │
│  │ (no audit)*      │ …        │ …        │ …           │ …         │               │
│  └──────────────────┴──────────┴──────────┴─────────────┴───────────┘               │
│  n clips · who labelled them (2 variants, §1.3) · run ID ↗ · *if WP7 ran it          │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  Try it   ·   Source on GitHub   ·   Use it inside Sigmora                           │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  footer                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Wireframe: mobile (≤ 480 px)

```
┌──────────────────────────────────┐
│ Safe Cut by Sigmora      [Menu]  │
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │      hero clip 1 (video)     │ │
│ │ [CC]                         │ │
│ └──────────────────────────────┘ │
│ ( Raw footage | ■ Safe Cut )     │
│ Staged demo. Everyone shown      │
│ signed a release.                │
│                                  │
│ Publish real-world footage       │
│ without exposing the people who  │
│ never agreed to be in it.        │
│ ...                              │
│ [ Try it with an access code ]   │
├──────────────────────────────────┤
│ How it works                     │
│ 1 Muse Spark decides who         │
│ 2 SAM 3.1 keeps them hidden      │
│ 3 An audit checks the render     │
├──────────────────────────────────┤
│ Blur every face vs Safe Cut      │
│ [ image A ]                      │
│ [ image B ]                      │
├──────────────────────────────────┤
│ Results (table scrolls inside    │
│ its own box, sideways)           │
├──────────────────────────────────┤
│ footer                           │
└──────────────────────────────────┘
```

### 1.3 Copy deck

| Element | Copy |
|---|---|
| `<title>` | Safe Cut: publish street footage without exposing strangers |
| Headline | Publish real-world footage without exposing the people who never agreed to be in it. |
| Sub | Safe Cut works out who's part of your story and hides everyone and everything else: passers-by, children, number plates, private screens. You approve every decision. |
| Primary button | Try it with an access code |
| Secondary link | See the results |
| Toggle | Raw footage · Safe Cut |
| Toggle hint (screen reader) | Switch between the original clip and the Safe Cut result. |
| Under the video | Staged demo. Everyone shown signed a release. |
| Step 1 title | Muse Spark decides who |
| Step 1 body | Muse Spark watches the clip, reads who said what (from Muse Voice Transcribe), and rules on each person and object SAM 3.1 has labelled: part of the story, or not. |
| Step 2 title | SAM 3.1 keeps them hidden |
| Step 2 body | SAM 3.1 follows each hidden person and item frame by frame. Anyone the tracker loses and finds again starts hidden. Anything uncertain stays hidden. |
| Step 3 title | An audit checks the render |
| Step 3 body | Before anything is published, Meta's EgoBlur checks every frame of the result and a second Muse Spark pass tries to read or recognise anything left. Any leak is fixed and recorded on your privacy receipt. |
| Side-by-side title | Blur every face vs Safe Cut |
| Side-by-side captions | Blur every face: your guest is hidden, the number plate isn't. · Safe Cut: your guest stays clear, the plate and the passer-by are hidden. |
| Results title | Results on our labelled test set |
| Results columns | Method · Recall · Exposure · Leak bursts · Over-blur |
| Results rows | Blur every face · EgoBlur Gen 2 · Detector only · Muse Spark, no tracking · Safe Cut · Safe Cut, no audit (if run) |
| Column help (tooltip and footnote) | Recall: of the people and things that should be hidden, the share that were hidden on at least 95% of the frames they're visible in. · Exposure: counting each should-be-hidden person or thing on each frame it's visible in, the share where less than 90% of it was covered. · Leak bursts: the number of times something that should be hidden was exposed for 3 or more frames in a row. · Over-blur: of the people and things that should stay clear, the share that were hidden on more than 10% of their frames. |
| Results footnote (two labellers) | `{n_clips}` clips filmed in public, labelled by two people (they agreed on `{percent_agreement}` of decisions; κ = `{kappa}`). Run `{run_id}`. How we measured ↗ |
| Results footnote (one labeller, plan R3) | `{n_clips}` clips filmed in public, labelled by one person. Agreement between two labellers wasn't measured. Run `{run_id}`. How we measured ↗ |
| Results placeholder (before WP8 fills it) | Numbers appear here after our frozen test runs. We publish them whether they're good or not. |
| Bottom links | Try it · Source on GitHub · Use it inside Sigmora |

The tooltips are plain-language restatements of [EVAL.md](EVAL.md) §2 with the same units (entities for recall and over-blur, entity-frames for exposure, runs for leak bursts); if EVAL.md changes, they change with it. The table rows are EVAL.md §3's baselines 1–4 plus Safe Cut full, and row 5 (without the audit) when WP7 runs it; Muse Spark without tracking stays in because it shows why SAM 3.1 is needed. All result numbers come from `eval/results/<run-id>/metrics.json` through WP8 ([AGENTS.md](../AGENTS.md) rule 9). WP6 ships the placeholder and the table component; it never types a number.

### 1.4 States

| State | What shows |
|---|---|
| Loading | Poster frame of hero clip 1 (redacted) with the toggle disabled; text skeletons. No spinner over the headline |
| Video fails to load | The poster stays; under it: "The demo video didn't load. You can still try Safe Cut with an access code." |
| Results not yet available | The placeholder line instead of the table |
| Single labeller (plan R3) | The one-labeller footnote. No κ, percent agreement or intra-rater figure appears anywhere on the page: an intra-rater re-label is a different measure and is never put in the κ slot ([SCHEDULE.md](labeling/SCHEDULE.md) R3) |
| Reduced motion | The hero video doesn't autoplay; a "Play demo" button shows instead |

### 1.5 Keyboard and accessibility

- The video autoplays muted (unless reduced motion), loops, has native controls, and has **captions** (WebVTT of the VO/dialogue; `[CC]` on by default).
- The Raw/Safe Cut toggle is a two-option radio group (arrow keys switch, label announced). Switching keeps the playback time.
- The side-by-side images have alt text describing what's hidden in each.
- The results table is a real `<table>` with `<th scope>`; on mobile it scrolls inside its own container, never the page.

### 1.6 Data

| Element | Source |
|---|---|
| Hero video (both versions) | Precomputed hero job (WP5 demo mode): the raw prepared clip and `redacted.mp4` from `GET /v1/jobs/{hero_id}/result` |
| Side-by-side | Two stills from WP7's `blur_all` and `full` runs on hero clip 1 (consented), exported by WP8 |
| Results table | WP8 writes a static JSON from `eval/RESULTS.md` / `metrics.json`; WP6 renders it |

---

## 2. Upload and progress (`/try`)

Goal: get from access code to the review panel with no surprises, and make the wait readable.

### 2.1 Wireframe: desktop, step A (access code)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ header                                                                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                     Try Safe Cut on your own clip                                    │
│                                                                                      │
│      Access code  [______________________]   [ Continue ]                            │
│      Judges: the code is in the submission's testing instructions.                   │
│                                                                                      │
│      What happens to your clip                                                       │
│      • It's sent to Meta's Model API in Standard mode, which doesn't train on it.    │
│      • Everything is deleted automatically after 24 hours, or sooner if you choose.  │
│      • Up to 60 seconds and 150 MB. MP4 or MOV.                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Wireframe: desktop, step B (drop the clip)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ header                                                                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│   ┌──────────────────────────────────────────────────────────────────────────────┐   │
│   │                                                                              │   │
│   │               Drop a clip here, or  [ Choose a file ]                        │   │
│   │               Up to 60 seconds and 150 MB. MP4 or MOV.                       │   │
│   │                                                                              │   │
│   └──────────────────────────────────────────────────────────────────────────────┘   │
│   [ ] I filmed this clip or have the right to use it.                                │
│                                                         [ Start ]  (disabled until   │
│                                                                     a file + tick)   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Wireframe: desktop, step C (progress)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ header                                                                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│  street-interview.mp4 · 0:31                                                         │
│  ┌───────────────────────────────┐   Working on your clip                            │
│  │ first frame (no overlay yet)  │                                                   │
│  └───────────────────────────────┘   ✓ Uploading your clip                           │
│                                      ✓ Getting your clip ready                       │
│                                      ● Finding people and objects        ~40 s left  │
│                                      ○ Listening for who's speaking                  │
│                                      ○ Watching the whole clip                       │
│                                      ○ Working out who's part of the story           │
│                                      ○ Deciding what to hide                         │
│                                      ○ Adding a safety margin                        │
│                                                                                      │
│  You can leave this page. Your review link: safecut…/jobs/j_8f2c  [Copy link]        │
│                                                              [ Cancel and delete ]   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Wireframe: mobile (all three steps stack)

```
┌──────────────────────────────────┐
│ header                           │
├──────────────────────────────────┤
│ Try Safe Cut on your own clip    │
│ Access code                      │
│ [____________________________]   │
│ [ Continue ]                     │
│ What happens to your clip …      │
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │  [ Choose a file ]           │ │
│ │  Up to 60 s, 150 MB          │ │
│ └──────────────────────────────┘ │
│ [ ] I filmed this clip or have   │
│     the right to use it.         │
│ [ Start ]                        │
├──────────────────────────────────┤
│ ✓ Uploading your clip            │
│ ● Finding people and objects     │
│ ○ …                              │
│ [Copy link] [Cancel and delete]  │
└──────────────────────────────────┘
```

### 2.5 Progress-stage labels

One row per pipeline stage ([WP5](work-packages/WP5.md) `run()` order), in this order. The row text is fixed; the detail line appears under the active row only.

| API `stage` | Row label | Detail line while active |
|---|---|---|
| `uploading` (client side) | Uploading your clip | `{percent}%` |
| `queued` | Waiting to start | Usually a few seconds. |
| `prepare` | Getting your clip ready | Converting to a standard format and reading its frames. |
| `track` | Finding people and objects | SAM 3.1 is looking for faces, people, plates, screens and documents. |
| `transcribe` | Listening for who's speaking | Muse Voice Transcribe is noting who speaks, and when. |
| `scene` | Watching the whole clip | Muse Spark is working out what's happening and who the host is. |
| `roles` | Working out who's part of the story | Muse Spark is ruling on each labelled person and object, three times over. |
| `miss_loop` | Looking again for anything missed | Muse Spark spotted something SAM 3.1 didn't. Tracking it now. |
| `decide` | Deciding what to hide | Anything uncertain stays hidden until you decide. |
| `guard` | Adding a safety margin | Extending each cover a little in space and time so nothing slips out at the edges. |
| `review` | Ready for you | (the page moves to the review panel) |
| `render` | Applying your choices | Covering every frame. |
| `audit` | Checking every frame of the result | EgoBlur and Muse Spark look for anything that slipped through. |
| `receipt` | Writing your privacy receipt | |
| `done` | Done | (the page moves to the result) |

The `miss_loop` row appears only if that stage runs. `~N s left` shows only when the API provides an estimate; otherwise nothing (never a fake countdown). Stages `render` → `receipt` show on the review page after "Approve & render" (§3.5), not here.

### 2.6 Copy deck: messages and errors

| Situation | Copy | Action |
|---|---|---|
| Code empty on Continue | Enter your access code. | focus the field |
| Code wrong (`401`) | That code didn't work. Check it and try again. | keep the text, select it |
| Daily limit reached (`429`, cap) | Safe Cut has reached today's limit for the public demo. Try again after midnight UTC, or watch the demo on the home page. | link to `/` |
| Too many requests (`429`, rate) | Too many tries in a short time. Wait a minute and try again. | |
| File too long (client check on metadata, or `422` `too_long`) | This clip is `{duration}` seconds long. The limit is 60 seconds. Trim it and try again. (`{duration}` = the clip's length rounded **up** to one decimal, e.g. 60.06 s → "60.1", so the number shown is always over the limit; §10.2) | |
| File too big | This file is `{size}` MB. The limit is 150 MB. (`{size}` = bytes ÷ 1,048,576 rounded **up** to one decimal, e.g. 157,286,401 bytes → "150.1"; §10.2) | |
| Wrong type | Safe Cut takes MP4 or MOV video files. | |
| No rights tick | Tick the box to confirm you can use this clip. | |
| Upload interrupted | The upload stopped. Check your connection and try again; nothing was processed. | [Try again] |
| A stage fails (`job.status = failed`) | Something went wrong while `{row label, lowercase}`. Your clip hasn't been published anywhere. You can try again, or delete it now. | [Try again] [Delete now] |
| Job cap would be exceeded | This clip would cost more than the per-clip limit to process. Try a shorter clip. | |
| Cancel and delete (confirm dialog) | Delete this clip and stop processing? This can't be undone. · [Delete] [Keep going] | |
| After delete | Deleted. Nothing from this clip is kept. | link to `/try` |
| Rights tick label | I filmed this clip or have the right to use it. | |
| More than one file dropped or chosen | Drop one clip at a time. | keep the drop zone empty |
| Render already running (`409` on render) | (no message: the page polls and shows the render stages) | |

### 2.7 States

Loading (button shows "Checking…" while the code is validated) · Empty (no file yet: Start disabled) · Error (above) · Uploading (progress bar with percent, Cancel available) · Processing (stage list) · Demo mode (§6: the banner shows, and the progress replays at real speed from saved timings).

### 2.8 Keyboard and accessibility

- The drop zone is also a real `<input type="file">` button ("Choose a file"); drag-and-drop is optional, never required.
- The stage list is an ordered list. The active row has `aria-current="step"`. A polite live region announces each new row label once ("Finding people and objects"), never the percent.
- Errors are tied to their field with `aria-describedby` and announced by a live region; focus moves to the field.
- The confirm dialog traps focus; Escape = "Keep going".

### 2.9 Data

| Element | Source |
|---|---|
| Upload | `POST /v1/jobs` → presigned URL + `job_id` ([WP5](work-packages/WP5.md)); then `POST /v1/jobs/{id}/start` |
| Stage rows | `GET /v1/jobs/{id}` → `stage`, `progress` (polled every 2 s; back off to 5 s after 1 min) |
| Duration / file name | client-side file metadata; after prepare, `job.json` `frames / fps` |
| First frame | `job.json` `prepared` (poster) |

---

## 3. Review panel (`/jobs/[id]`)

The heart of the demo ([DEMO.md](DEMO.md) beats 3–4). Goal: the creator understands each decision in seconds and changes any of them with one tap, without re-tracking.

### 3.1 Wireframe: desktop (≥ 1024 px)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ header                                                                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ street-interview.mp4 · 0:31        8 hidden · 2 kept clear · 1 needs you            │
│ ┌───────────────────────────────────────────────────────┐                            │
│ │                                                       │  ( Raw | ■ Safe Cut )      │
│ │       raw video + canvas overlay (plan.json)          │  Preview. The final        │
│ │       selected item outlined, its label shown         │  render covers the same    │
│ │                                                       │  areas.                    │
│ └───────────────────────────────────────────────────────┘                            │
│ ▶ 0:12 / 0:31 ━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━  [CC]                                  │
│   timeline: one thin bar per item where it's on screen (selected item highlighted)  │
├──────────────────────────────┬──────────────────────────────┬────────────────────────┤
│ ■ Hidden (8)                 │ 👁 Kept clear (2)            │ ? Needs you (1)        │
│ ┌──────────────────────────┐ │ ┌──────────────────────────┐ │ ┌────────────────────┐ │
│ │[thumb] Face 4 · Child 🔒 │ │ │[thumb] Face 2 · Person   │ │ │[img] Face 6 Person │ │
│ │ child in the background, │ │ │ the guest: introduced at │ │ │ looks at the       │ │
│ │ not addressed            │ │ │ 0:03, speaks to camera   │ │ │ camera; checks     │ │
│ │ 0:04–0:13                │ │ │ 0:00–0:31                │ │ │ disagreed          │ │
│ │ [Why?]   Always hidden   │ │ │ [Why?]  [Hide]           │ │ │ 0:09–0:14          │ │
│ └──────────────────────────┘ │ └──────────────────────────┘ │ │ [Why?]             │ │
│ ┌──────────────────────────┐ │ ┌──────────────────────────┐ │ │ [Hide] [Keep clear]│ │
│ │[thumb] Plate 1 · Plate   │ │ │[thumb] Face 1 · Person   │ │ └────────────────────┘ │
│ │ number plate on a parked │ │ │ the host                 │ │                        │
│ │ car                      │ │ │ ...                      │ │                        │
│ │ [Why?]  [Keep clear]     │ │ └──────────────────────────┘ │                        │
│ └──────────────────────────┘ │                              │                        │
│ ┌──────────────────────────┐ │                              │                        │
│ │[thumb] Face 9 · NEW      │ │                              │                        │
│ │ appeared again after     │ │                              │                        │
│ │ leaving; might be Face 2 │ │                              │                        │
│ │ [Why?] [Same as Face 2…] │ │                              │                        │
│ └──────────────────────────┘ │                              │                        │
│ …                            │                              │                        │
├──────────────────────────────┴──────────────────────────────┴────────────────────────┤
│ 1 item still needs you. If you render now, it stays hidden.   [ Approve & render ]   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Each chip's overflow menu (`⋯`, not drawn above) holds: "Remove this person from the video" (person items only) and "Jump to first appearance".

### 3.2 Wireframe: mobile (≤ 480 px)

```
┌──────────────────────────────────┐
│ header                           │
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │ video + overlay              │ │
│ └──────────────────────────────┘ │
│ ▶ 0:12 ━━━━●━━━━━━━━━━  [CC]     │
│ ( Raw | ■ Safe Cut )             │
├──────────────────────────────────┤
│ [Hidden 8] [Kept clear 2] [Needs │  ← tabs, scroll sideways
│  you 1]                          │
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │[thumb] Face 6 · Person       │ │
│ │ looks at the camera; checks  │ │
│ │ disagreed · 0:09–0:14        │ │
│ │ [Why?] [Hide] [Keep clear]   │ │
│ └──────────────────────────────┘ │
│ …                                │
├──────────────────────────────────┤
│ 1 still needs you                │  ← sticky bottom bar
│ [ Approve & render ]             │
└──────────────────────────────────┘
```

The video stays sticky at the top while the chip list scrolls. The tab that opens first is **Needs you** if it has items, otherwise **Hidden**.

### 3.3 The chip

| Part | Content | Source |
|---|---|---|
| Thumbnail (64×64, 96×96 on mobile) | A crop around the item at its first evidence frame, about twice the item's box, with the item itself drawn **covered** if hidden or needs-you, and **clear** if kept. The surroundings stay visible so the creator recognises the moment | `decisions.items[].evidence_frames[0]` → SoM keyframe image; box from `tracks.json` `boxes[frame]` for `track_ids[0]` |
| Label | The item's display label, e.g. "Face 7", "Plate 1" (§0 Item label) | primary track ID in `track_ids` |
| Kind | Person / Child / Number plate / Screen / Document / Other item, with its icon | `kind` |
| Badges | 🔒 **Always hidden** if `locked`; **NEW** if one of the item's tracks has a `reentry_of` that points to a track belonging to a **different** item (after a merge the earlier track is in the same item, so the badge goes away and never shows on the merge target); **Changed by you** if `decided_by = creator` | `locked`, `tracks[].reentry_of`, `decided_by` |
| Reason | One or two lines, first letter capitalised, no trailing full stop added | `reason` |
| Time range | `m:ss–m:ss` from the first to the last frame of the item's tracks, including tracks merged into it | `tracks.json` `first`/`last` over `track_ids` → `job.times` |
| Buttons | Hidden chip: [Why?] [Keep clear] · Kept chip: [Why?] [Hide] · Needs-you chip: [Why?] [Hide] [Keep clear] · Locked chip: [Why?] and the text "Always hidden" (no toggle) · NEW chip (hidden, re-acquired track) whose `reentry_of` track belongs to a **kept participant** item P: the line "Might be {P's label}: the tracker lost them and found them again." and [Why?] [Same as {P's label}…] [Keep clear], with "Same as …" first because merging is the usual fix · NEW chip whose `reentry_of` track belongs to any other item (a bystander, a child, an unsure person): the line "The tracker lost this person and found them again. They stay hidden." and [Why?] [Keep clear], **no merge button** | `decision`, `locked`, `tracks[].reentry_of` |
| Overflow `⋯` | Remove this person from the video (person/child items); Jump to first appearance | |

Clicking the chip body (not a button) **selects** it: the video seeks to its first evidence frame and pauses, the overlay outlines that item, and the timeline highlights its bars.

### 3.4 Creator actions (what each tap does)

All edits go through `POST /v1/jobs/{id}/review` (WP3's `apply_review`). The UI updates **optimistically**: the chip moves and the overlay changes at once; if the request fails, it moves back with an error toast.

| Action | Result | Copy (toast, polite live region) |
|---|---|---|
| Keep clear (on a hidden or needs-you item) | `decision → keep`, `decided_by → creator`; chip moves to Kept clear; overlay stops covering it | "{label} will be kept clear. [Undo]" (e.g. "Plate 1 will be kept clear.") |
| Hide (on a kept or needs-you item) | `decision → hide`; chip moves to Hidden; overlay covers it, including any tracks merged into it | "{label} will be hidden. [Undo]" (e.g. "Face 2 will be hidden.") |
| Keep clear on a **screen or document** | Same, plus a one-line confirm in place: "Only keep this clear if nothing on it is personal." [Keep clear] [Cancel] | |
| Toggle a locked child | Not possible: no toggle is rendered. The "Always hidden" text has a help link that opens the drawer at the explanation | — |
| Same as {label}… (re-entry merge; offered only on a NEW chip whose earlier track is a kept participant's, §3.3) | A small menu lists the items that are **part of the story** (kept participants), each with its thumbnail, the suggested one first: "Same person as Face 2 (the guest)". Choosing one merges the new item into it: the NEW chip leaves the columns, its tracks show under the target (time range, overlay, Details), and the header counts drop by one | "{source label} merged into {target label}. They'll be kept clear like {target label}. [Undo]" (e.g. "Face 9 merged into Face 2. They'll be kept clear like Face 2.") |
| Remove this person from the video | Confirm dialog (below). The item becomes hidden with the **Whole person covered** style and is marked "removed at your request" on the receipt | "{label} will be fully covered wherever they appear. [Undo]" |
| Undo | Reverts the last edit (one level per toast) | "Undone." |

**Remove-person dialog:** title "Remove this person?" · body "They'll be fully covered, not just their face, every time they appear. Your privacy receipt will record that you removed them." · [Remove] [Cancel]. (Cutting their segments out of the video is not in v1; don't offer it.)

**Merge rules the UI enforces** (from [DESIGN.md](DESIGN.md) §2.5): merge targets are only kept participants; children are never merge targets or merge sources; a re-acquired bystander is never offered a merge (the H1B van case in [STORYBOARD.md](STORYBOARD.md) 6.1 stays hidden); the merge never happens automatically.

### 3.5 Approve & render

| Situation | Bottom bar text | Button |
|---|---|---|
| Nothing needs you | Everything's decided. | **Approve & render** |
| `k` items need you | `k` item(s) still need you. If you render now, they stay hidden. | **Approve & render** (still enabled) |
| An edit is saving | Saving your changes… | disabled |
| Edited after rendering (`done`, reached with `?view=review`, §10.4) | You changed something after rendering. Render again to update the video and receipt. | **Approve & render** |
| Rendering | (the bar becomes the progress list from §2.5, `render` → `receipt`) | — |

Pressing it: `POST /v1/jobs/{id}/render`, then the stage rows `Applying your choices` → `Checking every frame of the result` → `Writing your privacy receipt`, then the page moves to `/jobs/[id]/result`. Chips are read-only during the render (a calm note: "Changes are paused while we render.").

### 3.6 The overlay

- A `<canvas>` sized to the video's displayed box, drawn on each `requestVideoFrameCallback` (rVFC). Per the WICG spec, `metadata.mediaTime` is the presentation timestamp of the frame being shown, on the `currentTime` timeline. Map it to a prepared frame exactly as PRE-A `docs/API-NOTES.md` §5b defines: **`i = max{ i : job.times[i] ≤ mediaTime + 0.001 }`**, found by binary search, then clamped to `[0, job.frames − 1]` (a `mediaTime` before `times[0]` gives frame 0). With rVFC, `mediaTime` equals `times[i]` exactly; the 1 ms tolerance only absorbs float error ([WP6](work-packages/WP6.md) step 4). This works for variable-frame-rate sources too, because `times` holds each prepared frame's own timestamp. If `times` isn't strictly increasing, doesn't start at 0, or doesn't have `job.frames` entries, the UI shows the unexpected-error page (§7) instead of drawing a misaligned overlay. Test cases: §10.6.
- Browser support (MDN browser-compat-data, 2026-10-23): rVFC is in Chrome 83+, Safari 15.4+ and Firefox 132+. On a browser without it, fall back to `requestAnimationFrame` reading `video.currentTime` through **the same `max{}` rule** (not nearest-rounding, which PRE-A §5b notes would draw one frame ahead). `currentTime` can lag the displayed frame, so say so next to the toggle: "Preview may lag by a frame in this browser. The final render isn't affected." Never fall back silently.
- For that frame, draw every region in `plan.json` `frames[frame]` whose item is currently hidden or needs-you after the creator's local edits. A region whose item has been merged into another follows the **target**'s decision (§10.5). `solid` and `person_solid` → opaque fill (mask shape when `mask` is present, else box); `pixelate` → coarse cells on the locked `grid` (a preview; the final render adds noise); `crowd_fills` → opaque fill.
- An item switched from kept to hidden by the creator has no plan regions yet: until the review response returns a new plan, draw its **track boxes** from `tracks.json` (padded 15% as a visual approximation) so the creator sees it covered immediately.
- **Raw / Safe Cut toggle** turns the overlay off and on. In Raw mode, a 2 px outline still shows each item's position with its label, so the creator can match chips to people.
- The selected item gets a 3 px focus outline (white with a dark edge, visible on any footage) and its label.
- The note next to the toggle: "Preview. The final render covers the same areas."

### 3.7 States

| State | What shows |
|---|---|
| Loading (job fetched, items not ready) | The progress list from §2.5 instead of the columns |
| Ready | As wireframed |
| Empty: nothing found at all | Columns replaced by: "Safe Cut didn't find any people, plates, screens or documents in this clip. If that's wrong, tell us and don't publish yet." [Approve & render] stays available |
| Empty column | Hidden: "Nothing is hidden." · Kept clear: "Nothing is kept clear. Tap Keep clear on a chip to change that." · Needs you: "Nothing needs you." |
| Needs you (has items) | The Needs-you column header shows the count in bold; on mobile it's the first tab |
| Locked child | Chip with 🔒 "Always hidden" and no toggle |
| Re-entry (NEW) | Chip with the NEW badge; "Same as {label}…" only when the earlier track is a kept participant's, otherwise the "They stay hidden." line and no merge button (§3.3) |
| Saving an edit | The chip shows a small "Saving…" under its buttons |
| Edit failed | Chip returns to its column; toast: "That change didn't save. Check your connection and try again." [Try again] |
| Job expired (`404` with `code: "expired"`; for any other `404` code see §7 "Job not found") | Full-page: "This clip has been deleted. Safe Cut deletes everything automatically after 24 hours." [Try another clip] |
| Demo mode | The banner (§6) and all edits work locally against the replay (WP5 replays them) |

### 3.8 Keyboard and accessibility

| Key (focus in the chip area) | Does |
|---|---|
| `Tab` / `Shift+Tab` | Moves through **every** button in reading order: the video controls, then each chip's buttons (Why?, Hide / Keep clear, Same as {label}…, `⋯`) column by column, then the bottom bar. Nothing is reachable only by a shortcut |
| `↑` / `↓` | Jumps to the same button on the previous / next chip in the column (a shortcut on top of Tab, not a replacement) |
| `←` / `→` | Jumps to the first chip of the neighbouring column |
| `Enter` / `Space` on a button | Activates it (native button behaviour), including the `⋯` menu, whose items (Remove this person, Jump to first appearance) are then reachable with `↑`/`↓` |
| `Enter` on a chip's body (when the chip itself is focused by `↑`/`↓`) | Opens the Why? drawer |
| `H` | Hide the focused item |
| `C` | Keep the focused item clear |
| `Z` / `Ctrl+Z` | Undo the last edit |
| `K` | Play / pause the video (`Space` does this only when the video itself has focus, so it never steals a button press) |
| `?` | Shows this list in a dialog |
| `Esc` | Closes a menu, dialog or the drawer, and returns focus to the chip that opened it |

- Each chip is an `<article>` with an accessible name like "Face 4, Child, hidden, always hidden. Child in the background, not addressed. 0:04 to 0:13." Buttons inside have full names ("Keep Plate 1 clear", "Hide Face 2").
- Moving a chip announces it in a polite live region (the toast text) and keeps focus on the moved chip in its new column.
- Visible focus ring on every interactive element (2 px, contrast ≥ 3:1 against both light and dark surfaces).
- Touch targets are at least 44×44 CSS px on mobile and 32×32 on desktop: stricter than WCAG 2.2's AA minimum of 24×24 (SC 2.5.8 Target Size (Minimum)).
- **Focus not obscured** (WCAG 2.2 SC 2.4.11): the sticky video at the top and the sticky bottom bar on mobile must never cover the focused chip. Set `scroll-padding-top` and `scroll-padding-bottom` to their heights so focus scrolls into the visible band, and test it by tabbing through a 20-chip list at 320 px wide.
- The overlay canvas is `aria-hidden`; the chip list carries all the information. The timeline bars are decorative; the time range is in each chip's text.
- Single-letter shortcuts (`H`, `C`, `Z`, `K`, `?`) work only when focus is in the chip area, and the `?` dialog has a switch to turn them off; either satisfies WCAG SC 2.1.4 Character Key Shortcuts. With them off, every action still works through Tab and Enter.

### 3.9 Data

| Element | Source |
|---|---|
| Header counts | `decisions.items[].decision` counts after local edits, counting each item once (an item merged into another isn't counted) |
| Video | `job.json` `prepared` (raw prepared clip), its `fps`, `width`, `height`, `times` |
| Overlay regions | `plan.json` `frames`, `crowd_fills`; the `grid` for pixelate previews |
| Timeline bars | `tracks.json` `first`/`last` per track, grouped by item |
| Chips | `decisions.items[]`: `item_id`, `track_ids`, `kind`, `decision`, `reason`, `evidence_frames`, `style`, `decided_by`, `locked` |
| NEW badge, merge suggestion | `tracks.json` `tracks[].reentry_of`, resolved to the item that owns that track (informational only: the suggestion is never applied without a tap) |
| Edits | `POST /v1/jobs/{id}/review` |

---

## 4. The "Why?" drawer

This is the Meta-tooling story on screen ([DEMO.md](DEMO.md) beat 4): the labelled keyframe SAM 3.1 tracked, Muse Spark's ruling, the votes, and the speech evidence. Goal: a creator (or judge) can see in ten seconds **why** this item is where it is.

### 4.1 Wireframe: desktop (side drawer, 480 px wide, from the right)

```
                                   ┌──────────────────────────────────────────────┐
                                   │ Face 4 · Child                    [ Close ✕ ]│
                                   │ ■ Hidden · 🔒 Always hidden                  │
                                   ├──────────────────────────────────────────────┤
                                   │ ┌──────────────────────────────────────────┐ │
                                   │ │ Set-of-Mark keyframe at 0:06             │ │
                                   │ │ [face:1] [face:2]     [face:4]◀ ring     │ │
                                   │ │        [license plate:1]                 │ │
                                   │ └──────────────────────────────────────────┘ │
                                   │ ◀ 0:04   ● 0:06   0:09 ▶   (evidence frames) │
                                   │ "This is the frame Muse Spark was shown. The │
                                   │  labels are the objects SAM 3.1 tracked."    │
                                   ├──────────────────────────────────────────────┤
                                   │ Why it's hidden                              │
                                   │ Child in the background, not addressed.      │
                                   │ Children are always hidden. You can't        │
                                   │ change this, because Safe Cut can't check    │
                                   │ a parent's consent.                          │
                                   ├──────────────────────────────────────────────┤
                                   │ What Muse Spark said (3 checks)              │
                                   │ ✓ Child  ✓ Child  ✓ Child                    │
                                   │ "small person walking with an adult behind   │
                                   │  the guest, never faces the host"            │
                                   ├──────────────────────────────────────────────┤
                                   │ What was said while Face 4 was on screen     │
                                   │ 0:03 S2  "Hi, I'm Amina, and today…"         │
                                   │ 0:07 S1  "So what brings you here?"          │
                                   │ No speech is linked to Face 4.               │
                                   ├──────────────────────────────────────────────┤
                                   │ Details                                      │
                                   │ Decided by Safe Cut's rules · Cover: solid   │
                                   │ Tracks: face:4 · frames 120–390              │
                                   │ Models: Muse Spark 1.3 · SAM 3.1 ·           │
                                   │ Muse Voice Transcribe                        │
                                   └──────────────────────────────────────────────┘
```

### 4.2 Wireframe: mobile (bottom sheet, full height when expanded)

```
┌──────────────────────────────────┐
│ ─── (drag handle)                │
│ Face 4 · Child       [Close ✕]   │
│ ■ Hidden · 🔒 Always hidden      │
│ ┌──────────────────────────────┐ │
│ │ keyframe, face:4 ringed      │ │
│ └──────────────────────────────┘ │
│ ◀ 0:04  ● 0:06  0:09 ▶           │
│ Why it's hidden                  │
│ …                                │
│ What Muse Spark said (3 checks)  │
│ …                                │
│ What was said                    │
│ …                                │
│ Details ▸ (collapsed)            │
│ [Hide] [Keep clear]  (if allowed)│
└──────────────────────────────────┘
```

On mobile, the drawer repeats the chip's action buttons at the bottom so the creator can decide without closing it.

### 4.3 Sections and copy

**Header.** `{label} · {Kind}` (e.g. "Face 4 · Child") then the state line: `■ Hidden`, `👁 Kept clear` or `? Needs you`, plus `🔒 Always hidden` / `NEW` / `Changed by you` badges.

**Keyframe.** The SoM keyframe image for the selected evidence frame, with a **ring** (3 px, white with a dark edge) drawn by the UI around the item's box on that frame. Arrows step through `evidence_frames`; the dot row shows how many there are. Caption: "This is the frame Muse Spark was shown. The labels are the objects SAM 3.1 tracked." followed by "On the keyframe: {primary track ID}" and, for each other track of the item (including merged ones), "also {track ID}" (e.g. "On the keyframe: face:2 · also person:1"). If no keyframe exists for the item (e.g. an item added by the audit), show the plan box on the nearest prepared frame and the caption "Added by the audit after rendering. There's no keyframe for it."

**"Why it's hidden / kept clear / needs you".** The `reason`, then one fixed sentence by case:

| Case | Fixed sentence |
|---|---|
| Hidden, bystander | People who aren't part of the story are hidden by default. |
| Hidden, child (`locked`) | Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent. |
| Hidden, new ID after re-entry | The tracker lost this person and found them again. Anyone found again starts hidden until you say who they are. |
| Hidden, plate / screen / document | Number plates, private screens and documents are always hidden unless you decide otherwise. |
| Kept clear, participant | All three checks agreed this person is part of the story, on at least two keyframes. |
| Kept clear by you | You chose to keep this clear. |
| Needs you, harmless screen or document | Muse Spark read this as nothing personal, but screens and documents are only kept clear when you confirm. |
| Needs you, votes disagreed (`role: unsure`) or any other reason | The checks didn't all agree, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear. |
| Removed at your request | You asked to remove this person. They're fully covered everywhere they appear. |
| Added by the audit | The final check found this after rendering and covered it. |

**"What Muse Spark said (n checks)".** One mark per vote in `votes`, each with its role word (Part of the story / Not part of the story / Child / Not sure); ✓ when it matches the final role, ✕ otherwise. Then Muse Spark's `evidence` text in quotes. If `escalated`: "The checks disagreed, so Muse Spark took a longer, closer look once." and then, from the track's `suggested_role` (PRE-A `docs/prompts/escalation.md`): when it isn't null, "A longer, closer look suggests: {role word}. You decide." followed by the escalation's evidence in quotes; when it's null, "A longer, closer look couldn't settle it." A suggestion never changes the item's column or decision: only the creator's tap does. For objects (screens, documents): "Muse Spark read it as: {content}" and "Personal: yes/no" from `objects[].sensitive`. For plates: "Number plates are hidden by default; Muse Spark isn't asked about them. Only you can keep one clear." (only if the role pass doesn't rule on plates; WP2 confirms). A plate isn't locked: the creator can keep it clear with one tap, without the screen/document confirm (§3.4).

There's no "Hidden, votes disagreed" case: a track whose votes disagree becomes `role: unsure` and the item goes to **Needs you**, never to Hidden on its own ([DESIGN.md](DESIGN.md) §2.3; PRE-A `docs/prompts/escalation.md` rules 3–4).

**"What was said while {label} was on screen".** Transcript turns that overlap the item's on-screen time, max 4, each as `m:ss S# "text"`. If the item's primary track has `matches_participant = k` (an index into `scene.participants`, set by the role pass, PRE-A `docs/prompts/role-pass.md`) and `scene.participants[k].speaker` is set, mark that speaker's lines with "said by {label}". Otherwise end with "No speech is linked to {label}." If there's no transcript: "No speech was found in this clip." If `job.audio` is `false`, the whole section is replaced by "This clip has no sound." Text is shown as heard; long turns are cut at 140 characters with "…".

**"Details"** (collapsed by default on mobile): `Decided by {Safe Cut's rules | Muse Spark | You}` · `Cover: {style word}` · `Tracks: {track_ids}` · `Frames {first}–{last}` · `Models: {receipt-style model list}`. This is the only place raw IDs and frame numbers appear.

### 4.4 States

| State | What shows |
|---|---|
| Loading the keyframe | The keyframe box with a neutral fill and "Loading the keyframe…" |
| Keyframe failed | "The keyframe didn't load." The rest of the drawer still shows |
| No votes (policy-only item, e.g. a plate) | The votes section is replaced by the fixed sentence for its case |
| Demo mode | Same content, from the replayed hero job |

### 4.5 Keyboard and accessibility

- Opens as a modal dialog (`role="dialog"`, `aria-modal="true"`, labelled by its header); focus moves to the header; focus is trapped; `Esc` closes and returns focus to the chip.
- `←` / `→` step evidence frames when the keyframe has focus.
- The keyframe has alt text built from the data: "Keyframe at 0:06. face:4 is ringed, in the back right. Other labelled objects: face:1, face:2, license plate:1."
- Vote marks have text, not just ✓/✕ ("Check 1: Child, agrees").
- Mobile bottom sheet: the drag handle is also a button ("Expand" / "Collapse").

### 4.6 Data

| Element | Source |
|---|---|
| Keyframe image | `roles.json` `keyframes[]` (the `som/*.jpg` matching the evidence frame), served by WP5 as a URL |
| Ring position | `tracks.json` `tracks[track_id].boxes[frame]` for the item's tracks on that frame |
| Evidence frames | `decisions.items[].evidence_frames` (falls back to `roles.tracks[].frames`) |
| Reason | `decisions.items[].reason` |
| Votes, evidence, escalation | `roles.json` `tracks[]`: `votes`, `role`, `evidence`, `escalated`, `suggested_role` (nullable; PRE-A escalation.md) for each track in `track_ids`; show the primary track first |
| Object content | `roles.json` `objects[]`: `sensitive`, `content` |
| Transcript | `transcript.json` `turns[]` overlapping `[times[first], times[last]]`: a turn overlaps when `turn.start ≤ times[last]` and `turn.end ≥ times[first]`. This assumes turn times are on the same timeline as `times` (ASR runs on the prepared clip's audio; request to WP2 in §8 to confirm) |
| Speaker link | `roles.json` `tracks[].matches_participant` (nullable index into `scene.participants`; PRE-A role-pass.md) → `scene.json` `participants[k].speaker` |
| Decided by, style, locked | `decisions.items[]` |
| Models | `receipt.json` `models` (or the job's config before a receipt exists) |

---

## 5. Result and receipt (`/jobs/[id]/result`)

Goal: the creator gets the redacted video, sees that it was checked, and has the receipt as evidence.

### 5.1 Wireframe: desktop

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ header                                                                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ Your clip is ready                                                                   │
│ ┌───────────────────────────────────────────────────────┐  ✓ Checked                 │
│ │                                                       │  900 frames checked.       │
│ │                 redacted.mp4                          │  1 leak found and fixed.   │
│ │                                                       │  Nothing left to fix.      │
│ └───────────────────────────────────────────────────────┘                            │
│ ▶ 0:00 / 0:31 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  [CC]        [ Download video ]        │
│                                                            [ Publish to Sigmora ]    │
│                                                            (only from Sigmora)       │
│                                                            Back to review            │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ Privacy receipt                                     [ Download receipt (JSON) ]      │
│ ┌──────────────────────────────────────────────────────────────────────────────────┐ │
│ │ receipt.html (sandboxed frame): every item, reason, who decided, the audit,      │ │
│ │ models used, data handling, cost, hash                                           │ │
│ └──────────────────────────────────────────────────────────────────────────────────┘ │
│ This clip and everything made from it will be deleted by 28 Oct, 11:00 UTC.          │
│                                                            [ Delete everything now ] │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Wireframe: mobile

```
┌──────────────────────────────────┐
│ header                           │
├──────────────────────────────────┤
│ Your clip is ready               │
│ ┌──────────────────────────────┐ │
│ │ redacted.mp4                 │ │
│ └──────────────────────────────┘ │
│ ✓ Checked                        │
│ 900 frames checked. 1 leak       │
│ found and fixed.                 │
│ [ Download video ]               │
│ [ Publish to Sigmora ]           │
│ Privacy receipt ▸                │
│ [ Download receipt (JSON) ]      │
│ Deleted by 28 Oct, 11:00 UTC     │
│ [ Delete everything now ]        │
└──────────────────────────────────┘
```

### 5.3 Copy deck

| Element | Copy |
|---|---|
| Title | Your clip is ready |
| Audit, clean | ✓ Checked · `{frames_scanned}` frames checked. No leaks found. |
| Audit, fixed | ✓ Checked · `{frames_scanned}` frames checked. `{n}` leak(s) found and fixed. Nothing left to fix. |
| Audit, unresolved | ⚠ Not ready to publish · `{frames_scanned}` frames checked. `{unresolved}` spot(s) couldn't be fixed automatically. Publishing is off until they're fixed. [Review them] (links to `/jobs/[id]?view=review`, §10.4) |
| Audit detail link | What the check does → (expands: "Meta's EgoBlur looked for faces and number plates on every frame of the result. Muse Spark looked at sampled frames and tried to read or recognise anything. Anything they found that wasn't kept clear on purpose was covered, and the clip was rendered again.") |
| Download | Download video |
| Publish | Publish to Sigmora |
| Publish disabled tooltip | Publishing is off until every spot is fixed. |
| After publish | Sent to Sigmora. You can close this tab. |
| Back | Back to review (links to `/jobs/[id]?view=review`, so the done-state redirect in §10.4 doesn't bounce the creator back here) |
| Receipt title | Privacy receipt |
| Receipt intro (above the frame) | A record of what was hidden, why, and who approved it. Keep it if anyone asks about this video. |
| Receipt download | Download receipt (JSON) |
| Deletion note | This clip and everything made from it will be deleted by `{deletes_at, local date and time}`. (`deletes_at` is the latest time the deletion job will have run, from WP5, not `created_at` + 24 h: a periodic job deletes *after* 24 h. The wireframe's example assumes upload on 27 Oct 10:00 UTC and an hourly job.) |
| Delete button | Delete everything now |
| Delete confirm | Delete the video, the receipt and all working files now? Download anything you need first. This can't be undone. · [Delete] [Cancel] |
| After delete | Deleted. Nothing from this clip is kept on Safe Cut. |

### 5.4 States

| State | What shows |
|---|---|
| Rendering (arrived early) | The progress list `render` → `receipt` from §2.5 |
| Edited after rendering | The job is back in `review` (§10.4), so `/result` redirects to the review panel; Publish can't be reached until the new render is `done` |
| Ready, clean / fixed | As wireframed |
| Unresolved > 0 | Warning panel (above), Publish disabled, Download still allowed with the note "This version has `{unresolved}` unfixed spot(s)." |
| Receipt failed to load | "The receipt didn't load. You can still download it as JSON." |
| From Sigmora (`?from=sigmora`) | Publish button shows; header shows "Back to Sigmora" |
| Not from Sigmora | No Publish button at all (not a disabled one) |
| Expired / deleted | The same full-page message as §3.7 |
| Demo mode | Banner; "Publish to Sigmora" is replaced by "Publishing is off in demo mode." |

### 5.5 Keyboard and accessibility

- The video has native controls and captions if the source had speech (WebVTT from `transcript.json`, built by WP5 or WP6).
- The audit panel is a `role="status"` region so its result is announced once when the page loads.
- The receipt frame has a title ("Privacy receipt") and is also reachable as a direct link ("Open the receipt in a new tab").
- Destructive actions (Delete) are the last in tab order and always confirm.

### 5.6 Data

| Element | Source |
|---|---|
| Video, download | `GET /v1/jobs/{id}/result` → signed URL for `redacted.mp4` |
| Audit summary | `audit.json`: `frames_scanned`; **leaks found and fixed = the number of distinct `patched_item` values** in `leaks[]` (one leaking person over 2 frames is 1 leak, not 2; `leaks[]` has one row per frame); `unresolved`; `passes` |
| Publish allowed | `audit.json` `unresolved == 0` ([ARCHITECTURE.md](ARCHITECTURE.md) §3.8) and `?from=sigmora` |
| Receipt frame / download | signed URLs for `receipt.html` and `receipt.json` (§3.9: items, audit, models, data_handling, approved_by/at, cost_usd, hash) |
| Deletion time | `deletes_at` from the API (WP5 computes it from its cleanup schedule) |
| Delete | `DELETE /v1/jobs/{id}` |

---

## 6. Demo-mode banner

Shown on **every** page whenever any API response carries `"mode": "replay"` ([WP5](work-packages/WP5.md) step 5), and on the landing page's hero player always (it's precomputed).

```
Desktop:
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ▶ Demo mode. You're seeing saved results from a real run on our consented demo clip. │
│   Nothing is sent to Meta right now.                              What's demo mode?  │
└──────────────────────────────────────────────────────────────────────────────────────┘
Mobile:
┌──────────────────────────────────┐
│ ▶ Demo mode: saved results from  │
│ a real run. What's this?         │
└──────────────────────────────────┘
```

| Element | Copy |
|---|---|
| Banner | Demo mode. You're seeing saved results from a real run on our consented demo clip. Nothing is sent to Meta right now. |
| Link | What's demo mode? → "Demo mode replays the exact responses Muse Spark, SAM 3.1 and Muse Voice Transcribe gave on a real run of this clip, through the same pipeline and the same screens. We use it when the live service is busy, and we always label it." |
| Landing player label | Precomputed result |

- It sits directly under the header, full width, not dismissible (it can't be hidden while replayed data is on screen). It uses its own neutral colour and the ▶ icon, plus the words "Demo mode" (never colour alone).
- `role="status"`; announced once per page load.
- In the demo video and at finals, the banner must be visible in any shot that uses replayed data ([STORYBOARD.md](STORYBOARD.md)).

---

## 7. Error and not-found pages

| Page | Copy | Actions |
|---|---|---|
| 404 (unknown route) | We couldn't find that page. | Go to the home page · Try Safe Cut |
| Job expired (`404` with `code: "expired"`) | This clip has been deleted. Safe Cut deletes everything automatically after 24 hours. | Try another clip |
| Job not found (`404` on a job route, any other code) | We couldn't find that clip. Check the link, or try another clip. | Try another clip |
| API unreachable | Safe Cut's service isn't responding right now. Your clip is safe and nothing has been published. Try again in a minute. | Try again · Watch the demo |
| Unexpected error | Something went wrong on our side. Nothing has been published. | Try again · Go to the home page |

Never show stack traces, request IDs to non-owners, API keys or raw model output on these pages.

---

## 8. Contract field map and requests to WP5

The API ([WP5](work-packages/WP5.md)) hasn't been written; these are the fields WP6 needs from it, by contract. WP6 mocks exactly these shapes in `web/mocks/`.

| UI need | Contract source ([ARCHITECTURE.md](ARCHITECTURE.md) §3) | API route |
|---|---|---|
| Stage and progress | WP5 `job_log.jsonl` stage names (§2.5 above) | `GET /v1/jobs/{id}` → `stage`, `progress`, `status` |
| Prepared video URL, `fps`, `width`, `height`, `frames`, `times`, `created_at` | §3.1 `job.json` | `GET /v1/jobs/{id}` |
| Items | §3.6 `decisions.json` `items[]` (all fields) | `GET /v1/jobs/{id}` → `items` |
| Track boxes, first/last, `reentry_of` | §3.2 `tracks.json` `tracks[]` (boxes only for the items' tracks) | `GET /v1/jobs/{id}` → `tracks` |
| Votes, evidence, escalation (`suggested_role`), participant link (`matches_participant`), keyframe list, object content | §3.5 `roles.json` (plus PRE-A's two added fields) | `GET /v1/jobs/{id}` → `roles` |
| SoM keyframe images | §3.5 `keyframes[]` | signed URLs in `GET /v1/jobs/{id}` → `keyframe_urls` |
| Overlay regions | §3.7 `plan.json` | `GET /v1/jobs/{id}` → `plan` (or `plan_url`) |
| Transcript | §3.3 `transcript.json` | `GET /v1/jobs/{id}` → `transcript` |
| Scene participants and speakers | §3.4 `scene.json` `participants[]` | `GET /v1/jobs/{id}` → `scene` |
| Edits | WP3 `apply_review` | `POST /v1/jobs/{id}/review` → returns updated `items` **and** `plan` |
| Audit | §3.8 `audit.json` | `GET /v1/jobs/{id}/result` → `audit` |
| Result files | `redacted.mp4`, §3.9 `receipt.html`, `receipt.json` | `GET /v1/jobs/{id}/result` |
| Demo mode | — | every response → `mode: "live" \| "replay"` |
| Deletion time | `job.json` `created_at` + WP5's cleanup schedule | `deletes_at` (required) |

**Requests for other WPs** (also listed in the PRE-B PR):
1. **WP5:** return the fields above, including `plan` with the review response, `mode` on every response, and `status: failed` with the failed `stage`.
2. **WP2:** draw each track's `<concept>:<n>` label on the Set-of-Mark keyframes exactly as PRE-A `docs/prompts/role-pass.md` specifies, using the track's own ID. The UI derives display labels from track IDs (§0), so no extra field is needed.
3. **WP2:** fill `roles.tracks[].matches_participant` (nullable index into `scene.participants`) and `suggested_role` (nullable, escalation only) as PRE-A `docs/prompts/role-pass.md` and `escalation.md` specify. The drawer's speaker link ("said by {label}") and escalation suggestion read them (§4.3, §4.6).
4. **WP3:** keep `reason` strings short (≤ 90 characters), plain, lowercase-first, no trailing full stop; the UI capitalises.
5. **WP3/WP5:** name the review edit types to match §3.4 and §10.5: `keep`, `hide`, `merge` (into an item ID), `remove_person`, and `undo` carrying the `edit_id` to revert. The server restores the item's state from before that edit (including `needs_you`, `decided_by` and an unmerge), so the UI never has to construct an inverse edit. After a `merge` is acknowledged, the server returns the target with the source's `track_ids` folded in and the source removed. An edit accepted while the job is `done` moves the job back to `review` (the previous render stays downloadable until a new one replaces it).
6. **WP1:** follow PRE-A `docs/API-NOTES.md` §5b exactly for `job.json` `times` (no trim, `times[0] = 0`, strictly increasing, `frames` entries, prepared MP4 encoded with exactly these timestamps). The overlay mapping (§3.6) and every displayed time depend on it.
7. **WP2:** put `transcript.json` turn times on the same timeline as `job.times` (seconds from prepared frame 0), or record which timeline they use, so the Why drawer's transcript overlap (§4.6) lines up.
8. **WP5:** return `deletes_at` as the latest time the 24 h cleanup will have removed the job (it depends on how often the cleanup runs).

---

## 9. Accessibility checklist

Target: WCAG 2.2 AA on every screen.

- [ ] Every action works with a keyboard; focus is always visible and never trapped except in dialogs and the drawer.
- [ ] Colour is never the only signal: every state has an icon and a word.
- [ ] Text contrast ≥ 4.5:1; icons and focus rings ≥ 3:1.
- [ ] Captions on every video with speech (the hero clip by default).
- [ ] Live regions announce stage changes and chip moves once, politely; no announcements on every progress tick.
- [ ] `prefers-reduced-motion`: no autoplay, no sliding drawers (they appear without animation).
- [ ] Touch targets ≥ 44×44 CSS px on mobile, ≥ 32×32 on desktop (above SC 2.5.8's 24×24); the layout reflows at 320 CSS px wide (SC 1.4.10) and at 200% zoom without horizontal page scroll.
- [ ] Focused elements are never hidden behind the sticky video or bottom bar (SC 2.4.11).
- [ ] Every drag action has a single-pointer alternative (SC 2.5.7): the drop zone has "Choose a file", the bottom sheet's handle is a button.
- [ ] Every image has alt text built from data (keyframes, thumbnails: "Face 4, Child, hidden").
- [ ] Single-key shortcuts only in the chip area, with a way to turn them off (SC 2.1.4).
- [ ] Dialogs: labelled, focus trapped, `Esc` closes, focus returns to the opener.

---

## 10. Build contract (for WP6)

This section is what WP6 codes and tests against, so nothing in §1–§9 has to be guessed. Field names marked *(proposal)* are WP6↔WP5 proposals: if WP5 names them differently, WP5's names win and the mocks follow in the same PR. Every user-facing string here already appears in a copy-deck table above; if a builder needs a string that isn't in a copy deck, that's a spec gap: add it to the copy deck first.

### 10.1 Mock fixtures (`web/mocks/`)

One file per screen state. Component and page tests load these through the API client (`web/src/lib/api.ts`), which uses the mocks whenever `NEXT_PUBLIC_SAFECUT_API` is unset ([WP6](work-packages/WP6.md) step 2).

| File | Endpoint it stands in for | Screen state it drives |
|---|---|---|
| `job-processing-track.json` | `GET /v1/jobs/{id}` | §2.3 progress, active row "Finding people and objects" |
| `job-processing-miss-loop.json` | `GET /v1/jobs/{id}` | §2.5 progress with the optional "Looking again for anything missed" row shown |
| `job-failed-roles.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `stage: "roles"`) | §2.6 stage-failure message: "Something went wrong while working out who's part of the story. …" |
| `job-review-hero1.json` | `GET /v1/jobs/{id}` | §3.1 review panel: hidden, kept clear and needs-you items, a locked child, a plate (full example below) |
| `job-review-cafe.json` | `GET /v1/jobs/{id}` | the context test ([STORYBOARD.md](STORYBOARD.md) 5.1–5.2): an inbox screen hidden, a menu screen in Needs you, the screen keep-confirm (§3.4), and the drawer's "Muse Spark read it as …" (§4.3) (example below) |
| `job-review-empty.json` | `GET /v1/jobs/{id}` (`items: []`) | §3.7 "Empty: nothing found at all" |
| `job-review-needs-you-only.json` | `GET /v1/jobs/{id}` | every item `needs_you`; mobile opens on the Needs-you tab; bottom bar "3 items still need you…" |
| `job-review-locked-child.json` | `GET /v1/jobs/{id}` | one locked child only: no toggle, "Always hidden" |
| `job-review-reentry.json` | `GET /v1/jobs/{id}` | a kept guest (`face:2`, item i_1) plus a NEW hidden item `face:9` whose `reentry_of` is `face:2`: merge offered (§3.4) |
| `job-review-reentry-bystander.json` | `GET /v1/jobs/{id}` | a hidden bystander (`face:5`) plus a NEW hidden item `face:8` whose `reentry_of` is `face:5` (the H1B van case): no merge button, the "They stay hidden." line (§3.3) |
| `job-done-edited.json` | `GET /v1/jobs/{id}` (`status: "review"` after an edit made in `done` with `?view=review`) | the §3.5 "You changed something after rendering…" bar |
| `job-review-200-items.json` | `GET /v1/jobs/{id}` | the performance case in §10.7 |
| `job-review-no-audio.json` | `GET /v1/jobs/{id}` (`job.audio: false`, no `transcript`) | drawer shows "This clip has no sound." |
| `job-replay.json` | `GET /v1/jobs/{id}` (`mode: "replay"`) | demo-mode banner (§6) on the review panel |
| `job-rendering-audit.json` | `GET /v1/jobs/{id}` (`stage: "audit"`) | §3.5 bottom bar replaced by the render stages; chips read-only |
| `result-clean.json` | `GET /v1/jobs/{id}/result` | §5.3 "No leaks found." |
| `result-fixed.json` | `GET /v1/jobs/{id}/result` | §5.3 "1 leak(s) found and fixed. Nothing left to fix." (two `leaks[]` rows with the same `patched_item`: proves the distinct-item count, §5.6) |
| `result-unresolved.json` | `GET /v1/jobs/{id}/result` (`audit.unresolved: 1`) | §5.4 warning, Publish disabled |
| `review-ack.json` | `POST /v1/jobs/{id}/review` | an accepted edit returning updated `items` and `plan` |
| `error-401.json` | any | "That code didn't work. …" |
| `error-429-cap.json` | any (`error.code: "daily_cap"`) | "Safe Cut has reached today's limit …" |
| `error-429-rate.json` | any (`error.code: "rate_limited"`) | "Too many tries in a short time. …" |
| `error-404-expired.json` | `GET /v1/jobs/{id}` (`error.code: "expired"`) | §7 "This clip has been deleted. …" |
| `error-404-not-found.json` | `GET /v1/jobs/{id}` (`error.code: "not_found"`) | §7 "We couldn't find that clip. …" |
| `job-failed-render.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `stage: "render"`) | stage-failure message; [Try again] re-renders (§10.4) |
| `error-413.json` | `POST /v1/jobs` (`error.code: "too_large"`, `error.size_bytes`) | "This file is {size} MB. …" |
| `error-422-duration.json` | `POST /v1/jobs` (`error.code: "too_long"`, `error.duration_s`) | "This clip is {duration} seconds long. …" |
| `error-422-job-cap.json` | `POST /v1/jobs/{id}/start` (`error.code: "job_cap"`) | "This clip would cost more than the per-clip limit …" |
| `error-409-rendering.json` | `POST /v1/jobs/{id}/render` | no message; keep polling |
| `error-500.json` | any | §7 "Something went wrong on our side. …" |

Error body *(proposal)*: `{"error": {"code": "<snake_case>", "message": "<for logs only, never shown>", …extra fields}}`. The UI chooses its copy from `status` + `code` (§10.3), never from `message`.

**`job-review-hero1.json`** (complete and self-consistent: a 12-frame excerpt at 30 fps, so `times` has exactly `frames` entries and passes the §3.6 check; every evidence frame is a keyframe with a box for the item's primary track; track IDs use PRE-A's `<concept>:<n>` labels):

```json
{
  "job_id": "j_hero1", "mode": "live", "status": "review", "stage": "review", "progress": 1.0,
  "deletes_at": "2026-10-28T11:00:00Z",
  "job": {"fps": 30.0, "width": 1280, "height": 720, "frames": 12, "audio": true,
          "times": [0.0, 0.0333, 0.0667, 0.1, 0.1333, 0.1667, 0.2, 0.2333, 0.2667, 0.3, 0.3333, 0.3667],
          "created_at": "2026-10-27T10:00:00Z",
          "prepared_url": "https://example.invalid/j_hero1/prepared.mp4"},
  "items": [
    {"item_id": "i_1", "track_ids": ["face:2", "person:1"], "kind": "person", "decision": "keep",
     "reason": "the guest: introduced at the start, speaks to camera", "evidence_frames": [3, 9],
     "style": "pixelate", "decided_by": "policy", "locked": false},
    {"item_id": "i_2", "track_ids": ["face:4"], "kind": "child", "decision": "hide",
     "reason": "child in the background, not addressed", "evidence_frames": [6],
     "style": "solid", "decided_by": "policy", "locked": true},
    {"item_id": "i_3", "track_ids": ["license plate:1"], "kind": "plate", "decision": "hide",
     "reason": "number plate on a parked car", "evidence_frames": [1],
     "style": "solid", "decided_by": "policy", "locked": false},
    {"item_id": "i_4", "track_ids": ["face:6"], "kind": "person", "decision": "needs_you",
     "reason": "looks at the camera; checks disagreed", "evidence_frames": [9],
     "style": "pixelate", "decided_by": "model", "locked": false}
  ],
  "tracks": [
    {"track_id": "face:2", "concept": "face", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"3": [400, 120, 470, 210], "9": [410, 122, 480, 212]}},
    {"track_id": "person:1", "concept": "person", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"3": [360, 100, 560, 700], "9": [370, 102, 570, 700]}},
    {"track_id": "face:4", "concept": "face", "first": 4, "last": 10, "reentry_of": null,
     "boxes": {"6": [900, 200, 940, 250]}},
    {"track_id": "license plate:1", "concept": "license plate", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"1": [1050, 560, 1150, 590]}},
    {"track_id": "face:6", "concept": "face", "first": 8, "last": 11, "reentry_of": null,
     "boxes": {"9": [700, 150, 750, 215]}}
  ],
  "roles": {
    "tracks": [
      {"track_id": "face:2", "role": "participant", "votes": ["participant", "participant", "participant"], "escalated": false,
       "suggested_role": null, "matches_participant": 0, "evidence": "introduced at frame 3, speaks to camera", "frames": [3, 9]},
      {"track_id": "face:4", "role": "child", "votes": ["child", "child", "child"], "escalated": false,
       "suggested_role": null, "matches_participant": null, "evidence": "small person walking with an adult behind the guest", "frames": [6]},
      {"track_id": "face:6", "role": "unsure", "votes": ["bystander", "participant", "bystander"], "escalated": true,
       "suggested_role": "bystander", "matches_participant": null, "evidence": "looks at the camera at frame 9, never speaks", "frames": [9]}
    ],
    "objects": [], "missed": [], "keyframes": ["som/000001.jpg", "som/000003.jpg", "som/000006.jpg", "som/000009.jpg"]
  },
  "keyframe_urls": {"1": "https://example.invalid/j_hero1/som/000001.jpg", "3": "https://example.invalid/j_hero1/som/000003.jpg",
                    "6": "https://example.invalid/j_hero1/som/000006.jpg", "9": "https://example.invalid/j_hero1/som/000009.jpg"},
  "plan": {"frames": {"1": [{"item_id": "i_3", "shape": "box", "box": [1042, 552, 1158, 598], "mask": null, "style": "solid", "grid": null}],
                      "6": [{"item_id": "i_2", "shape": "box", "box": [894, 193, 946, 257], "mask": null, "style": "solid", "grid": null}],
                      "9": [{"item_id": "i_4", "shape": "box", "box": [692, 140, 758, 225], "mask": null, "style": "pixelate", "grid": [692, 140, 11]}]},
           "crowd_fills": []},
  "transcript": {"source": "muse-voice-transcribe-1.0",
                 "turns": [{"speaker": "S2", "start": 0.1, "end": 0.3, "text": "Hi, I'm Amina, and today…"}]},
  "scene": {"model": "muse-spark-1.3", "summary": "street interview with a guest",
            "participants": [{"description": "woman in yellow jacket", "evidence": "introduced by S1 at the start", "speaker": "S2"}],
            "candidate_objects": []}
}
```

The `plan` lists only a few frames to stay short; frames it leaves out simply draw nothing (§10.7). A real job has a plan entry on every frame where a hidden item is visible.

**`job-review-cafe.json`** (the context test; the fields not shown are as in the hero mock, with `job_id: "j_cafe"`, the same 12-frame `job` and transcript, and `scene.participants: []`, so no speaker link is shown):

```json
{
  "items": [
    {"item_id": "i_1", "track_ids": ["face:1"], "kind": "person", "decision": "keep",
     "reason": "the host: speaks to camera throughout", "evidence_frames": [2, 7],
     "style": "pixelate", "decided_by": "policy", "locked": false},
    {"item_id": "i_5", "track_ids": ["screen:2"], "kind": "screen", "decision": "hide",
     "reason": "laptop showing an email inbox with names", "evidence_frames": [4],
     "style": "solid", "decided_by": "policy", "locked": false},
    {"item_id": "i_6", "track_ids": ["screen:3"], "kind": "screen", "decision": "needs_you",
     "reason": "menu, nothing personal", "evidence_frames": [4, 7],
     "style": "solid", "decided_by": "policy", "locked": false}
  ],
  "tracks": [
    {"track_id": "face:1", "concept": "face", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"2": [300, 120, 370, 210], "7": [305, 121, 375, 211]}},
    {"track_id": "screen:2", "concept": "screen", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"4": [700, 400, 900, 520]}},
    {"track_id": "screen:3", "concept": "screen", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"4": [950, 410, 1150, 530], "7": [950, 410, 1150, 530]}}
  ],
  "roles": {
    "tracks": [{"track_id": "face:1", "role": "participant", "votes": ["participant", "participant", "participant"], "escalated": false,
                "suggested_role": null, "matches_participant": null, "evidence": "speaks to camera throughout", "frames": [2, 7]}],
    "objects": [
      {"track_id": "screen:2", "sensitive": true, "content": "email inbox with names", "frames": [4]},
      {"track_id": "screen:3", "sensitive": false, "content": "café menu", "frames": [4, 7]}
    ],
    "missed": [], "keyframes": ["som/000002.jpg", "som/000004.jpg", "som/000007.jpg"]
  },
  "keyframe_urls": {"2": "https://example.invalid/j_cafe/som/000002.jpg", "4": "https://example.invalid/j_cafe/som/000004.jpg",
                    "7": "https://example.invalid/j_cafe/som/000007.jpg"},
  "plan": {"frames": {"4": [{"item_id": "i_5", "shape": "box", "box": [684, 384, 916, 536], "mask": null, "style": "solid", "grid": null},
                            {"item_id": "i_6", "shape": "box", "box": [934, 394, 1166, 546], "mask": null, "style": "solid", "grid": null}],
                      "7": [{"item_id": "i_6", "shape": "box", "box": [934, 394, 1166, 546], "mask": null, "style": "solid", "grid": null}]},
           "crowd_fills": []}
}
```

`i_6` is in the plan because `needs_you` renders hidden until the creator decides (ARCHITECTURE §3.6).

*(proposal)* fields beyond ARCHITECTURE §3: `job_id`, `mode`, `status`, `stage`, `progress` (0–1), `deletes_at`, `job.prepared_url`, `keyframe_urls` (frame → signed URL). `roles.tracks[].suggested_role` and `matches_participant` are PRE-A's additions to `roles.json` (escalation.md, role-pass.md). Everything else is the contract shape.

**Mock invariants** (a mock test checks them): `times` has `frames` entries, is strictly increasing and starts at 0; every frame number is in `[0, frames − 1]`; every `track_ids` entry exists in `tracks`; every evidence frame is in `roles.keyframes` and in `keyframe_urls`, with a box for the item's primary track on that frame; every `plan` region's `item_id` exists; every `reentry_of` names an existing track. `example.invalid` is a reserved non-resolving domain, so a mock can never fetch real media.

### 10.2 Input validation (`/try`)

The client checks these for fast feedback; **the server enforces the same limits** (WP5), because the client can be bypassed.

| Field | Rule | Trigger | Copy (§2.6) | Focus |
|---|---|---|---|---|
| Access code | Trim whitespace; must be non-empty; `maxlength="64"` on the input (longer input can't be typed or pasted beyond 64 characters). No other format check: only the server knows valid codes | Continue pressed | Empty: "Enter your access code." · `401`: "That code didn't work. Check it and try again." | Stay on the field; on `401`, select its text |
| File count | Exactly one file | Drop or choose | More than one: "Drop one clip at a time." (nothing is kept) | The drop zone's "Choose a file" button |
| File type | Extension `.mp4` or `.mov` (case-insensitive) **and** MIME `video/mp4` or `video/quicktime`. If either check fails, reject. An empty MIME string (some browsers) counts as a fail only if the extension also fails | Drop or choose | "Safe Cut takes MP4 or MOV video files." | "Choose a file" button |
| File size | `size ≤ 157,286,400` bytes (= 150 × 1024 × 1024; WP5 must use the same number). Shown as `{size}` = bytes ÷ 1,048,576, rounded **up** to 1 decimal (157,286,401 bytes → "150.1"), so the number shown is never ≤ the limit | Drop or choose | "This file is {size} MB. The limit is 150 MB." | "Choose a file" button |
| Duration | Read `duration` from a hidden `<video preload="metadata">`. Reject if `duration > 60.05` s (60 s plus a 0.05 s float tolerance). If the metadata hasn't loaded within 10 s, or `duration` is `NaN` or `Infinity`, don't show a client error: the server decides (`422` `too_long`). `{duration}` is shown in seconds, rounded **up** to 1 decimal (60.06 s → "60.1"; for the server's `422`, from `error.duration_s`) | After the file is accepted by the checks above | "This clip is {duration} seconds long. The limit is 60 seconds. Trim it and try again." | "Choose a file" button |
| Rights tick | Must be ticked | Start pressed | "Tick the box to confirm you can use this clip." | The checkbox |

The Start button is enabled once a file passes every check above, but pressing it with the box unticked shows the rights message (so the requirement is announced rather than silently blocking the button). Errors are announced through the live region and tied to their field with `aria-describedby` (§2.8).

### 10.3 Errors, retries and timeouts

| Situation | Detection | Copy | Action | Retry policy |
|---|---|---|---|---|
| Wrong code | `401` | §2.6 "That code didn't work. …" | stay on step A | none (user retries) |
| Daily cap | `429` + `code: "daily_cap"` | §2.6 "Safe Cut has reached today's limit …" | link to `/` | none |
| Rate limited | `429` + `code: "rate_limited"` | §2.6 "Too many tries in a short time. …" | | none automatic; if a `Retry-After` header is present, the button stays disabled until then |
| Too large / too long | `413` `too_large` / `422` `too_long` | §2.6 matching row | back to step B | none |
| Job cap | `422` `job_cap` | §2.6 "This clip would cost more than the per-clip limit …" | back to step B | none |
| Job expired | `404` with `code: "expired"` on a job route | §7 "This clip has been deleted. …" | [Try another clip] | none |
| Job not found | `404` with any other code on a job route | §7 "We couldn't find that clip. …" | [Try another clip] | none |
| Stage failed | `status: "failed"` | §2.6 stage-failure message, filled with that stage's §2.5 row label | [Try again] = `POST /render` if the failed stage is `render`, `audit` or `receipt` (re-render with the creator's decisions); otherwise `POST /start` *(proposal, WP5)* · [Delete now] | none automatic |
| Edit rejected | `POST /review` non-2xx, or timeout | §3.7 "That change didn't save. …" | chip reverts (§10.5 `SERVER_REJECT`) | **none automatic**: the creator presses [Try again] |
| Render already running | `409` on `POST /render` | no message | keep polling | n/a |
| Network error or timeout on a GET | fetch rejects, or no response in **15 s** | after 3 failed retries: §7 "Safe Cut's service isn't responding right now. …" | [Try again] restarts polling | retry after 2 s, 4 s, 8 s; then stop and show the message |
| Upload stalls | no progress event for **30 s** | §2.6 "The upload stopped. …" | [Try again] restarts the upload | none automatic |
| Anything else | other `5xx`, malformed JSON, failed `times` check (§3.6) | §7 "Something went wrong on our side. …" | [Try again] · [Go to the home page] | none automatic |

- **Timeouts:** every JSON request is aborted after 15 s (`AbortController`). Uploads have no overall timeout, only the 30 s stall rule.
- **Polling:** `GET /v1/jobs/{id}` every 2 s for the first 60 s of a page view, then every 5 s. Stop polling when the tab is hidden (`visibilitychange`) and resume immediately when it's visible again. Polling **pauses** in `review` while no render is in flight, and **resumes** as soon as `POST /render` is sent (or answered `409`), so the render stages show. It **stops** in `done`, `failed`, `expired` and `not_found`; in `done` it restarts only when an edit made at `?view=review` is acknowledged with `status: "review"` (§10.4), and then follows the rules above.
- **Idempotency:** each review edit carries an `edit_id` (a UUID v4 made in the browser) *(proposal; request to WP5)*. A manual retry resends the same `edit_id`, so the server can't apply it twice. `POST /render` is protected by disabling the button until the response, plus the `409` rule.
- **Logging:** errors go to the console with the job ID and the HTTP status, never the access code or signed URLs.

### 10.4 Job page state machine

| State | Entered when (`GET /v1/jobs/{id}`) | Route that renders it | Shows |
|---|---|---|---|
| `loading` | before the first response | either route | skeleton: video box and three empty columns, no spinner over text |
| `processing(stage)` | `status: "processing"`, `stage` ∈ `queued`, `prepare`, `track`, `transcribe`, `scene`, `roles`, `miss_loop`, `decide`, `guard` | `/jobs/[id]` | §2.5 stage list (as on `/try` step C) |
| `review` | `status: "review"` | `/jobs/[id]` | §3 review panel |
| `rendering(stage)` | `status: "rendering"`, `stage` ∈ `render`, `audit`, `receipt` | `/jobs/[id]` · `/jobs/[id]/result` | on `/jobs/[id]`: review panel, read-only, with the render stages in the bottom bar (§3.5); on `/result`: §5.4 "Rendering (arrived early)" |
| `done` | `status: "done"` | `/jobs/[id]/result`; also `/jobs/[id]?view=review` | on `/result`: §5. On `/jobs/[id]?view=review`: the §3 review panel, **editable** (reached only from "Back to review" or "[Review them]"). The first edit there is sent as usual; the server moves the job back to `review` *(proposal, §8 request 5)*, and the bottom bar shows §3.5's "You changed something after rendering. …" until a new render finishes |
| `failed(stage)` | `status: "failed"` | either route | §2.6 stage-failure message with that stage's §2.5 label; [Try again] per §10.3 |
| `expired` | `404` with `code: "expired"` | either route | §7 "This clip has been deleted. …" |
| `not_found` | `404` with any other code | either route | §7 "We couldn't find that clip. …" (the route-level 404 "We couldn't find that page." is only for unknown URLs) |

Transitions follow the server: `loading → processing → review → rendering → done`; any state can go to `failed` or `expired`. **Redirects** (with `router.replace`, so Back doesn't bounce): `/jobs/[id]` in `done` → `/jobs/[id]/result`, **except** with `?view=review`, which stays on the review panel; `/jobs/[id]/result` in `processing` or `review` → `/jobs/[id]`. `/result` in `rendering` doesn't redirect: it shows §5.4's "Rendering (arrived early)" and moves on to the result when the job is `done`. Neither route redirects in `failed`, `expired` or `not_found`. Query parameters (`?from=sigmora`, `?demo=1`) are kept across redirects; `view=review` is dropped when a redirect leaves the review route. Because an edit made in `done` moves the job to `review`, `/result` then redirects to the review panel, so Publish can't be reached with a stale video and receipt.

### 10.5 Review reducer

**State** *(per job)*: `items: Record<item_id, {label, track_ids, decision, decided_by, locked, kind, role, reentry_target: item_id | null, merged_into: item_id | null, removed: boolean}>`. `label` is the §0 display label; `role` is the item's primary-track role from `roles.json`, or `null` for objects; `reentry_target` is the item that owns the track named by one of this item's tracks' `reentry_of`, or `null`. Derived, never stored: an item is **visible in the columns** when `merged_into = null`; an item's **effective decision** is its target's when `merged_into` is set; its **tracks shown** are its own plus those of every item merged into it. Also: `rendering: boolean`, `pending: Record<edit_id, {edit, prev}>`, `undo: Edit[]` (unlimited within the page session; each toast's [Undo] undoes **that** edit and only appears while the toast is visible, 6 s), `confirm: {item_id} | null` (the screen/document keep confirm).

**Guards on every mutating action** (`KEEP`, `CONFIRM_KEEP`, `HIDE`, `MERGE`, `REMOVE_PERSON`, `UNDO`): `rendering` is false, and no edit is pending on any item the action touches (for `MERGE`, both `src` and `dst`). If a guard fails, nothing changes and **no request** is sent; while rendering, the note "Changes are paused while we render." shows.

**Actions and preconditions** (on top of the guards; otherwise: no state change, **no request**):

| Action | Precondition | Effect |
|---|---|---|
| `KEEP(id)` | `merged_into = null`; not `locked`; `decision ≠ keep` | `kind ∈ {screen, document}`: sets `confirm = {id}` only; no request yet. Any other kind (person, plate, other): `decision = keep`, `decided_by = creator`, edit sent |
| `CONFIRM_KEEP` | `confirm` is set and its item still passes `KEEP`'s precondition | `decision = keep`, `decided_by = creator`, edit sent; `confirm = null` |
| `CANCEL_CONFIRM` | `confirm` is set | `confirm = null`; nothing sent |
| `HIDE(id)` | `merged_into = null`; `decision ≠ hide` | `decision = hide`, `decided_by = creator`; items merged into it follow (effective decision); edit sent |
| `MERGE(src, dst)` | **all of:** `src ≠ dst`; `src.kind = person`; `src` not `locked`; `src.merged_into = null`; `src.reentry_target` is set **and** that item is `kind = person`, `decision = keep`, `role = participant` (this is when the chip offers the merge, §3.3); `dst.kind = person`; `dst.decision = keep`; `dst.role = participant`; `dst` not `locked`; `dst.merged_into = null` | `src.merged_into = dst`, `decided_by = creator`; `src` leaves the columns; `dst` shows `src`'s tracks (time range, overlay, drawer); header counts drop by one; edit sent |
| `REMOVE_PERSON(id)` | `kind ∈ {person, child}` (sent only after the §3.4 dialog's [Remove]) | `removed = true`, `decision = hide`, style shown as Whole person covered; on a kept participant this hides them; edit sent |
| `UNDO(edit_id)` | the edit is in `undo` and isn't pending | restores that edit's `prev` locally (for a merge: `src` back as a separate hidden NEW item with its own tracks) and sends an `undo` edit carrying `edit_id`; the server restores the prior state (§8 request 5) *(proposal, WP3/WP5)* |
| `SERVER_ACK(edit_id, items, plan)` | edit is pending | drop from `pending`; replace items and plan with the server's (after a merge, the server's `dst` already holds `src`'s `track_ids` and `src` is gone; because the re-entry track now belongs to the same item, `dst` shows no NEW badge, §3.3) |
| `SERVER_REJECT(edit_id)` | edit is pending | restore `prev`; show the §3.7 edit-failed toast |

Children are never `MERGE` sources or targets: a child is `kind = child`, which fails both `kind = person` checks, and is `locked`.

**Test cases** (expected state and UI after the action):

| # | Initial | Action | Expected |
|---|---|---|---|
| R1 | café mock: i_6 menu screen, needs_you | `KEEP(i_6)` | `confirm = {i_6}`; inline "Only keep this clear if nothing on it is personal."; no request yet |
| R2 | R1 state | `CONFIRM_KEEP` | i_6 keep, creator; chip in Kept clear; toast "Screen 3 will be kept clear. [Undo]"; one request; `confirm = null` |
| R2b | R1 state | `CANCEL_CONFIRM` | i_6 unchanged (needs_you); `confirm = null`; no request |
| R2c | hero mock: i_3 plate, hide | `KEEP(i_3)` | i_3 keep, creator, **no confirm** (plates aren't screens or documents); toast "Plate 1 will be kept clear. [Undo]"; one request |
| R3 | i_2 locked child | `KEEP(i_2)` | no change; **no request**; no toast (the button isn't rendered; this guards keyboard and devtools paths) |
| R4 | i_4 needs_you | `HIDE(i_4)` | hide, creator; chip in Hidden; toast "Face 6 will be hidden. [Undo]" |
| R5 | R4 state (acknowledged) | `UNDO(R4)` | i_4 back to needs_you, decided_by model; chip in Needs you; toast "Undone."; one `undo` edit sent with R4's `edit_id` |
| R6 | i_1 keep | `HIDE(i_1)` twice quickly (double-click) | one state change, **one request** (the second fails the pending-edit guard) |
| R7 | i_4 needs_you | `KEEP(i_4)` | keep, creator; Kept clear; toast "Face 6 will be kept clear. [Undo]" |
| R8 | reentry mock: i_9 (`face:9`, hidden, `reentry_of: face:2`) and i_1 (`face:2`, kept guest) | `MERGE(i_9, i_1)` | `i_9.merged_into = i_1`; i_9 leaves the columns; i_1's range and overlay include `face:9`; header counts drop by one; toast "Face 9 merged into Face 2. They'll be kept clear like Face 2. [Undo]"; one request |
| R8b | R8 state (acknowledged: server returns i_1 with `track_ids` `[face:2, person:1, face:9]`, no i_9) | `HIDE(i_1)` | i_1 hide, creator; the overlay covers `face:9`'s frames too; no NEW badge on i_1; toast "Face 2 will be hidden. [Undo]" |
| R9 | R8 state (acknowledged) | `UNDO(R8)` | i_9 back in Hidden as its own item with `face:9`, NEW again with [Same as Face 2…]; i_1's range back; header counts back; toast "Undone."; one `undo` edit sent with R8's `edit_id` |
| R9b | reentry-bystander mock: i_8 (`face:8`, hidden, `reentry_of: face:5`), i_5 (`face:5`, hidden bystander), i_1 kept guest | render the chip, then `MERGE(i_8, i_1)` | chip shows "The tracker lost this person and found them again. They stay hidden." and no merge button; the action is rejected (`reentry_target` isn't a kept participant); no request |
| R10 | i_9, i_2 child | `MERGE(i_9, i_2)` | rejected; no request (child target) |
| R11 | i_2 child | `MERGE(i_2, i_1)` | rejected; no request (child source) |
| R12 | i_9, i_4 needs_you | `MERGE(i_9, i_4)` | rejected (target not kept) |
| R12b | i_9, i_7 a bystander the creator kept (`role = bystander`, keep) | `MERGE(i_9, i_7)` | rejected (target isn't a participant) |
| R12c | i_9 with an edit pending | `MERGE(i_9, i_1)` | rejected by the pending-edit guard; no request |
| R13 | i_1 kept participant | `REMOVE_PERSON(i_1)` (after the dialog's [Remove]) | i_1 hide, removed, Whole person covered; toast "Face 2 will be fully covered wherever they appear. [Undo]" |
| R14 | i_4 needs_you | `HIDE(i_4)` then `SERVER_REJECT` | back to needs_you; toast "That change didn't save. Check your connection and try again." |
| R15 | i_4 needs_you | `HIDE(i_4)` then `SERVER_ACK` with server items | items replaced by the server's; plan replaced; overlay redraws from the new plan |
| R16 | `rendering = true` | any mutating action | rejected by the guard; no request; note "Changes are paused while we render." |
| R17 | replay mode | `HIDE(i_4)` | same behaviour; the request goes to WP5's replay API (§3.7 demo mode) |
| R18 | `done`, opened at `/jobs/[id]?view=review` (hero mock with `status: "done"`) | `HIDE(i_4)`, then `SERVER_ACK` with `status: "review"` | edit applied as usual; bottom bar "You changed something after rendering. Render again to update the video and receipt." with **Approve & render**; opening `/result` now redirects to the review panel, so Publish isn't reachable until the new render is `done` |

### 10.6 Frame-mapping test cases (§3.6, PRE-A §5b)

`frame(m) = clamp(max{ i : times[i] ≤ m + 0.001 }, 0, frames − 1)`; when no `i` qualifies (`m < −0.001`), the result is 0.

| Case | `times` | `m` | Expected frame |
|---|---|---|---|
| CFR, exact start | `[0, 0.0333, 0.0667, 0.1]` | `0` | 0 |
| CFR, exact boundary | same | `0.0667` | 2 |
| CFR, just below a boundary, inside tolerance | same | `0.0660` | 2 (0.0660 + 0.001 ≥ 0.0667) |
| CFR, below a boundary, outside tolerance | same | `0.0650` | 1 |
| Before 0 | same | `−0.5` | 0 |
| Past the end | same | `5.0` | 3 |
| VFR (uneven gaps) | `[0, 0.040, 0.050, 0.120, 0.130]` | `0.100` | 2 |
| VFR, on a late frame | same | `0.1205` | 3 |
| Display time | `times[1500] = 50.02` | — | `0:50` (and `0:50.0` in the drawer) |
| Invalid `times` | `[0, 0.04, 0.04]` (not strictly increasing) | — | unexpected-error page, overlay not drawn |

### 10.7 Edge states checklist

| Case | Expected |
|---|---|
| Zero items | §3.7 "Empty: nothing found at all"; Approve & render still available |
| All items locked | Hidden column only; Kept clear "Nothing is kept clear. …"; Needs you "Nothing needs you."; bottom bar "Everything's decided." |
| Exactly 1 item | normal layout; the other two columns show their empty copy |
| 200 items | each column virtualises its list above 100 chips (only visible chips are in the DOM, with an accessible count in the column header); the overlay draws at most 200 regions per frame, and `crowd_fills` count as one region each; keyboard order still visits every chip |
| Very long `reason` | chip clamps to 2 lines with "…"; the full text is in the drawer and in the chip's accessible name |
| Missing keyframe URL | drawer shows "The keyframe didn't load." (§4.4); the rest of the drawer works |
| Empty transcript (`turns: []`) | drawer: "No speech was found in this clip." |
| `job.audio: false` | drawer section replaced by "This clip has no sound." |
| No `scene`, or `matches_participant` null | the "said by {label}" link is never shown; nothing else changes |
| `plan.frames` has no entry for a frame | draw nothing on that frame; no error (frames with nothing to cover are left out of the plan) |
| A track ID that isn't `<concept>:<n>` | label = the raw track ID, and a console warning (it signals a WP1/WP2 contract gap); never a made-up number |
| Signed URL expired (`403` on media) | refetch `GET /v1/jobs/{id}` once for fresh URLs; if it fails again, §7 unexpected-error |
