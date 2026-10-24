# Safe Cut: creator pilot programme

Status: **v1, 2026-10-24 (PRE-B, docs only).** This is the Impact evidence (30% of the score, [MAXXING.md](MAXXING.md) §3): **5 creator pilots** with the time saved measured on their own footage. Owner step O4: Claude drafts, the owner sends (sent **Oct 27**, pilots run **Oct 30 – Nov 2**, [MAXXING.md](MAXXING.md) §5). The pain points and personas behind it are in [CREATOR-PROBLEMS.md](CREATOR-PROBLEMS.md); the measured metric is "Creator time" in [EVAL.md](EVAL.md) §2.

## 1. Who we want

Creators who publish footage of real public places with other people in it, and who already have to think about who's in frame. Global, not one country: aim for at least three regions across the 5 pilots.

| Profile | Why they matter | What a good candidate looks like |
|---|---|---|
| **Street interviewers** | The demo persona; highest takedown risk ([CREATOR-PROBLEMS.md](CREATOR-PROBLEMS.md) pain 3) | Posts street Q&A or vox-pop clips weekly; passers-by visible behind the guest |
| **Travel and walk-and-talk vloggers** (including smart-glasses POV) | High volume of incidental faces; Meta-native | Markets, transit, festivals; mentions blurring or privacy in comments or descriptions |
| **Real-estate and property videographers** | Commercial use needs releases and an audit trail; documents and family photos in shot (pain 7) | Agent or videographer posting home tours |
| **Local and citizen news creators** | Protecting witnesses and protesters (persona 3) | Independent local news pages, community reporters |
| **Family creators** (secondary) | Children in shot; child-influencer laws (pain 5) | Only if they already blur other people's children |

Good signs: they've posted about a privacy complaint, they visibly blur faces today, or their audience has asked them to. Not a fit: anyone whose format depends on filming people covertly or mocking them (the BBC and Change.org stories in [CREATOR-PROBLEMS.md](CREATOR-PROBLEMS.md)); we don't want to make that easier to publish, and they'd be a bad story for the submission.

## 2. Where to find 15 candidates

We contact creators only through their **public business channels**, never personal accounts of private individuals, and we don't name anyone in this repo. The candidate list lives in the owner's private sheet (channel link, profile, region, contact route, status).

