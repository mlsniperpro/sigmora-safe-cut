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

Both are under 120 words (DM: 102; email body, without the subject: 109; placeholders count as one word, as in RULES-CHECKLIST §4). Personalise the `{…}` parts with something specific from their own videos; never send a template without it.

### 3.1 DM (Instagram, TikTok, X)

> Hi {name}, I liked your {video}, especially {specific detail}. I'm building Safe Cut, a tool that hides passers-by, children, number plates and private screens in street footage while keeping you and your guests clear. It's a hackathon build for Meta's AI developer hackathon, not a finished product. Would you try it on one clip you haven't published yet, between Oct 30 and Nov 2 (UTC)? It takes up to an hour: mask the clip your usual way for at most 30 minutes, run it through Safe Cut, and answer 3 questions. Your footage is deleted automatically afterwards. Can I send details? {your name}, Sigmora

### 3.2 Email

> **Subject:** Try a hackathon tool that hides strangers in your footage?
>
> Hi {name},
>
> I watch your {channel}; {specific detail} is the kind of clip I have in mind. I'm building Safe Cut for Meta's AI developer hackathon (deadline Nov 4). It works out who's part of your video and hides everyone else, plus children, number plates and private screens. You approve every decision.
>
> It's an honest hackathon build, not a finished product. Would you test it on one unpublished clip between Oct 30 and Nov 2 (UTC)? Up to an hour: your usual masking (capped at 30 minutes), then Safe Cut, then 3 questions. Footage is deleted automatically afterwards.
>
> Interested? I'll send an access code and the details.
>
> {your name}, Sigmora (sigmora.org)

**Follow-up** (once, 2 days later, on Oct 29, only if no reply): "Just checking this reached you. No worries if it's not for you."

## 4. Consent and data note (send this before they upload)

> **What happens to your clip in the Safe Cut pilot**
>
> - **It's your footage and stays yours.** You upload it yourself with a personal access code. We don't publish it, share it, or use it in our demo, video or repo.
> - **Deleted automatically.** The clip, the redacted version, the receipt and all working files are stored only with Safe Cut's hosting providers (Modal for processing, Cloudflare R2 for uploads; Meta's part is below) and are deleted within `{deletion_deadline}` of upload (the exact time is shown on your result page), or straight away if you press "Delete everything now".
> - **Meta Model API, Standard mode.** To decide what to hide, Safe Cut sends your clip to Meta's Model API (Muse Spark, SAM 3.1, Muse Voice Transcribe) in Standard mode, asking Meta not to store requests (`store: false`) wherever its API accepts that, and deleting the uploaded files after each run. Your privacy receipt records how your data was handled: Standard mode, whether storage was turned off for each model Safe Cut used, and that the uploaded files were deleted. `store: false` doesn't control Meta's short-lived prompt cache, which can briefly hold parts of a request in memory; Safe Cut never asks Meta to keep it longer, and your receipt says so too. We never use Contributor mode, whose inputs Meta may use to improve its models.
> - **People in your clip.** Your clip may show people who didn't agree to be filmed. That's what Safe Cut is for: the processing exists to hide them, and nobody at our end views your footage unless you share your screen with us.
> - **What we keep:** only what you tell us — your timings, your answers, and (only if you say yes in writing) a quote and how you'd like to be credited. Your timings, and short anonymised descriptions of anything Safe Cut missed that you report (never your footage), are published anonymously in our public results (no name, no footage). You can withdraw any of it until **Nov 3, 12:00 UTC**, when we collect results; we publish only after that. After it, we remove your data from every later version on request, but it can't be taken out of copies already published.
> - **It's a hackathon build.** Check the result before publishing anything. If you spot something Safe Cut missed, please tell us; that's the most useful thing you can do.

Data-handling facts in this note must match what's deployed ([ARCHITECTURE.md](ARCHITECTURE.md) §5, [AGENTS.md](../AGENTS.md) rule 6). So the two messages make different promises:
- The **outreach on Oct 27** promises only that footage is deleted automatically, which is a design requirement every WP5 build has to meet.
- **This note and the access codes go out only after Claude has checked the live service** (on Oct 29 or the first day after it that WP5 is deployed): the 24 h cleanup job runs, files uploaded to Meta are deleted after each run, a live receipt's `data_handling.store_by_model` and `no_store_param` match what PRE-A `docs/API-NOTES.md` §10.6 sends (which models get `store: false`, and which take no `store` field), and its `data_handling.notes` carries the prompt-cache sentence (PRE-A §3.7), as the note promises. `{deletion_deadline}` is then filled from WP5's real cleanup schedule (e.g. "25 hours" for an hourly job that deletes jobs older than 24 h).

