# Submission: paste-ready fields for the Cerebral Valley form

The form is login-gated. These are the fields the official guide (`docs/OFFICIAL-GUIDE.md`, captured 2026-10-26) requires or implies: the project, the theme, the Meta models used, a public repo, a live product, a three-minute video, the team, and how to test it. Copy each block as it is. Lines in `⟨…⟩` are owner inputs (`BLOCKED.md`) to fill on the day.

## Title

Sigmora Safe Cut

## Tagline

Publish real-world footage without exposing the people who never agreed to be in it.

## Track and theme

Startups track · Build for Your World

## Description

Creators who film in public (street interviews, vlogs, events) publish strangers, children, number plates and screens full of personal data every day. The tools they have either blur every face, including their own guest, or leave them hours of masking by hand. So most just publish.

Safe Cut decides from context what shouldn't be published in the picture, and proves it (the soundtrack is kept as recorded, and the receipt says so):
1. **SAM 3.1** tracks every face, person, plate, screen and document through the clip.
2. **Muse Voice Transcribe** hears who speaks.
3. **Muse Spark** watches the whole clip, then rules three times, independently, on numbered keyframes, about who is part of the story. Disputes escalate once at maximum effort, and a miss loop asks what the tracker didn't catch.
4. A deny-by-default policy hides everything uncertain. Children are always hidden, and a person the tracker loses and finds again comes back hidden.
5. A leak guard pads and holds every cover so nothing flickers through, and covers only what identifies, with one frosted look: faces and heads (never bodies) and plates, screens and documents, under a coarse mosaic of the region's mean colour, blurred, so nothing underneath can be recovered and nothing is a dark box. Bodies stay in the shot, covers never run ahead of their object, and a kept participant's face is never covered by someone else's cover.
6. The creator reviews every item, sees why each was decided, and approves.
7. Before anything is published, an independent detector checks every rendered frame and a Muse Spark red team checks sampled frames. Leaks are patched automatically.
8. A hash-chained privacy receipt records every decision, who made it, and how the data was handled.

It is a production service: an API with access codes, service keys for Sigmora, per-clip and daily spend caps, signed uploads, 24-hour deletion and a labelled demo mode, a review web app, and a CLI. It is built to be called by Sigmora, our existing creator platform, as its host app (service keys). All of Safe Cut was built during the hackathon; what existed before is listed in the README.

## Meta models used

SAM 3.1 · Muse Spark (`muse-spark-1.3`, and `muse-spark-1.2` as the speech fallback) · Muse Voice Transcribe · ⟨owner: keep only if the Baseten steps in BLOCKED.md are done and it ran: Muse Spark Open on Baseten (`meta-models/muse-spark-open-1026`, the optional open-weight audit opinion)⟩ · EgoBlur Gen 2 (Meta's open face and plate detector, the every-frame auditor of the rendered video, on a Modal GPU; if the GPU can't answer, the bundled YuNet face detector runs instead with plates left to the red team, and `audit.json` and the receipt name the detector, and the GPU, that actually ran). What each one does: README, "What each Meta model does here".

## Links

- Repository: https://github.com/mlsniperpro/sigmora-safe-cut (public ⟨owner: make it public⟩)
- Live product: https://safecut.sigmora.org ⟨owner: Vercel project and Modal deploy⟩
- Demo video: ⟨owner: YouTube link⟩
- X post (Most Viral bonus): ⟨owner: post link⟩

## Team

⟨owner: every contributor's name and Cerebral Valley handle⟩

## Testing instructions for judges

1. Open https://safecut.sigmora.org. The service sleeps when no one is using it, so the first request after a quiet spell may take up to a minute while it wakes (the page says so). The landing page plays the demo job, labelled as a demo: until the owner records the hero clips, it is a synthetic test clip (drawn shapes, scripted answers), and the page says so. The Raw / Safe Cut toggle compares the original and the result.
2. Press **Try it** and enter the access code ⟨owner: type the judge code here in the form itself, never in this file: the repo is public⟩. It works ⟨owner: from Nov 5 00:00, or the opening you set in `SAFECUT_CODE_WINDOWS`⟩ to Nov 10 23:59 UTC, within a daily spend cap.
3. Upload a clip of up to ⟨owner: 60 seconds, or 30 if you kept the default daily cap (BLOCKED.md)⟩ and 150 MB (MP4 or MOV), tick the rights box and press Start. Safe Cut redacts the picture only: the audio is kept as recorded (the receipt says so).
4. When the review panel appears, open **Why?** on any item to see the numbered keyframe and the three votes. Try:
   - **Hide** or **Keep clear** on an item;
   - **Undo**;
   - **Same as…**, to merge a person the tracker lost and found again;
   - **Remove this person**, from the ⋯ menu.

   A child can't be kept clear.
5. Press **Approve & render**. The result page shows the final check's summary, the video and the privacy receipt (HTML and JSON).
6. **Delete everything now** removes the clip, the result and the receipt at once. Otherwise they are deleted after 24 hours.

To run it offline from the repo instead (no account, no network), follow the README's "Run it yourself": one `uv sync`, then `safecut run … --replay`.

## Running cost

The service scales to zero: when no one uses it, only the 15-minute deletion job runs. Estimates from Modal's
published rates and the container sizes in `deploy/modal_app.py`, not a measured bill (the method and the
assumptions: `docs/DEPLOY-COSTS.md`; `python -m deploy.costs` prints this table). Meta's spend per clip is separate.

```text
Modal cost (estimate)        What runs                                                 USD  per
Idle, before (always on)     API, 2 cores + 4 GiB, all day                          3.0384  day
Idle, now (scaled to zero)   cleanup cron only, 96 runs of ~14 s                    0.0026  day
A visit's quiet tail         API stays up 300 s after the last request              0.0053  visit
One 60 s clip, API           ~300 s of the API container                            0.0053  clip
One 60 s clip, GPU audit     ~210 s on an L4, plus its 30 s tail                    0.0628  clip
One clip, GPU worst case     what the estimate reserves: 930 s                      0.2454  clip
```
