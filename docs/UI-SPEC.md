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

**Time display.** Every frame number shown to a person is converted to clip time `m:ss` (or `m:ss.s` in the Why drawer) through `job.times[frame]` ([ARCHITECTURE.md](ARCHITECTURE.md) §3.1). Never show raw frame numbers outside the Why drawer's details row.

**Item number.** Items are numbered `#1, #2, …` in the order of their first appearance. When an item has a SAM track that appears on the Set-of-Mark keyframes, the number shown is **the number drawn on the keyframe** (the SoM mark), so the drawer and the chip match. (Request to WP2/WP5: expose that mark number per item; see §8.)

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
│  │ Safe Cut         │ …        │ …        │ …           │ …         │               │
│  └──────────────────┴──────────┴──────────┴─────────────┴───────────┘               │
│  n clips · labelled by 2 people (agreement κ = …) · run ID ↗                         │
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
| Step 1 body | Muse Spark watches the clip, listens to who's speaking, and rules on each person and object SAM 3.1 has numbered: part of the story, or not. |
| Step 2 title | SAM 3.1 keeps them hidden |
| Step 2 body | SAM 3.1 follows each hidden person and item frame by frame. Anyone the tracker loses and finds again starts hidden. Anything uncertain stays hidden. |
| Step 3 title | An audit checks the render |
| Step 3 body | Before anything is published, Meta's EgoBlur and a second Muse Spark pass check every frame of the result. Any leak is fixed and recorded on your privacy receipt. |
| Side-by-side title | Blur every face vs Safe Cut |
| Side-by-side captions | Blur every face: your guest is hidden, the number plate isn't. · Safe Cut: your guest stays clear, the plate and the passer-by are hidden. |
| Results title | Results on our labelled test set |
| Results columns | Method · Recall · Exposure · Leak bursts · Over-blur |
| Column help (tooltip and footnote) | Recall: share of things that should be hidden that were hidden for at least 95% of their frames. · Exposure: share of frames where something that should be hidden was less than 90% covered. · Leak bursts: runs of 3 or more exposed frames in a row. · Over-blur: share of people and items that should stay clear but were hidden for more than 10% of their frames. |
| Results footnote | `{n_clips}` clips filmed in public, labelled by `{n_labellers}` people (agreement κ = `{kappa}`). Run `{run_id}`. How we measured ↗ |
| Results placeholder (before WP8 fills it) | Numbers appear here after our frozen test runs. We publish them whether they're good or not. |
| Bottom links | Try it · Source on GitHub · Use it inside Sigmora |

All result numbers come from `eval/results/<run-id>/metrics.json` through WP8 ([AGENTS.md](../AGENTS.md) rule 9). WP6 ships the placeholder and the table component; it never types a number.

### 1.4 States

