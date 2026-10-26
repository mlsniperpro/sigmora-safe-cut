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

**Time display: two clocks** (PRE-A `docs/API-NOTES.md` §5b owns the time axes; [ARCHITECTURE.md](ARCHITECTURE.md) §3.1). The prepared clip has a **constant frame rate** `job.fps` (an integer, at most 30), so everything a person sees is on the **prepared clock**: prepared frame `i` is at `i / job.fps` seconds. That covers the player and scrubber, the overlay, chip time ranges, the drawer's keyframe times, transcript lines and toasts. `job.times[i]` is the **source clock** (source seconds of the source frame that prepared frame `i` shows); the UI uses it **only** for the receipt's "source time" column, never to place anything on screen. Times are computed in integers so they never round the wrong way: whole seconds `= floor(i / fps)`, shown as `m:ss` (frame 1977 at 30 fps → `1:05`); tenths `= floor(10·i / fps)`, shown as `m:ss.s` in the Why drawer (`1:05.9`). Never show raw frame numbers outside the Why drawer's details row; frame numbers inside Muse Spark's own text are rewritten to times (§4.3).

**Item label.** One rule, so the chip and the keyframe always agree. SAM 3.1's keyframes carry each track's label `<concept>:<n>` (e.g. `face:7`, `person:2`, `license plate:1`), burned in exactly as PRE-A `docs/prompts/role-pass.md` specifies, and track IDs use the same form ([ARCHITECTURE.md](ARCHITECTURE.md) §3.2). An item's **display label** is its **primary track**'s label in plain words: the primary track is the first `face:*` track in `track_ids` order if it has one (after a merge the server keeps the target's tracks first, request 5), otherwise the first track in `track_ids`; the label is the concept word plus `n`. Concept words: `face` → Face, `person` → Person, `license plate` → Plate, `screen` → Screen, `phone` → Phone, `document` → Document, `name badge` → Badge; any other (Muse-proposed) concept → its phrase with the first letter capitalised. So `face:7` → "Face 7", `license plate:1` → "Plate 1". Labels are unique because each concept numbers its own tracks.

**Breakpoints.** Widths of 1024 px and up use the desktop layouts; anything narrower (including 481–1023 px and 200% zoom, §9) uses the mobile layout, with the drawer as a bottom sheet. **Wireframes are illustrative:** where a wireframe's text or buttons differ from the copy deck (§1.3, §2.6, §5.3, §7) or §3.3's button sets, the deck and §3.3 win.

**Item kind.** WP3 sets `decisions.items[].kind` from the primary track's concept, and the UI relies on exactly this mapping (request 14 in §8): `face`, `person` → `person`, or `child` when the role is `child`; any track with `child_phrase: true` (a miss-loop child phrase such as "kid") → `child`, locked, whatever its concept; `license plate` → `plate`; `screen`, `phone` → `screen`; `document`, `name badge` → `document`; any other (Muse-proposed) concept → `other`. **Objects** are the kinds `plate`, `screen`, `document` and `other`; **people** are `person` and `child`. Kind words in copy: Person, Child, Number plate, Screen, Document, Other item (plural: people, children, number plates, screens, documents, items like this). The drawer shows the raw label too ("On the keyframe: face:7", plus "also person:2" for the item's other tracks), so the creator can find it in the image. Items added by the audit have no tracks and no keyframe label; their `kind` comes from the server (PRE-A §12: a `face`/`person` leak → `person`, `plate` → `plate`, anything else → `other`; a covered spot by the same rule over its leak rows), their label is their `audit_label` (`A1, A2, …`, numbered by the server: in first-frame order when an audit pass writes them, the next free number for a spot covered later), and their chip is locked, so its ⋯ menu offers only "Jump to first appearance" (no Remove); a U chip's kind follows the same rule over its spot's leak rows; **unfixed audit spots** (§3.3) are labelled `U1, U2, …` in order of their first frame. When a spot is covered, the server turns it into an audit-added item and gives it the next free `A` number; the remaining `U` labels don't change until the next audit. The two prefixes never overlap, so every label on screen is unique. The UI derives labels from track IDs and these server-assigned audit numbers; it never invents one.

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
│  │ …suggestions acc.│ …        │ …        │ …           │ …         │               │
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
| Step 2 body | SAM 3.1 keeps each hidden person and item covered through the clip. Anyone the tracker loses and finds again starts hidden. Anything uncertain stays hidden. |
| Step 3 title | An audit checks the render |
| Step 3 body | Before anything is published, Meta's EgoBlur checks the final render for faces and number plates, and a second Muse Spark pass tries to read or recognise anything left. Any leak is fixed and recorded on your privacy receipt. |
| Side-by-side title | Blur every face vs Safe Cut |
| Side-by-side captions | Blur every face: your guest is hidden, the number plate isn't. · Safe Cut: your guest stays clear, the plate and the passer-by are hidden. |
| Results title | Results on our labelled test set |
| Results columns | Method · Recall · Exposure · Leak bursts · Over-blur |
| Results rows | Blur every face · EgoBlur Gen 2 (or "EgoBlur Gen 2: not run (EgoBlur weights unavailable)" when the test run's `metrics.json` has no EgoBlur baseline row, auditor name rule below) · Detector only · Muse Spark, no tracking · Safe Cut (as shipped, the headline) · Safe Cut, suggestions accepted (labelled; LABEL-FORMAT §9.3: Needs-you items Muse Spark ruled harmless counted as kept; over-blur differs, other columns as WP7 reports them) · Safe Cut, no audit (if run) |
| Column help (tooltip and footnote) | Recall: of the people and things that should be hidden, the share that were hidden on at least 95% of the frames they're visible in. · Exposure: counting each should-be-hidden person or thing on each frame it's visible in, the share where less than 90% of it was covered. · Leak bursts: the number of times something that should be hidden was exposed for 3 or more frames in a row. · Over-blur: of the people and things that should stay clear, the share that were hidden on more than 10% of their frames. |
| Results footnote (two labellers) | `{n_clips}` test clips (`{n_public}` filmed in public, `{n_staged}` staged with consenting actors), labelled by two people. They agreed on `{percent_agreement}` of `{n_entities}` decisions (both said hide: `{a}` · only the first said hide: `{b}` · only the second said hide: `{c}` · both said keep: `{d}`); κ = `{kappa}`. Run `{run_id}`. How we measured ↗ |
| Results footnote (two labellers, κ not computable) | `{n_clips}` test clips (`{n_public}` filmed in public, `{n_staged}` staged with consenting actors), labelled by two people. They agreed on `{percent_agreement}` of `{n_entities}` decisions (both said hide: `{a}` · only the first said hide: `{b}` · only the second said hide: `{c}` · both said keep: `{d}`). κ can't be computed: both labellers made the same call on every item. Run `{run_id}`. How we measured ↗ |
| Results footnote (one labeller, plan R3) | `{n_clips}` test clips (`{n_public}` filmed in public, `{n_staged}` staged with consenting actors), labelled by one person. Agreement between two labellers wasn't measured. Run `{run_id}`. How we measured ↗ |
| Results placeholder (before WP8 fills it) | Numbers appear here after our frozen test runs. We publish them whether they're good or not. |
| Bottom links | Try it · Source on GitHub · Use it inside Sigmora |

**Auditor name rule** (PRE-A `docs/API-NOTES.md` §12, WP4 deviation, @ `02c605e`): copy that names the frame-by-frame detector takes it from `audit.json` `egoblur.model`, never a fixed "EgoBlur Gen 2" (AGENTS rule 9). `egoblur-gen2` or `egoblur-gen1`: the copy as written. `yunet-face` (the Oct 28 fallback when EgoBlur's weights are unavailable): "Meta's EgoBlur checks the final render for faces and number plates" becomes "a face detector (YuNet) checks every frame of the final render for faces; number plates are checked by Muse Spark only", and §5.3's audit detail changes the same way ("A face detector (YuNet) looked for faces on `{frames_scanned}` of the result's `{frames}` frames. … Muse Spark looked at sampled frames for number plates and anything else it could read or recognise. …"). When `egoblur.plates` is `null` (no plate detector ran), no plate count is shown anywhere, the receipt included; never `0`. The landing page's step 3 uses the pinned hero job's `audit.json` (`GET /v1/demo/{hero_id}`); the §2.5 `audit` stage line names no detector, since it shows before `audit.json` exists. Under `egoblur-gen1` the copy says "EgoBlur" without a generation (the results row names its own baseline).

**Footnote sources** (not part of the copy): `{n_clips}`, `{n_public}`, `{n_staged}`, `{percent_agreement}`, `{n_entities}`, the 2×2 counts `{a}`–`{d}` and `{kappa}` come from the test run's `metrics.json` (WP7's label report, request 22); `{run_id}` is that run's directory name.

The tooltips are plain-language restatements of [EVAL.md](EVAL.md) §2 with the same units (entities for recall and over-blur, entity-frames for exposure, runs for leak bursts); if EVAL.md changes, they change with it. The table rows are EVAL.md §3's baselines 1–4 plus Safe Cut full, and row 5 (without the audit) when WP7 runs it; Muse Spark without tracking stays in because it shows why SAM 3.1 is needed. All result numbers come from `eval/results/<run-id>/metrics.json` through WP8 ([AGENTS.md](../AGENTS.md) rule 9). WP6 ships the placeholder and the table component; it never types a number.

### 1.4 States

| State | What shows |
|---|---|
| Loading | Poster frame of hero clip 1 (redacted) with the toggle disabled; text skeletons. No spinner over the headline |
| Video fails to load | The poster stays; under it: "The demo video didn't load. You can still try Safe Cut with an access code." |
| Results not yet available | The placeholder line instead of the table |
| Single labeller (plan R3) | The one-labeller footnote. No κ, percent agreement or intra-rater figure appears anywhere on the page: an intra-rater re-label is a different measure and is never put in the κ slot ([SCHEDULE.md](labeling/SCHEDULE.md) R3) |
| κ not computable | The "κ not computable" footnote (when `1 − pe` is within 1e-9 of 0, [LABEL-FORMAT.md](labeling/LABEL-FORMAT.md) §9.2 K3). The counts and percentage still show; `null`, `NaN` or an empty κ is never rendered |
| Two labellers, κ computed | Percent agreement, κ **and** the 2×2 counts always appear together ([LABELING-GUIDE.md](labeling/LABELING-GUIDE.md) §5): κ is never shown on its own |
| Reduced motion | The hero video doesn't autoplay; a "Play demo" button shows instead |

### 1.5 Keyboard and accessibility

- The video autoplays muted (unless reduced motion), loops, has native controls, and has **captions** (WebVTT of the VO/dialogue; `[CC]` on by default).
- The Raw/Safe Cut toggle is a two-option radio group (arrow keys switch, label announced). Switching keeps the playback time.
- The side-by-side images have alt text describing what's hidden in each.
- The results table is a real `<table>` with `<th scope>`; on mobile it scrolls inside its own container, never the page.

### 1.6 Data

| Element | Source |
|---|---|
| Hero video (both versions) | Precomputed hero job (WP5 demo mode): the raw prepared clip and `redacted.mp4` from **`GET /v1/demo/{hero_id}`**, a public, read-only route that needs no access code and serves only **pinned** hero jobs, which the 24 h cleanup never deletes (*proposal*, §8 request 19) |
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
│      • It's sent to Meta's Model API in Standard mode, never Contributor mode.       │
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
│                                                                     a file is in)    │
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
| `render` | Applying your choices | Covering each hidden item on every frame it appears in. |
| `render` with `stage_reason: "audit_patch"` | Covering what the check found | The final check found something; covering it and checking again. (Used while an audit's auto-patch renders, so the creator isn't told their choices are being re-applied. `stage_reason` is a WP5 proposal.) |
| `audit` | Checking the result | Safe Cut's final check looks for anything that slipped through. |
| `receipt` | Writing your privacy receipt | |
| `done` | Done | (the page moves to the result) |

The `miss_loop` row appears only if that stage runs. `~N s left` shows only when the API provides an estimate; otherwise nothing (never a fake countdown). Stages `render` → `receipt` show on the review page after "Approve & render" (§3.5), not here.

### 2.6 Copy deck: messages and errors

**Plurals.** In every copy string, "(s)", "is/are", "it/they" and "it/them" are plural markers, and so is any verb whose subject carries one ("need"/"needs", "stay"/"stays"): the UI renders them grammatically by count ("1 leak found and fixed", "2 leaks found and fixed"; "1 item still needs you. If you render now, it stays hidden."), never the literal "(s)". Tests assert the rendered form.

