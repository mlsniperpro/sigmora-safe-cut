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
5. A leak guard pads and holds every cover so nothing flickers through.
6. The creator reviews every item, sees why each was decided, and approves.
7. Before anything is published, an independent detector checks every rendered frame and a Muse Spark red team checks sampled frames. Leaks are patched automatically.
8. A hash-chained privacy receipt records every decision, who made it, and how the data was handled.

It is a production service: an API with access codes, service keys for Sigmora, per-clip and daily spend caps, signed uploads, 24-hour deletion and a labelled demo mode, a review web app, and a CLI. It is built to be called by Sigmora, our existing creator platform, as its host app (service keys). All of Safe Cut was built during the hackathon; what existed before is listed in the README.

## Meta models used

SAM 3.1 · Muse Spark (`muse-spark-1.3`, and `muse-spark-1.2` as the speech fallback) · Muse Voice Transcribe · Muse Spark Open on Baseten (`meta-models/muse-spark-open-1026`, the optional open-weight audit opinion) · EgoBlur Gen 2 (Meta's open face and plate detector, as the every-frame auditor on a GPU machine with its gated weights; the deployed service has no GPU, so its audit runs the bundled YuNet face detector with plates left to the red team, and `audit.json` and the receipt name the detector that ran). What each one does: README, "What each Meta model does here".

## Links

- Repository: https://github.com/mlsniperpro/sigmora-safe-cut (public ⟨owner: make it public⟩)
- Live product: https://safecut.sigmora.org ⟨owner: Vercel project and Modal deploy⟩
- Demo video: ⟨owner: YouTube link⟩
- X post (Most Viral bonus): ⟨owner: post link⟩

## Team

⟨owner: every contributor's name and Cerebral Valley handle⟩

## Testing instructions for judges

1. Open https://safecut.sigmora.org. The landing page plays the demo job, labelled as a demo: until the owner records the hero clips, it is a synthetic test clip (drawn shapes, scripted answers), and the page says so. The Raw / Safe Cut toggle compares the original and the result.
2. Press **Try it** and enter the access code ⟨owner: type the judge code here in the form itself, never in this file: the repo is public⟩. It works from Nov 5 00:00 to Nov 10 23:59 UTC, within a daily spend cap.
3. Upload a clip of up to 60 seconds and 150 MB (MP4 or MOV), tick the rights box and press Start. Safe Cut redacts the picture only: the audio is kept as recorded (the receipt says so).
4. When the review panel appears, open **Why?** on any item to see the numbered keyframe and the three votes. Try:
   - **Hide** or **Keep clear** on an item;
   - **Undo**;
   - **Same as…**, to merge a person the tracker lost and found again;
   - **Remove this person**, from the ⋯ menu.

   A child can't be kept clear.
5. Press **Approve & render**. The result page shows the final check's summary, the video and the privacy receipt (HTML and JSON).
6. **Delete everything now** removes the clip, the result and the receipt at once. Otherwise they are deleted after 24 hours.

To run it offline from the repo instead (no account, no network), follow the README's "Run it yourself": one `uv sync`, then `safecut run … --replay`.