If the check fails, no codes go out: the pilot window **shrinks** (it still ends Nov 2 23:59 UTC, the pilot kind's code window, and results are still collected Nov 3 12:00 UTC), pilots are told the new start date, and the promise doesn't change.

## 5. Pilot protocol (up to about an hour for the creator)

**Before:** the owner sends a personal access code (one per pilot, so cost and usage are separate; it starts new work until **Nov 2 23:59 UTC**, given in the pilot's local time, and the clip can be viewed and deleted after that), the consent note, and this protocol. Each pilot runs **one clip** (§5). The $6 code cap covers that clip plus one retry, so a failed or repeated upload doesn't end the pilot. **Decision (caps, PRE-B's to set):** each pilot code has a hard cap of **$6**, and the whole pilot programme a hard cap of **$20**, enforced across all codes by WP5 (a per-code USD limit plus a shared pilot total). $6 is PRE-A's request (`docs/API-NOTES.md` §9.1, `origin/pre-a-research` @ `565eee3`): two busy 60 s clips cost $4.04–4.18 there (§9.1 A10 @ `565eee3`), with pre-call reservations in flight, so a $4 cap could stop a pilot on their second clip. Pilot clips are **15–45 s**. At PRE-A's figures a 45 s clip costs about $1.5–1.7 (between its $1.12 at 30 s and $2.02–2.09 at 60 s), so the expected spend is about 5 × $1.5–1.7 ≈ $8 for five pilots, and even if every pilot needs one retry (10 runs) the total is about $15–17 of the $20. That leaves room for a few re-runs, but not unlimited ones. If the shared $20 runs out anyway, the next pilot is told "The pilot budget has been used up" (UI-SPEC §2.6 `pilot_pool_cap`) rather than to ask for a new code, and the README reports how many pilots finished. **The cost figures are PRE-A's:** it estimates the pilots at **$11.20** (10 clips × $1.12 per 30 s clip, §9.1–9.2). Longer clips cost more, which is why the clip length above is capped at 45 s. If its figures change, the estimate changes and the caps don't. Request to WP5: support the per-code and shared pilot caps, and **keep pilot codes outside the public demo's daily cap**. PRE-A plans `SAFECUT_DAILY_USD_CAP` at **$3/day** for the public "Try it" (§9.2), and one pilot's 45 s clip (about $1.5–1.7) would use half a day's budget, locking judges out or being locked out by them. Pilot spend counts only against the pilot caps.

**The clip:** one clip they haven't published yet, 15–45 s and **at most 150 MB** (Safe Cut's upload limit, [ARCHITECTURE.md](ARCHITECTURE.md) §5; if the file is bigger, export it at 1080p first), with at least one person in it who isn't part of the video (a passer-by, a shop worker) or a plate, screen or document.

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

- **Numbers.** The per-pilot timings (no names, no footage) are committed as a results file under WP7's results folder, e.g. `eval/results/pilots-2026-11-03/metrics.json` with `per_pilot.csv`, committed only after the Nov 3 12:00 UTC withdrawal cutoff (§4) and by Nov 3 18:00 EAT (STORYBOARD §2), so the README, SUBMISSION and video cite them like any other result ([AGENTS.md](../AGENTS.md) rule 9). Report the median and every individual value, plus "n = `{n_pilots}` (self-reported)", the real count, never a planned 5. `metrics.json` carries `n_pilots` (pilots who completed the protocol, capped ones included) and `n_capped` (the subset of them who hit the 30-minute cap on the manual step), which STORYBOARD shot 8.3 uses. Capped attempts are marked, and never treated as measured times.
- **Misses they report** go into the honest-failures section next to the eval's worst-5 exposures.
- **Quotes** appear only with written permission, word for word, credited exactly as they asked. Nothing is paraphrased into a stronger claim. **When `n_pilots` ≤ 2**, a median or an individual value can reveal a pilot's own time, so across the whole submission (README, SUBMISSION, video and the committed `per_pilot.csv`) quotes carry **only the anonymous credit** (format + country), never a name or handle, even if a pilot chose a named credit; the pilot is told why. Then no published timing can be tied to a named person. With 3 or more pilots, named credits are allowed as each pilot chose, and timings stay unattributed.
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
| Oct 29 (or WP5's first live day) | Check the cleanup job, Meta file deletion, and the receipt's `store_by_model` / `no_store_param` (PRE-A §10.6) and prompt-cache note (PRE-A §3.7) on the live service; fill `{deletion_deadline}` | Claude |
| Right after that check passes | Send the consent note, protocol and per-pilot access codes | Owner |
| **Oct 30 – Nov 2** | Pilots run | Creators |
| Nov 3 15:00 EAT (12:00 UTC) | Collect timings, answers, permissions (pilot codes stopped at Nov 2 23:59 UTC; this leaves time for late answers) | Owner |
| Nov 3, by 18:00 EAT | Commit the pilot results file; WP8 uses it for the script (final by 20:00 EAT) | Claude / WP8 |