| Situation | Copy | Action |
|---|---|---|
| Code empty on Continue | Enter your access code. | focus the field |
| Code wrong (`401`, any `error.code` except `code_not_active`) | That code didn't work. Check it and try again. | On step A (answer to Continue): keep the text, select it. On step B (answer to `POST /v1/jobs` or `POST /start`, because the code was revoked after Continue, request 20): the **step-B refusal** (§2.6.1) with this copy |
| Code refused on a job page (`401`, any `error.code`, on `POST /start`, `POST /render` or `POST /audit` of an existing job: its code was revoked, or its window has ended (any kind); request 20) | The access code for this clip no longer works, so Safe Cut can't process it further. Nothing has been published. (For `code_not_active` with a past `valid_until`: "This access code has expired, so Safe Cut can't run more work on this clip. You can still download or delete it.") | the **job-page refusal** (§2.6.1) |
| Code outside its dates (`401` `code_not_active`, with `error.valid_from` and/or `error.valid_until` when the code has them; requests 20 and 21) | Chosen by comparing the device clock with the dates (each shown as the viewer's local date and time): **before `valid_from`**: "This code isn't active yet. It works from `{valid_from}`." (with " to `{valid_until}`" added before the full stop when the code also has an end); **after `valid_until`**: "This code has expired. It worked until `{valid_until}`."; **otherwise, or with neither date** (e.g. a skewed device clock): "This code isn't active right now. Check the dates that came with it." | On step A (answer to Continue, request 21): keep the text, don't select it; Continue stays enabled. On step B (answer to `POST /v1/jobs` or `POST /start`, when the window closed after Continue; request 20): the **step-B refusal** (§2.6.1). On a job page (any code past its window): the **job-page refusal** (§2.6.1) with the previous row's copy, chosen by the same `valid_until` test |
| Daily limit reached (`429` `daily_cap`; on a job page see also §2.6.1) | Safe Cut has reached today's limit for the public demo. Try again tomorrow, or watch the demo on the home page. ("Tomorrow" = after the reset at 00:00 UTC, request 10 in §8. If WP5 sends `retry_at`, the copy may say "after {local time}" instead.) | **Two contexts, one mapping (§10.3):** on `/try` (answer to `POST /v1/jobs` or `POST /start`), a link to `/`, and Start is disabled until `retry_at`. On a job page (answer to `POST /render` or `POST /audit`, or `POST /start` from a failed-job page), the copy is the job-page variant "Safe Cut has reached today's limit for the public demo. Try again tomorrow." (no home-page link), the button that sent the request stays and is disabled until `retry_at`, or hidden under the §2.6.1 expiry rule (§3.5 row 0) |
| Access code budget used (`429` `code_cap`, on `POST /v1/jobs` or `POST /start` from `/try`; on a job page, the §2.6.1 job-page cap line) | This access code doesn't have enough budget left for this clip. Ask the person who gave it to you to add more, then press Start again. | Start stays enabled; pressing it re-sends the request that failed (`POST /v1/jobs`, or `POST /start` for the same `job_id`, which is kept) (§10.3) |
| Shared pilot budget used (`429` `pilot_pool_cap`, on any paid request; on a job page, the §2.6.1 job-page cap line) | The pilot budget has been used up, so Safe Cut can't take more pilot clips. Thank you for helping. Your timings and answers so far still count. | The $20 pool isn't refilled ([PILOTS.md](PILOTS.md) §5), so the button that sent it is disabled and never re-sends. On `/try`: if a `job_id` exists the UI sends `DELETE /v1/jobs/{id}`. On any job page (including `POST /start` from a failed-job page): no automatic `DELETE` (§2.6.1); the page's delete control stays |
| Too many requests (`429`, rate) | Too many tries in a short time. Wait a minute and try again. | |
| File too long (client check on metadata, or after upload `failure.reason` = `too_long`) | This clip is `{duration}` seconds long. The limit is 60 seconds. Trim it and try again. (`{duration}` = the clip's length rounded **up** to one decimal, e.g. 60.06 s → "60.1", so the number shown is always over the limit; §10.2). With no duration known (neither client metadata nor `failure.duration_s`): "This clip is longer than 60 seconds. Trim it and try again." | |
| File too big | This file is `{size}` MB. The limit is 150 MB. (`{size}` = bytes ÷ 1,048,576 rounded **up** to one decimal, e.g. 157,286,401 bytes → "150.1"; §10.2) | |
| Wrong type | Safe Cut takes MP4 or MOV video files. | |
| No rights tick | Tick the box to confirm you can use this clip. | |
| Upload interrupted (no progress for 30 s, or the `PUT` failed) | The upload stopped. Check your connection and try again; nothing was processed. | [Try again]: `DELETE` the job once, then `POST /v1/jobs` and a fresh upload (request 17) |
| Upload didn't arrive (`409` `upload_incomplete` on `POST /start`, request 17) | The upload didn't finish, so nothing was processed. Choose the clip again to upload it. | [Try another clip] (the UI sends `DELETE` for the job once); no [Try again] |
| A stage fails (`status: "failed"`, `failure.reason` = `internal`, or no `failure` given) | Something went wrong while `{row label, lowercase}`. Your clip hasn't been published anywhere. You can try again, or delete it now. | [Try again] [Delete now] |
| `prepare` finds the clip too long, too large or unreadable after upload (`failure.reason` = `too_long`, `too_large` or `bad_media`, stage `prepare`; *proposal*, §8 request 17) | `too_long`: This clip is `{duration}` seconds long. The limit is 60 seconds. Trim it and try again. (`{duration}` rounded **up** to one decimal, as above.) `too_large`: the §2.6 "This file is …" copy with `{size}` from `failure.size_bytes` ("This file is larger than 150 MB." if it's missing). `bad_media`: Safe Cut couldn't read this video file. Try exporting it again as MP4 or MOV. Your clip hasn't been published anywhere. | [Try another clip] [Delete now] (no [Try again]: the same file fails the same way) |
| A stage fails on the per-job cap (`failure.reason` = `job_cap`, PRE-A §10.3 `BudgetExceeded` against `SAFECUT_JOB_USD_CAP`) | This clip needs more processing than one job allows. Your clip hasn't been published anywhere. Try a shorter clip. | [Try another clip] [Delete now] (no [Try again]: re-running would fail the same way and bill again) |
| A stage fails on the service's daily cap (`failure.reason` = `daily_cap`, PRE-A §10.3 `BudgetExceeded` against `SAFECUT_DAILY_USD_CAP`) | Safe Cut has reached today's limit for the public demo. Your clip is fine; try it again tomorrow. Nothing has been published. | [Try again tomorrow] (hidden by the §2.6.1 expiry rule when `retry_at` is after `code_valid_until`, with the failed-job expiry string above instead of this copy; otherwise disabled until `retry_at`; then `POST /render` if the failed stage is `render`, `audit` or `receipt`, otherwise `POST /start`, as in §10.3) [Delete now] |
| A stage fails on the code's budget (`failure.reason` = `code_cap`) | This access code ran out of budget. Ask the person who gave it to you to add more, then try again. Your clip hasn't been published anywhere. | [Try again] (works once the code's cap is raised; stage routing as §10.3) [Delete now] |
| A queued retry found the code's window closed (`failure.reason` = `code_not_active`, PRE-A §9.2) | This access code has expired, so Safe Cut can't run more work on this clip. You can still download or delete it. | [Delete now] (no [Try again]: the window won't reopen) |
| Final check unavailable (`503` `auditor_unavailable`, on `POST /start` from `/try`; PRE-A §12: EgoBlur couldn't load) | Safe Cut's final check isn't available right now, so it can't start new clips. Try again later. | Start stays enabled; pressing it re-sends `POST /start`; no `DELETE` |
| Meta credits ran out (`503` `billing`, on `POST /start` from `/try`; PRE-A §10.3 `MetaBillingError`, vector R13) | Safe Cut can't start new clips right now. Try again later. | as the row above: Start stays enabled; no `DELETE` |
| A stage fails on the shared pilot budget (`failure.reason` = `pilot_pool_cap`) | The pilot budget has been used up, so this clip couldn't finish. Thank you for helping. Your clip hasn't been published anywhere. | [Delete now] |
| A stage fails for any other deterministic reason (`failure.reason` = `config`, `bad_request`, `refusal` or `incomplete`; PRE-A §10.3) | Safe Cut couldn't process this clip. Your clip hasn't been published anywhere. We've logged the problem. | [Try another clip] [Delete now] (no [Try again]) |
| Job cap would be exceeded (`422` `job_cap`, on `POST /start` from `/try`; on a job page, the §2.6.1 job-page cap line; PRE-A §10.3) | This clip would cost more than the per-clip limit to process. Try a shorter clip. | the UI sends `DELETE /v1/jobs/{id}` (this clip can never start) and returns to step B to choose another file |
| Meta's service is busy (`status: "retry_later"`) | Meta's service is busy right now. Safe Cut will try once more in a few minutes on its own; you can leave this page and come back with your review link. Nothing has been published. | [Copy link] [Cancel and delete] |
| The one automatic retry also failed (`failure.reason` = `upstream`) | Meta's service didn't recover in time. Nothing was published. You can try again. | [Try again] (stage routing as §10.3) [Delete now] |
| Cancel and delete (confirm dialog) | Delete this clip and stop processing? This can't be undone. · [Delete] [Keep going] | |
| After delete | Deleted. Nothing from this clip is kept. | link to `/try` |
| Upload never finished (`status: "created"`, §10.4) | This clip hasn't finished uploading. Upload it again to start. | [Upload again] → `/try` |
| Rights tick label | I filmed this clip or have the right to use it. | |
| "What happens to your clip" heading | What happens to your clip | |
| Data bullet 1 | It's sent to Meta's Model API in Standard mode, never Contributor mode (Contributor mode can use inputs to improve Meta's models). Wireframes show it shortened; the full sentence is the copy. Never claim "doesn't train on it" or "storage off": PRE-A `docs/API-NOTES.md` §7 found no Standard-mode retention terms, and §10.6 says `store: false` on `sam-3.1` is unverified | |
| Data bullet 2 | Everything is deleted automatically after 24 hours, or sooner if you choose. | |
| Data bullet 3 | Up to 60 seconds and 150 MB. MP4 or MOV. | |
| More than one file dropped or chosen | Drop one clip at a time. | keep the drop zone empty |
| Render already running (`409` on render) | (no message: the page polls and shows the render stages) | |

#### 2.6.1 Two refusal patterns

Every refusal of the access code uses one of these, so each is defined once:
- **Step-B refusal** (`/try`, after Continue succeeded): the row's copy above the drop zone; Start disabled; a [Use a different code] link back to step A; and if a `job_id` already exists, the UI sends `DELETE /v1/jobs/{id}` once (always allowed, request 20), so no half-made job waits for the 24 h cleanup.
- **Job-page refusal** (a `401` on `POST /start`, `POST /render` or `POST /audit` of an existing job): the row's copy in the page's action area (the §3.5 bar row 0 on the review page; next to the button on a failed-job page); the button that sent the request is disabled until the page is reloaded; the page's own delete control stays ([Delete everything now] on the review page, §3.5 row 0; [Delete now] on a failed-job page). **The UI never sends `DELETE` on its own from a job page**: a job page holds the creator's work (a review, or a downloadable render), so only the creator deletes it.
- **Expiry rule** (one rule for every retry or re-run control, PRE-A §9.2): when the earliest time the control could work (`retry_at`) is after the job's `code_valid_until` (request 20; `null` or absent = no limit), the control is **hidden**, not disabled, and the copy is replaced by these complete strings: **failed-job page** "Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again. Nothing has been published." (with [Delete now], and [Download this version] when `has_render`); **job-page cap line** (review page, §3.5 row 0) "Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again."; **§3.5 row 2** shows no "Available after …" line (the §5.3 banner's expiry sentence already says it); **§5.3 banner** as written there. In §10.5 the refusal is then `refusal = {code: "daily_cap", until: null}` (until reload), never `retry_at`. This covers [Try again tomorrow] (§2.6, §10.3), [Run the audit again] for `daily_cap` (§3.5 rows 0 and 2, §5.3), row 0's Approve & render (hidden, not disabled) and the job-page `daily_cap` cap line.
- **Download or delete.** Copy that says "You can still download or delete it." says it only when `has_render` is true, and the page then shows [Download this version] (`result.video_url`) next to its delete control; otherwise it says "You can still delete it."
- **The page decides, not the request.** The §2.6 rows' `/try` actions (Start, step B, deleting the created job) apply **only on `/try`**. The same request sent from a job page (for example `POST /start` from a failed-job page's [Try again] or [Try again tomorrow], or `POST /render` / `POST /audit` from the review page) gets the **job-page cap line** next to the button that sent it, never a `DELETE`: `code_cap` "This access code ran out of budget." (button stays enabled, it works once the cap is raised); `pilot_pool_cap` "The pilot budget ran out." (disabled); `daily_cap` the §2.6 daily-limit job-page variant "Safe Cut has reached today's limit for the public demo. Try again tomorrow." (disabled until `retry_at`, or, under the expiry rule above, hidden with the job-page cap line expiry string); `job_cap` "This clip needs more processing than one job allows." (disabled); `rate_limited` as in §10.3.

### 2.7 States

Loading (button shows "Checking…" while the code is validated) · Empty (no file yet: Start disabled) · Error (above) · Uploading (progress bar with percent, Cancel available) · Processing (stage list) · Meta busy (`status: "retry_later"`: the §2.6 "Meta's service is busy right now. …" line above the stage list, polling every 30 s, §10.3) · Demo mode (§6: the banner shows, and the progress replays at real speed from saved timings).

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
│                                                          [ Delete everything now ]   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Each chip's overflow menu (`⋯`, not drawn above) holds: "Remove this person from the video" (person and child items, except audit-added ones, §0) and "Jump to first appearance".

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
│ [ Delete everything now ]        │
└──────────────────────────────────┘
```

The video stays sticky at the top while the chip list scrolls. The tab that opens first is **Needs you** if it has items, otherwise **Hidden**.

### 3.3 The chip

| Part | Content | Source |
|---|---|---|
| Thumbnail (64×64, 96×96 on mobile) | A crop around the item at its first evidence frame, about twice the item's box, with the item itself drawn **covered** if hidden or needs-you, and **clear** if kept. The surroundings stay visible so the creator recognises the moment | `decisions.items[].evidence_frames[0]` → SoM keyframe image; box from `tracks.json` `boxes[frame]` for the item's **primary track** (its first `face:*` track in `track_ids` order if it has one, otherwise its first track: the same track the label and the drawer ring use, §0). If the primary track has no box on that frame, use the first other track of the item that does. If no track has a box there, show the neutral placeholder tile (kind icon on a grey square, no crop) and never crop around a guessed box. The box is in prepared-frame pixels; map it into the keyframe image with the §4.3 keyframe geometry (shift down by `bar_h`) before cropping |
| Label | The item's display label, e.g. "Face 7", "Plate 1" (§0 Item label) | primary track ID in `track_ids` |
| Kind | Person / Child / Number plate / Screen / Document / Other item, with its icon | `kind` |
| Badges | 🔒 **Always hidden** if `locked`; **NEW** if one of the item's tracks has a `reentry_of` that points to a track belonging to a **different** item (after a merge the earlier track is in the same item, so the badge goes away and never shows on the merge target); **Changed by you** if `decided_by = creator` | `locked`, `tracks[].reentry_of`, `decided_by` |
| Reason | One or two lines, first letter capitalised, no trailing full stop added | `reason` |
| Time range | `m:ss–m:ss` from the first to the last frame of the item's tracks, including tracks merged into it | `tracks.json` `first`/`last` over `track_ids` → `first / job.fps` to `last / job.fps` (prepared clock, §0) |
| Buttons | Hidden chip: [Why?] [Keep clear] · Kept chip: [Why?] [Hide] · Needs-you chip: [Why?] [Hide] [Keep clear] · Locked chip: [Why?] and the text "Always hidden" (no toggle) · NEW chip (hidden, re-acquired track) whose `reentry_of` track belongs to a **kept participant** item P: the line "Might be {P's label}: the tracker lost them and found them again." and [Why?] [Same as {P's label}…] [Keep clear], with "Same as …" first because merging is the usual fix · NEW chip whose `reentry_of` track belongs to any other item (a bystander, a child, an unsure person): the line "The tracker lost this person and found them again. They stay hidden." and [Why?] [Keep clear], **no merge button** | `decision`, `locked`, `tracks[].reentry_of` |
| Overflow `⋯` | Remove this person from the video (person/child items, not audit-added ones: those offer only Jump to first appearance, §0); Jump to first appearance | |

Clicking the chip body (not a button) **selects** it: the video seeks to its first evidence frame (or the item's first frame when `evidence_frames` is empty, e.g. a static item) and pauses, the overlay outlines that item, and the timeline highlights its bars.

**Unfixed audit spots.** PRE-A owns the audit contract (`docs/API-NOTES.md` §10.3 and §12, `origin/pre-a-research` @ `565eee3`): `audit.json` `unresolved` counts every frame or spot that isn't verified clean, and `blocked_reason` (`null` \| `"unresolved_leaks"` \| `"audit_failed"` \| `"over_budget"`) says why, with the invariant **`blocked_reason != null` ⇔ `unresolved > 0`**. Two kinds of unresolved entry are shown differently:
- **An unfixed spot** (a *spot*: WP4 groups the `leaks[]` rows marked `unresolved: true` over the **audited** frames: consecutive audited frames, at most `audit.sample_step` apart (`sample_step` = `round(job.fps)`, the red-team's step for its 1 fps sampling, PRE-A `docs/API-NOTES.md` §12; EgoBlur scans every frame, so its leak rows fall inside that step and group the same way), whose boxes overlap with IoU ≥ 0.3 form one spot. WP4 returns each in `audit.spots[]` as `{spot_id, first, last, boxes: {frame: box}, covered_by: item_id | null}`; *proposal*, §8 request 18). **One spot = one chip**, so a face the patch loop couldn't cover across 12 frames is one chip, not 12: a **Needs-you chip** `Unfixed spot U{n}` (numbered by `first`) showing the spot's time range, a thumbnail cropped around its box on `first`, the reason "The final check found this and couldn't cover it automatically", and one action, **[Cover it]** (reducer `COVER_SPOT`, §10.5), which sends a `cover_spot` edit (`{type: "cover_spot", spot_id, edit_id}`) that adds **one** hidden item carrying that `spot_id`. The item has **one static box, the union of the spot's `boxes`** (an interpolated box could miss a face moving between audited frames), and spans `first − half − temporal.extend` … `last + half + temporal.extend`, clamped to `[0, frames − 1]`, with `half = ceil(sample_step / 2)` and no back-fill (PRE-A `docs/API-NOTES.md` §12), so the unsampled frames around the leak are covered too. It's a `decisions.items[]` entry with `origin: "audit_patch"` and `audit_label` `A<n>`, `track_ids: []`, `decision: "hide"` and **`locked: true`** (PRE-A §12: a found leak isn't un-hidden in review), so its chip shows only [Why?] and 🔒 Always hidden, with no toggle. Its overlay comes from the plan like any hidden item; its time range, timeline bar and transcript window use `items[].first`/`last` (it has no tracks), and its thumbnail (the Thumbnail row above) uses `items[].box` on its one evidence frame (the finding frame) when that frame is a keyframe, otherwise the neutral tile. A U chip's thumbnail likewise uses the spot's box on `first` when that frame is a keyframe, otherwise the neutral tile. When the edit is accepted the server sets the spot's `covered_by` to that item. A spot is **uncovered** while `covered_by` is `null`, which the UI reads from the job response, so a reload never brings a covered spot back. The overlay rings the spot's box on each of its frames. There's no Keep clear: a leak is by definition something that should be hidden. Counting matches the fixed-leak rule (§5.6, distinct items): `{unfixed_spots}` counts spots, never frames. **While the job is `needs_you`** the U chips are shown read-only, without [Cover it] (§10.5 `readOnly`). [Run the audit again] re-runs the same audit pass as a first audit on the existing render (request 11, §5.3: EgoBlur on every output frame, and Muse Spark's red-team on sampled frames, DESIGN §2.8), with request 11's outcomes: `done`; `done` with `blocked_reason: "unresolved_leaks"`; or `needs_you` again. It doesn't promise to fix a U spot, because a spot is one the patch loop already couldn't cover, and it usually stays unfixed; when the job is `done` with `unresolved_leaks`, the creator covers it with [Cover it] via [Review them] (§5.3).
- **Frames the audit couldn't check** (no box, so no chip). The banner and the read-only rule are chosen by **job status**, never by `blocked_reason` alone: only while the job is `needs_you` (PRE-A §10.3) is the panel **read-only** (§10.5 `readOnly`), with the banner above the columns carrying the §5.3 message for `blocked_reason` and `audit_budget_cause`. The actions live in the bottom bar (§3.5, the `needs_you` row): [Run the audit again], [Download this version], [Delete everything now] and, for `job_cap` only, [Try another clip], chosen by `audit_budget_cause`. Edits are impossible while the job is `needs_you`.
Mock: `result-unresolved-review.json`.

### 3.4 Creator actions (what each tap does)

All edits go through `POST /v1/jobs/{id}/review` (WP3's `apply_review`). The UI updates **optimistically**: the chip moves and the overlay changes at once; if the request fails, it moves back with an error toast.

| Action | Result | Copy (toast, polite live region) |
|---|---|---|
| Keep clear (on a hidden or needs-you item) | `decision → keep`, `decided_by → creator`; chip moves to Kept clear; overlay stops covering it | "{label} will be kept clear. [Undo]" (e.g. "Plate 1 will be kept clear.") |
| Hide (on a kept or needs-you item) | `decision → hide`; chip moves to Hidden; overlay covers it, including any tracks merged into it | "{label} will be hidden. [Undo]" (e.g. "Face 2 will be hidden.") |
| Keep clear on an **object** (plate, screen, document or other item, §0 Item kind) | Same, plus a one-line confirm in place. Screens and documents: "Only keep this clear if nothing on it is personal." Plates and other items: "Only keep this clear if nothing on it identifies anyone." [Keep clear] [Cancel] | |
| Keep clear on a person you removed | Same as Keep clear; the server's `keep` edit sets `removed_by_creator` to `false` (§8 request 9), and the reducer clears `removed` optimistically to match. [Undo] restores both the hide and the removal | "{label} will be kept clear. They're no longer removed. [Undo]" |
| Toggle a locked child | Not possible: no toggle is rendered. The "Always hidden" text has a help link that opens the drawer at the explanation | — |
| Same as {label}… (re-entry merge; offered only on a NEW chip whose earlier track is a kept participant's, §3.3) | A small menu lists the items that are **part of the story** (kept participants), each with its thumbnail, the suggested one first: "Same person as Face 2 (the guest)". Choosing one merges the new item into it: the NEW chip leaves the columns, its tracks show under the target (time range, overlay, Details), and the header counts drop by one | "{source label} merged into {target label}. They'll be kept clear like {target label}. [Undo]" (e.g. "Face 9 merged into Face 2. They'll be kept clear like Face 2.") |
| Remove this person from the video | Confirm dialog (below). The item becomes hidden with the **Whole person covered** style and is marked "removed at your request" on the receipt | "{label} will be fully covered wherever they appear. [Undo]" |
| Undo | Reverts the edit on top of the undo stack; pressing Undo (or `Ctrl+Z`) again steps back one more (§10.5) | "Undone." |

**Remove-person dialog:** title "Remove this person?" · body "They'll be fully covered, not just their face, every time they appear. Your privacy receipt will record that you removed them." · [Remove] [Cancel]. (Cutting their segments out of the video is not in v1; don't offer it.)

**Merge rules the UI enforces** (from [DESIGN.md](DESIGN.md) §2.5): merge targets are only kept participants; children are never merge targets or merge sources; a re-acquired bystander is never offered a merge (the H1B van case in [STORYBOARD.md](STORYBOARD.md) 6.1 stays hidden); the merge never happens automatically.

### 3.5 Approve & render

**Which row applies.** Rows are checked in this order, and the first match wins. The bar is always chosen from the job **status** (and `has_render`, `audit_budget_cause`, `audit.spots[]`), never from `blocked_reason` alone:
0. The last paid request from this page (`POST /render` or `POST /audit`) was refused with a **blocking** answer: a `401` (§2.6.1 job-page refusal) or a `429` `pilot_pool_cap`, `daily_cap` or `rate_limited` (§2.6.1 job-page cap line). It holds until the page is reloaded (for `daily_cap`, until `retry_at`, or until reload under the §2.6.1 expiry rule; for `rate_limited`, until `Retry-After`, or 60 s without one) → **Refused**. (A job cap reached during a render or audit shows up as `failure.reason: "job_cap"` or `audit_budget_cause: "job_cap"`, never as an HTTP refusal of `/render` or `/audit`; `422 job_cap` exists only on `POST /start`, PRE-A §10.3.) A `429 code_cap` is **not** blocking and never selects row 0: the bar comes from rules 1–8 as usual, and the job-page cap line "This access code ran out of budget." shows as a note above the bar until the next request from that button succeeds (§10.5 `capNote`; not in `needs_you` with `audit_budget_cause: "code_cap"`, where the banner and row 2 already say it).
1. `status` is `rendering` → **Rendering**.
2. `status` is `needs_you` → **Audit couldn't check some frames**.
3. An edit is pending → **An edit is saving**.
4. `status` is `review` (or `done` at `?view=review`) and at least one U spot is uncovered (`covered_by: null`) → **Unfixed spots not yet covered**. This beats every row below, so Approve & render is never enabled while a spot is visible.
5. `status` is `done` (opened at `?view=review`; "no edits since the render" means exactly this, because request 5 moves the job to `review` on its first edit) → **Nothing changed since the render**.
6. `status` is `review` and `has_render` is true → **Edited after rendering**.
7. Some items need you → **Items need you**.
8. Otherwise → **Nothing needs you**.

**Delete is always there.** Whatever the row, the bar's right end always shows **[Delete everything now]** → `DELETE /v1/jobs/{id}`, in every status including `rendering`. Its confirm is the §5.3 "Delete confirm" when a render exists (`has_render: true` and the status isn't `rendering`), otherwise the §2.6 "Cancel and delete" dialog (the same choice applies to [Delete now] on a failed-job page, where a failed `render`, `audit` or `receipt` stage may leave a render); after either, the page shows the §2.6 "After delete" text "Deleted. Nothing from this clip is kept." with a link to `/try` ([PILOTS.md](PILOTS.md) §4 promises immediate deletion from every state; WP5 accepts `DELETE` in every state, request 5). The rows below list only the main action; the §3.1–3.2 wireframes show the delete control at the bar's right end.

| # | Situation | Bottom bar text | Button |
|---|---|---|---|
| 0 | Refused (§2.6.1) | for a `401`, the §2.6 "Code refused on a job page" copy; for a `429`, the §2.6.1 job-page cap line | Buttons by status. **`review`** (or `done` at `?view=review`): **Approve & render** shown disabled (hidden for `daily_cap` under the §2.6.1 expiry rule); [Download this version] when `has_render` (§2.6.1); [Delete everything now] as always. **`needs_you`**: row 2's set with [Run the audit again] disabled (hidden for `daily_cap` under the §2.6.1 expiry rule), and [Download this version] and [Delete everything now] unchanged (no Approve & render) |
| 1 | Rendering | (the bar becomes the progress list from §2.5, `render` → `receipt`) | — |
| 2 | Audit couldn't check some frames (job **status** `needs_you`) | the §5.3 message, then "This version hasn't been fully checked." For `audit_budget_cause: "job_cap"`: "This clip used up its processing budget. You can download this version, or try a shorter clip." | Chips are read-only (§10.5 `readOnly`): no edits and no Approve & render. Exactly these actions, each with its own rule:<br>• **[Run the audit again]** → `POST /v1/jobs/{id}/audit` (§10.3). Hidden for `job_cap`. For `daily_cap`, disabled until `retry_at`, with "Available after `{retry_at}`." (under the §2.6.1 expiry rule: hidden, and no "Available after" line). For `code_cap`, shown with the line "This access code ran out of budget." and kept enabled, so it works as soon as the cap is raised (a `429 code_cap` answer changes nothing: the line is already shown and `capNote` isn't set, §10.5). For `pilot_pool_cap`, shown with the line "The pilot budget ran out." and **disabled**, because the $20 pool isn't refilled ([PILOTS.md](PILOTS.md) §5). What it does: it re-runs the audit on the existing render, scanning the same frames a first audit does (§3.3); the creator's decisions aren't rendered again (PRE-A API-NOTES §10.3). Like a first audit, it runs WP4's auto-patch loop, so only a segment it patches is rendered again (stages `audit` ↔ `render`, ARCHITECTURE §2, WP4 step 2), then the receipt stage; outcomes as in request 11.<br>• **[Download this version]** → `result.video_url` from `GET /v1/jobs/{id}` (§8): always shown.<br>• **[Delete everything now]** → `DELETE /v1/jobs/{id}` with the §5.3 confirm: always shown (PILOTS §4 promises immediate deletion from every state; WP5 accepts `DELETE` in every state, request 5).<br>• **[Try another clip]** → `/try`: for `job_cap` only. |
| 3 | An edit is saving | Saving your changes… | disabled |
| 4 | `u` unfixed spots not yet covered | `u` unfixed spot(s) are visible in the video. Cover them before rendering. | **Approve & render** disabled until every spot is covered (an unfixed spot is *not* hidden, so "they stay hidden" would be false) |
| 5 | Nothing changed since the render (`status: "done"` at `?view=review`, no uncovered spot) | Nothing has changed since the last render. | **Approve & render** disabled, plus a [Back to result] link to `/jobs/[id]/result` (re-rendering an unchanged clip would only spend budget) |
| 6 | Edited after rendering (`status: "review"` with `has_render: true`, e.g. after an edit at `?view=review`, §10.4) | You changed something after rendering. Render again to update the video and receipt. | **Approve & render** |
| 7 | `k` items need you (none of them an unfixed spot) | `k` item(s) still need you. If you render now, they stay hidden. | **Approve & render** (still enabled) |
| 8 | Nothing needs you | Everything's decided. | **Approve & render** |

Pressing it: `POST /v1/jobs/{id}/render`, then the stage rows `Applying your choices` → `Checking the result` → `Writing your privacy receipt`, then the page moves to `/jobs/[id]/result`. Chips are read-only during the render (a calm note: "Changes are paused while we render.").

### 3.6 The overlay

- A `<canvas>` sized to the video's displayed box, drawn on each `requestVideoFrameCallback` (rVFC). Per the WICG spec, `metadata.mediaTime` is the presentation timestamp of the frame being shown, on the `currentTime` timeline, which is the prepared clock. Map it to a prepared frame with PRE-A `docs/API-NOTES.md` §5b's formula: **`i = clamp(floor(mediaTime × job.fps + 0.25), 0, job.frames − 1)`**. This supersedes [WP6](work-packages/WP6.md) step 4's "via `job.times`", which predates PRE-A §5b (request 12 in §8). The prepared clip is constant frame rate, so this needs no search and doesn't use `job.times`; the quarter-frame term switches to the next frame three quarters of the way through a frame, which absorbs timestamp rounding (PRE-A vector T5). **Checks before drawing anything** (any failure → the unexpected-error page, §7, instead of a misaligned overlay): `job.fps` is an integer from 1 to 30; `job.frames ≥ 1`; `job.times` has exactly `job.frames` entries, all finite, and is **non-decreasing**. Repeated values are valid (a variable-frame-rate source repeats a frame where it had a gap), and `times[0]` may be slightly above 0 (PRE-A T6a, T6c), so the UI must **not** require strictly increasing values or `times[0] = 0`. Test cases: §10.6.
- Browser support (MDN browser-compat-data, 2026-10-23): rVFC is in Chrome 83+, Safari 15.4+ and Firefox 132+. On a browser without it, fall back to `requestAnimationFrame` reading `video.currentTime` through **the same formula** (`floor(currentTime × job.fps + 0.25)`, clamped). `currentTime` can lag the displayed frame, so say so next to the toggle: "Preview may lag by a frame in this browser. The final render isn't affected." Never fall back silently.
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
| `Enter` on a chip's body (when the chip itself is focused by `↑`/`↓`) | Opens the Why? drawer; on an Unfixed spot U chip, which has no drawer (§3.3), it moves the player to the spot's `first` frame |
| `H` | Hide the focused item |
| `C` | Keep the focused item clear |
| `Z` / `Ctrl+Z` | Undo the last edit: `UNDO(the last edit in undo)`, §10.5 (pressed again, it undoes the one before) |
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
| Header counts | `decisions.items[].decision` counts after local edits, counting each item once (an item merged into another isn't counted); the **Needs you** count, its tab and its empty state also include uncovered U chips (`audit.spots[]` with `covered_by: null`), because each needs the creator. "Nothing needs you." shows only when both are zero. §3.5 row 7's "`k` items" still counts items only (row 4 handles U chips) |
| Video | `job.json` `prepared` (raw prepared clip), its `fps`, `frames`, `width`, `height`; `times` only for the §3.6 checks and the receipt's source-time column |
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
                                   │ 0:03 Voice S2 "Hi, I'm Amina, and…"          │
                                   │ 0:07 Voice S1 "So what brings you?"          │
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

**Keyframe.** The SoM keyframe image for the selected evidence frame, with a **ring** (3 px, white with a dark edge) drawn by the UI around the item's box on that frame. Arrows step through `evidence_frames`; the dot row shows how many there are. Caption: "This is the frame Muse Spark was shown. The labels are the objects SAM 3.1 tracked." followed by "On the keyframe: {primary track ID}" and, for each other track of the item (including merged ones), "also {track ID}" (e.g. "On the keyframe: face:2 · also person:1"). If no keyframe exists for the item, show the plan box on the nearest prepared frame with a caption by origin: an item added by the audit, "Added by the audit after rendering. There's no keyframe for it."; a static item (`origin: "static"`), "Muse Spark spotted this, but SAM 3.1 couldn't follow it, so there's no keyframe for it."

**Keyframe geometry.** The keyframe image is the Set-of-Mark image **exactly as sent** to Muse Spark: the prepared frame at its own resolution (never resized), with a black frame-number bar `bar_h` pixels tall **above** it, so the image is `job.width × (job.height + bar_h)` (PRE-A `docs/API-NOTES.md` §5 and §10.6; `bar_h = 40`). Track boxes are in prepared-frame pixels, so to draw the ring (or crop the thumbnail) on the image: `x_img = x`, `y_img = y + bar_h`, and then on screen multiply both by `s = displayed image width / image natural width`. The UI reads the geometry from `keyframe_geometry: {bar_h, frame_width, frame_height, image_width, image_height}` (*proposal*, §8 request 13). The ring is drawn only when **all** of these hold, checked after the image loads: `frame_width = job.width`, `frame_height = job.height`, `image_width = frame_width`, `image_height = frame_height + bar_h`, and the loaded image's `naturalWidth = image_width` and `naturalHeight = image_height`. If any one fails, the drawer shows the image without a ring plus "The keyframe's size doesn't match this clip, so the outline is hidden.", never a misplaced ring. Test case: `job` 1280×720, `bar_h` 40, image 1280×760 shown 640 px wide (s = 0.5), box `[600, 200, 660, 250]` → ring at `[300, 120, 330, 145]` on screen.

**"Why it's hidden / kept clear / needs you".** The `reason`, then one fixed sentence by case (for an audit-added item only the fixed sentence, so the audit sentence isn't shown twice):

| Case | Fixed sentence |
|---|---|
| Hidden, bystander | People who aren't part of the story are hidden by default. |
| Hidden, child (`locked`) | Children are always hidden. You can't change this, because Safe Cut can't check a parent's consent. |
| Hidden, new ID after re-entry | The tracker lost this person and found them again. Anyone found again starts hidden until you say who they are. |
| Hidden, other item from the second look (`kind = other`) | Things Safe Cut found on a second look stay hidden unless you keep them clear. |
| Hidden, object (plate, screen or document) | Number plates, private screens and documents are hidden unless you decide otherwise. |
| Kept clear, participant | All three checks agreed this person is part of the story, on at least two keyframes. |
| Kept clear by you (`decided_by = creator`, `decision = keep`) | You chose to keep this clear. |
| Hidden by you (`decided_by = creator`, `decision = hide`, not removed) | You chose to hide this. |
| Needs you, harmless object (plate, screen or document: all three checks said `sensitive: false`, PRE-A TEST-VECTORS B1; also `other`) | Muse Spark read this as nothing personal, but {kind word, plural} are only kept clear when you confirm. (e.g. "…but number plates are only kept clear when you confirm.") |
| Needs you, all three said part of the story but on fewer than 2 keyframes (`role: unsure`, votes 3/3 `participant`; PRE-A role-pass.md rule 3) | All three checks said part of the story, but on only one keyframe, so Safe Cut wants you to confirm. It stays hidden unless you keep it clear. |
| Static area (`origin: "static"`: a miss-loop item SAM 3.1 couldn't track, no votes, no keyframe label; PRE-A §12) | Muse Spark spotted something here that SAM 3.1 couldn't follow, so Safe Cut covered the area. Keep it clear if it's harmless. |
| Needs you, `hold: "no_roles"` (`decisions.items[].hold`, PRE-A §12) | Safe Cut's checks couldn't run on this, so it stays hidden until you decide. |
| Needs you, `hold: "no_scene"` | The scene check didn't run, so we didn't keep anyone clear automatically. |
| Needs you, `hold: "no_speech"` | The speech check didn't work for this clip, so we didn't keep anyone clear automatically. |
| Needs you, `hold: "unmatched_child"` | A child may be in this video and we couldn't tell who, so we didn't keep this person clear automatically. Keep them clear if they're part of the story. |
| Needs you, `hold: "no_speech_link"` (3/3 `participant`, but nothing links them to speech or an introduction while a transcript exists; PRE-A vectors P8, P9c) | All three checks said part of the story, but Safe Cut couldn't link them to anyone speaking or introduced, so it's your call. |
| Needs you, votes disagreed (`role: unsure`) or any other reason | The checks didn't all agree, so Safe Cut couldn't decide on its own. It stays hidden unless you keep it clear. |
| Removed at your request (only while `removed` and `decision = hide`) | You asked to remove this person. They're fully covered everywhere they appear. |
| Added by the audit | The final check found this after rendering and covered it. |

**"What Muse Spark said (n checks)".** One mark per vote in `votes`, each with its role word (Part of the story / Not part of the story / Child / Not sure); ✓ when it matches the **majority vote** (the role at least 2 of the 3 checks gave), ✕ otherwise, and no marks when all three differ. Marks never compare against the final role, which can be `unsure` even when all three votes agree (the one-keyframe case above). Then Muse Spark's `evidence` text in quotes, with its frame references rewritten to clip times (below). The quoted `evidence` is always the **role pass's** text; the escalation's own words live in separate fields, so neither overwrites the other. `escalated` is `true` only when the escalation call ran and returned a valid ruling (PRE-A `docs/prompts/escalation.md` rule 4); a failed call, invalid cited frames (rule 3) or a call skipped for budget leave `escalated: false` and `suggested_role: null`, and then the drawer shows **nothing** about escalation (it never claims a look that didn't happen). If `escalated` and the track's `role` is `child` (PRE-A escalation.md rule 2: a `child` ruling locks the item hidden, so its row is Hidden, child), the escalation text is only "A longer, closer look found they may be under 18, so Safe Cut keeps them hidden." followed by `escalation_evidence` in quotes, in place of the sentences below. Otherwise, if `escalated`, the opening sentence depends on the votes: when all three votes are `participant` (the one-keyframe case, PRE-A role-pass.md rule 3), "Because it was seen on only one keyframe, Muse Spark took a longer, closer look once."; otherwise (the votes differ) "The checks disagreed, so Muse Spark took a longer, closer look once." and then, from the track's `suggested_role`: when it isn't null, "A longer, closer look suggests: {role word}. You decide." followed by `escalation_evidence` in quotes (frame references rewritten the same way; its `escalation_frames` become extra steps in the keyframe arrows); when it's null (the ruling was `unsure`), "A longer, closer look couldn't settle it." A suggestion never changes the item's column or decision: only the creator's tap does (a `child` ruling isn't a suggestion; see above). For objects (screens, documents, phones, badges **and plates**, which PRE-A `docs/prompts/role-pass.md` has Muse Spark judge as objects: `sensitive` + `content`): "Muse Spark read it as: {content}" and "Personal: yes/no" from `objects[].sensitive`, in place of the vote marks. For a plate, add "Number plates are hidden by default. Only you can keep one clear." A plate isn't locked: the creator can keep it clear, after the same one-line confirm as every object (§3.4).

**Other items (`kind = other`).** These come from the miss loop: Muse Spark named something unboxed, and SAM 3.1 tracked it under a new concept such as `envelope` (PRE-A `docs/prompts/miss-loop.md` step 5: new tracks are hidden by default). PRE-A's role pass judges every label that isn't `face:`/`person:` as an object (`role-pass.md`, `miss-loop.md`), so an `other` item has `roles.objects[]` rulings like any object, and the drawer shows them in the votes section the same way. It also shows "Found when Muse Spark looked again for anything missed: {what}", with `what` from the `roles.missed[]` entry that created the track (located by `missed[].track_ids`, *proposal*, §8 request 15), then the fixed sentence from the table above. If no `missed` entry names the track, the line is left out. Keep clear still asks the object confirm (§3.4), and the harmless-object row applies to `other` like any object.

**Frame references in Muse Spark's text.** The role pass cites frames only by the number burned into each keyframe (PRE-A `docs/prompts/role-pass.md`), which is a prepared-frame index, so the drawer rewrites every reference before showing the text. The rewrite works sentence by sentence (a sentence ends at `.`, `;` or the end of the string) and is case-insensitive. `N` below means a run of digits; each converted `N` becomes `m:ss` on §0's prepared clock, and a range `N–N` becomes `m:ss–m:ss` (an en dash, whether the source used `-` or `–`).
1. **"frame"/"frames" followed by numbers.** `\bframes?\s+` followed by a **list** of numbers or ranges, separated by `,`, `and` or `, and` (regex for one element: `\d+(?:\s*[–-]\s*\d+)?`). The word "frame(s)" is dropped and every element is converted: "frames 90 and 120" → "0:03 and 0:04"; "frames 90, 120 and 150" → "0:03, 0:04 and 0:05"; "frames 120–600" → "0:04–0:20".
2. **Burned-in labels.** `\bF\s?0*(\d+)\b` → `m:ss` ("F 000090" and "F90" → "0:03").
3. **Bare ranges after a reference.** In a sentence where rule 1 or 2 converted something, a later bare range `\b(\d+)\s*[–-]\s*(\d+)\b` is also converted, if both numbers are **≥ 10** and `< job.frames` (numbers already turned into `m:ss` by rules 1–2 aren't bare, so they're never converted twice). That covers ARCHITECTURE §3.5's own example: "introduced at frame 90, speaks to camera 120–600" → "introduced at 0:03, speaks to camera 0:04–0:20". The ≥ 10 floor keeps counts like "2–3 people" as written.

**Limits:**
- A **bare single number** is never converted, even after "at", "from" or "to" ("speaks at 120" stays as written), because it can't be told apart from a count.
- A number that isn't a valid frame (`≥ job.frames`) is left as written, never turned into an invented time.
- "Face 7" and other words starting with F don't match rule 2, because it needs a digit right after `F` and an optional space.

The role-pass prompt asks Muse Spark to cite frames as "F nnnnnn" (PRE-A `docs/prompts/role-pass.md`), so rule 2 is the common case. The unedited text stays in the Details row ("Muse Spark's words: …"). Test cases: §10.6.

**Precedence:** the first row that matches wins, in this order: Added by the audit → Removed at your request → Hidden, child → Kept clear by you → Hidden by you → Static area (below Hidden, child, so a locked child static item never says "keep it clear") → Hidden, other item from the second look → Hidden, new ID after re-entry → Hidden, object → Hidden, bystander → Kept clear, participant → Needs you, harmless object → `hold: "no_roles"` → `hold: "no_scene"` → `hold: "no_speech"` → `hold: "unmatched_child"` → `hold: "no_speech_link"` → Needs you, all three said part of the story but on fewer than 2 keyframes → Needs you, votes disagreed or any other reason. Every row of the table appears once in this list. A removed person the creator later keeps clear is no longer `removed` (§3.4), so they get "Kept clear by you", never the Removed sentence.

There's no "Hidden, votes disagreed" case: a track whose votes disagree becomes `role: unsure` and the item goes to **Needs you**, never to Hidden on its own ([DESIGN.md](DESIGN.md) §2.3; PRE-A `docs/prompts/escalation.md` rules 3–4).

**"What was said while {label} was on screen".** Transcript turns that overlap the item's on-screen time (§4.6), max 4, each as `m:ss Voice S# "text"` (speakers carry the prefix "Voice", e.g. "Voice S1", "Voice U1", because the speech fallback's uncertain voices `U1`, `U2`, … would otherwise collide with the `U{n}` unfixed-spot chips, PRE-A §4.2), where `m:ss` is `floor(turn.start)` on the prepared clock (turn times are prepared-clock seconds, PRE-A §5b step 6). If the item's primary track has `matches_participant = k` (an index into `scene.participants`, set by the role pass, PRE-A `docs/prompts/role-pass.md`) and `scene.participants[k].speaker` is set, mark that speaker's lines with "said by {label}". Otherwise end with "No speech is linked to {label}." If there's no transcript: "No speech was transcribed. Safe Cut's speech check covers 25 languages, not including Swahili." (PRE-A §4.2: speech in an unsupported language gives an empty, successful transcript) If `job.audio` is `false`, the whole section is replaced by "This clip has no sound."

**Limited speech check.** When `transcript.degraded` is `true` (PRE-A `docs/prompts/speech-fallback.md`: Voice Transcribe failed or the audio was dropped) or `transcript.source_kind` is `"fallback"` (*proposal*, §8 request 16: the server says whether the primary ASR or the fallback produced the turns). The UI never compares `transcript.source` with a model ID, because model IDs come from env and can change (AGENTS.md rule 8):
- the heading becomes "What was probably said (speech check was limited)";
- an empty `turns` list shows "Speech couldn't be checked reliably for this clip.", never the "No speech was transcribed" line;
- fallback turn times are untrusted (PRE-A: ±1.5 s), so the overlap window widens by 1.5 s on each side (§4.6), and each line's time is shown as "about m:ss" (e.g. "about 0:12 Voice S2 \"Hi, I'm Amina\"").

Precedence: "This clip has no sound." (`job.audio: false`) → limited-check copy → normal copy. Text is shown as heard; long turns are cut at 140 characters with "…".

**"Details"** (collapsed by default on mobile): `Decided by {Safe Cut's rules | Muse Spark | You}` · `Cover: {style word}` ("Cover: none (kept clear)" when `style` is `null`, as on every `keep` item, PRE-A §12) · `Tracks: {track_ids}` · `Frames {first}–{last}` · `Muse Spark's words: "{evidence, unedited}"` · `Models: {receipt-style model list}`. This is the only place raw track IDs and frame numbers appear, apart from the keyframe caption and alt text (which name the burned-in labels) and numbers in Muse Spark's quoted text that the frame-reference rules leave as written (§4.3 "Limits").

### 4.4 States

| State | What shows |
|---|---|
| Loading the keyframe | The keyframe box with a neutral fill and "Loading the keyframe…" |
| Keyframe failed | "The keyframe didn't load." The rest of the drawer still shows |
| Keyframe size doesn't match the clip (§4.3 keyframe geometry) | The image without a ring, and "The keyframe's size doesn't match this clip, so the outline is hidden." The rest of the drawer still shows |
| Limited speech check (`transcript.degraded`, or `transcript.source_kind = "fallback"`) | Heading "What was probably said (speech check was limited)"; lines timed "about m:ss"; an empty list shows "Speech couldn't be checked reliably for this clip." (§4.3) |
| No votes (an object such as a plate, screen or document; or an audit-added item) | Objects show "Muse Spark read it as …" and "Personal: yes/no" in place of the votes (§4.3); an object entry with `content: ""` (PRE-A's failure placeholder) counts as no entry, so neither line shows. An audit-added item shows the fixed sentence for its case |
| Demo mode | Same content, from the replayed hero job |

### 4.5 Keyboard and accessibility

- Opens as a modal dialog (`role="dialog"`, `aria-modal="true"`, labelled by its header); focus moves to the header; focus is trapped; `Esc` closes and returns focus to the chip.
- `←` / `→` step evidence frames when the keyframe has focus.
- The keyframe has alt text built from the data: "Keyframe at 0:06. face:4 is ringed, in the back right. Other labelled objects: face:1, face:2, license plate:1."
- Vote marks have text, not just ✓/✕ ("Check 1: Child, agrees with the majority").
- Mobile bottom sheet: the drag handle is also a button ("Expand" / "Collapse").

### 4.6 Data

| Element | Source |
|---|---|
| Keyframe image | `roles.json` `keyframes[]` (the `som/*.jpg` matching the evidence frame), served by WP5 as a URL |
| Ring position | `tracks.json` `tracks[track_id].boxes[frame]` for the item's tracks on that frame, mapped into the image with the keyframe geometry (§4.3: `y + bar_h`, then the display scale); `bar_h` from `keyframe_geometry` (*proposal*, §8 request 13) |
| Evidence frames | `decisions.items[].evidence_frames` (falls back to `roles.tracks[].frames`) |
| Reason | `decisions.items[].reason` |
| Votes, evidence, escalation | `roles.json` `tracks[]`: `votes`, `role`, `evidence` (role pass only), `escalated` (true only for a returned ruling), `suggested_role` (nullable; PRE-A escalation.md), `escalation_evidence` and `escalation_frames` (nullable; *proposal*, request 3 in §8) for each track in `track_ids`; show the primary track first |
| Object content | `roles.json` `objects[]`: `sensitive`, `content`, for screens, documents, phones, badges and plates (`license plate:` tracks; PRE-A role-pass.md) |
| Transcript | `transcript.json` `turns[]` whose span overlaps the item's prepared-clock span `[first / job.fps, (last + 1) / job.fps)`: a turn overlaps when `turn.start < (last + 1) / job.fps` and `turn.end ≥ first / job.fps`. Turn times are prepared-clock seconds, because the ASR audio is extracted from `prepared.mp4` (PRE-A `docs/API-NOTES.md` §5b step 6). For a limited transcript (`degraded: true` or `source_kind: "fallback"`, §4.3) the window is `[first / job.fps − 1.5, (last + 1) / job.fps + 1.5)` |
| Transcript quality | `transcript.json` `degraded` (boolean, default false; PRE-A speech-fallback.md adds it to the §3.3 contract) and `source_kind` (`"primary"` or `"fallback"`, *proposal*, §8 request 16). `source` (ARCHITECTURE §3.3) is shown in Details only, never compared in logic |
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
│ │                                                       │  930 of 930 frames checked.│
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
│ 930 of 930 frames checked. 1 leak│
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
| Audit, clean | ✓ Checked · `{frames_scanned}` of `{frames}` frames checked. No leaks found. |
| Audit, fixed | ✓ Checked · `{frames_scanned}` of `{frames}` frames checked. `{n}` leak(s) found and fixed. Nothing left to fix. |
| Audit, unresolved | ⚠ Not ready to publish · `{frames_scanned}` of `{frames}` frames checked. `{unfixed_spots}` spot(s) couldn't be fixed automatically. Publishing is off until they're fixed. [Review them] (links to `/jobs/[id]?view=review`, §10.4, where each spot is a Needs-you chip, §3.3) |
| Audit detail link | What the check does → (expands: "Meta's EgoBlur looked for faces and number plates on `{frames_scanned}` of the result's `{frames}` frames. It's meant to scan all of them; any frame it couldn't check counts as not checked, and publishing stays off until it is. Muse Spark looked at sampled frames and tried to read or recognise anything. Anything they found that wasn't kept clear on purpose was covered, and the clip was rendered again.") |
| (number rule) | **`{unchecked_frames}`** = `unresolved` − the number of `leaks[]` rows with `unresolved: true` (one row per frame of each spot). Banners about unchecked frames use it, never raw `{unresolved}`, so a leak spot is never counted as an unchecked frame. `{unfixed_spots}` = the number of `audit.spots[]` entries (spots, not frames) |
| Audit, couldn't finish (`blocked_reason: "audit_failed"`) | ⚠ Not ready to publish · The final check couldn't finish on `{unchecked_frames}` frame(s). Publishing is off until it runs. (Actions: the §3.5 `needs_you` bar.) |
| Audit over budget (`blocked_reason: "over_budget"`) | ⚠ Not ready to publish · The final check ran out of budget on `{unchecked_frames}` frame(s). Publishing is off. A second line from `audit_budget_cause` (request 11): `daily_cap` → "Today's limit was reached. You can run it again after `{retry_at}`." (or, under the §2.6.1 expiry rule, "Today's limit was reached, and this access code expires before then, so this can't be run again."); `job_cap` → "This clip used up its processing budget. You can download this version, or try a shorter clip."; `code_cap` → "This access code ran out of budget."; `pilot_pool_cap` → "The pilot budget ran out." Which buttons show, and when they're enabled, is defined once, in the §3.5 `needs_you` bar. If a re-run fails again, the same banner returns |
| `{frames}` wording rule | Never write "every frame" unless `frames_scanned == frames` (`frames` from `job.json`) |
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
| After delete | Deleted. Nothing from this clip is kept. (The same string as §2.6, on every page, with a link to `/try`.) |

### 5.4 States

| State | What shows |
|---|---|
| Rendering (arrived early) | The progress list `render` → `receipt` from §2.5 |
| Edited after rendering | The job is back in `review` (§10.4), so `/result` redirects to the review panel; Publish can't be reached until the new render is `done` |
| Ready, clean / fixed | As wireframed |
| Unresolved > 0 (`blocked_reason: "unresolved_leaks"`) | Warning panel (above), Publish disabled, Download still allowed with the note "This version has `{unfixed_spots}` unfixed spot(s)." |
| Audit couldn't finish or over budget (`blocked_reason` `audit_failed` / `over_budget`) | The job is in `needs_you` (PRE-A §10.3), so `/result` redirects to the review page: read-only panel, the §5.3 banner and the §3.5 `needs_you` bar ([Run the audit again], [Download this version] and [Delete everything now], or for `job_cap` [Download this version], [Try another clip] and [Delete everything now]). Unchecked frames have no box, so no chip; boxed unresolved leaks, if any, show as read-only U chips (§3.3). Publish disabled. Download (from `result.video_url`) shows the note "This version hasn't been fully checked." |
| Receipt failed to load | "The receipt didn't load. You can still download it as JSON." |
| From Sigmora (`?from=sigmora`) | Publish button shows; header shows "Back to Sigmora" |
| Not from Sigmora | No Publish button at all (not a disabled one), in demo mode too (the demo-mode line below is only for jobs from Sigmora) |
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
| Video, download | `GET /v1/jobs/{id}/result` → signed URL for `redacted.mp4`; also `GET /v1/jobs/{id}` → `result: {video_url}` whenever a render exists (request 1), which the `needs_you` bar's [Download this version] uses |
| Audit summary | `audit.json`: `frames_scanned`; **leaks found and fixed = the number of distinct `patched_item` values** in `leaks[]` (one leaking person over 2 frames is 1 leak, not 2; `leaks[]` has one row per frame); `unresolved`; `passes`; `blocked_reason` (PRE-A's field, API-NOTES §12) picks the panel; `frames_scanned` and `job.frames` fill "`{frames_scanned}` of `{frames}`" |
| Publish allowed | `audit.json` `unresolved == 0` ([ARCHITECTURE.md](ARCHITECTURE.md) §3.8) **and** `?from=sigmora`. That's the one gate: by PRE-A's invariant every unchecked frame counts in `unresolved` (API-NOTES §12), so no second field is needed |
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
| Items | §3.6 `decisions.json` `items[]` (all fields), plus `removed_by_creator` (request 9) | `GET /v1/jobs/{id}` → `items` |
| Track boxes, first/last, `reentry_of` | §3.2 `tracks.json` `tracks[]` (boxes only for the items' tracks) | `GET /v1/jobs/{id}` → `tracks` |
| Votes, evidence, escalation (`suggested_role`), participant link (`matches_participant`), keyframe list, object content | §3.5 `roles.json` plus PRE-A's additions to `tracks[]`: `matches_participant` (role-pass.md) and `suggested_role` (escalation.md) | `GET /v1/jobs/{id}` → `roles` |
| SoM keyframe images | §3.5 `keyframes[]` | signed URLs in `GET /v1/jobs/{id}` → `keyframe_urls` |
| Overlay regions | §3.7 `plan.json` | `GET /v1/jobs/{id}` → `plan` (or `plan_url`) |
| Transcript | §3.3 `transcript.json` | `GET /v1/jobs/{id}` → `transcript` |
| Scene participants, speakers, children | §3.4 `scene.json` with PRE-A's scene-pass.md shape: `summary`, `participants[]` (`description`, `evidence`, `speaker`, `introduced_in_turn` (0-based turn index or `null`), `introduction_quote` (string or `null`; WP2 sets both to `null` unless the quote is found in that turn), `is_creator`), `children[]` (`description`), `others_present`, `candidate_objects[]` (`what`, `approx_time` ∈ `beginning`/`middle`/`end`/`throughout`/`unknown`), `model` | `GET /v1/jobs/{id}` → `scene` |
| Edits | WP3 `apply_review` | `POST /v1/jobs/{id}/review` → returns updated `items` **and** `plan`, plus `status`, `has_render` and `audit.spots` (the review page pauses polling, so the ack is its only source for them) |
| Audit | §3.8 `audit.json` (+ PRE-A's `blocked_reason`, `leaks[].flag`) | `GET /v1/jobs/{id}/result` → `audit`, and also `GET /v1/jobs/{id}` → `audit` whenever an audit has run, so the review panel can show unfixed spots and the audit banner |
| Result files | `redacted.mp4`, §3.9 `receipt.html`, `receipt.json` | `GET /v1/jobs/{id}/result` |
| Demo mode | — | every response → `mode: "live" \| "replay"` |
| Deletion time | `job.json` `created_at` + WP5's cleanup schedule | `deletes_at` (required) |

**Requests for other WPs** (also listed in the PRE-B PR):
1. **WP5:** return the fields above, including `plan` with the review response, `mode` on every response, `status: failed` with the failed `stage`, and `status: retry_later` (PRE-A `docs/API-NOTES.md` §10.3: a transient failure in a stage needed to hide something; WP5 re-queues it **once**, after 5 minutes; if that retry fails too, the job goes to `failed` with `failure.reason: "upstream"`), ideally with `retry_at` (ISO time) *(proposal)*. A `failed` job also carries `failure: {stage, reason}` with `reason` ∈ `job_cap` or `daily_cap` (PRE-A §10.3 raises one `BudgetExceeded` for both; WP5 tells them apart by which cap the pre-call estimate failed, and sets `retry_at` to the next 00:00 UTC for `daily_cap`), `code_cap` (the per-access-code cap of a pilot, recording or owner code, PILOTS.md §5), `pilot_pool_cap` (the shared $20 pilot total, request 20), `config` (`MetaAuthError` or `MetaConfigError`), `bad_request`, `refusal`, `incomplete`, `upstream` (the one `retry_later` re-queue also failed), `code_not_active` (a re-queued job whose code window closed, PRE-A §9.2), `internal` *(proposal)*. `POST /start` refuses before any call when a cap can't cover the job's §9.1 estimate (PRE-A `docs/API-NOTES.md` §10.3 @ `565eee3`): **`422 job_cap`** when the job cap can't (the same clip can never fit, so it isn't a retryable `429`), and **`429`** with `code_cap`, `pilot_pool_cap` or `daily_cap` for a caller cap; the estimate is `max($1.12, clip_seconds × $2.24 / 60)` (PRE-A `docs/API-NOTES.md` §9.2 and §10.3), so a job that can't finish is refused before it spends anything. `POST /v1/jobs` (before the upload, so the duration is unknown) refuses with `429 code_cap` or `pilot_pool_cap` when the code's remaining cap or the pool is below the estimate's **$1.12 floor**, so an exhausted code is caught before the creator uploads. `GET /v1/jobs/{id}` also carries `result: {video_url}` (a signed URL) whenever a render exists, including in `needs_you`, and `has_render: true` whenever a render exists (also in `review` after an edit at `?view=review`) *(proposal)*.
2. **WP2:** draw each track's `<concept>:<n>` label on the Set-of-Mark keyframes exactly as PRE-A `docs/prompts/role-pass.md` specifies, using the track's own ID. The UI derives display labels from track IDs (§0), so no extra field is needed.
3. **WP2:** fill `roles.tracks[].matches_participant` (nullable index into `scene.participants`) and `suggested_role` (nullable, escalation only) as PRE-A `docs/prompts/role-pass.md` and `escalation.md` specify. The drawer's speaker link ("said by {label}") and escalation suggestion read them (§4.3, §4.6). Also write the escalation ruling's evidence and frames to `escalation_evidence` (string or null) and `escalation_frames` (int array or null) *(proposal; PRE-A escalation.md rule 4 says the ruling's evidence goes to the review card but names no field, so this is also a request to PRE-A)*, never into `evidence`, and set `escalated: true` only for a returned, valid ruling.
4. **WP3:** keep `reason` strings short (≤ 90 characters), plain, lowercase-first, no trailing full stop; the UI capitalises. Audit-added items (`origin: "audit_patch"`, WP4) are exempt: their `reason` is PRE-A §12's fixed sentence "Added by the audit: the final check found this after rendering and covered it.", shown as is.
5. **WP3/WP5:** name the review edit types to match §3.4 and §10.5: `keep`, `hide`, `merge` (into an item ID), `remove_person`, `cover_spot` (a `spot_id`; §3.3), and `undo`, which has its own `edit_id` and names the edit to revert in `reverts` (an undo that reused the original `edit_id` would be swallowed by the idempotency check, §10.3). The server restores the item's state from before that edit (including `needs_you`, `decided_by`, `removed_by_creator` and an unmerge), so the UI never has to construct an inverse edit. After a `merge` is acknowledged, the server returns the target with the source's `track_ids` appended after the target's own and the source removed. Undoing a `cover_spot` removes its audit-added item and sets the spot's `covered_by` back to `null`, so the U chip returns (R21). An edit accepted while the job is `done` (opened with `?view=review`) moves the job back to `review` (the previous render stays downloadable until a new one replaces it). Edits are never accepted in `needs_you`: the server answers `409` `read_only`, and the UI never sends one because the panel is read-only there; a `needs_you` job leaves that state through [Run the audit again] (request 11) or `DELETE /v1/jobs/{id}`. **WP5 accepts `DELETE` in every job state** (PILOTS §4 promises immediate deletion), including `needs_you`, `rendering` and `failed`.
6. **WP1:** implement PRE-A `docs/API-NOTES.md` §5b exactly: a constant-frame-rate prepared clip at `job.fps`, `job.frames` read back with the bundled ffmpeg's `framemd5` output (line count; `imageio-ffmpeg` has no ffprobe), and `job.times` as source seconds (non-decreasing, repeats allowed, `times[0]` possibly slightly above 0). The UI places everything on the prepared clock `i / job.fps` (§0, §3.6) and checks `times` only as §3.6 lists.
7. **WP2:** keep `transcript.json` turn times on the prepared clock by transcribing audio extracted from `prepared.mp4`, as PRE-A §5b step 6 specifies; the Why drawer's transcript overlap (§4.6) depends on it.
8. **WP5:** return `deletes_at` as the latest time the 24 h cleanup will have removed the job (it depends on how often the cleanup runs).
9. **WP0/WP3 (contract change, [AGENTS.md](../AGENTS.md) rule 3):** add `removed_by_creator: boolean` (default `false`) to `decisions.json` `items[]` in ARCHITECTURE §3.6 and `contracts.py`. WP3's `apply_review` sets it to `true` on a `remove_person` edit and back to `false` on any later `keep` edit of that item (a removed person the creator keeps clear is no longer removed). An `undo` restores whatever the reverted edit changed: undoing the `remove_person` sets it to `false`, and undoing the later `keep` sets it back to `true`. Nothing else can tell a removed person from a prominent bystander, because both use the `person_solid` style (DESIGN §2.7b). The reducer reads it from the server (§10.5), and the drawer's "Removed at your request" sentence and the receipt's "removed at your request" mark use it.
10. **WP5:** reset `SAFECUT_DAILY_USD_CAP` spending at **00:00 UTC** each day *(decision for the copy "Try again tomorrow", §2.6)*, and include `retry_at` on `daily_cap` errors.
11. **WP4/WP5:** implement PRE-A's `audit.json` `blocked_reason` and its invariant (API-NOTES §12), send `status: "needs_you"` when an audit pass couldn't run or finish (§10.3), and implement "Run the audit again" as **`POST /v1/jobs/{id}/audit`**, which re-runs the audit on the existing render (the creator's decisions aren't rendered again, matching PRE-A API-NOTES §10.3). Like a first audit, it runs WP4's auto-patch loop, so a leak it finds is covered and only the affected segment is rendered again (stages `audit` ↔ `render` alternate, ARCHITECTURE §2, WP4 step 2). After the last pass the pipeline continues with the receipt stage, ending in `done` *(proposal)*. Outcomes: a clean pass (after any auto-patches) → stage `receipt` → `done` with `receipt.html` and `receipt.json`; leaks it can't patch → `done` with `blocked_reason: "unresolved_leaks"` (the Unfixed-spot path, §3.3); the pass fails or runs over budget again → back to `needs_you` with the new `blocked_reason` and `audit_budget_cause`. Answers: `202` → `status: "rendering"`, `stage: "audit"`; `409` if a render or audit is already running; `429` with `daily_cap`, `code_cap`, `pilot_pool_cap` or `rate_limited`. **Wording request to PRE-A:** API-NOTES §10.3 says "re-runs only the audit"; please add that the receipt stage then runs as after a first audit, so WP4/WP5 don't stop before writing the receipt. While an audit's auto-patch renders, the job response carries `stage: "render"` with `stage_reason: "audit_patch"` *(proposal)*, so §2.5 can label it. PRE-B's one addition: with `blocked_reason: "over_budget"`, the job response also carries `audit_budget_cause` (`daily_cap`, `job_cap`, `code_cap` or `pilot_pool_cap`), plus `retry_at` when the cause is `daily_cap` *(proposal)*.
12. **WP6 brief owner:** WP6 step 4 says the overlay maps frames "via `job.times`"; that is superseded by PRE-A `docs/API-NOTES.md` §5b, where the player uses `i / job.fps` and `job.times` holds source seconds (§3.6 here).
13. **WP2/WP5:** expose the keyframe image geometry with the job: `keyframe_geometry: {bar_h, frame_width, frame_height, image_width, image_height}` (*proposal*; `frame_*` is the prepared frame inside the image, `image_*` the whole image including the bar, so `image_height = frame_height + bar_h`; today `bar_h = 40`, PRE-A API-NOTES §5), so the ring and thumbnails land on the right pixels (§4.3).
14. **WP3:** set `decisions.items[].kind` with the §0 concept → kind mapping (`license plate` → `plate`; `screen`, `phone` → `screen`; `document`, `name badge` → `document`; Muse-proposed concepts → `other`; and `child`, locked, whenever the item's track has `child_phrase: true`, PRE-A §12), and send every object whose three checks all said `sensitive: false` to `needs_you`, never `keep` (PRE-A TEST-VECTORS B1, DESIGN §2.5).
15. **WP2:** record which tracks each miss created: `roles.missed[].track_ids` (*proposal*, a list of the new track IDs SAM returned for that `missed` item), so the drawer can say what an `other` item is (§4.3). Today `roles.missed[]` has `what`, `sam_phrase`, `frame` and `point` (ARCHITECTURE §3.5) but no link to the resulting tracks.
16. **WP2/WP5:** add `transcript.source_kind: "primary" | "fallback"` (*proposal*), set by WP2 from which path produced the turns (Muse Voice Transcribe, or PRE-A's speech fallback). The UI keys the limited-speech display on it and on `degraded`, never on a model ID (AGENTS.md rule 8).
17. **WP5:** add job `status: "created"` (job made, upload or start not done) and `failure.reason` values `too_long`, `too_large` and `bad_media` from `prepare`, with `failure.duration_s` for `too_long` and `failure.size_bytes` for `too_large`. `POST /v1/jobs` takes the file's `size_bytes` and `content_type` (the file's MIME type, `video/mp4` or `video/quicktime`) and answers `413 too_large` (with `error.size_bytes`) above 157,286,400 bytes; the presigned `PUT` (valid 15 min, never re-signed) is signed for exactly that `Content-Length` and `Content-Type`, and the browser sends both unchanged. A stalled or failed upload's [Try again] sends `DELETE` for that job and starts again from `POST /v1/jobs`. `POST /start` answers `409 upload_incomplete` when the uploaded object is missing or has another size (PRE-A §12, `research/modal.md`). The server's length check runs in `prepare`, because `POST /v1/jobs` comes before the upload.
18. **WP4/WP3/WP5:** in `audit.json` `leaks[]`, mark leaks the patch loop couldn't fix with `unresolved: true` (with `frame`, `box`, `kind`); report `audit.sample_step` = `round(job.fps)`, the red-team's step for its 1 fps sampling, for every row, EgoBlur rows included (PRE-A `docs/API-NOTES.md` §12, which adopted this request); group the unresolved rows into `audit.spots[]` = `{spot_id, first, last, boxes: {frame: box}, covered_by: item_id | null}`, one spot per maximal run of audited frames at most `sample_step` apart whose boxes overlap with IoU ≥ 0.3 (WP4 does the grouping, so every client counts the same way); and accept a review edit `cover_spot` (`spot_id`) that adds **one** hidden item, carrying the `spot_id`, with one static box (the union of the spot's `boxes`) over `first − half − temporal.extend` … `last + half + temporal.extend`, `half = ceil(sample_step / 2)`, clamped to `[0, frames − 1]`, no back-fill, as a `decisions.items[]` entry with `origin: "audit_patch"` and `audit_label` `A<n>` (PRE-A §12; the mock invariants require both fields on every audit-added item), and set the spot's `covered_by` to that item. This changes the ARCHITECTURE §3.8 contract (AGENTS rule 3: ARCHITECTURE + `contracts.py`, owned by WP0/WP4).
19. **WP5:** add `GET /v1/demo/{hero_id}`: public (no access code), read-only, rate-limited per IP, serving only hero jobs marked `pinned: true`. The 24 h cleanup skips pinned jobs. It returns the same result shape as `GET /v1/jobs/{id}/result` with `mode: "replay"`, **plus** the hero job's `job` (`prepared_url`, `fps`, `frames`, `times`) for the Raw side of the toggle and its `audit` (with `egoblur.model`, for the §1.3 auditor name rule), so the landing player and the demo-mode banner work unchanged.
20. **WP5 and WP0:** access-code kinds with their own caps, outside `SAFECUT_DAILY_USD_CAP`: **pilot codes** ($6 each, which is enough for a pilot's clip plus one retry, with no separate job count; and a shared pilot total of $20, which returns `pilot_pool_cap` once used up; [PILOTS.md](PILOTS.md) §5), and one **owner recording code** ($12 in total, not per day, for the Nov 3 recordings; the owner may raise it by updating the deploy secret below, by **at most $3.00 in total, to $15.00**, which is PRE-A's whole headroom against the $150 and is shared with every other overrun, `docs/API-NOTES.md` §9.2 @ `565eee3`; [STORYBOARD.md](STORYBOARD.md) §3). One **owner code** (`kind: "owner"`, `cap_usd` ≤ 6.00, WP5's smoke and live end-to-end runs before Nov 5, counted in WP5's $6 line; PRE-A §12 env table) has its own cap too. Judge and public codes stay under the daily cap. The pre-call budget check lives in WP0's Meta client (PRE-A `docs/API-NOTES.md` §10.2 and §10.5), so WP0's guard takes the caps that apply to the job's code kind (pilot: per-code and pool; recording: per-code; judge and public: daily), and `cost.jsonl` gains `code_kind` and `code_id` so spend can be charged to the right cap (a contract addition for WP0, and a request to PRE-A, which owns the client spec). The recording code is **revoked after Nov 3** (BLOCKED-PRE-B). **Where codes and caps live:** only in a deploy secret, never in the repo (AGENTS.md rule 4). `SAFECUT_ACCESS_CODES` becomes a JSON list, `[{"code": "…", "kind": "judge"|"public"|"pilot"|"recording"|"owner", "cap_usd": 6.0, "valid_from": "…Z", "valid_until": "…Z"}]` (`cap_usd` optional for judge and public codes, which use the daily cap). **Every code has a validity window set by its kind** (PRE-A `docs/API-NOTES.md` §9.2 and its `SAFECUT_CODE_WINDOWS` defaults in WP0's `config.py`): judge and public Nov 5 00:00 – Nov 10 23:59 UTC; recording until Nov 3 23:59 UTC; pilot until Nov 2 23:59 UTC; owner until Nov 10 23:59 UTC. An entry's optional `valid_from`/`valid_until` may only **narrow** its kind's window (a wider value fails config validation at startup), and an unknown kind fails too, so no code is ever valid without a window. The window is checked on **every request that can start paid work**, for every kind (`POST /v1/codes/check` reports it too): `POST /v1/jobs`, `POST /start` (including a restart), `POST /render` and `POST /audit` answer `401 code_not_active` outside it, with both `valid_from` and `valid_until` keys (`null` where unbounded, §2.6), so nothing spends outside PRE-A's ledger lines. Reading a job, review edits, download and `DELETE` always work, whatever the window, so a pilot can always see and delete their clip ([PILOTS.md](PILOTS.md) §4). Every job response carries **`code_valid_until`**, so the UI can hide a retry that would land after it (§2.6 `daily_cap`), and a `retry_later` job whose window closed before its re-queue fails with `failure.reason: "code_not_active"` (§2.6). **Revoking** a code (removing it from the secret) is different: paid requests on its jobs (`POST /start`, `/render`, `/audit`) answer a plain `401`, while `GET`, review edits and `DELETE` are authorised by the job link and keep working (§2.6 "Code refused on a job page"). **Service keys** (`SAFECUT_SERVICE_KEYS`, WP5) have the judge window too: outside Nov 5 00:00:00 – Nov 10 23:59:59 UTC every paid request with a service key answers `401 code_not_active`, with no replay (PRE-A §9.2 @ `02c605e`); the Sigmora integration is built against a local `SAFECUT_REPLAY=1` deployment. The pilot end (Nov 2 23:59 UTC = Nov 3 02:59 EAT) gives every pilot the advertised Oct 30 – Nov 2 in East Africa and Europe and until 15:59 PST / 18:59 EST in the US; the code's message states the end in the pilot's local time ([PILOTS.md](PILOTS.md) §5 "Before"), and the outreach already says "Nov 2 (UTC)" (§3), and the shared pilot total is `SAFECUT_PILOT_POOL_USD` (default `20`). Both are set as a Modal/environment secret. The owner raises a cap by updating the secret and redeploying. WP0's `config.py` parses both (a request to WP0), and ARCHITECTURE §4's env table gains them (a request to its owner).
21. **WP5:** add `POST /v1/codes/check` (*proposal*): body `{code}`, no side effects and no Meta calls, rate-limited per IP like every route. It answers `200 {kind, valid_from, valid_until}` (both date keys always present, `null` where the code has none), `401` for an unknown code, and `401 code_not_active` with the dates outside the code's window (request 20). Continue on `/try` step A sends it (§10.2), so a wrong or expired code is caught before the creator picks a file. `POST /v1/jobs` and `POST /start` still check the code, because a window can close between Continue and Start.
22. **WP7:** write `n_clips`, `n_public` (real-public clips) and `n_staged` (staged clips), plus the label report's `percent_agreement`, `n_entities`, 2×2 counts `a`–`d` and `kappa` (LABEL-FORMAT §9.2), into the test run's `metrics.json` from the frozen split (`eval/splits/test.sha256` and its metadata), so the results footnotes (§1.3) and STORYBOARD's `{n_test_clips}` cite a committed `metrics.json` (AGENTS rule 9) rather than `config.json`.

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
| `job-done-edited.json` | `GET /v1/jobs/{id}` (`status: "review"`, `has_render: true`, after an edit made in `done` with `?view=review`) | the §3.5 "You changed something after rendering…" bar |
| `job-review-200-items.json` | `GET /v1/jobs/{id}` | the performance case in §10.7 |
| `job-review-no-audio.json` | `GET /v1/jobs/{id}` (`job.audio: false`; `transcript` as PRE-A's speech-fallback.md writes it for no audio: `status: "ok"`, `turns: []`, `degraded: false`, `source_kind: null`) | drawer shows "This clip has no sound." |
| `job-review-speech-limited.json` | `GET /v1/jobs/{id}` (hero mock with `transcript: {"status": "ok", "source": "muse-spark-1.2", "source_kind": "fallback", "degraded": true, "turns": []}`, and, as PRE-A §12 rules for a degraded transcript, **no person auto-kept**: `i_1` is `decision: "needs_you"` with `hold: "no_speech"` and `reason: "speech check was limited, so not kept automatically"` (PRE-A §12 `transcript.json` `status`/`degraded` rule; vectors P9/P9b), and the mock's `plan` adds two `i_1` regions, written out in full: frame 3 `{"item_id": "i_1", "shape": "box", "box": [390, 106, 480, 224], "mask": null, "style": "pixelate", "grid": [390, 106, 15]}` and frame 9 `{"item_id": "i_1", "shape": "box", "box": [400, 108, 490, 226], "mask": null, "style": "pixelate", "grid": [390, 106, 15]}` (its `face:2` boxes padded by about 15%, an approximation of WP3's 15% + 8 px; cell 15 keeps the face at 6 blocks across, WP3's ≤ 6 rule, and the grid stays locked to the first box on every frame, ARCHITECTURE §3.7), because `needs_you` renders hidden) | drawer heading "What was probably said (speech check was limited)" and "Speech couldn't be checked reliably for this clip." (§4.3) |
| `job-review-speech-fallback.json` | its own 4 s mock, given in full below (10 fps, 40 frames), with `source_kind: "fallback"` and one turn at 1.2–1.8 s | the turn shows under Face 4 (frames 25–39, i.e. 2.5–4.0 s) only because of the ±1.5 s widening; the same mock with `source_kind: "primary"` must **not** show it under Face 4 (§4.6). It shows under Face 1 (0–4.0 s) either way |
| `job-review-keyframe-mismatch.json` | hero mock with `keyframe_geometry.image_height` 720 and the stub loader reporting a 1280×720 natural size (an image with no bar) | drawer shows the image without a ring and "The keyframe's size doesn't match this clip, so the outline is hidden." (§4.3) |
| `job-replay.json` | `GET /v1/jobs/{id}` (`mode: "replay"`) | demo-mode banner (§6) on the review panel |
| `job-rendering-audit.json` | `GET /v1/jobs/{id}` (`stage: "audit"`) | §3.5 bottom bar replaced by the render stages; chips read-only |
| `result-clean.json` | `GET /v1/jobs/{id}/result` (`unresolved: 0`, `blocked_reason: null`) | §5.3 "No leaks found." |
| `result-clean-yunet.json` | as `result-clean.json`, with `audit.egoblur: {model: "yunet-face", faces: 0, plates: null}` (PRE-A's Oct 28 fallback) | §5.3 audit detail in the §1.3 auditor-name-rule YuNet wording; no plate count anywhere, the receipt included |
| `result-fixed.json` | `GET /v1/jobs/{id}/result` | §5.3 "1 leak found and fixed. Nothing left to fix." (two `leaks[]` rows with the same `patched_item`: proves the distinct-item count, §5.6) |
| `result-unresolved.json` | `GET /v1/jobs/{id}/result` (`audit.unresolved: 1`, `blocked_reason: "unresolved_leaks"`, and `audit.spots` holding the one spot `s1` as in `result-unresolved-review.json`) | §5.4 warning, Publish disabled |
| `result-audit-failed.json` | `GET /v1/jobs/{id}` (items, tracks, roles and plan as in the hero mock, which every `result-audit-*.json` below also uses; `status: "needs_you"`, `audit.blocked_reason: "audit_failed"`, `unresolved: 4`, no unresolved leak boxes, `result.video_url` set) | review page with the §5.3 "couldn't finish on 4 frames" banner and [Run the audit again]; no Unfixed-spot chips; Approve & render replaced by [Run the audit again] |
| `result-audit-failed-with-leak.json` | `GET /v1/jobs/{id}` (`status: "needs_you"`, `audit.blocked_reason: "audit_failed"`, `unresolved: 5` = 4 unchecked frames + one single-frame spot U1 (`spot_id` `s1`, `covered_by: null`; one `leaks[]` row with `kind: "face"`, `unresolved: true`), `audit.sample_step` set, `result.video_url` set) | banner "couldn't finish on 4 frames" (`{unchecked_frames}` = 5 − 1); the U1 chip shown read-only, without [Cover it] |
| `job-audit-rerun-patch.json` | `GET /v1/jobs/{id}` (`status: "rendering"`, `stage: "render"`, `stage_reason: "audit_patch"`) | stage row "Covering what the check found" (§2.5), not "Applying your choices" |
| `result-audit-over-budget.json` | `GET /v1/jobs/{id}` (`status: "needs_you"`, `audit.blocked_reason: "over_budget"`, `audit_budget_cause: "daily_cap"`, `unresolved: 4`, `retry_at` set, `result.video_url` set) | review page with the "ran out of budget on 4 frames" banner; [Run the audit again] disabled until `retry_at` |
| `result-audit-over-budget-code.json` | same, with `audit_budget_cause: "code_cap"` and no `retry_at` | the banner with "This access code ran out of budget."; [Run the audit again] enabled (a `429 code_cap` answer changes nothing: the line is already shown and `capNote` isn't set, §10.5), [Download this version] |
| `result-audit-over-budget-jobcap.json` | same, with `audit_budget_cause: "job_cap"`, no `retry_at`, `result.video_url` set | banner "This clip used up its processing budget. You can download this version, or try a shorter clip."; bar: [Download this version], [Try another clip] and [Delete everything now] only; chips read-only |
| `render-ack.json` | `POST /v1/jobs/{id}/render` (`202`, `status: "rendering"`, `stage: "render"`) | the bar becomes the render stages at `Applying your choices`; polling resumes (§10.5 `ACTION_ACK`) |
| `delete-ok.json` | `DELETE /v1/jobs/{id}` (`204`) | page state `deleted` (§10.4) |
| `error-404-delete.json` | `DELETE /v1/jobs/{id}` (`404`, `error.code: "expired"`) | treated as success: page state `deleted` |
| `error-500-delete.json` | `DELETE /v1/jobs/{id}` (`500`) | page keeps its state; §7 "Something went wrong on our side. …" next to the delete control |
| `audit-ack.json` | `POST /v1/jobs/{id}/audit` (`202`, `status: "rendering"`, `stage: "audit"`) | the bar becomes the render stages at `Checking the result`; polling resumes |
| `job-audit-rerun-receipt.json` | `GET /v1/jobs/{id}` during the re-run (`status: "rendering"`, `stage: "receipt"`) | stage row `Writing your privacy receipt` |
| `job-audit-rerun-done.json` | `GET /v1/jobs/{id}` after the re-run (`status: "done"`, `audit.blocked_reason: null`, `unresolved: 0`, receipt URLs set) | redirect to `/result`; clean audit panel and the receipt |
| `review-ack-cover-spot.json` | `POST /v1/jobs/{id}/review` answering `cover_spot` `s1` on `result-unresolved-review.json` | `items` gains `{"item_id": "p_1", "origin": "audit_patch", "audit_label": "A1", "track_ids": [], "spot_id": "s1", "kind": "person", "decision": "hide", "locked": true, "reason": "Added by the audit: the final check found this after rendering and covered it.", "evidence_frames": [7], "box": [600, 200, 660, 250], "first": 0, "last": 11, "style": "solid", "decided_by": "policy", "removed_by_creator": false}` (span clamped to the 12-frame clip; `kind` from the spot's leak rows, `face` → `person`); `plan.frames` gains `{"item_id": "p_1", "shape": "box", "box": [600, 200, 660, 250], "mask": null, "style": "solid", "grid": null}` on every frame 0–11; `audit.spots` has `s1` with `covered_by: "p_1"`; `status: "review"`, `has_render: true`; R19's expectations |
| `review-ack.json` | `POST /v1/jobs/{id}/review` | an accepted edit returning updated `items`, `plan`, `status`, `has_render` and `audit.spots` |
| `error-401.json` | `POST /v1/codes/check` | step A: "That code didn't work. …", text selected |
| `error-401-job-render.json` | `POST /v1/jobs/{id}/render` (`401`, `error.code: "unauthorized"`), from a job in `review` | §3.5 row 0: "The access code for this clip no longer works …"; Approve & render disabled; [Delete everything now] shown; no `DELETE` sent |
| `error-401-job-expired-audit.json` | `POST /v1/jobs/{id}/audit` (job with `has_render: true`; `401`, `error.code: "code_not_active"`, `valid_from: "2026-11-05T00:00:00Z"`, `valid_until: "2026-11-10T23:59:59Z"`), test clock after it, a judge code's `needs_you` job | §3.5 row 0 with "This access code has expired, so Safe Cut can't run more work on this clip. You can still download or delete it."; [Run the audit again] disabled; [Download this version] and [Delete everything now] still shown; no Approve & render; no `DELETE` sent |
| `error-401-not-yet-active.json` | `POST /v1/codes/check` (`401`, `error.code: "code_not_active"`, `valid_from: "2026-11-05T00:00:00Z"`, `valid_until: "2026-11-10T23:59:59Z"`), with the test clock before Nov 5 | "This code isn't active yet. It works from … to …." with both dates in local time; text kept unselected |
| `error-401-expired.json` | `POST /v1/jobs` (`401`, `error.code: "code_not_active"`, `valid_from: null`, `valid_until: "2026-11-03T23:59:59Z"`), with the test clock after it | step B: "This code has expired. It worked until ….", Start disabled, [Use a different code]; no `DELETE` (no job was created) |
| `error-401-revoked-start.json` | `POST /v1/jobs/{id}/start` from `/try` (`401`, `error.code: "unauthorized"`) | step B: "That code didn't work. …", Start disabled, [Use a different code], and one `DELETE /v1/jobs/{id}` sent |
| `code-check-ok.json` | `POST /v1/codes/check` (`200`, `{kind: "judge", valid_from: "2026-11-05T00:00:00Z", valid_until: "2026-11-10T23:59:59Z"}`) | moves to step B |
| `error-429-cap.json` | any (`error.code: "daily_cap"`) | "Safe Cut has reached today's limit …" |
| `error-429-rate.json` | any (`error.code: "rate_limited"`) | "Too many tries in a short time. …" |
| `error-404-expired.json` | `GET /v1/jobs/{id}` (`error.code: "expired"`) | §7 "This clip has been deleted. …" |
| `error-404-not-found.json` | `GET /v1/jobs/{id}` (`error.code: "not_found"`) | §7 "We couldn't find that clip. …" |
| `job-retry-later.json` | `GET /v1/jobs/{id}` (`status: "retry_later"`, `stage: "track"`, `retry_at`) | §2.6 "Meta's service is busy right now. …" above the stage list; polling every 30 s (§10.3) |
| `job-failed-job-cap.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `failure: {stage: "track", reason: "job_cap"}`) | §2.6 per-job-cap copy; no [Try again] |
| `job-created.json` | `GET /v1/jobs/{id}` (`status: "created"`) | §10.4 `created`: "This clip hasn't finished uploading. …" [Upload again] |
| `result-unresolved-review.json` | `GET /v1/jobs/{id}` (`status: "done"`, `has_render: true`) with `view=review` data plus `audit.leaks[]` holding one `{frame: 7, box: [600, 200, 660, 250], kind: "face", unresolved: true, patched_item: null}` and `audit.spots[]` holding `{spot_id: "s1", first: 7, last: 7, boxes: {"7": [600, 200, 660, 250]}, covered_by: null}`, `audit.sample_step` = `round(job.fps)` of its base mock (PRE-A §12) and `audit.unresolved: 1`, `blocked_reason: "unresolved_leaks"` | §3.3 "Unfixed spot U1" chip in Needs you with [Cover it]; Publish disabled on `/result` |
| `job-failed-daily-cap-expiring.json` | `GET /v1/jobs/{id}` (`failure.reason: "daily_cap"`, `retry_at: "2026-11-11T00:00:00Z"`, `code_valid_until: "2026-11-10T23:59:59Z"`) | "Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again. Nothing has been published."; no [Try again tomorrow]; [Delete now] |
| `job-failed-code-not-active.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `failure.reason: "code_not_active"`, `has_render: false`) | "This access code has expired, so Safe Cut can't run more work on this clip. You can still delete it."; [Delete now] only, no [Try again] |
| `job-failed-daily-cap.json` | `GET /v1/jobs/{id}` (`failure.reason: "daily_cap"`, `retry_at` set) | §2.6 daily-cap copy; [Try again tomorrow] disabled until `retry_at` |
| `job-failed-code-cap.json` | `GET /v1/jobs/{id}` (`failure.reason: "code_cap"`) | §2.6 code-budget copy; [Try again] shown (stage routing) |
| `job-failed-upstream.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `failure: {stage: "track", reason: "upstream"}`) | §2.6 "Meta's service didn't recover in time. …"; [Try again] |
| `job-failed-deterministic.json` | `GET /v1/jobs/{id}` (`failure.reason: "refusal"`) | §2.6 deterministic-failure copy, shared by `config`, `bad_request`, `refusal` and `incomplete` (tests swap the reason and expect the same copy); no [Try again] |
| `error-429-render-code-cap.json` | `POST /v1/jobs/{id}/render` (`429`, `error.code: "code_cap"`), from a job in `review` with nothing needing you | bar row 8 "Everything's decided." with the note "This access code ran out of budget." above it; Approve & render stays enabled; no `DELETE` |
| `error-429-render-daily-cap-expiring.json` | `POST /v1/jobs/{id}/render` (`429`, `error.code: "daily_cap"`, `retry_at: "2026-11-11T00:00:00Z"`), job with `code_valid_until: "2026-11-10T23:59:59Z"` | bar row 0 with "Safe Cut has reached today's limit for the public demo, and this access code expires before the limit resets, so this can't be run again."; Approve & render hidden; `refusal.until = null`; no `DELETE` |
| `error-429-render-daily-cap.json` | `POST /v1/jobs/{id}/render` (`429`, `error.code: "daily_cap"`, `retry_at`) | bar row 0 with the daily-limit copy; Approve & render disabled until `retry_at`; [Delete everything now] shown; no `DELETE` |
| `error-429-code-cap.json` | `POST /v1/jobs/{id}/start` (`429`, `error.code: "code_cap"`) | §2.6 "This access code doesn't have enough budget left for this clip. …" |
| `error-429-pilot-pool-cap.json` | `POST /v1/jobs/{id}/start` (`429`, `error.code: "pilot_pool_cap"`) | §2.6 "The pilot budget has been used up…" |
| `job-failed-pilot-pool-cap.json` | `GET /v1/jobs/{id}` (`failure.reason: "pilot_pool_cap"`) | §2.6 shared-pilot-budget failure copy; no [Try again] |
| `job-failed-render.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `stage: "render"`) | stage-failure message; [Try again] re-renders (§10.4) |
| `error-413.json` | `POST /v1/jobs` (`error.code: "too_large"`, `error.size_bytes`) | "This file is {size} MB. …" |
| `error-409-upload-incomplete.json` | `POST /v1/jobs/{id}/start` (`409`, `error.code: "upload_incomplete"`) | §2.6 "The upload didn't finish, so nothing was processed. …"; [Try another clip]; one `DELETE` sent; no [Try again] |
| `job-failed-too-long.json` | `GET /v1/jobs/{id}` (`status: "failed"`, `failure: {stage: "prepare", reason: "too_long", duration_s: 60.4}`) | "This clip is 60.4 seconds long. …"; [Try another clip] and [Delete now], no [Try again]. `POST /v1/jobs` comes before the upload, so it can't know the duration; the server's length check happens in `prepare` |
| `error-422-job-cap.json` | `POST /v1/jobs/{id}/start` (`422`, `error.code: "job_cap"`) | "This clip would cost more than the per-clip limit …" |
| `error-409-rendering.json` | `POST /v1/jobs/{id}/render` | no message; keep polling |
| `error-503-auditor-unavailable.json` | `POST /v1/jobs/{id}/start` (`503`, `error.code: "auditor_unavailable"`) | §2.6 "Safe Cut's final check isn't available right now …"; Start stays enabled; no `DELETE` |
| `error-503-billing.json` | `POST /v1/jobs/{id}/start` (`503`, `error.code: "billing"`) | §2.6 "Safe Cut can't start new clips right now. Try again later."; Start stays enabled; no `DELETE` |
| `demo-hero.json` | `GET /v1/demo/{hero_id}` (`200`, `mode: "replay"`, the result shape plus `job` with `prepared_url`, `fps`, `frames`, `times`, and `audit.egoblur: {model: "egoblur-gen2", faces: 0, plates: 0}`; request 19) | the landing player's Raw/Safe Cut toggle plays both videos; "Precomputed result" label; step 3 copy as written |
| `demo-hero-yunet.json` | as `demo-hero.json`, with `audit.egoblur: {model: "yunet-face", faces: 0, plates: null}` | step 3 in the §1.3 auditor-name-rule YuNet wording |
| `results-no-egoblur.json` | WP8's static results JSON (§1.6) with no EgoBlur baseline row | the row reads "EgoBlur Gen 2: not run (EgoBlur weights unavailable)", with no numbers |
| `job-review-why-rows.json` | `GET /v1/jobs/{id}` (`status: "review"`): the hero mock plus one item per §4.3 Why row that no other mock drives, each built under the §10.1 mock invariants: a `hold` of `no_roles`, `no_scene`, `no_speech`, `unmatched_child` and `no_speech_link` (one item each), an `origin: "static"` item, a `kind: "other"` item with a `roles.objects[]` ruling, an escalated track ruled `child`, an escalated track with `suggested_role: null`, a 3/3 `participant` track on one keyframe, and a `removed_by_creator` item | each item's drawer shows its §4.3 row (the precedence list decides any overlap) and its escalation text as §4.3 says |
| `error-500.json` | any | §7 "Something went wrong on our side. …" |

Error body *(proposal)*: `{"error": {"code": "<snake_case>", "message": "<for logs only, never shown>", …extra fields}}`. The UI chooses its copy from `status` + `code` (§10.3), never from `message`.

**`job-review-hero1.json`** (complete and self-consistent: a 12-frame excerpt at 30 fps, so `times` has exactly `frames` entries and passes the §3.6 check; every evidence frame is a keyframe with a box for the item's primary track; track IDs use PRE-A's `<concept>:<n>` labels):

```json
{
  "job_id": "j_hero1", "mode": "live", "status": "review", "stage": "review", "progress": 1.0,
  "deletes_at": "2026-10-28T11:00:00Z",
  "job": {"fps": 30, "width": 1280, "height": 720, "frames": 12, "audio": true,
          "times": [0.0, 0.03333333333333333, 0.06666666666666667, 0.1, 0.13333333333333333, 0.16666666666666666, 0.2, 0.23333333333333334, 0.26666666666666666, 0.3, 0.3333333333333333, 0.36666666666666664],
          "created_at": "2026-10-27T10:00:00Z",
          "prepared_url": "https://example.invalid/j_hero1/prepared.mp4"},
  "items": [
    {"item_id": "i_1", "track_ids": ["face:2", "person:1"], "kind": "person", "decision": "keep",
     "reason": "the guest: introduced at the start, speaks to camera", "evidence_frames": [3, 9],
     "style": null, "decided_by": "policy", "locked": false, "removed_by_creator": false},
    {"item_id": "i_2", "track_ids": ["face:4"], "kind": "child", "decision": "hide",
     "reason": "child in the background, not addressed", "evidence_frames": [6],
     "style": "solid", "decided_by": "policy", "locked": true, "removed_by_creator": false},
    {"item_id": "i_3", "track_ids": ["license plate:1"], "kind": "plate", "decision": "hide",
     "reason": "number plate on a parked car", "evidence_frames": [1],
     "style": "solid", "decided_by": "policy", "locked": false, "removed_by_creator": false},
    {"item_id": "i_4", "track_ids": ["face:6"], "kind": "person", "decision": "needs_you",
     "reason": "looks at the camera; checks disagreed", "evidence_frames": [9],
     "style": "pixelate", "decided_by": "model", "locked": false, "removed_by_creator": false}
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
  "roles": {"status": "ok",
    "tracks": [
      {"track_id": "face:2", "role": "participant", "votes": ["participant", "participant", "participant"], "escalated": false,
       "suggested_role": null, "escalation_evidence": null, "escalation_frames": null, "matches_participant": 0, "evidence": "introduced at F 000003, speaks to camera at F 000003 and F 000009", "frames": [3, 9]},
      {"track_id": "face:4", "role": "child", "votes": ["child", "child", "child"], "escalated": false,
       "suggested_role": null, "escalation_evidence": null, "escalation_frames": null, "matches_participant": null, "evidence": "small person walking with an adult behind the guest at F 000006", "frames": [6]},
      {"track_id": "face:6", "role": "unsure", "votes": ["bystander", "participant", "bystander"], "escalated": true,
       "suggested_role": "bystander", "escalation_evidence": "faces the lens at F 000009 but is never addressed and never speaks", "escalation_frames": [9],
       "matches_participant": null, "evidence": "Judges disagreed: looks at the camera at frame 9, never speaks", "frames": [9]}
    ],
    "objects": [{"track_id": "license plate:1", "sensitive": true, "content": "number plate, characters legible", "frames": [1]}],
    "missed": [], "keyframes": ["som/000001.jpg", "som/000003.jpg", "som/000006.jpg", "som/000009.jpg"]
  },
  "keyframe_geometry": {"bar_h": 40, "frame_width": 1280, "frame_height": 720, "image_width": 1280, "image_height": 760},
  "keyframe_urls": {"1": "https://example.invalid/j_hero1/som/000001.jpg", "3": "https://example.invalid/j_hero1/som/000003.jpg",
                    "6": "https://example.invalid/j_hero1/som/000006.jpg", "9": "https://example.invalid/j_hero1/som/000009.jpg"},
  "plan": {"frames": {"1": [{"item_id": "i_3", "shape": "box", "box": [1042, 552, 1158, 598], "mask": null, "style": "solid", "grid": null}],
                      "6": [{"item_id": "i_2", "shape": "box", "box": [894, 193, 946, 257], "mask": null, "style": "solid", "grid": null}],
                      "9": [{"item_id": "i_4", "shape": "box", "box": [692, 140, 758, 225], "mask": null, "style": "pixelate", "grid": [692, 140, 11]}]},
           "crowd_fills": []},
  "transcript": {"status": "ok", "source": "muse-voice-transcribe-1.0", "source_kind": "primary", "degraded": false,
                 "turns": [{"speaker": "S1", "start": 0.0, "end": 0.1, "text": "So, who are you?"},
                           {"speaker": "S2", "start": 0.1, "end": 0.3, "text": "Hi, I'm Amina, and today…"}]},
  "scene": {"status": "ok", "model": "muse-spark-1.3", "summary": "street interview with a guest",
            "participants": [{"description": "woman in yellow jacket", "evidence": "introduces herself at the start: \"Hi, I'm Amina\"", "speaker": "S2", "introduced_in_turn": 1, "introduction_quote": "I'm Amina", "is_creator": false},
                             {"description": "man holding the microphone", "evidence": "asks the questions", "speaker": "S1", "introduced_in_turn": null, "introduction_quote": null, "is_creator": true}],
            "children": [{"description": "small child walking with an adult behind the guest"}],
            "others_present": "a few passers-by behind the guest",
            "candidate_objects": [{"what": "parked car with a visible number plate", "approx_time": "throughout"}]}
}
```

The `plan` lists only a few frames to stay short; frames it leaves out simply draw nothing (§10.7). A real job has a plan entry on every frame where a hidden item is visible.

**`job-review-speech-fallback.json`** (complete; a 4 s mock at 10 fps, so `times` has 40 entries, written in full as each is `i / 10`; it exists to tell the ±1.5 s widening apart from the normal overlap. Under the normal window, Face 4's span `[2.5, 4.0)` and the turn `1.2–1.8` don't overlap (`1.8 < 2.5`). Under the fallback window, `[1.0, 5.5)`, they do (`1.8 ≥ 1.0`). Face 1, on screen `[0, 4.0)`, overlaps the turn either way. A test runs it twice, once as written and once with `source_kind` set to `"primary"`, and expects Face 4's drawer to show the line only the first time):

```json
{"job_id": "j_speech", "mode": "live", "status": "review", "stage": "review", "progress": 1.0, "deletes_at": "2026-10-28T11:00:00Z", "job": {"fps": 10, "width": 1280, "height": 720, "frames": 40, "audio": true, "times": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9], "created_at": "2026-10-27T10:00:00Z", "prepared_url": "https://example.invalid/j_speech/prepared.mp4"}, "items": [{"item_id": "i_1", "track_ids": ["face:1"], "kind": "person", "decision": "keep", "reason": "the host, talks to camera throughout", "evidence_frames": [10, 30], "style": null, "decided_by": "policy", "locked": false, "removed_by_creator": false}, {"item_id": "i_4", "track_ids": ["face:4"], "kind": "person", "decision": "hide", "reason": "passer-by, never addressed", "evidence_frames": [30], "style": "pixelate", "decided_by": "policy", "locked": false, "removed_by_creator": false}], "tracks": [{"track_id": "face:1", "concept": "face", "first": 0, "last": 39, "reentry_of": null, "boxes": {"10": [400, 120, 470, 210], "30": [410, 122, 480, 212]}}, {"track_id": "face:4", "concept": "face", "first": 25, "last": 39, "reentry_of": null, "boxes": {"30": [900, 200, 940, 250]}}], "roles": {"status": "ok", "tracks": [{"track_id": "face:1", "role": "participant", "votes": ["participant", "participant", "participant"], "escalated": false, "suggested_role": null, "escalation_evidence": null, "escalation_frames": null, "matches_participant": 0, "evidence": "talks to camera at F 000010 and F 000030", "frames": [10, 30]}, {"track_id": "face:4", "role": "bystander", "votes": ["bystander", "bystander", "bystander"], "escalated": false, "suggested_role": null, "escalation_evidence": null, "escalation_frames": null, "matches_participant": null, "evidence": "walks behind the host at F 000030, never addressed", "frames": [30]}], "objects": [], "missed": [], "keyframes": ["som/000010.jpg", "som/000030.jpg"]}, "keyframe_geometry": {"bar_h": 40, "frame_width": 1280, "frame_height": 720, "image_width": 1280, "image_height": 760}, "keyframe_urls": {"10": "https://example.invalid/j_speech/som/000010.jpg", "30": "https://example.invalid/j_speech/som/000030.jpg"}, "plan": {"frames": {"30": [{"item_id": "i_4", "shape": "box", "box": [894, 193, 946, 257], "mask": null, "style": "pixelate", "grid": [894, 193, 9]}]}, "crowd_fills": []}, "transcript": {"status": "ok", "source": "muse-spark-1.2", "source_kind": "fallback", "degraded": false, "turns": [{"speaker": "S1", "start": 1.2, "end": 1.8, "text": "Welcome back to the market."}]}, "scene": {"status": "ok", "model": "muse-spark-1.3", "summary": "walk-and-talk vlog in a market", "participants": [{"description": "man holding the camera", "evidence": "talks to camera throughout", "speaker": "S1", "introduced_in_turn": null, "introduction_quote": null, "is_creator": true}], "children": [], "others_present": "shoppers passing behind the host", "candidate_objects": []}}
```

**`job-review-cafe.json`** (the context test; the fields not shown are as in the hero mock, with `job_id: "j_cafe"`, the same 12-frame `job` and transcript, and a `scene` with `participants: [{"description": "the host", "evidence": "speaks to camera", "speaker": "S1", "introduced_in_turn": null, "introduction_quote": null, "is_creator": true}]` (the roles track `face:1` has `matches_participant: 0`, so the host's keep is linked to speech and PRE-A's `hold: "no_speech_link"` doesn't apply), `children: []`, `others_present: "café customers at other tables"` and `candidate_objects: [{"what": "two laptop screens", "approx_time": "throughout"}]`, so the host's transcript lines are marked "said by Face 1"):

```json
{
  "items": [
    {"item_id": "i_1", "track_ids": ["face:1"], "kind": "person", "decision": "keep",
     "reason": "the host: speaks to camera throughout", "evidence_frames": [2, 7],
     "style": null, "decided_by": "policy", "locked": false, "removed_by_creator": false},
    {"item_id": "i_5", "track_ids": ["screen:2"], "kind": "screen", "decision": "hide",
     "reason": "laptop showing an email inbox with names", "evidence_frames": [4],
     "style": "solid", "decided_by": "policy", "locked": false, "removed_by_creator": false},
    {"item_id": "i_6", "track_ids": ["screen:3"], "kind": "screen", "decision": "needs_you",
     "reason": "menu, nothing personal", "evidence_frames": [4, 7],
     "style": "solid", "decided_by": "policy", "locked": false, "removed_by_creator": false}
  ],
  "tracks": [
    {"track_id": "face:1", "concept": "face", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"2": [300, 120, 370, 210], "7": [305, 121, 375, 211]}},
    {"track_id": "screen:2", "concept": "screen", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"4": [700, 400, 900, 520]}},
    {"track_id": "screen:3", "concept": "screen", "first": 0, "last": 11, "reentry_of": null,
     "boxes": {"4": [950, 410, 1150, 530], "7": [950, 410, 1150, 530]}}
  ],
  "roles": {"status": "ok",
    "tracks": [{"track_id": "face:1", "role": "participant", "votes": ["participant", "participant", "participant"], "escalated": false,
                "suggested_role": null, "escalation_evidence": null, "escalation_frames": null, "matches_participant": 0, "evidence": "speaks to camera at F 000002 and F 000007", "frames": [2, 7]}],
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

*(proposal)* fields beyond ARCHITECTURE §3: `job_id`, `mode`, `status`, `stage`, `progress` (0–1), `deletes_at`, `retry_at`, `code_valid_until` (ISO UTC, `null` = no limit; request 20), `job.prepared_url`, `keyframe_urls` (frame → signed URL), `items[].removed_by_creator` (§8 request 9), `keyframe_geometry` (§8 request 13), `failure: {stage, reason}` (§8 request 1), `roles.tracks[].escalation_evidence` and `escalation_frames` (§8 request 3), and on review edits `edit_id` plus `reverts` (§8 request 5). **PRE-A's additions** (decided in its prompt specs; WP0 adds them to `contracts.py`): `roles.tracks[].matches_participant` (role-pass.md) and `suggested_role` (escalation.md); `scene.participants[].is_creator`, `introduced_in_turn` and `introduction_quote`, `scene.children[]`, `scene.others_present`, and the `approx_time` enum on `scene.candidate_objects[]` (scene-pass.md); `status` on `scene`, `roles` and `transcript`; `decisions.items[].hold`, `origin` and `audit_label`; and the rest of PRE-A `docs/API-NOTES.md` §12's contract rows. Everything else is the ARCHITECTURE §3 contract shape.

**Mock invariants** (a mock test checks them): `job.fps` is an integer from 1 to 30; `times` has `frames` entries, all finite and non-decreasing (§3.6); every frame number is in `[0, frames − 1]`; every `track_ids` entry exists in `tracks`; every evidence frame is in `roles.keyframes` and in `keyframe_urls`, with a box for the item's primary track on that frame (except `origin: "static"` and `origin: "audit_patch"` items, which have no keyframe, PRE-A §12 and §4.3); every `plan` region's `item_id` exists; every `reentry_of` names an existing track; every item has `removed_by_creator`; `keyframe_geometry` has `image_width = frame_width = job.width`, `frame_height = job.height` and `image_height = frame_height + bar_h` (except in the keyframe-mismatch fixture); `transcript` has `degraded` and `source_kind` (`null` only when `job.audio` is `false`); `scene`, `roles` and `transcript` each carry `status` (`"ok"` unless the mock is about that stage failing; required by PRE-A §12); `scene` has every field of PRE-A's scene-pass.md schema; every `roles.objects[]` entry names an existing track. `example.invalid` is a reserved non-resolving domain, so a mock can never fetch real media. **Component tests never fetch it either:** they stub image and video loading, and the stub reports a natural size for each URL (default: `image_width × image_height` from `keyframe_geometry`; a fixture can override it, as the keyframe-mismatch one does), so "didn't load" and "size doesn't match" are separate, testable states. **Every `needs_you` or `hide` item in a mock has a `plan` region on at least one of its evidence frames** (for `origin: "static"` items, which have no evidence frames, on at least one frame of the item's span; an `audit_patch` item's one evidence frame is its finding frame, PRE-A §12, which its span covers); **every audit-added item in a mock has `origin: "audit_patch"` and an `audit_label` `A<n>`**, and **`has_render` is `true` in every job mock whose `result.video_url` is set** (so the `needs_you` mocks, `result-audit-*.json`, get the §5.3 delete confirm, §3.5).

### 10.2 Input validation (`/try`)

The client checks these for fast feedback; **the server enforces the same limits** (WP5), because the client can be bypassed.

| Field | Rule | Trigger | Copy (§2.6) | Focus |
|---|---|---|---|---|
| Access code | The input is **masked**: `type="text"` with CSS `-webkit-text-security: disc` (Chrome, Safari), `autocomplete="off"`, `autocapitalize="off"`, `spellcheck="false"`, and a "Show" toggle button, so a screen recording or a shoulder never shows a code. Not `type="password"`: Chrome ignores `autocomplete="off"` on password fields and offers "Save password?", whose bubble would cover the drop zone in shot 3.1 and store the code in the browser. Browsers without `text-security` show the code in clear, which is acceptable because the recordings use Chrome and the code is typed before recording starts (STORYBOARD SR-01). Trim whitespace; must be non-empty; `maxlength="64"` on the input (longer input can't be typed or pasted beyond 64 characters). No other format check: only the server knows valid codes | Continue pressed | Empty: "Enter your access code." · `401`: "That code didn't work. Check it and try again."; `401 code_not_active`: the §2.6 "Code outside its dates" copy. Continue sends `POST /v1/codes/check` (request 21) and moves to step B only on `200` | Stay on the field; on `401` select its text, except for `code_not_active`, which keeps the text unselected |
| File count | Exactly one file | Drop or choose | More than one: "Drop one clip at a time." (nothing is kept) | The drop zone's "Choose a file" button |
| File type | Extension `.mp4` or `.mov` (case-insensitive) **and** MIME `video/mp4` or `video/quicktime`. If either check fails, reject. An empty MIME string (some browsers) counts as a fail only if the extension also fails | Drop or choose | "Safe Cut takes MP4 or MOV video files." | "Choose a file" button |
| File size | `size ≤ 157,286,400` bytes (= 150 × 1024 × 1024; WP5 must use the same number). Shown as `{size}` = bytes ÷ 1,048,576, rounded **up** to 1 decimal (157,286,401 bytes → "150.1"), so the number shown is never ≤ the limit | Drop or choose | "This file is {size} MB. The limit is 150 MB." | "Choose a file" button |
| Duration | Read `duration` from a hidden `<video preload="metadata">`. Reject if `duration > 60.05` s (60 s plus a 0.05 s tolerance for container rounding). **The server uses the same rule** (`duration > 60.05` s → `too_long`; a request to WP5 under request 17), so the client and server agree on every clip; ARCHITECTURE §5's "≤60 s" is read as this rule. If the metadata hasn't loaded within 10 s, or `duration` is `NaN` or `Infinity`, don't show a client error: `prepare` decides after upload (`failure.reason: "too_long"` with `failure.duration_s`, §2.6). `{duration}` is shown in seconds, rounded **up** to 1 decimal (60.06 s → "60.1"), from the client metadata or from `failure.duration_s`; if neither exists, the copy is "This clip is longer than 60 seconds. Trim it and try again." | After the file is accepted by the checks above | "This clip is {duration} seconds long. The limit is 60 seconds. Trim it and try again." | "Choose a file" button |
| Rights tick | Must be ticked | Start pressed | "Tick the box to confirm you can use this clip." | The checkbox |

The Start button is enabled once a file passes every check above, but pressing it with the box unticked shows the rights message (so the requirement is announced rather than silently blocking the button). Errors are announced through the live region and tied to their field with `aria-describedby` (§2.8).

### 10.3 Errors, retries and timeouts

| Situation | Detection | Copy | Action | Retry policy |
|---|---|---|---|---|
| Wrong code | `401` (any `error.code` except `code_not_active`) on `POST /v1/codes/check`, or on `POST /v1/jobs` / `POST /start` from `/try` (revoked after Continue) | §2.6 "That code didn't work. …" | step A: stay; step B: the §2.6.1 step-B refusal | none (user retries) |
| Code revoked, job page | `401` (including `code_not_active` for any code past its window) on `POST /start`, `POST /render` or `POST /audit` of an existing job | §2.6 "The access code for this clip no longer works …" | the §2.6.1 job-page refusal (§3.5 row 0 on the review page) | none |
| Code outside its dates | `401` `code_not_active` on `POST /v1/codes/check` (step A), or on `POST /v1/jobs` or `POST /start` from `/try` (step B, the window closed meanwhile); on a job page it's the "Code revoked, job page" row above | the §2.6 "Code outside its dates" row, chosen by the dates | step A: stay; step B: the §2.6.1 step-B refusal | none (user retries) |
| Too large (before upload) | `413` `too_large` on `POST /v1/jobs` (it takes `size_bytes`, request 17) | §2.6 matching row | back to step B | none |
| Too long, too large or unreadable (found in `prepare`) | `failure.reason` `too_long` / `too_large` / `bad_media` | §2.6 matching row | [Try another clip] → `/try`; [Delete now] | none |
| Job cap | `422` `job_cap` on `POST /start` (PRE-A §10.3: the job cap can't cover the job's estimate; not retryable) | §2.6 "This clip would cost more than the per-clip limit …" | on `/try`: `DELETE` the job, back to step B; on a job page: §2.6.1 job-page cap line, button disabled, no `DELETE` | none |
| Delete | any answer to `DELETE /v1/jobs/{id}` | `2xx` or `404` (any code) → page state `deleted` (§10.4); a `429` → §2.6 "Too many tries …" next to the delete control, which re-enables after `Retry-After` (or 60 s); any other non-2xx or a timeout → §7 "Something went wrong on our side. …" next to the delete control, the page keeps its state | the creator presses delete again. On `/try`: step C's [Cancel and delete] behaves the same; the **automatic** step-B delete (§2.6.1) fails silently and the 24 h cleanup removes the job | none automatic |
| Job expired | `404` with `code: "expired"` on a job route (except `DELETE`, row above) | §7 "This clip has been deleted. …" | [Try another clip] | none |
| Job not found | `404` with any other code on a job route | §7 "We couldn't find that clip. …" | [Try another clip] | none |
| Meta busy, retrying later | `status: "retry_later"` (WP5 retries once; a second failure becomes `failed` + `upstream`) | §2.6 "Meta's service is busy right now. …" | stay on the page; [Copy link] · [Cancel and delete] | poll every **30 s**, or once at `retry_at` if the API gives one *(proposal)*; the page moves on when the status changes |
| Stage failed | `status: "failed"` + `failure: {stage, reason}` *(proposal, WP5; reason names: `job_cap` and `daily_cap` split PRE-A §10.3's `BudgetExceeded` by cap, the others are proposals)* | the §2.6 row for that `reason`, filled with the stage's §2.5 row label | Only when `reason` is `internal`, `upstream` or `code_cap` (the last works once the owner raises the code's cap), or `failure` is missing, or `daily_cap` (labelled [Try again tomorrow], shown at once but disabled until `retry_at`, or hidden by the §2.6.1 expiry rule, as in §2.6): [Try again] = `POST /render` if the failed stage is `render`, `audit` or `receipt` (re-render with the creator's decisions); otherwise `POST /start` *(proposal, WP5)*. Every other reason: no [Try again]. Always [Delete now] | none automatic |
| Cap reached on an action (`429` with `code_cap`, `pilot_pool_cap` or `daily_cap`, on **any** of `POST /v1/jobs`, `POST /start`, `POST /render`, `POST /audit`) | `429` + `error.code` | the §2.6 row for that code (`daily_cap` → "Safe Cut has reached today's limit…"; `code_cap` → "This access code doesn't have enough budget left for this clip. Ask the person who gave it to you to add more, then press Start again." on `/try`, or "This access code ran out of budget." next to the button elsewhere; `pilot_pool_cap` → "The pilot budget has been used up…") | the button that sent it stays enabled for `code_cap` (pressing it re-sends the same request); disabled until `retry_at` for `daily_cap` (hidden under the §2.6.1 expiry rule); disabled for `pilot_pool_cap` (on `/try` the created job is deleted; never on a job page, §2.6.1) | none automatic |
| Run the audit again | `POST /v1/jobs/{id}/audit` → `202` (mock `audit-ack.json`) | the bar becomes the render stages: `Checking the result`, alternating with `Covering what the check found` while an auto-patch renders (`stage: render`, `stage_reason: audit_patch`), then `Writing your privacy receipt`; polling resumes | `409` (already running) → **resume polling**, no message | — |
| Rate limited on an action (`429` `rate_limited` on any `POST` except `POST /review`, next row; `DELETE` has its own row) | `429` + `code: "rate_limited"` | §2.6 "Too many tries in a short time. …" | the button is disabled until `Retry-After` when given, or for 60 s without one | none automatic |
| Edit rejected | `POST /review` non-2xx, or timeout | §3.7 "That change didn't save. …"; for a `429` `rate_limited`, the toast is §2.6 "Too many tries in a short time. Wait a minute and try again." instead | chip reverts (§10.5 `SERVER_REJECT`) | **none automatic**: the creator presses [Try again] |
| Rate limited while polling | `429` on `GET /v1/jobs/{id}` | none (silent) | polling waits for `Retry-After` (or 60 s without one), then resumes on its normal schedule | one wait, then normal polling |
| Render already running | `409` on `POST /render` | no message | keep polling | n/a |
| Network error or timeout on a GET | fetch rejects, or no response in **15 s** | after 3 failed retries: §7 "Safe Cut's service isn't responding right now. …" | [Try again] restarts polling | retry after 2 s, 4 s, 8 s; then stop and show the message |
| Upload stalls or fails | no progress event for **30 s**, or the `PUT` errors | §2.6 "The upload stopped. …" | [Try again]: `DELETE` the job, then `POST /v1/jobs` and a new upload (the signed URL is never reused, request 17) | none automatic |
| Upload incomplete | `409` `upload_incomplete` on `POST /start` | §2.6 "The upload didn't finish, so nothing was processed. …" | [Try another clip]; the job is deleted once | none |
| Final check unavailable | `503` `auditor_unavailable` on `POST /start` (PRE-A §12) | §2.6 "Safe Cut's final check isn't available right now …" | on `/try` as §2.6; on a job page (a failed job's [Try again]) the same copy next to the button, which stays enabled; never a `DELETE` | none automatic |
| Meta credits ran out | `503` `billing` on `POST /start` (PRE-A §10.3, vector R13) | §2.6 "Safe Cut can't start new clips right now. Try again later." | as the row above | none automatic |
| Anything else | other `5xx` (except on `DELETE`, the Delete row, and `503 auditor_unavailable` and `503 billing`, the rows above), malformed JSON, failed `times` check (§3.6) | §7 "Something went wrong on our side. …" | [Try again] · [Go to the home page] | none automatic |

- **Timeouts:** every JSON request is aborted after 15 s (`AbortController`). Uploads have no overall timeout, only the 30 s stall rule. A timed-out `POST /v1/codes/check`, `POST /v1/jobs`, `POST /start`, `POST /render` or `POST /audit` re-enables its button and shows §7 "Safe Cut's service isn't responding right now. …" next to it; for `/start`, `/render` and `/audit` polling resumes too, so a request the server did accept shows up on the next `GET` (a re-pressed `POST /render` is then answered `409`, §10.3).
- **Polling (the one authoritative rule):** `GET /v1/jobs/{id}` every 2 s for the first 60 s of a page view, then every 5 s, in `processing` (every stage, `queued` included) and in `rendering`; every **30 s** in `retry_later`. It **pauses** in `review` and `needs_you`, and **resumes** as soon as `POST /start` (including from `failed` via [Try again] or [Try again tomorrow]), `POST /render` or `POST /audit` (answered `202` or `409`) is sent. After an edit made at `?view=review` in `done` is acknowledged with `status: "review"`, the job sits in `review` and polling stays paused until a render. It **stops** in `done`, `failed`, `expired`, `not_found` and `created`, until one of the requests above restarts it. In `deleted` it stops for good, and no request restarts it (§10.4). Independently of state, it stops while the tab is hidden (`visibilitychange`) and resumes immediately when it's visible again.
- **Idempotency:** each review edit carries an `edit_id` (a UUID v4 made in the browser) *(proposal; request to WP5)*. A manual retry resends the same `edit_id`, so the server can't apply it twice. An `undo` is a new edit with a new `edit_id`, pointing at the edit it reverts through `reverts` (§10.5). `POST /render` is protected by disabling the button until the response, plus the `409` rule.
- **Logging:** errors go to the console with the job ID and the HTTP status, never the access code or signed URLs.

### 10.4 Job page state machine

| State | Entered when (`GET /v1/jobs/{id}`) | Route that renders it | Shows |
|---|---|---|---|
| `loading` | before the first response | either route | skeleton: video box and three empty columns, no spinner over text |
| `created` | `status: "created"` (the job exists, but its upload never finished or `POST /start` was never sent; *proposal*, §8 request 17) | either route | "This clip hasn't finished uploading. Upload it again to start." [Upload again] → `/try`. No polling |
| `processing(stage)` | `status: "processing"`, `stage` ∈ `queued`, `prepare`, `track`, `transcribe`, `scene`, `roles`, `miss_loop`, `decide`, `guard` | `/jobs/[id]` | §2.5 stage list (as on `/try` step C) |
| `retry_later(stage)` | `status: "retry_later"` | `/jobs/[id]` (and `/try` step C) | §2.6 "Meta's service is busy right now. …" above the §2.5 stage list, with the waiting stage marked; polling every 30 s (§10.3). WP5 retries once; if that fails, the job becomes `failed` with `upstream` |
| `review` | `status: "review"` | `/jobs/[id]` | §3 review panel |
| `rendering(stage)` | `status: "rendering"`, `stage` ∈ `render`, `audit`, `receipt` | `/jobs/[id]` · `/jobs/[id]/result` | on `/jobs/[id]`: review panel, read-only, with the render stages in the bottom bar (§3.5); on `/result`: §5.4 "Rendering (arrived early)" |
| `done` | `status: "done"` | `/jobs/[id]/result`; also `/jobs/[id]?view=review` | on `/result`: §5. On `/jobs/[id]?view=review`: the §3 review panel, **editable** (reached only from "Back to review" or "[Review them]"). The first edit there is sent as usual; the server moves the job back to `review` *(proposal, §8 request 5)*, and the bottom bar shows §3.5's "You changed something after rendering. …" until a new render finishes |
| `needs_you` | `status: "needs_you"` (PRE-A §10.3: an audit pass couldn't run or finish; `audit.blocked_reason` is `audit_failed` or `over_budget`) | `/jobs/[id]` (`/result` redirects here) | §3 review panel, **read-only**, with the §5.3 audit banner and the §3.5 `needs_you` bar: [Run the audit again] (`POST /audit` → `rendering`, stages `audit` ↔ `render` (auto-patch, `stage_reason: audit_patch`) then `receipt`, ending in `done` (clean or with `unresolved_leaks`) or back in `needs_you`; [Delete everything now] → `DELETE` is always available; polling resumes as for any render), [Download this version], [Delete everything now]; for `audit_budget_cause: "job_cap"` only [Download this version], [Delete everything now] and [Try another clip]. Polling is paused while in `needs_you` |
| `failed(stage)` | `status: "failed"` | either route | §2.6 stage-failure message with that stage's §2.5 label; [Try again] per §10.3 |
| `expired` | `404` with `code: "expired"` | either route | §7 "This clip has been deleted. …" |
| `deleted` | this page's own `DELETE /v1/jobs/{id}` got a 2xx (any prior state) | either route | §2.6 "After delete": "Deleted. Nothing from this clip is kept." with a link to `/try`. **Polling stops at once and every later response for this job is ignored**, so a `404` from an in-flight `GET` can't replace it with the §7 expiry copy. A `404` (any code) on `DELETE` also counts as success, because the job is gone either way. A `429` on `DELETE` follows the §10.3 Delete row (rate-limit copy, control re-enabled after `Retry-After` or 60 s). If the `DELETE` gets any other non-2xx or times out, the page stays in its previous state and shows the §7 "Something went wrong on our side. …" error next to the delete control; the creator can press it again |
| `not_found` | `404` with any other code | either route | §7 "We couldn't find that clip. …" (the route-level 404 "We couldn't find that page." is only for unknown URLs) |

Transitions follow the server: `loading → created → processing` (`created` only when the upload or start never happened), `loading → processing → review → rendering → done`; `processing` or `rendering` can go to `retry_later` and back to the same stage; `rendering` (stage `audit`) can go to `needs_you`; `needs_you → rendering` (stage `audit` ↔ `render` with `stage_reason: "audit_patch"`, then `receipt`) `→ done` (clean, or with `blocked_reason: "unresolved_leaks"`) `| needs_you` (the pass failed or ran over budget again) on [Run the audit again] (`POST /audit`); `needs_you →` deleted on `DELETE`; edits are never accepted in `needs_you`, and it has no path back to `review`; `retry_later → failed` (`upstream`) when the one re-queue also fails; any state can go to `failed` or `expired`. `/jobs/[id]/result` in `retry_later` redirects to `/jobs/[id]`, like `processing`. **Redirects** (with `router.replace`, so Back doesn't bounce): `/jobs/[id]` in `done` → `/jobs/[id]/result`, **except** with `?view=review`, which stays on the review panel; `/jobs/[id]/result` in `processing`, `review` or `needs_you` → `/jobs/[id]`. `/result` in `rendering` doesn't redirect: it shows §5.4's "Rendering (arrived early)" and moves on to the result when the job is `done`. Neither route redirects in `failed`, `expired` or `not_found`. Query parameters (`?from=sigmora`, `?demo=1`) are kept across redirects; `view=review` is dropped when a redirect leaves the review route. Because an edit made in `done` moves the job to `review`, `/result` then redirects to the review panel, so Publish can't be reached with a stale video and receipt.

### 10.5 Review reducer

**State** *(per job)*: `items: Record<item_id, {label, track_ids, decision, decided_by, locked, kind, role, reentry_target: item_id | null, merged_into: item_id | null, removed: boolean}>`, where `removed` is read from the server's `items[].removed_by_creator` (§8 request 9) and survives `SERVER_ACK` and reloads. `label` is the §0 display label; `role` is the item's primary-track role from `roles.json`, or `null` for objects; `reentry_target` is the item that owns the track named by one of this item's tracks' `reentry_of`, or `null`. Derived, never stored: an item is **visible in the columns** when `merged_into = null`; an item's **effective decision** is its target's when `merged_into` is set; its **tracks shown** are its own plus those of every item merged into it. Also: `status` (the job status from the last `GET` or `SERVER_ACK`; there is no separate `rendering` flag), `has_render` (from the job response, §8 request 1), `readOnly: boolean` = `status ∈ {rendering, needs_you}` (derived, never stored), `pending: Record<edit_id, {edit, prev}>`, `undo: Edit[]` (unlimited within the page session; each toast's [Undo] undoes **that** edit and only appears while the toast is visible, 6 s; **only one edit toast shows at a time**: a new toast, including "Undone.", replaces the previous one, and undoing an edit by any route dismisses its toast, so a visible [Undo] always targets the top of `undo`; **push rule:** every edit-sending action (`KEEP` for a person, `CONFIRM_KEEP`, `HIDE`, `MERGE`, `REMOVE_PERSON`, `COVER_SPOT`) pushes its edit onto `undo` when it's sent, and the toast's [Undo] is disabled while that edit is pending), `confirm: {item_id} | null` (the object keep confirm, for every object kind: screen, document, plate and other; §3.4), `spots: Record<spot_id, {first, last, boxes, covered_by: item_id | null}>` (from `audit.spots[]` in the last `GET` or `SERVER_ACK`), `refusal: {code, until: timestamp | null} | null` (§3.5 rule 0: set by a blocking refusal of `POST /render` or `POST /audit`; `until` is `retry_at` (or `null` under the §2.6.1 expiry rule), or `Retry-After` / 60 s for `rate_limited`, or `null` = until reload; cleared at `until` or on reload, never by `SERVER_ACK` or a `GET`), and `capNote: {button: "render" | "audit"} | null` (the `code_cap` note above the bar; cleared only by `ACTION_ACK` for that button, never by `SERVER_ACK` or a `GET`; **not set** while the job is `needs_you` with `audit_budget_cause: "code_cap"`, because the §5.3 banner and §3.5 row 2 already say "This access code ran out of budget."). Both are page-session state, not stored on the server.

**Guards on every mutating action** (`KEEP`, `CONFIRM_KEEP`, `HIDE`, `MERGE`, `REMOVE_PERSON`, `UNDO`, `COVER_SPOT`): `readOnly` is false, and no edit is pending on any item the action touches (for `MERGE`, both `src` and `dst`). If a guard fails, nothing changes and **no request** is sent; while `status` is `rendering`, the note "Changes are paused while we render." shows; in `needs_you` no note shows (the banner and the §3.5 bar explain why).

**Actions and preconditions** (on top of the guards; otherwise: no state change, **no request**):

| Action | Precondition | Effect |
|---|---|---|
| `KEEP(id)` | `merged_into = null`; not `locked`; `decision ≠ keep` | object kinds (`plate`, `screen`, `document`, `other`; §0 Item kind): sets `confirm = {id}` only; no request yet. People (`person`): `decision = keep`, `decided_by = creator`, **`removed = false`**, edit sent |
| `CONFIRM_KEEP` | `confirm` is set and its item still passes `KEEP`'s precondition | `decision = keep`, `decided_by = creator`, `removed = false`, edit sent; `confirm = null` |
| `CANCEL_CONFIRM` | `confirm` is set | `confirm = null`; nothing sent |
| `HIDE(id)` | `merged_into = null`; `decision ≠ hide` | `decision = hide`, `decided_by = creator`; items merged into it follow (effective decision); edit sent |
| `MERGE(src, dst)` | **all of:** `src ≠ dst`; `src.kind = person`; `src` not `locked`; `src.merged_into = null`; `src.reentry_target` is set **and** that item is `kind = person`, `decision = keep`, `role = participant` (this is when the chip offers the merge, §3.3); `dst.kind = person`; `dst.decision = keep`; `dst.role = participant`; `dst` not `locked`; `dst.merged_into = null` | `src.merged_into = dst`, `decided_by = creator`; `src` leaves the columns; `dst` shows `src`'s tracks (time range, overlay, drawer); header counts drop by one; edit sent |
| `REMOVE_PERSON(id)` | `kind ∈ {person, child}` and `track_ids` non-empty (audit-added items have none, §0) (sent only after the §3.4 dialog's [Remove]) | `removed = true`, `decision = hide`, style shown as Whole person covered; on a kept participant this hides them; edit sent |
| `COVER_SPOT(spot_id)` | `readOnly` is false; no pending edit; the spot exists in `spots` and its `covered_by` is `null` | `spots[spot_id].covered_by` is set optimistically to a pending item, and the chip leaves Needs you and shows under Hidden as a pending audit-added item carrying the `spot_id` (label `A?` until `SERVER_ACK` assigns the next `A` number and the server's `covered_by`); one `cover_spot` request with a new `edit_id`; pushed to `undo` (undo sends an `undo` edit with `reverts`, which brings the spot back as `U{n}`) |
| `UNDO(edit_id)` | the edit is in `undo` and isn't pending | restores that edit's `prev` locally (for a merge: `src` back as a separate hidden NEW item with its own tracks) and sends an `undo` edit with **its own new `edit_id`** and `reverts: <edit_id of the edit being undone>`, which enters `pending` with `prev` = the state just before the undo (so a reject re-applies the undone edit); the server restores the prior state (§8 request 5) *(proposal, WP3/WP5)*. Reusing the original `edit_id` would make the server's idempotency check (§10.3) treat the undo as a retry of the original and silently ignore it. **Stack rule:** the undone edit is removed from `undo` when the `undo` edit is sent (and put back **at its original position** in `undo` if that edit gets `SERVER_REJECT`), and the `undo` edit itself is never pushed onto `undo` (there's no redo). So repeated `Ctrl+Z` steps back one edit at a time |
| `SERVER_ACK(edit_id, items, plan, status, has_render, spots)` | edit is pending | drop from `pending`; set `status` (and so `readOnly`), `has_render` and `spots` from the server; replace items and plan with the server's (after a merge, the server's `dst` already holds `src`'s `track_ids` and `src` is gone; because the re-entry track now belongs to the same item, `dst` shows no NEW badge, §3.3) |
| `SERVER_REJECT(edit_id)` | edit is pending | drop it from `pending`; restore `prev`; keep the rejected edit for the toast's [Try again]; remove the edit from `undo` (an `undo` edit instead follows the stack rule's put-back); show the §3.7 edit-failed toast |
| `RETRY(edit_id)` | the edit-failed toast's [Try again] for a rejected edit (§3.7, §10.3) | re-run the original action's guards and precondition against the current state; if they fail, dismiss the toast and send nothing. Otherwise re-apply its optimistic effect, put it in `pending` with a fresh `prev`, and resend it with the **same `edit_id`** (§10.3 idempotency). A normal edit is pushed onto `undo` again (push rule); a rejected `undo` edit removes its target from `undo` again |
| `ACTION_ACK(button, status)` | a `POST /render` or `POST /audit` from this page got a `202` (`render-ack.json`, `audit-ack.json`) | `status` = the response's status (`rendering`); `capNote = null` when `capNote.button` = `button`; polling resumes (§10.3) |
| `ACTION_REFUSE(button, code, until)` | a `POST /render` or `POST /audit` from this page got a **blocking** answer (§3.5 rule 0: a `401`, or a `429` `pilot_pool_cap`, `daily_cap` or `rate_limited`) | `refusal = {code, until}`, with `until` as defined under State; `capNote` unchanged; nothing re-sent |
| `ACTION_CAP(button)` | that request got `429 code_cap` | `capNote = {button}`, unless the job is `needs_you` with `audit_budget_cause: "code_cap"` (then nothing changes); `refusal` unchanged (`code_cap` is never blocking) |
| `REFUSAL_EXPIRED` | `refusal.until` is set and the clock reaches it (one timer per page) | `refusal = null`; the bar follows rules 1–8 (R25) |

Children are never `MERGE` sources or targets: a child is `kind = child`, which fails both `kind = person` checks, and is `locked`.

**Reducer fixture** (`web/mocks/reducer-state.json`). This is the reducer's input state, not an API response, so the API-mock invariants in §10.1 don't apply to it. Unless a row names another mock, every R-row starts from this state, with `status: "review"`, `has_render: false`, no pending edits and an empty `undo` list. It uses the same item IDs and labels as the hero mock, plus the extra items the merge cases need:

```json
{"items": {
  "i_1": {"label": "Face 2", "track_ids": ["face:2", "person:1"], "decision": "keep", "decided_by": "policy", "locked": false, "kind": "person", "role": "participant", "reentry_target": null, "merged_into": null, "removed": false},
  "i_2": {"label": "Face 4", "track_ids": ["face:4"], "decision": "hide", "decided_by": "policy", "locked": true, "kind": "child", "role": "child", "reentry_target": null, "merged_into": null, "removed": false},
  "i_3": {"label": "Plate 1", "track_ids": ["license plate:1"], "decision": "hide", "decided_by": "policy", "locked": false, "kind": "plate", "role": null, "reentry_target": null, "merged_into": null, "removed": false},
  "i_4": {"label": "Face 6", "track_ids": ["face:6"], "decision": "needs_you", "decided_by": "model", "locked": false, "kind": "person", "role": "unsure", "reentry_target": null, "merged_into": null, "removed": false},
  "i_5": {"label": "Face 5", "track_ids": ["face:5"], "decision": "hide", "decided_by": "policy", "locked": false, "kind": "person", "role": "bystander", "reentry_target": null, "merged_into": null, "removed": false},
  "i_7": {"label": "Face 7", "track_ids": ["face:7"], "decision": "keep", "decided_by": "creator", "locked": false, "kind": "person", "role": "bystander", "reentry_target": null, "merged_into": null, "removed": false},
  "i_8": {"label": "Face 8", "track_ids": ["face:8"], "decision": "hide", "decided_by": "policy", "locked": false, "kind": "person", "role": "bystander", "reentry_target": "i_5", "merged_into": null, "removed": false},
  "i_9": {"label": "Face 9", "track_ids": ["face:9"], "decision": "hide", "decided_by": "policy", "locked": false, "kind": "person", "role": "unsure", "reentry_target": "i_1", "merged_into": null, "removed": false}
}, "confirm": null, "pending": {}, "undo": [], "status": "review", "has_render": false, "spots": {}, "refusal": null, "capNote": null}
```

`reentry_target` is the item that owns the track named in the re-entry track's `reentry_of` (i_9's `face:9` has `reentry_of: face:2`, which belongs to i_1; i_8's `face:8` has `reentry_of: face:5`, which belongs to i_5).

**Test cases** (expected state and UI after the action):

| # | Initial | Action | Expected |
|---|---|---|---|
| R1 | café mock: i_6 menu screen, needs_you | `KEEP(i_6)` | `confirm = {i_6}`; inline "Only keep this clear if nothing on it is personal."; no request yet |
| R2 | R1 state | `CONFIRM_KEEP` | i_6 keep, creator; chip in Kept clear; toast "Screen 3 will be kept clear. [Undo]"; one request; `confirm = null` |
| R2b | R1 state | `CANCEL_CONFIRM` | i_6 unchanged (needs_you); `confirm = null`; no request |
| R2c | hero mock: i_3 plate, hide | `KEEP(i_3)` | `confirm = {i_3}`; inline "Only keep this clear if nothing on it identifies anyone."; no request yet (every object kind confirms, §3.4) |
| R2d | R2c state | `CONFIRM_KEEP` | i_3 keep, creator; toast "Plate 1 will be kept clear. [Undo]"; one request |
| R3 | i_2 locked child | `KEEP(i_2)` | no change; **no request**; no toast (the button isn't rendered; this guards keyboard and devtools paths) |
| R4 | i_4 needs_you | `HIDE(i_4)` | hide, creator; chip in Hidden; toast "Face 6 will be hidden. [Undo]" |
| R5 | R4 state (acknowledged) | `UNDO(R4)` | i_4 back to needs_you, decided_by model; chip in Needs you; toast "Undone."; one `undo` edit sent with a new `edit_id` and `reverts` = R4's `edit_id` |
| R6 | i_1 keep | `HIDE(i_1)` twice quickly (double-click) | one state change, **one request** (the second fails the pending-edit guard) |
| R7 | i_4 needs_you | `KEEP(i_4)` | keep, creator; Kept clear; toast "Face 6 will be kept clear. [Undo]" |
| R8 | reentry mock: i_9 (`face:9`, hidden, `reentry_of: face:2`) and i_1 (`face:2`, kept guest) | `MERGE(i_9, i_1)` | `i_9.merged_into = i_1`; i_9 leaves the columns; i_1's range and overlay include `face:9`; header counts drop by one; toast "Face 9 merged into Face 2. They'll be kept clear like Face 2. [Undo]"; one request |
| R8b | R8 state (acknowledged: server returns i_1 with `track_ids` `[face:2, person:1, face:9]`, no i_9) | `HIDE(i_1)` | i_1 hide, creator; the overlay covers `face:9`'s frames too; no NEW badge on i_1; toast "Face 2 will be hidden. [Undo]" |
| R9 | R8 state (acknowledged) | `UNDO(R8)` | i_9 back in Hidden as its own item with `face:9`, NEW again with [Same as Face 2…]; i_1's range back; header counts back; toast "Undone."; one `undo` edit sent with a new `edit_id` and `reverts` = R8's `edit_id` |
| R9b | reducer fixture (i_8 re-entry of the hidden bystander i_5; i_1 kept guest); the chip is checked against the reentry-bystander mock | render the chip, then `MERGE(i_8, i_1)` | chip shows "The tracker lost this person and found them again. They stay hidden." and no merge button; the action is rejected (`reentry_target` isn't a kept participant); no request |
| R10 | i_9, i_2 child | `MERGE(i_9, i_2)` | rejected; no request (child target) |
| R11 | i_2 child | `MERGE(i_2, i_1)` | rejected; no request (child source) |
| R12 | i_9, i_4 needs_you | `MERGE(i_9, i_4)` | rejected (target not kept) |
| R12b | i_9, i_7 a bystander the creator kept (`role = bystander`, keep) | `MERGE(i_9, i_7)` | rejected (target isn't a participant) |
| R12c | i_9 with an edit pending | `MERGE(i_9, i_1)` | rejected by the pending-edit guard; no request |
| R13 | i_1 kept participant | `REMOVE_PERSON(i_1)` (after the dialog's [Remove]) | i_1 hide, removed, Whole person covered; toast "Face 2 will be fully covered wherever they appear. [Undo]" |
| R13b | R13 state (acknowledged) | `KEEP(i_1)` | i_1 keep, creator, `removed = false` (the edit clears `removed_by_creator`); no confirm (a person); toast "Face 2 will be kept clear. They're no longer removed. [Undo]"; drawer shows "Kept clear by you", not the Removed sentence |
| R14 | i_4 needs_you | `HIDE(i_4)` then `SERVER_REJECT` | back to needs_you; `pending` empty; toast "That change didn't save. Check your connection and try again." with [Try again] |
| R14b | R14 state | [Try again] (`RETRY`) | i_4 hidden again; one request with the **same** `edit_id`; the edit is pending and on top of `undo` |
| R15 | i_4 needs_you | `HIDE(i_4)` then `SERVER_ACK` with server items | items replaced by the server's; plan replaced; overlay redraws from the new plan |
| R16 | `status = "rendering"` (`readOnly`) | any mutating action | rejected by the `readOnly` guard; no request; note "Changes are paused while we render." |
| R17 | replay mode | `HIDE(i_4)` | same behaviour; the request goes to WP5's replay API (§3.7 demo mode) |
| R18 | `done`, opened at `/jobs/[id]?view=review` (hero mock with `status: "done"`, `has_render: true`) | `HIDE(i_4)`, then `SERVER_ACK` with `status: "review"` (`has_render` stays true) | edit applied as usual; bottom bar "You changed something after rendering. Render again to update the video and receipt." with **Approve & render**; opening `/result` now redirects to the review panel, so Publish isn't reachable until the new render is `done` |
| R19 | `result-unresolved-review.json` (U1 uncovered) | `COVER_SPOT("s1")` | U1 leaves Needs you; a hidden `A?` item appears with `spot_id: "s1"`; `spots.s1.covered_by` is set; one request. While it's pending the bar is row 3, "Saving your changes…" (disabled). After `SERVER_ACK` the item is `A1`, `covered_by` is `A1`'s ID, the "unfixed spot(s) are visible" row no longer applies, and the bar is row 6, 7 or 8 for the new state (here row 6, Edited after rendering, since `has_render` is true) |
| R20 | R19 state, request pending | `COVER_SPOT("s1")` again (double-click) | rejected by the pending-edit guard; no second request |
| R21 | R19 state (acknowledged) | `UNDO` | one `undo` edit with its own `edit_id` and `reverts`; U1 back in Needs you; Approve & render disabled again |
| R22 | `result-audit-failed.json` (`needs_you`, `audit_failed`) | open the review page | read-only panel; banner "The final check couldn't finish on 4 frames…"; bar shows [Run the audit again], [Download this version] and [Delete everything now]; no Approve & render; no U chips |
| R23 | `result-audit-over-budget-jobcap.json` (`needs_you`, `over_budget`, `job_cap`) | open the review page; press Hide on any chip | banner "This clip used up its processing budget. You can download this version, or try a shorter clip."; bar shows only [Download this version], [Try another clip] and [Delete everything now]; the Hide is rejected by the `readOnly` guard, no request sent |
| R24 | `result-audit-failed-with-leak.json` (`needs_you`, `audit_failed`), with the undo stack **seeded** with one previously acknowledged edit (`HIDE(i_4)`, acked before the job reached `needs_you`) | `HIDE(i_1)`, `HIDE(i_4)`, `MERGE(i_4, i_1)`, `REMOVE_PERSON(i_1)`, `COVER_SPOT("s1")` and `UNDO` in turn; then read the bar. U1's leak exists and the stack isn't empty, so `COVER_SPOT` and `UNDO` can each be rejected only by `readOnly` | every action is rejected by `readOnly` with no request; the bar shows exactly [Run the audit again] and [Download this version] plus [Delete everything now] (no Approve & render, no other button) |
| R25 | `refusal = {code: "daily_cap", until: <retry_at>}` (bar row 0) | `HIDE(i_4)` then `SERVER_ACK` with `status: "review"`; then a polling `GET` | `refusal` unchanged, bar still row 0, Approve & render still disabled; at `until`, `refusal = null` and the bar follows rules 1–8 |
| R26 | `capNote = {button: "render"}` after `error-429-render-code-cap.json` | `POST /render` again, answered by `render-ack.json` → `ACTION_ACK("render", "rendering")` | `capNote = null`; `status = "rendering"`; bar row 1 (Rendering) |
| R27 | job in `rendering`, polling running | [Delete everything now] → confirm → `DELETE` answered by `delete-ok.json`; then an in-flight `GET` answers `error-404-expired.json` | page state `deleted`: "Deleted. Nothing from this clip is kept."; the late `404` is ignored; no further `GET` is sent |
| R28 | job in `review` | `DELETE` answered by `error-500-delete.json` | page stays in `review`; §7 "Something went wrong on our side. …" next to the delete control; pressing it again re-sends `DELETE` |
| R28b | job in `review` | `DELETE` answered by `error-404-delete.json` | page state `deleted` (a `404` on `DELETE` counts as success); no error shown; polling stopped |
| R29 | reducer fixture | `HIDE(i_4)`, `HIDE(i_1)` (both acknowledged), then `Ctrl+Z` twice (each `undo` edit acknowledged before the next) | i_1 back to keep, then i_4 back to needs_you; two `undo` edits sent, with `reverts` = the `HIDE(i_1)` and then the `HIDE(i_4)` `edit_id`; `undo` ends empty |
| R30 | reducer fixture | `HIDE(i_4)` (acknowledged; its toast showing), then `Ctrl+Z` | i_4 back to needs_you; the `HIDE` toast is replaced by "Undone." with no [Undo]; `undo` is empty |
| R31 | reducer fixture | `HIDE(i_4)` then `SERVER_REJECT`; then `Ctrl+Z` | i_4 back to needs_you; edit-failed toast; `undo` empty; the `Ctrl+Z` sends nothing |
| R32 | reducer fixture | [Approve & render] answered by `error-429-render-daily-cap.json` → `ACTION_REFUSE("render", "daily_cap", <retry_at>)` | `refusal = {code: "daily_cap", until: <retry_at>}`; bar row 0; then R25's expectations |
| R33 | reducer fixture | [Approve & render] answered by `error-429-render-code-cap.json` → `ACTION_CAP("render")` | `capNote = {button: "render"}`; `refusal = null`; the bar from rules 1–8 with the "This access code ran out of budget." note above it |

### 10.6 Frame-mapping and time test cases (§0, §3.6, §4.3; PRE-A §5b)

**Player → prepared frame:** `frame(m) = clamp(floor(m × job.fps + 0.25), 0, job.frames − 1)`. All cases use `job.fps = 30` and `job.frames = 900`. The first seven are PRE-A `docs/API-NOTES.md` §11.3 vector T5.

| Case | `m` (s) | `m × 30 + 0.25` | Expected frame |
|---|---|---|---|
| Start | `0.0` | 0.25 | 0 |
| Just before the switch point | `0.0249` | 0.997 | 0 |
| At the switch point (¾ through frame 0) | `0.025` | 1.0 | 1 |
| Exactly frame 1 | `1/30` | 1.25 | 1 |
| Middle of frame 1 | `0.05` | 1.75 | 1 |
| Near the end | `29.99` | 899.95 | 899 |
| Past the end | `31.0` | 930.25 | 899 (clamped) |
| Before 0 | `−0.5` | −14.75 | 0 (clamped) |
| Just below the next switch | `0.0583` | 1.999 | 1 |
| Just above it | `0.0584` | 2.002 | 2 |

**`job.times` checks** (§3.6). These decide only whether the panel draws; `times` never moves the overlay. Times in every mock and test are full-precision doubles (the shortest repr that round-trips, e.g. `0.03333333333333333`), never rounded: WP7 matches `times` to source timestamps within 1e-6, and a 4-decimal list fails that check ([LABEL-FORMAT.md](labeling/LABEL-FORMAT.md) §2, vector M8). The UI's own checks don't need full precision, but mocks copy the real shape.

| Case | `job.frames` | `times` | Expected |
|---|---|---|---|
| CFR source | 4 | `[0.0, 0.03333333333333333, 0.06666666666666667, 0.1]` | valid |
| VFR source with a repeat (PRE-A T6a, `job.fps` 10) | 4 | `[0.00, 0.10, 0.10, 0.26]` | **valid** (repeats are allowed) |
| First frame above 0 (PRE-A T6c) | 4 | `[0.04, 0.10, 0.10, 0.10]` | **valid** |
| Decreasing | 3 | `[0.0, 0.10, 0.05]` | unexpected-error page, overlay not drawn |
| Wrong length | 5 | `[0.0, 0.03333333333333333, 0.06666666666666667, 0.1]` | unexpected-error page |
| Not finite | 3 | `[0.0, NaN, 0.06666666666666667]` (or `null`) | unexpected-error page |
| `job.fps` not an integer 1–30 | — | `job.fps = 29.97` or `60` | unexpected-error page (PRE-A §5b: `job.fps = min(30, round(source fps))`) |

**Display times** (§0, integer arithmetic, `job.fps = 30`):

| Frame | `m:ss` | Drawer `m:ss.s` |
|---|---|---|
| 0 | `0:00` | `0:00.0` |
| 9 | `0:00` | `0:00.3` |
| 90 | `0:03` | `0:03.0` |
| 1500 | `0:50` | `0:50.0` |
| 1977 | `1:05` | `1:05.9` |

**Evidence rewrite** (§4.3, `job.fps = 30`, `job.frames = 900`):

| Muse Spark's text | Shown in the drawer |
|---|---|
| `introduced at F 000090, speaks to camera` | `introduced at 0:03, speaks to camera` |
| `speaks to camera at frames 120–600` | `speaks to camera at 0:04–0:20` |
| `waves at F90 and F120` | `waves at 0:03 and 0:04` |
| `looks at the camera at frame 9, never speaks` | `looks at the camera at 0:00, never speaks` |
| `Face 7 is the host` | `Face 7 is the host` (no match: no digit right after `F`) |
| `seen at F 001200` (frame ≥ `job.frames`) | `seen at F 001200` (left as written) |
| `background, never addressed` | unchanged |
| `introduced at frame 90, speaks to camera 120–600` (ARCHITECTURE §3.5's example) | `introduced at 0:03, speaks to camera 0:04–0:20` (rule 1, then rule 3) |
| `seen in frames 90 and 120` | `seen in 0:03 and 0:04` |
| `frames 90, 120 and 150, never addressed` | `0:03, 0:04 and 0:05, never addressed` |
| `at F 000090 with 2–3 people nearby` | `at 0:03 with 2–3 people nearby` (rule 3 needs both numbers ≥ 10) |
| `speaks at 120` (no frame word or F label) | `speaks at 120` (bare single numbers are never converted) |
| `at frame 90. Later 120–240` | `at 0:03. Later 120–240` (rule 3 only applies within the sentence that had a reference) |
| `frames 240-600` (hyphen) | `0:08–0:20` |

### 10.7 Edge states checklist

| Case | Expected |
|---|---|
| Zero items | §3.7 "Empty: nothing found at all"; Approve & render still available |
| All items locked | Hidden column only; Kept clear "Nothing is kept clear. …"; Needs you "Nothing needs you."; bottom bar "Everything's decided." |
| Exactly 1 item | normal layout; the other two columns show their empty copy |
| 200 items | each column virtualises its list above 100 chips (only visible chips are in the DOM, with an accessible count in the column header); the overlay draws at most 200 regions per frame, and `crowd_fills` count as one region each; keyboard order still visits every chip |
| Very long `reason` | chip clamps to 2 lines with "…"; the full text is in the drawer and in the chip's accessible name |
| Missing keyframe URL | drawer shows "The keyframe didn't load." (§4.4); the rest of the drawer works |
| Empty transcript (`turns: []`, `degraded: false`, Voice Transcribe) | drawer: "No speech was transcribed. Safe Cut's speech check covers 25 languages, not including Swahili." |
| Empty and limited transcript (`degraded: true`, or `source_kind: "fallback"`) | drawer: "Speech couldn't be checked reliably for this clip." under the limited-check heading (§4.3) |
| Any keyframe geometry check fails (§4.3: frame size ≠ job size, `image_height ≠ frame_height + bar_h`, or the loaded natural size ≠ `image_width × image_height`) | image without a ring, plus "The keyframe's size doesn't match this clip, so the outline is hidden." |
| Harmless plate (`sensitive: false` ×3) | Needs you, "…but number plates are only kept clear when you confirm."; Keep clear asks the object confirm |
| `job.audio: false` | drawer section replaced by "This clip has no sound." |
| No `scene`, or `matches_participant` null | the "said by {label}" link is never shown; nothing else changes |
| `plan.frames` has no entry for a frame | draw nothing on that frame; no error (frames with nothing to cover are left out of the plan) |
| A track ID that isn't `<concept>:<n>` | label = the raw track ID, and a console warning (it signals a WP1/WP2 contract gap); never a made-up number |
| `times` has repeated values, or `times[0]` is slightly above 0 | valid: draw normally (§3.6, §10.6); it only reflects a variable-frame-rate source |
| `status: "retry_later"` | §10.4 `retry_later` state; polling every 30 s; the review link stays valid. One automatic retry only; then `failed` + `upstream` (`job-failed-upstream.json`) |
| Plate with no `roles.objects[]` entry, or PRE-A's failure placeholder (`sensitive: true`, `content: ""`; role pass failed closed) | the drawer shows the fixed sentence and "Number plates are hidden by default. Only you can keep one clear." without a "Muse Spark read it as" line |
| Signed URL expired (`403` on media) | refetch `GET /v1/jobs/{id}` once for fresh URLs; if it fails again, §7 unexpected-error |