| State | What shows |
|---|---|
| Loading | Poster frame of hero clip 1 (redacted) with the toggle disabled; text skeletons. No spinner over the headline |
| Video fails to load | The poster stays; under it: "The demo video didn't load. You can still try Safe Cut with an access code." |
| Results not yet available | The placeholder line instead of the table |
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
│      • Everything is deleted 24 hours after upload, or sooner if you choose.         │
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
| `roles` | Working out who's part of the story | Muse Spark is ruling on each numbered person and object, three times over. |
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
| File too long (client check on metadata, or `413`/`422`) | This clip is `{duration}` long. The limit is 60 seconds. Trim it and try again. | |
| File too big | This file is `{size}` MB. The limit is 150 MB. | |
| Wrong type | Safe Cut takes MP4 or MOV video files. | |
| No rights tick | Tick the box to confirm you can use this clip. | |
| Upload interrupted | The upload stopped. Check your connection and try again; nothing was processed. | [Try again] |
| A stage fails (`job.status = failed`) | Something went wrong while `{row label, lowercase}`. Your clip hasn't been published anywhere. You can try again, or delete it now. | [Try again] [Delete now] |
| Job cap would be exceeded | This clip would cost more than the per-clip limit to process. Try a shorter clip. | |
| Cancel and delete (confirm dialog) | Delete this clip and stop processing? This can't be undone. · [Delete] [Keep going] | |
| After delete | Deleted. Nothing from this clip is kept. | link to `/try` |
| Rights tick label | I filmed this clip or have the right to use it. | |

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
│ │       selected item outlined, its # shown             │  render covers the same    │
│ │                                                       │  areas.                    │
│ └───────────────────────────────────────────────────────┘                            │
│ ▶ 0:12 / 0:31 ━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━  [CC]                                  │
│   timeline: one thin bar per item where it's on screen (selected item highlighted)  │
├──────────────────────────────┬──────────────────────────────┬────────────────────────┤
│ ■ Hidden (8)                 │ 👁 Kept clear (2)            │ ? Needs you (1)        │
│ ┌──────────────────────────┐ │ ┌──────────────────────────┐ │ ┌────────────────────┐ │
│ │[thumb] #4 Child   🔒     │ │ │[thumb] #2 Person         │ │ │[thumb] #6 Person   │ │
│ │ child in the background, │ │ │ the guest: introduced at │ │ │ looks at the       │ │
│ │ not addressed            │ │ │ 0:03, speaks to camera   │ │ │ camera; checks     │ │
│ │ 0:04–0:13                │ │ │ 0:00–0:31                │ │ │ disagreed          │ │
│ │ [Why?]   Always hidden   │ │ │ [Why?]  [Hide]           │ │ │ 0:09–0:14          │ │
│ └──────────────────────────┘ │ └──────────────────────────┘ │ │ [Why?]             │ │
│ ┌──────────────────────────┐ │ ┌──────────────────────────┐ │ │ [Hide] [Keep clear]│ │
│ │[thumb] #5 Number plate   │ │ │[thumb] #1 Person         │ │ └────────────────────┘ │
│ │ number plate on a parked │ │ │ the host                 │ │                        │
│ │ car                      │ │ │ ...                      │ │                        │
│ │ [Why?]  [Keep clear]     │ │ └──────────────────────────┘ │                        │
│ └──────────────────────────┘ │                              │                        │
│ ┌──────────────────────────┐ │                              │                        │
│ │[thumb] #9 Person  NEW    │ │                              │                        │
│ │ appeared again after     │ │                              │                        │
│ │ leaving; might be #2     │ │                              │                        │
│ │ [Why?] [Same as #2…]     │ │                              │                        │
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
│ │[thumb] #6 Person             │ │
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
| Number | `#n` (the SoM mark) | §0 Item number |
| Kind | Person / Child / Number plate / Screen / Document / Other item, with its icon | `kind` |
| Badges | 🔒 **Always hidden** if `locked`; **NEW** if any track has `reentry_of` set and the item hasn't been merged; **Changed by you** if `decided_by = creator` | `locked`, `tracks[].reentry_of`, `decided_by` |
| Reason | One or two lines, first letter capitalised, no trailing full stop added | `reason` |
| Time range | `m:ss–m:ss` from the first to the last frame of the item's tracks | `tracks.json` `first`/`last` over `track_ids` → `job.times` |
| Buttons | Hidden chip: [Why?] [Keep clear] · Kept chip: [Why?] [Hide] · Needs-you chip: [Why?] [Hide] [Keep clear] · Locked chip: [Why?] and the text "Always hidden" (no toggle) · NEW chip (hidden, re-acquired track): [Why?] [Same as #n…] [Keep clear]; "Same as #n…" comes first because merging is the usual fix | `decision`, `locked` |
| Overflow `⋯` | Remove this person from the video (person/child items); Jump to first appearance | |

Clicking the chip body (not a button) **selects** it: the video seeks to its first evidence frame and pauses, the overlay outlines that item, and the timeline highlights its bars.

### 3.4 Creator actions (what each tap does)

All edits go through `POST /v1/jobs/{id}/review` (WP3's `apply_review`). The UI updates **optimistically**: the chip moves and the overlay changes at once; if the request fails, it moves back with an error toast.

| Action | Result | Copy (toast, polite live region) |
|---|---|---|
| Keep clear (on a hidden or needs-you item) | `decision → keep`, `decided_by → creator`; chip moves to Kept clear; overlay stops covering it | "#5 will be kept clear. [Undo]" |
| Hide (on a kept or needs-you item) | `decision → hide`; chip moves to Hidden; overlay covers it | "#2 will be hidden. [Undo]" |
| Keep clear on a **screen or document** | Same, plus a one-line confirm in place: "Only keep this clear if nothing on it is personal." [Keep clear] [Cancel] | |
| Toggle a locked child | Not possible: no toggle is rendered. The "Always hidden" text has a help link that opens the drawer at the explanation | — |
| Same as #n… (re-entry merge) | A small menu lists the items that are **part of the story** (kept participants), each with its thumbnail: "Same person as #2 (the guest)". Choosing one merges the new track into that item; the NEW chip disappears and #2's time range grows | "#9 merged into #2. They'll be kept clear like #2. [Undo]" |
| Remove this person from the video | Confirm dialog (below). The item becomes hidden with the **Whole person covered** style and is marked "removed at your request" on the receipt | "#7 will be fully covered wherever they appear. [Undo]" |
| Undo | Reverts the last edit (one level per toast) | "Undone." |

**Remove-person dialog:** title "Remove this person?" · body "They'll be fully covered, not just their face, every time they appear. Your privacy receipt will record that you removed them." · [Remove] [Cancel]. (Cutting their segments out of the video is not in v1; don't offer it.)

**Merge rules the UI enforces** (from [DESIGN.md](DESIGN.md) §2.5): merge targets are only kept participants; children are never merge targets or merge sources; the merge never happens automatically.

### 3.5 Approve & render

| Situation | Bottom bar text | Button |
|---|---|---|
| Nothing needs you | Everything's decided. | **Approve & render** |
| `k` items need you | `k` item(s) still need you. If you render now, they stay hidden. | **Approve & render** (still enabled) |
| An edit is saving | Saving your changes… | disabled |
| Rendering | (the bar becomes the progress list from §2.5, `render` → `receipt`) | — |

Pressing it: `POST /v1/jobs/{id}/render`, then the stage rows `Applying your choices` → `Checking every frame of the result` → `Writing your privacy receipt`, then the page moves to `/jobs/[id]/result`. Chips are read-only during the render (a calm note: "Changes are paused while we render.").

### 3.6 The overlay

- A `<canvas>` sized to the video's displayed box, drawn on each `requestVideoFrameCallback`. The callback's `mediaTime` maps to a prepared-frame index by finding the last `job.times[i] ≤ mediaTime` ([WP6](work-packages/WP6.md) step 4).
- For that frame, draw every region in `plan.json` `frames[frame]` whose `item_id` is currently hidden or needs-you (after the creator's local edits). `solid` and `person_solid` → opaque fill (mask shape when `mask` is present, else box); `pixelate` → coarse cells on the locked `grid` (a preview; the final render adds noise); `crowd_fills` → opaque fill.
- An item switched from kept to hidden by the creator has no plan regions yet: until the review response returns a new plan, draw its **track boxes** from `tracks.json` (padded 15% as a visual approximation) so the creator sees it covered immediately.
- **Raw / Safe Cut toggle** turns the overlay off and on. In Raw mode, a 2 px outline still shows each item's position with its `#n`, so the creator can match chips to people.
- The selected item gets a 3 px focus outline (white with a dark edge, visible on any footage) and its `#n` label.
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
| Re-entry (NEW) | Chip with NEW badge and "Same as #n…" |
| Saving an edit | The chip shows a small "Saving…" under its buttons |
| Edit failed | Chip returns to its column; toast: "That change didn't save. Check your connection and try again." [Try again] |
| Job expired (`404` after 24 h) | Full-page: "This clip has been deleted. Safe Cut deletes everything 24 hours after upload." [Try another clip] |
| Demo mode | The banner (§6) and all edits work locally against the replay (WP5 replays them) |

### 3.8 Keyboard and accessibility

| Key (focus in the chip area) | Does |
|---|---|
| `Tab` / `Shift+Tab` | Moves between the three columns, the video, the bottom bar |
| `↑` / `↓` | Moves between chips in a column (roving tabindex; one tab stop per column) |
| `←` / `→` | Moves to the same position in the neighbouring column |
| `Enter` | Opens the Why? drawer for the focused chip |
| `H` | Hide the focused item |
| `C` | Keep the focused item clear |
| `Z` / `Ctrl+Z` | Undo the last edit |
| `Space` | Play / pause the video (also when the video has focus) |
| `?` | Shows this list in a dialog |
| `Esc` | Closes a menu, dialog or the drawer, and returns focus to the chip that opened it |

- Each chip is an `<article>` with an accessible name like "#4, Child, hidden, always hidden. Child in the background, not addressed. 0:04 to 0:13." Buttons inside have full names ("Keep #5 clear", "Hide #2").
- Moving a chip announces it in a polite live region (the toast text) and keeps focus on the moved chip in its new column.
- Visible focus ring on every interactive element (2 px, contrast ≥ 3:1 against both light and dark surfaces).
- Touch targets are at least 44×44 px on mobile.
- The overlay canvas is `aria-hidden`; the chip list carries all the information. The timeline bars are decorative; the time range is in each chip's text.
- Single-letter shortcuts work only when focus is in the chip area (WCAG 2.1.4), and the `?` dialog has a switch to turn them off.

### 3.9 Data

| Element | Source |
|---|---|
| Header counts | `decisions.items[].decision` counts (after local edits) |
| Video | `job.json` `prepared` (raw prepared clip), its `fps`, `width`, `height`, `times` |
| Overlay regions | `plan.json` `frames`, `crowd_fills`; the `grid` for pixelate previews |
| Timeline bars | `tracks.json` `first`/`last` per track, grouped by item |
| Chips | `decisions.items[]`: `item_id`, `track_ids`, `kind`, `decision`, `reason`, `evidence_frames`, `style`, `decided_by`, `locked` |
| NEW badge, merge suggestion | `tracks.json` `tracks[].reentry_of` (informational only: the suggestion is never applied without a tap) |
| Edits | `POST /v1/jobs/{id}/review` |

---

## 4. The "Why?" drawer

This is the Meta-tooling story on screen ([DEMO.md](DEMO.md) beat 4): the numbered keyframe SAM 3.1 tracked, Muse Spark's ruling, the votes, and the speech evidence. Goal: a creator (or judge) can see in ten seconds **why** this item is where it is.

### 4.1 Wireframe: desktop (side drawer, 480 px wide, from the right)

```
                                   ┌──────────────────────────────────────────────┐
                                   │ #4 · Child                        [ Close ✕ ]│
                                   │ ■ Hidden · 🔒 Always hidden                  │
                                   ├──────────────────────────────────────────────┤
                                   │ ┌──────────────────────────────────────────┐ │
                                   │ │ Set-of-Mark keyframe at 0:06             │ │
                                   │ │  [1]   [2]                [4]◀ ring      │ │
                                   │ │            [5]                           │ │
                                   │ └──────────────────────────────────────────┘ │
                                   │ ◀ 0:04   ● 0:06   0:09 ▶   (evidence frames) │
                                   │ "This is the frame Muse Spark was shown. The │
                                   │  numbers are the objects SAM 3.1 tracked."   │
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
                                   │ What was said while #4 was on screen         │
                                   │ 0:03 S2  "Hi, I'm Amina, and today…"         │
                                   │ 0:07 S1  "So what brings you here?"          │
                                   │ No speech is linked to #4.                   │
                                   ├──────────────────────────────────────────────┤
                                   │ Details                                      │
                                   │ Decided by Safe Cut's rules · Cover: solid   │
                                   │ Tracks: face:7, person:2 · frames 120–390    │
                                   │ Models: Muse Spark 1.3 · SAM 3.1 ·           │
                                   │ Muse Voice Transcribe                        │
                                   └──────────────────────────────────────────────┘
```

### 4.2 Wireframe: mobile (bottom sheet, full height when expanded)

```
┌──────────────────────────────────┐
│ ─── (drag handle)                │
│ #4 · Child           [Close ✕]   │
│ ■ Hidden · 🔒 Always hidden      │
│ ┌──────────────────────────────┐ │
│ │ keyframe, #4 ringed          │ │
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

**Header.** `#n · {Kind}` then the state line: `■ Hidden`, `👁 Kept clear` or `? Needs you`, plus `🔒 Always hidden` / `NEW` / `Changed by you` badges.

**Keyframe.** The SoM keyframe image for the selected evidence frame, with a **ring** (3 px, white with a dark edge) drawn by the UI around the item's box on that frame, plus its number. Arrows step through `evidence_frames`; the dot row shows how many there are. Caption: "This is the frame Muse Spark was shown. The numbers are the objects SAM 3.1 tracked." If no keyframe exists for the item (e.g. an item added by the audit), show the plan box on the nearest prepared frame and the caption "Added by the audit after rendering. There's no keyframe for it."

**"Why it's hidden / kept clear / needs you".** The `reason`, then one fixed sentence by case:

| Case | Fixed sentence |
|---|---|
| Hidden, bystander | People who aren't part of the story are hidden by default. |
| Hidden, `unsure` / split votes | The checks didn't all agree, so it stays hidden. |
| Hidden, child (`locked`) | Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent. |
| Hidden, new ID after re-entry | The tracker lost this person and found them again. Anyone found again starts hidden until you say who they are. |
| Hidden, plate / screen / document | Number plates, private screens and documents are always hidden unless you decide otherwise. |
| Kept clear, participant | All three checks agreed this person is part of the story, on at least two keyframes. |
| Kept clear by you | You chose to keep this clear. |
| Needs you, harmless screen or document | Muse Spark read this as nothing personal, but screens and documents are only kept clear when you confirm. |
| Needs you, other | Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear. |
| Removed at your request | You asked to remove this person. They're fully covered everywhere they appear. |
| Added by the audit | The final check found this after rendering and covered it. |

**"What Muse Spark said (n checks)".** One mark per vote in `votes`, each with its role word (Part of the story / Not part of the story / Child / Not sure); ✓ when it matches the final role, ✕ otherwise. Then Muse Spark's `evidence` text in quotes. If `escalated`: "The checks disagreed, so Muse Spark took a longer, closer look once." For objects (screens, documents): "Muse Spark read it as: {content}" and "Personal: yes/no" from `objects[].sensitive`. For plates: "Number plates are always hidden; Muse Spark isn't asked about them." (only if the role pass doesn't rule on plates; WP2 confirms).

**"What was said while #n was on screen".** Transcript turns that overlap the item's on-screen time, max 4, each as `m:ss S# "text"`. If the scene pass links a speaker to this person (`scene.participants[].speaker` matched to the item; see §8), mark that speaker's lines with "said by #n". Otherwise end with "No speech is linked to #n." If there's no transcript: "No speech was found in this clip." Text is shown as heard; long turns are cut at 140 characters with "…".

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
- The keyframe has alt text built from the data: "Keyframe at 0:06. Item #4 is ringed, in the back right. Other numbered items: #1, #2, #5."
- Vote marks have text, not just ✓/✕ ("Check 1: Child, agrees").
- Mobile bottom sheet: the drag handle is also a button ("Expand" / "Collapse").

### 4.6 Data

| Element | Source |
|---|---|
| Keyframe image | `roles.json` `keyframes[]` (the `som/*.jpg` matching the evidence frame), served by WP5 as a URL |
| Ring position | `tracks.json` `tracks[track_id].boxes[frame]` for the item's tracks on that frame |
| Evidence frames | `decisions.items[].evidence_frames` (falls back to `roles.tracks[].frames`) |
| Reason | `decisions.items[].reason` |
| Votes, evidence, escalation | `roles.json` `tracks[]`: `votes`, `role`, `evidence`, `escalated` (for each track in `track_ids`; show the person's face track first) |
| Object content | `roles.json` `objects[]`: `sensitive`, `content` |
| Transcript | `transcript.json` `turns[]` overlapping `[times[first], times[last]]` |
| Speaker link | `scene.json` `participants[].speaker` (when WP2 links a participant to a track) |
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
│ This clip and everything made from it will be deleted on 27 Oct, 10:00 UTC.          │
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
│ Deleted on 27 Oct, 10:00 UTC     │
│ [ Delete everything now ]        │
└──────────────────────────────────┘
```

### 5.3 Copy deck

| Element | Copy |
|---|---|
| Title | Your clip is ready |
| Audit, clean | ✓ Checked · `{frames_scanned}` frames checked. No leaks found. |
| Audit, fixed | ✓ Checked · `{frames_scanned}` frames checked. `{n}` leak(s) found and fixed. Nothing left to fix. |
| Audit, unresolved | ⚠ Not ready to publish · `{frames_scanned}` frames checked. `{unresolved}` spot(s) couldn't be fixed automatically. Publishing is off until they're fixed. [Review them] |
| Audit detail link | What the check does → (expands: "Meta's EgoBlur looked for faces and number plates on every frame of the result. Muse Spark looked at sampled frames and tried to read or recognise anything. Anything they found that wasn't kept clear on purpose was covered, and the clip was rendered again.") |
| Download | Download video |
| Publish | Publish to Sigmora |
| Publish disabled tooltip | Publishing is off until every spot is fixed. |
| After publish | Sent to Sigmora. You can close this tab. |
| Back | Back to review |
| Receipt title | Privacy receipt |
| Receipt intro (above the frame) | A record of what was hidden, why, and who approved it. Keep it if anyone asks about this video. |
| Receipt download | Download receipt (JSON) |
| Deletion note | This clip and everything made from it will be deleted on `{deletes_at, local date and time}`. |
| Delete button | Delete everything now |
| Delete confirm | Delete the video, the receipt and all working files now? Download anything you need first. This can't be undone. · [Delete] [Cancel] |
| After delete | Deleted. Nothing from this clip is kept on Safe Cut. |

### 5.4 States

| State | What shows |
|---|---|
| Rendering (arrived early) | The progress list `render` → `receipt` from §2.5 |
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
| Audit summary | `audit.json`: `frames_scanned`, `leaks.length` (found and patched), `unresolved`, `passes` |
| Publish allowed | `audit.json` `unresolved == 0` ([ARCHITECTURE.md](ARCHITECTURE.md) §3.8) and `?from=sigmora` |
| Receipt frame / download | signed URLs for `receipt.html` and `receipt.json` (§3.9: items, audit, models, data_handling, approved_by/at, cost_usd, hash) |
| Deletion time | `job.json` `created_at` + 24 h (or a `deletes_at` from the API) |
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
| Job not found or expired | This clip has been deleted. Safe Cut deletes everything 24 hours after upload. | Try another clip |
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
| Votes, evidence, escalation, keyframe list, object content | §3.5 `roles.json` | `GET /v1/jobs/{id}` → `roles` |
| SoM keyframe images | §3.5 `keyframes[]` | signed URLs in `GET /v1/jobs/{id}` → `keyframe_urls` |
| Overlay regions | §3.7 `plan.json` | `GET /v1/jobs/{id}` → `plan` (or `plan_url`) |
| Transcript | §3.3 `transcript.json` | `GET /v1/jobs/{id}` → `transcript` |
| Scene participants and speakers | §3.4 `scene.json` `participants[]` | `GET /v1/jobs/{id}` → `scene` |
| Edits | WP3 `apply_review` | `POST /v1/jobs/{id}/review` → returns updated `items` **and** `plan` |
| Audit | §3.8 `audit.json` | `GET /v1/jobs/{id}/result` → `audit` |
| Result files | `redacted.mp4`, §3.9 `receipt.html`, `receipt.json` | `GET /v1/jobs/{id}/result` |
| Demo mode | — | every response → `mode: "live" \| "replay"` |
| Deletion time | `job.json` `created_at` + 24 h | optional `deletes_at` |

**Requests for other WPs** (also listed in the PRE-B PR):
1. **WP5:** return the fields above, including `plan` with the review response, `mode` on every response, and `status: failed` with the failed `stage`.
2. **WP2/WP5:** expose each item's **SoM mark number** (the number drawn on the keyframes), so chips and the drawer show the same `#n` as the image.
3. **WP2:** where the scene pass links a participant to a speaker and a track, record the track ID (today `scene.json` participants have `description`, `evidence`, `speaker` but no track), so the drawer can say "said by #n".
4. **WP3:** keep `reason` strings short (≤ 90 characters), plain, lowercase-first, no trailing full stop; the UI capitalises.
5. **WP3:** name the review edit types to match §3.4: `keep`, `hide`, `merge` (into an item ID), `remove_person`, `undo` (or the UI replays the inverse edit).

---

## 9. Accessibility checklist

Target: WCAG 2.2 AA on every screen.

- [ ] Every action works with a keyboard; focus is always visible and never trapped except in dialogs and the drawer.
- [ ] Colour is never the only signal: every state has an icon and a word.
- [ ] Text contrast ≥ 4.5:1; icons and focus rings ≥ 3:1.
- [ ] Captions on every video with speech (the hero clip by default).
- [ ] Live regions announce stage changes and chip moves once, politely; no announcements on every progress tick.
- [ ] `prefers-reduced-motion`: no autoplay, no sliding drawers (they appear without animation).
- [ ] Touch targets ≥ 44×44 px; the layout works at 320 px wide and at 200% zoom without horizontal page scroll.
- [ ] Every image has alt text built from data (keyframes, thumbnails: "#4, Child, hidden").
- [ ] Single-key shortcuts only in the chip area, with a way to turn them off.
- [ ] Dialogs: labelled, focus trapped, `Esc` closes, focus returns to the opener.
