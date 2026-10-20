> Imported unchanged from `sigmora-platform/docs/meta-hackathon/DEMO.md` on 2026-10-20 (pre-event design). Where file paths or the Oct 14 model choices differ, [ARCHITECTURE.md](ARCHITECTURE.md) and [MAXXING.md](MAXXING.md) take precedence: this repo is standalone, and it adds Muse Voice Transcribe and an optional Muse Wonder escalation.

# Safe Cut: demo video and live demo

The demo is 25% of the score ("a working, impressive demo… holds up live… quality of the demo video"). Impact is another 30% and is mostly *told* by the demo. Target **2:30–2:50**; judges skim long videos. It's made in Sigmora itself, so the demo video is also product proof.

## Story in one line

*You filmed a great interview on a busy street. Before Safe Cut, publishing it meant hours of masking strangers by hand, or risking a takedown. With Safe Cut, it's one pass and a few taps, and you can see why each thing was hidden.*

## Beats

| # | Time | Beat | On screen | VO (draft) |
|---|---|---|---|---|
| 1 | 0:00–0:12 | **Hook** | Hero clip 1 plays raw: the guest talking, a child passes, a phone screen with a number, a car plate | "This is a normal street interview. It also shows a child, a stranger's phone number and a number plate. None of them agreed to be in it." |
| 2 | 0:12–0:30 | **The status quo fails** | Split screen: YouTube-style "blur all faces" (the guest blurred too, the plate and phone untouched) vs manual masking in an editor (time-lapse, timer running) | "Today you either blur everyone, including your guest, or mask by hand for hours. Most creators just publish." |
| 3 | 0:30–0:55 | **One pass** | In Sigmora: Safe Cut on the clip → progress → the **review panel** appears: *Hidden* (child, phone screen, plate, 3 passers-by), *Kept clear* (guest, host), *Needs you* (one person who looked at the camera) | "Muse Spark watches the whole clip and decides who's part of the story and who isn't. Every decision comes with a reason." |
| 4 | 0:55–1:20 | **Why: the reasoning** | Tap a chip: the keyframe with numbered SAM boxes (Set-of-Mark) and the reason text: "#4, child in the background, not addressed, hide." "#2, the guest: introduced at 0:03, speaks, faces camera, keep." | "We show Muse Spark the people SAM 3.1 is tracking, numbered, and it rules on each one. Reasoning picks *who*; SAM keeps the blur on them, frame by frame." |
| 5 | 1:20–1:40 | **The context test** | Café hero clip: laptop A (inbox) hidden; laptop B (menu) clear | "A screen isn't private because it's a screen. This inbox is. That menu isn't. No blur tool on the market makes that call." |
| 6 | 1:40–2:00 | **The guarantee** | Re-entry clip: the bystander ducks behind a van and comes out with a new SAM ID → stays hidden; the audit pass caught one 2-frame leak and re-tracked it (show the before/after frames) | "If the tracker ever loses someone, they stay blurred until you say otherwise. Then a second look checks the final render frame by frame before anything goes live." |
| 7 | 2:00–2:20 | **Numbers** | The results table: blur-every-face vs detector-only vs Safe Cut (recall, exposure, leak bursts, over-blur); the human-agreement ceiling line | "On our labelled test set, Safe Cut hides X% of what should be hidden, with Y leak bursts, while keeping Z% of participants clear." |
| 8 | 2:20–2:40 | **Ship** | Approve all → render → publish to YouTube via Sigmora; the privacy receipt (what was hidden, why, who approved) | "Approve, publish. It's live in Sigmora today, for every creator who films the real world." |
| 9 | 2:40–2:50 | **Close** | Logo plus sigmora.org, the repo link, "Built with Muse Spark + SAM 3.1" | — |

The numbers in beat 7 are filled in ONLY from frozen test-split runs (EVAL.md). If a number is weak, show it anyway; honest beats impressive.

## Production

- Edited in Sigmora (dogfood); captions on; the VO is Peter's own voice, or his ElevenLabs clone (the AI-label decision is the owner's).
- Screen recordings at 1080p; the cursor is visible; no real API keys, emails or private footage on screen (the waiver: nothing is confidential).
- Uploaded to YouTube (unlisted → public at submission) on Silicon Savannah Guy, plus X @algocracked for the community-vote and most-viral bonus prizes.

## Live demo (finals, Nov 9)

- Run on **hero clip 1** live, with cached results ready if the API is slow ("demo mode" replays saved responses and is labelled as such).
- Have one judge-supplied twist ready: upload any short public clip they hand over, then run it live.
- Rehearse twice and time it.
