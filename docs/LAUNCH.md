# Launch posts (Most Viral and Community Vote bonuses)

Posted by the owner from their own accounts after submission (`BLOCKED.md`). Plain, specific claims, no hype words. Each line is posted only once it's true: the live URL after the deploy check passes, "everyone on screen signed a release" once the hero clips with releases are the ones shown, and the repo link once it's public (MIT, `LICENSE`). Any result quoted must appear in `eval/RESULTS.md` with its run ID. Until a test-split run is committed, the posts quote no numbers.

## X thread (6 posts, @algocracked)

1. Filming in public means publishing strangers: kids walking past, a phone screen with someone's number, a parked car's plate. I built Safe Cut for the Meta AI hackathon: it works out from context who shouldn't be in your video, and hides them. 🧵 ⟨video⟩
2. "Blur every face" tools blur your guest too, and miss the plate and the phone. Safe Cut asks a different question: who is part of this story? Meta's SAM 3.1 tracks every face, person, plate and screen; Muse Voice Transcribe hears who speaks; Muse Spark decides who's who.
3. Muse Spark sees numbered keyframes and votes three separate times on each person. A participant is kept clear only if every vote agrees and there's evidence: an introduction, or speech. Anything uncertain stays hidden. Children are always hidden.
4. It reads context, not just objects. A laptop showing an inbox gets hidden. A laptop showing a menu goes to "needs you", so you confirm it before it's shown.
5. Before anything is published, a second pass audits the rendered video: an independent detector on every frame, plus a Muse Spark red team. Leaks get patched automatically. Then you get a privacy receipt of every decision and who made it.
6. It's open source (MIT), and it runs as a service with spend caps, signed uploads and 24-hour deletion. Watch the demo: safecut.sigmora.org (trying it needs an access code) · code: github.com/mlsniperpro/sigmora-safe-cut · #MetaAIHackathon

## LinkedIn

Creators who film in public publish people who never agreed to be filmed, every day. The tools on the market either blur everyone, guests included, or leave the creator masking by hand for hours.

For the Meta Global AI Developer Hackathon I built **Sigmora Safe Cut**. It decides from context what shouldn't be published:
- Meta's SAM 3.1 tracks faces, people, plates and screens through the whole clip.
- Muse Voice Transcribe works out who speaks.
- Muse Spark votes three independent times on who is part of the story, on numbered keyframes.

Everything uncertain stays hidden, children always are, and the creator approves each decision with the reason in front of them. A final audit checks the rendered video frame by frame before it goes live, and a privacy receipt records what was hidden, why, and who approved it.

It's open source, and it's built to be called by Sigmora, our creator platform. Live demo: safecut.sigmora.org. Code: github.com/mlsniperpro/sigmora-safe-cut.

## 20-second vertical (9:16), side by side

| Time | Top half | Bottom half | Caption |
|---|---|---|---|
| 0–3 s | Raw hero clip 1 | — | "Who shouldn't be in this video?" |
| 3–8 s | Every face blurred in an editor (labelled "illustration": the repo renders no baseline video) | Safe Cut's result | "Blur everything… or decide." |
| 8–14 s | The review panel: the Why drawer on the child (locked) and on the guest (three votes) | — | "Muse Spark votes 3× on who's in the story" |
| 14–18 s | The audit summary and the privacy receipt | — | "Checked frame by frame, then a receipt" |
| 18–20 s | Title card | — | "Safe Cut · built with Meta SAM 3.1 + Muse Spark" |

Shot list: R-01 and R-02 and SR-03, SR-07 from `docs/VIDEO-SCRIPT.md`, re-cropped to 9:16; captions burned in.

## YouTube description

Sigmora Safe Cut: publish real-world footage without exposing the people who never agreed to be in it. Built for the Meta Global AI Developer Hackathon with SAM 3.1, Muse Spark and Muse Voice Transcribe on the Meta Model API.

Safe Cut tracks every face, person, plate and screen. It decides from context who is part of the story, hides everything uncertain, and lets you approve each decision with its reason. It then audits the final render before anything is published, and gives you a privacy receipt.

Safe Cut redacts the picture; the audio is kept as recorded. Everyone on screen is an actor who signed a release. Results and how we measured them: github.com/mlsniperpro/sigmora-safe-cut/blob/main/eval/RESULTS.md

Live demo: https://safecut.sigmora.org · Code (MIT): https://github.com/mlsniperpro/sigmora-safe-cut
