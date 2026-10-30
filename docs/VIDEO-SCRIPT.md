# Demo video script (final structure; ends at 2:50)

The beats of `docs/DEMO.md`, shot by shot in `docs/STORYBOARD.md`, timed here to **2:50**. The VO is about 235 to 265 words (depending on which 2:00 line is used and how many figures it reads), under 1:50 at 150 words a minute, so every beat has room for its screen.

The rules carry over from the storyboard:
- every screen is a recording of the deployed app;
- replayed data shows its demo-mode banner;
- only people with signed releases appear on screen;
- **every number on screen or in the VO comes from `eval/RESULTS.md`, with its run ID visible.**

A beat whose number has no committed source changes its shot (beat 7 below); nobody types a number in.

## Recordings needed

| ID | What | Clip |
|---|---|---|
| R-01 | Hero 1 raw, full frame | H1A (street interview, signed releases) |
| R-02 | Hero 1 with every face blurred, made in a video editor and labelled "Blur every face (illustration)" on screen: the repo's `blur_all` baseline scores plans and renders no video | H1A |
| SR-01 | `/try`: code, drop the clip, Start, the progress list (time-lapse, labelled "sped up") | H1A |
| SR-02 | The review panel: Hidden, Kept clear, Needs you | H1A |
| SR-03 | The Why drawer: the child (locked), then the guest (three votes, the transcript line) | H1A |
| SR-04 | One tap on the Needs-you chip, with its toast and Undo | H1A |
| SR-05 | The café: the inbox screen hidden, the menu in Needs you, Keep clear with its confirm | H2 |
| SR-06 | The re-entry: the bystander comes back with a new ID and stays hidden; the audit's patch (A1) if the real run found one | H1B |
| SR-07 | Approve & render → the result, the receipt | H1A |
| CH-01 | The results chart from `eval/report.py` (`eval/results/charts/`) | test split |

## Script

| Time | Beat | On screen | VO |
|---|---|---|---|
| 0:00–0:12 | Hook | R-01; thin labels as each problem appears: "Child", "Phone number", "Number plate"; corner: "Staged with actors. Everyone signed a release." | "Here's a typical street interview. It also shows a child, a stranger's phone number and a number plate. In real footage, none of them agreed to be in it." |
| 0:12–0:30 | The status quo fails | Split: R-02, labelled "Blur every face (illustration)", next to a manual-masking time-lapse | "Today you either blur everyone, including your guest, or mask by hand, frame by frame. Most creators just publish, and hope nobody complains." |
| 0:30–0:55 | One pass | SR-01, then SR-02 | "With Safe Cut you upload the clip once. SAM 3.1 tracks every face, person, plate and screen. Muse Voice Transcribe hears who's speaking. Muse Spark decides who is part of the story, and everything uncertain stays hidden." |
| 0:55–1:20 | Why | SR-03, SR-04 | "We show Muse Spark the people SAM is tracking, numbered on the frame, three separate times. The guest is kept clear because every check agrees: they're introduced, and they speak. Children are always hidden. When the checks disagree, it's your call: one tap, and you can undo it." |
| 1:20–1:40 | The context test | SR-05 | "A screen isn't private because it's a screen. This inbox is. Muse Spark reads the other one as a menu, and asks you before it's shown." |
| 1:40–2:00 | The guarantee | SR-06 | "If the tracker loses someone, they come back hidden. Then, before anything is published, an independent detector checks every rendered frame, and Muse Spark checks again. Anything it finds is covered automatically, and if a leak can't be fixed, the result says so before you publish." |
| 2:00–2:20 | Numbers | CH-01 with its run ID, from the frozen test split. **Until a test-split run is committed, this shot shows instead the offline end-to-end check passing (`bash scripts/entry-check.sh`), with no numbers.** | With numbers: "On our labelled test set, compared with blurring every face:" then the recall, leak-burst and over-blur figures exactly as `eval/RESULTS.md` prints them. Without: "Every stage is checked end to end, offline, against ground truth, before every release." |
| 2:20–2:40 | Ship | SR-07: the receipt's list ("hidden: child · always", "kept clear: guest · you approved") | "Approve, render, publish. The privacy receipt records every decision, who made it, and how your footage was handled, and it's deleted from our servers after a day." |
| 2:40–2:50 | Close | Title card: Safe Cut · sigmora.org · the repo link · "Built with SAM 3.1, Muse Spark and Muse Voice Transcribe" | — |

## Before recording

- Use the deployed app with the recording code (`BLOCKED.md`: its own cap, valid until Nov 3), on hero clips 1 and 2.
- Record at 1080p with the cursor visible, and keep captions on.
- Show no real keys, emails or private footage on screen.
- Don't imply the audio is redacted: Safe Cut covers the picture and keeps the soundtrack as recorded (the receipt says so). The VO says "hides" of people on screen only.
- If something the script expects didn't happen on the real run (for example the audit found no leak), change the script to what did happen.
