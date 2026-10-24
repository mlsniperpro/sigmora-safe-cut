# Safe Cut: demo video storyboard (2:50)

Status: **v1, 2026-10-24 (PRE-B, docs only).** Shot by shot for the beats in [DEMO.md](DEMO.md). The screens are specified in [UI-SPEC.md](UI-SPEC.md); the clips are the hero clips in [SHOTLIST.md](SHOTLIST.md); the numbers come from WP7's `eval/RESULTS.md` ([EVAL.md](EVAL.md), [WP7](work-packages/WP7.md)). The pipeline the VO describes is [DESIGN.md](DESIGN.md) §2 (Set-of-Mark role calls §2.3, re-entry policy §2.5, audit §2.8). WP8 turns this into the final `docs/VIDEO-SCRIPT.md` on Nov 3.

## Rules for this video

1. **Numbers are placeholders** like `{recall_full}` until WP8 fills them from a committed `eval/results/<run-id>/metrics.json` ([AGENTS.md](../AGENTS.md) rule 9). If a number is weak, it's shown anyway ([DEMO.md](DEMO.md)). If a placeholder has no committed source by Nov 3, the shot changes; nobody types a number in.
2. **Nothing staged as real.** Every screen shot is a recording of the deployed app. If a shot uses replayed data, the demo-mode banner is visible in it ([UI-SPEC.md](UI-SPEC.md) §6). If something the script expects didn't happen on the real run (e.g. the audit found no leak), the script changes to what did happen.
3. **Only consenting people on screen.** Hero clips only (signed releases), fake PII on every screen and document, no real keys, emails or private footage ([SHOTLIST.md](SHOTLIST.md), [DEMO.md](DEMO.md) Production).
4. **The café menu is shown in Needs you, not Kept clear.** Under the policy ([DESIGN.md](DESIGN.md) §2.5, WP3), a harmless screen goes to Needs you and is never kept clear automatically, so beat 5 shows the real behaviour: Muse Spark reads it as a menu, then the creator confirms with one tap. That's stronger on screen than an automatic keep, because it shows reasoning and human control together. [DEMO.md](DEMO.md) beat 5 says "clear"; this storyboard supersedes that line.
5. **Baselines are labelled as ours.** "Blur every face" is our implementation of that approach (WP7's `blur_all`), labelled "Blur every face (baseline)". Don't say it's YouTube's or CapCut's actual output.
6. **Captions on** for the whole video. **Decision: the VO is the owner's own recorded voice (O9), not the ElevenLabs clone.** That leaves nothing AI-generated to label or disclose, and if a rule asks about synthetic voices the answer is already no. VO at about 150 words a minute; the VO below is about 290 words, so no line runs faster than about 150 wpm.

**Sources key.** `H1A`/`H1B` = hero clip 1 "street interview", take A / take B (the van re-entry); `H2` = hero 2 "café"; `H3` = hero 3 "walk-through". `R-xx` = a render; `SR-xx` = a screen recording (§3); `CH-xx` = a chart from `eval/report.py`; `GFX` = a title card made in the editor.

## 1. Shot list

| # | Time | Dur | Frame | On-screen text | VO | Source |
|---|---|---|---|---|---|---|
| **Beat 1: Hook** | | | | | | |
| 1.1 | 0:00–0:03 | 3 s | H1A raw, full frame: the guest talking to the host on a busy street | Corner, for the whole of beat 1: "Staged with actors. Everyone signed a release." | "Here's a typical street interview." | `R-01` (H1A raw) |
| 1.2 | 0:03–0:12 | 9 s | Same clip continues; each problem gets a thin outline and label as it appears: the child passing, actor 2's phone with the fake number, the parked car's plate | "Child" · "Phone number" · "Number plate" (small labels next to each) · bottom: "In real footage, none of them agreed to be in it." | "It also shows a child, a stranger's phone number and a number plate. In real footage, none of them agreed to be in it." | `R-01` + outlines from the labelled boxes of H1A |
| **Beat 2: The status quo fails** | | | | | | |
| 2.1 | 0:12–0:20 | 8 s | Split screen, same moment of H1A. Left: blur-every-face baseline (the guest is covered; plate and phone visible). Right: manual masking in an editor, time-lapse, real timer in the corner | Left: "Blur every face (baseline)". Right: "Masking by hand · `{manual_minutes}` min for this `{h1a_seconds}` s clip" | "Today you either blur everyone, including your guest," | `R-02` (H1A `blur_all`) + `SR-10` (manual masking, time-lapse) |
| 2.2 | 0:20–0:30 | 10 s | Right half fills the frame: the timer keeps running; then cut to a black card | Card: "Most creators just publish." | "or mask by hand for `{manual_minutes}` minutes. Most creators just publish, and hope nobody complains." | `SR-10`, `GFX` |
| **Beat 3: One pass** | | | | | | |
| 3.1 | 0:30–0:37 | 7 s | The Safe Cut upload page: drop H1A, tick the rights box, Start | — | "With Safe Cut, you upload the clip once." | `SR-01` |
| 3.2 | 0:37–0:45 | 8 s | Progress list ticking through "Finding people and objects", "Listening for who's speaking", "Working out who's part of the story" (time-lapse, labelled) | Corner: "Sped up `{speedup}`× · real time `{upload_to_review_s}` s" | "SAM 3.1 tracks faces, people, plates and screens, frame by frame. Muse Voice Transcribe hears who's speaking." | `SR-01` |
| 3.3 | 0:45–0:55 | 10 s | Review panel appears: Hidden (child, phone screen, plate, passers-by), Kept clear (guest, host), Needs you (one person who looked at the camera). Slow push-in on the columns | — | "Muse Spark decides who's part of the story and who isn't. Everything uncertain stays hidden, and every decision has a reason." | `SR-02` |
| **Beat 4: Why: the reasoning** | | | | | | |
| 4.1 | 0:55–1:05 | 10 s | Tap the child's chip → the Why? drawer: the Set-of-Mark keyframe with numbered boxes, the child's label (e.g. `face:4`) ringed; "Always hidden" lock; 3 vote marks | Drawer text as recorded (e.g. "Face 4 · Child · Always hidden"; labels match the keyframe's `face:4`, UI-SPEC §0) | "We show Muse Spark the people SAM 3.1 is tracking, numbered, and it rules on each one. Children are always hidden." | `SR-03` |
| 4.2 | 1:05–1:14 | 9 s | Close; tap the guest's chip → drawer: "introduced at 0:03, speaks to camera", 3/3 votes, the transcript line "Hi, I'm …" | — | "The guest is kept clear because all three checks agree: they're introduced, and they speak to the camera." | `SR-03` |
| 4.3 | 1:14–1:20 | 6 s | Back on the panel: the Needs-you chip (the person who looked at the camera); tap Hide; the chip moves to Hidden and the overlay covers them at once | Toast: "Face 6 will be hidden. Undo" | "When the checks disagree, it's your call. One tap." | `SR-04` |
| **Beat 5: The context test** | | | | | | |
| 5.1 | 1:20–1:30 | 10 s | H2 review panel: laptop A (fake inbox) in Hidden; laptop B (menu) in Needs you, reason "menu, nothing personal" | Labels: "Inbox: hidden" · "Menu: needs you" | "A screen isn't private because it's a screen. This inbox is. Muse Spark reads the other one as a menu," | `SR-05` |
| 5.2 | 1:30–1:40 | 10 s | Tap Keep clear on laptop B (the one-line confirm shows), then Raw/Safe Cut toggle on the video: inbox covered, menu readable | — | "and asks you to confirm before it's shown. Blur-every-face tools don't make that call." | `SR-05` |
| **Beat 6: The guarantee** | | | | | | |
| 6.1 | 1:40–1:50 | 10 s | H1B: the passer-by walks behind the van and comes out; the cover stays on. Then the NEW chip: "appeared again after leaving" | "Lost and found again → still hidden" | "If the tracker loses someone, they come back hidden, until you say otherwise." | `SR-06` + `R-03B` (H1B Safe Cut render) |
| 6.2 | 1:50–2:00 | 10 s | Result page: the audit panel "`{h1_frames_scanned}` frames checked. `{h1_leaks_fixed}` leak(s) found and fixed." If a leak was fixed: before/after frames side by side | Audit text as recorded | "Then Meta's EgoBlur checks every frame of the final render, and Muse Spark tries to read anything left, before it goes live." | `SR-07`; before/after stills from WP4's audit on H1 |
| **Beat 7: Numbers** | | | | | | |
| 7.1 | 2:00–2:12 | 12 s | The results chart/table with the five rows of [EVAL.md](EVAL.md) §3 (blur every face, EgoBlur Gen 2, detector only, Muse Spark without tracking, Safe Cut full; plus "Safe Cut without the audit" if WP7 ran it): recall, exposure, leak bursts, over-blur. A thin line marks human agreement | Table values as committed; footer "`{n_test_clips}` clips · run `{run_id}`" | "On `{n_test_clips}` labelled test clips, Safe Cut hid `{recall_full}` of what should be hidden, with `{leak_bursts_full}` leak bursts." | `CH-01` (from `eval/report.py`) |
| 7.2 | 2:12–2:20 | 8 s | Same chart, over-blur column highlighted | "Over-blur: `{overblur_blur_all}` → `{overblur_full}`" | "Blur every face hid `{overblur_blur_all}` of the people who should stay clear. Safe Cut: `{overblur_full}`." | `CH-01` |
| **Beat 8: Ship** | | | | | | |
| 8.1 | 2:20–2:28 | 8 s | Approve & render → result → "Publish to Sigmora" → Sigmora's publish screen | — | "Approve, and publish straight from Sigmora." Only if the Sigmora integration is merged and `SR-09` was recorded; otherwise the frame ends on the result page and the line is "Approve, and download the result." | `SR-08` + `SR-09` |
| 8.2 | 2:28–2:35 | 7 s | The privacy receipt: items, reasons, who approved, audit result, data handling | — | "You keep a privacy receipt: what was hidden, why, and who approved it." | `SR-07` |
| 8.3 | 2:35–2:40 | 5 s | Pilot card (only with a pilot's written permission): their quote and minutes saved | "`{pilot_quote}` — `{pilot_name_or_handle}`, `{pilot_format}` · `{pilot_minutes_manual}` min → `{pilot_minutes_safecut}` min" | "`{pilot_vo_line}`" (≤ 10 words, e.g. "Pilot creators: `{pilot_median_manual}` minutes of masking became `{pilot_median_safecut}`."). **Capped values:** if any pilot hit the 30-minute cap ([PILOTS.md](PILOTS.md) §5), the manual figure is never shown as a plain median. The card says "≥ 30 min (`{n_capped}` of `{n_pilots}` didn't finish)", the VO becomes "Masking by hand took over 30 minutes for `{n_capped}` of `{n_pilots}` pilot creators", and per-pilot values carry "≥" | `GFX` from [PILOTS.md](PILOTS.md) results |
| **Beat 9: Close** | | | | | | |
| 9.1 | 2:40–2:50 | 10 s | Logo, `safecut.sigmora.org`, the repo URL, "Built with Muse Spark, SAM 3.1 and Muse Voice Transcribe" | As described | — | `GFX` + `SR-11` (landing page in the background) |

Total: 2:50. If shot 8.3 has no permitted pilot data, it's cut and 8.2 runs to 2:40 with the line "…and who approved it. It's live in Sigmora today." (only if the Sigmora integration is merged; otherwise "…and who approved it.").

## 2. Placeholders (all filled by WP8 from committed results)

Every placeholder, timings and audit counts included, must resolve to a value in a committed `eval/results/<run-id>/metrics.json` ([AGENTS.md](../AGENTS.md) rule 9). Values that don't come from an eval run (the hero run's latency and audit, the manual-masking time, the pilots) need their own results directory, committed before Nov 3 (requests to WP5/WP7 in the PRE-B PR). A placeholder without one is cut from the video, not estimated.

| Placeholder | Meaning | Source |
|---|---|---|
| `{recall_full}` | entity recall, Safe Cut full, test split | `eval/results/<run-id>/metrics.json` (variant `full`) |
| `{leak_bursts_full}` | leak bursts, Safe Cut full, test split | same |
| `{exposure_full}` | exposure rate, Safe Cut full (in the table) | same |
| `{overblur_full}`, `{overblur_blur_all}` | over-blur rate, full vs `blur_all` | `full` and `blur_all` runs |
| `{n_test_clips}` | number of clips in the frozen test split | `config.json` / `eval/splits/test.sha256` |
| `{run_id}` | the run shown | the run directory name |
| `{kappa}` | Cohen's κ on `should_hide`, shown with the raw percent agreement (or "not measured, single labeller") | WP7's label report, committed under `eval/results/<run-id>/` |
| `{manual_minutes}` | owner's timed manual masking of H1A | EVAL.md §2 "Creator time", timed once on 3 clips; committed as `eval/results/creator-time-<date>/metrics.json` |
| `{upload_to_review_s}` | real wall-clock from upload to "Ready for you" on the recorded H1A run | `eval/results/hero-live-<date>/metrics.json` (stage timings from WP5's `job_log.jsonl`) |
| `{speedup}` | the time-lapse factor applied in the edit | derived from committed numbers only: `{upload_to_review_s}` (committed above) ÷ the shot's on-screen seconds. It describes the edit, not the product, so it needs no metrics file of its own |
| `{h1a_seconds}` | the length of H1A | the same `creator-time-<date>` run's `config.json` (clip duration from `job.json`) |
| `{h1_frames_scanned}`, `{h1_leaks_fixed}` | the audit on the recorded H1 run | the same `hero-live-<date>` run, copied from its `audit.json` |
| `{pilot_*}` | pilot results, quotes and names | numbers from `eval/results/pilots-<date>/metrics.json`; quotes and names only with written permission ([PILOTS.md](PILOTS.md) §6) |

## 3. Screen recordings to capture on Nov 3

**Setup for every recording:** the deployed app on the custom domain (not localhost, not a preview URL); a fresh Chrome profile with no extensions, bookmarks or notifications; window content exactly 1920×1080 at 100% zoom; cursor visible; 30 fps; system audio off (VO is added later). Use the hero jobs run **live** on Nov 3 where possible; if the API is down and replay is used, the demo-mode banner is visible and stays in the edit. Record each one at least twice.

| ID | What to capture | Clip / job | Length to record | Shots |
|---|---|---|---|---|
| `SR-01` | `/try`: enter the access code, drop the clip, tick, Start, the whole progress list to "Ready for you". Note the wall-clock time | H1A, live | full run (real time) | 3.1, 3.2 |
| `SR-02` | Review panel arriving; hover slowly across the three columns; no clicks | H1A job | 30 s | 3.3 |
| `SR-03` | Open the child's Why? drawer, step through its evidence frames, close; open the guest's drawer, scroll to the transcript line, close | H1A job | 60 s | 4.1, 4.2 |
| `SR-04` | Tap Hide on the Needs-you person; show the toast and the overlay change on the paused video; then Undo and Hide again (for a clean take) | H1A job | 30 s | 4.3 |
| `SR-05` | Café review: show both laptops' chips; tap Keep clear on the menu laptop (confirm); play 5 s; switch Raw/Safe Cut twice | H2, live | 60 s | 5.1, 5.2 |
| `SR-06` | Play the van stretch with Safe Cut on, at normal speed and once frame by frame; then the NEW chip and its Why? drawer | H1B, live | 60 s | 6.1 |
| `SR-07` | Result page: the audit panel, expand "What the check does", scroll through the receipt | H1A job | 45 s | 6.2, 8.2 |
| `SR-08` | Approve & render from the review panel, through the render stages, to the result page | H1A job | full (real time) | 8.1 |
| `SR-09` | From Sigmora: open the Safe Cut job from Sigmora, "Publish to Sigmora", Sigmora's publish confirmation (only if the integration is merged; publish to a private/unlisted target) | H1A via Sigmora | 30 s | 8.1 |
| `SR-10` | The owner masks H1A by hand in an ordinary editor (the faces of the child and passers-by, the plate, the phone) with an on-screen timer, start to finish | H1A raw | the whole session | 2.1, 2.2 |
| `SR-11` | The landing page: the hero toggle, a slow scroll through How it works and the results table | — | 30 s | 9.1 |

**Renders needed (WP7/WP8 export them):** `R-01` H1A raw prepared clip; `R-02` H1A `blur_all` variant; `R-03`/`R-03B` H1A and H1B Safe Cut `redacted.mp4`; WP4's audit before/after stills for H1; `CH-01` the results chart (consistent colours, from `eval/report.py`).

**On-screen text style:** one sans-serif face, white on a 60% black strip, bottom third, max 7 words per line; never over a face that should be visible.

## 4. Checks before export

- [ ] Every number on screen or in the VO is a filled placeholder with a run ID in the WP8 PR.
- [ ] Every replayed shot shows the demo-mode banner.
- [ ] Nobody without a release is visible anywhere, including reflections.
- [ ] No real PII, keys, emails or account names in any frame.
- [ ] Length ≤ 2:50; captions match the VO; the audio is the owner's own voice.