| Channel type | How to search | Target count |
|---|---|---|
| YouTube channels | Search "street interview", "vox pop", "walking tour 4K", "house tour" with region names; filter to channels with 1k–200k subscribers (big enough to have the problem, small enough to reply). Use the contact email on the channel's About page | 5 |
| TikTok and Instagram creator accounts | Hashtags for street interviews, walking tours and property tours; contact via the business email or the DM route the account invites | 4 |
| Creator communities with self-promotion rules that allow it | Subreddits like r/PartneredYoutube and r/NewTubers (read each community's rules first; post a single call for testers only where allowed, or reply only where someone asked for exactly this, e.g. the threads in [CREATOR-PROBLEMS.md](CREATOR-PROBLEMS.md)) | 2 |
| Property-video professionals | Public business pages and portfolio sites of property videographers and agencies | 2 |
| Local news creators | Public pages of independent local news and citizen-journalism outlets | 2 |

15 candidates → expect about a third to reply and about 5 to finish. If fewer than 5 agree by Oct 29, the owner widens the search the same day; no paid incentives (it would colour the answers), but every pilot gets free access after the event if Safe Cut continues.

## 3. Outreach drafts

Both are under 120 words (DM: 103; email body, without the subject: 110). Personalise the `{…}` parts with something specific from their own videos; never send a template without it.

### 3.1 DM (Instagram, TikTok, X)

> Hi {name}, I liked your {video}, especially {specific detail}. I'm building Safe Cut, a tool that hides passers-by, children, number plates and private screens in street footage while keeping you and your guests clear. It's a hackathon build for Meta's AI developer hackathon, not a finished product. Would you try it on one clip you haven't published yet, between Oct 30 and Nov 2? It takes up to an hour: mask the clip your usual way for at most 30 minutes, run it through Safe Cut, and answer 3 questions. Your footage is deleted automatically afterwards. Can I send details? {your name}, Sigmora

### 3.2 Email

> **Subject:** Try a hackathon tool that hides strangers in your footage?
>
> Hi {name},
>
> I watch your {channel}; {specific detail} is the kind of clip I have in mind. I'm building Safe Cut for Meta's AI developer hackathon (deadline Nov 4). It works out who's part of your video and hides everyone else, plus children, number plates and private screens. You approve every decision.
>
> It's an honest hackathon build, not a finished product. Would you test it on one unpublished clip between Oct 30 and Nov 2? Up to an hour: your usual masking (capped at 30 minutes), then Safe Cut, then 3 questions. Footage is deleted automatically afterwards.
>
> Interested? I'll send an access code and the details.
>
> {your name}, Sigmora (sigmora.org)

**Follow-up** (once, 3 days later, only if no reply): "Just checking this reached you. No worries if it's not for you."

## 4. Consent and data note (send this before they upload)

> **What happens to your clip in the Safe Cut pilot**
>
> - **It's your footage and stays yours.** You upload it yourself with a personal access code. We don't publish it, share it, or use it in our demo, video or repo.
> - **Deleted automatically.** The clip, the redacted version, the receipt and all working files are deleted within `{deletion_deadline}` of upload (the exact time is shown on your result page), or straight away if you press "Delete everything now".
> - **Meta Model API, Standard mode.** To decide what to hide, Safe Cut sends your clip to Meta's Model API (Muse Spark, SAM 3.1, Muse Voice Transcribe) in Standard mode, asking Meta not to store requests (`store: false`) wherever its API accepts that, and deleting the uploaded files after each run. Your privacy receipt records how your data was handled: Standard mode, whether storage was turned off for each model Safe Cut used, and that the uploaded files were deleted. We never use Contributor mode, whose inputs Meta may use to improve its models.
> - **People in your clip.** Your clip may show people who didn't agree to be filmed. That's what Safe Cut is for: the processing exists to hide them, and nobody at our end views your footage unless you share your screen with us.
> - **What we keep:** only what you tell us — your timings, your answers, and (only if you say yes in writing) a quote and how you'd like to be credited. You can withdraw any of it before Nov 4 and we'll remove it.
> - **It's a hackathon build.** Check the result before publishing anything. If you spot something Safe Cut missed, please tell us; that's the most useful thing you can do.

Data-handling facts in this note must match what's deployed ([ARCHITECTURE.md](ARCHITECTURE.md) §5, [AGENTS.md](../AGENTS.md) rule 6). So the two messages make different promises:
- The **outreach on Oct 27** promises only that footage is deleted automatically, which is a design requirement every WP5 build has to meet.
- **This note and the access codes go out only after Claude has checked the live service** (on Oct 29 or the first day after it that WP5 is deployed): the 24 h cleanup job runs, files uploaded to Meta are deleted after each run, and `store: false` is set. `{deletion_deadline}` is then filled from WP5's real cleanup schedule (e.g. "25 hours" for an hourly job that deletes jobs older than 24 h).

If the check fails, no codes go out: the pilot window moves, the promise doesn't.

## 5. Pilot protocol (up to about an hour for the creator)

**Before:** the owner sends a personal access code (one per pilot, so cost and usage are separate), the consent note, and this protocol. Each pilot runs at most **2 clips**. **Decision (caps, PRE-B's to set):** each pilot code has a hard cap of **$6**, and the whole pilot programme a hard cap of **$20**, enforced across all codes by WP5 (a per-code USD limit plus a shared pilot total). $6 is PRE-A's request (`docs/API-NOTES.md` §9.1, `origin/pre-a-research` @ `948b678`): two busy 60 s clips cost $3.82–3.98 there, with pre-call reservations in flight, so a $4 cap could stop a pilot on their second clip. Five codes × $6 could exceed $20, but the $20 total binds first, and pilots are run in order, so at worst the last pilot is told "This access code has used its processing budget" (UI-SPEC §2.6). **The cost figures are PRE-A's:** it estimates the pilots at **$11.20** (10 clips × $1.12 per 30 s clip, §9.1–9.2), well inside the $20 cap. If its figures change, the estimate changes and the caps don't. Request to WP5: support the per-code and shared pilot caps, and **keep pilot codes outside the public demo's daily cap**. PRE-A plans `SAFECUT_DAILY_USD_CAP` at **$3/day** for the public "Try it" (§9.2), and one pilot's two 60 s clips would use most of a day's budget, locking judges out or being locked out by them. Pilot spend counts only against the pilot caps.

**The clip:** one clip they haven't published yet, 15–60 s and **at most 150 MB** (Safe Cut's upload limit, [ARCHITECTURE.md](ARCHITECTURE.md) §5; if the file is bigger, export it at 1080p first), with at least one person in it who isn't part of the video (a passer-by, a shop worker) or a plate, screen or document.

**Steps:**
1. **Usual way, timed, capped at 30 minutes for everyone.** They mask the clip the way they normally would (their editor, YouTube Studio's blur, an app) until they'd be happy to publish it, or until 30 minutes are up. They write down the **minutes**, and if they hit the cap, how far they got (e.g. "3 of 5 people masked"). Capped results are reported as "≥ 30 min (not finished)", never as a measured time. (If they already masked this clip before, they can report that time instead, and say so.) The cap keeps the pilot to about an hour, which is what the outreach promises.
2. **Safe Cut, timed.** Upload the same clip at the pilot link, review the decisions, change anything they disagree with, and render until they'd be happy to publish. They note: total **minutes** from upload to approved render, and how many **chips they changed**.
3. **Check.** They watch the Safe Cut result once and note anything that was **missed** (visible when it shouldn't be) or **wrongly hidden**.
4. **Three questions** (written, a sentence or two each):
   1. Would you publish the Safe Cut version as it is? If not, what would you change first?
   2. Was there a decision you didn't expect? Did its reason make sense?
   3. Would you use this on your next clip? What would stop you?
5. **Permission (separate, optional):** "May we quote your answer to question {n} in our hackathon submission and video? If yes, how should we credit you: name, channel handle, or anonymous with your format and country (e.g. 'a street-interview creator in Lagos')?" **Decision:** each pilot chooses their own credit, and if they don't say, it's the anonymous form. That's the most privacy-protective default, and an upgrade to a name is easy where the reverse isn't.

**Order effect, stated honestly:** the usual way always comes first, so by the Safe Cut step they know the clip. That favours the second method slightly in time, and the submission says so. With 5 pilots this is a small, self-reported study, not a benchmark; it's reported as exactly that.

**What we record per pilot** (private sheet, then committed numbers only): profile, region, clip length, usual-way minutes (and whether it was a capped attempt), Safe Cut minutes, chips changed, misses and wrong hides they reported, the three answers, permission status.

## 6. How results appear in the submission

- **Numbers.** The per-pilot timings (no names, no footage) are committed as a results file under WP7's results folder, e.g. `eval/results/pilots-2026-11-02/metrics.json` with `per_pilot.csv`, so the README, SUBMISSION and video cite them like any other result ([AGENTS.md](../AGENTS.md) rule 9). Report the median and every individual value, plus "n = 5 (self-reported)". Capped attempts are marked, and never treated as measured times.
- **Misses they report** go into the honest-failures section next to the eval's worst-5 exposures.
- **Quotes** appear only with written permission, word for word, credited exactly as they asked. Nothing is paraphrased into a stronger claim.
- **Their footage never appears**, not even redacted, unless a pilot offers it in writing *and* everyone visible unblurred has consented; in practice, assume never.
- If fewer than 5 pilots finish, the submission says how many did. A pilot who found Safe Cut slower or wrong is reported the same way as one who loved it.
- What the pilots test is the review flow in [DESIGN.md](DESIGN.md) §2 (deny by default, one-tap keep); if a pilot asks how decisions are made, point them there.
- Where it shows: the README Impact section and the results table footnote (WP8), [STORYBOARD.md](STORYBOARD.md) shot 8.3 (beat 8 of [DEMO.md](DEMO.md), only with permission), and `docs/SUBMISSION.md`.

## 7. Timeline

| When (EAT) | What | Who |
|---|---|---|
| Oct 25–26 | Build the private list of 15 candidates | Owner (Claude can search public channel types and suggest, never contact) |
| **Oct 27** | Personalise and send DMs/emails | Owner |
| Oct 28–29 | Replies; one follow-up | Owner |
| Oct 29 (or WP5's first live day) | Check the cleanup job, Meta file deletion and `store: false` on the live service; fill `{deletion_deadline}` | Claude |
| Right after that check passes | Send the consent note, protocol and per-pilot access codes | Owner |
| **Oct 30 – Nov 2** | Pilots run | Creators |
| Nov 2 23:59 | Collect timings, answers, permissions | Owner |
| Nov 3 | Commit the pilot results file; WP8 uses it | Claude / WP8 |
