# Official rules checklist (for Oct 26)

Status: **v1, 2026-10-24 (PRE-B, docs only).** The official rules publish at kickoff (Oct 26 12:00 ET = 16:00 UTC = 19:00 EAT). Claude reads them that evening, answers every question below with a **quote and the URL**, applies the matching plan, and updates the event table in [MAXXING.md](MAXXING.md) §1 (the "to confirm" line there is this list). What we assume today is in MAXXING §1 and [AGENTS.md](../AGENTS.md); nothing below is a fact about the rules until it's checked.

**How to use this:** for each item, find the clause, paste it into the "Found" line in the PR that updates MAXXING, pick the matching row, and **do the action straight away**. Claude decides every row; nothing here waits for an answer. Rows marked 🚩 could disqualify us, so their action happens the same evening. Steps only the owner can physically do (accepting the rules, filling the entry form, identity checks, creating or publishing a repo) go into [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md) as checklist items with the default written in, and work continues around them. If the rules are silent, take the "silent" row.

## 0. Answers from the official participant guide (captured 2026-10-26 16:25Z)

The owner transcribed the login-gated participant guide into [OFFICIAL-GUIDE.md](OFFICIAL-GUIDE.md) (source: cerebralvalley.ai/e/meta-ai-developer-hackathon/details); it's the authoritative source for the rows below. Where the guide is silent, the "Silent" rows of §1–§11 still apply until the full legal rules are read.

| Topic | The guide says | Row that applies → what we do |
|---|---|---|
| Theme (Stage 1, pass/fail) | Build toward "Build for Your World" or "Push the Frontier"; "reasonably uses the Meta Model API and/or Meta open-weight models" | **Build for Your World**: a creator's own problem (publishing street footage without exposing bystanders), solved with Muse Spark, SAM 3.1 and Muse Voice Transcribe through the Meta Model API. The submission names the theme in its first line (§5) |
| Anti-projects | No medical advice, basic RAG, "simple image analyzers", education chatbots, job screeners, nutrition coaches, personality analyzers, sports coaches, politics or war | None apply. Safe Cut isn't a simple image analyzer: it's a video pipeline that tracks people through a clip, decides who's part of the story from speech and context, audits its own render and keeps a human approval step. The submission's first paragraph says so, so a Stage 1 reviewer can't file it as one. It analyses no one's personality, health or sport. It's a neutral privacy tool: political or war footage isn't a target use case, and the submission and video keep the "protesters" persona of PILOTS §1 out of their copy |
| New work only (§1) | "The demo must show only features, code and functionality built during the Hackathon. Judges must be able to tell what was created during the event"; startups "must clearly identify what is new" | §1 row 2 (pre-existing work allowed if disclosed): every product-code commit is after Oct 26 16:00 UTC; the pre-kickoff commits are planning docs plus README, LICENSE, AGENTS.md, `.gitignore` and agent tooling under `.agent/`. The README and `docs/SUBMISSION.md` (WP8) open with a **"Built during the event"** paragraph: first code commit, its time ("Safe Cut's code was built during the hackathon, from 2026-10-26 16:00 UTC; the planning docs under `docs/` were started before kickoff and updated during the event; git history dates every change", adapted from PRE-A's wording), each clip's real filming and labelling dates, from the owner (never a blanket claim), and that Sigmora is an existing product while the Safe Cut integration with it is new. The video's end card states the code boundary, that the demo clips were filmed with consenting actors (dates in the README), and (only when 8.1 shows Sigmora) the Sigmora split ([STORYBOARD.md](STORYBOARD.md) 9.1), and any Sigmora screen carries an on-screen label (8.1) |
| Team (§7) | At most 4 people; solo allowed; "every contributor is listed"; one Representative submits | Solo entry by the owner (the Representative). If labeller B agrees, list them as a contributor (labels); Claude is a tool, not a contributor |
| Track (§7) | Indie Developer track and Startups track; the problem statements are themes, not tracks | **Startups track** (MAXXING), theme Build for Your World |
| Video (§4) | A three-minute demo video | §4 row "a limit of 3 minutes or more": keep the 2:50 cut; no Stage A/B cut needed |
| Live product | Required, and "holds up live" is part of the Demo criterion | As planned (WP5/WP6 on the custom domain; judge codes Nov 5–10, §11). From Nov 11 the landing page runs on `GET /v1/demo` only (UI-SPEC request 19, no Meta calls) and `/try` answers every code with UI-SPEC §2.6's "Code outside its dates" copy (PRE-A `docs/API-NOTES.md` §9.2) |
| Repo (§3) | "Repositories must be public"; check it's public before submitting | Public at submission. The owner keeps it private until they OK it, so going public is an owner step in [BLOCKED-PRE-B.md](BLOCKED-PRE-B.md), after Claude's secrets-and-footage check |
| Judging (§8) | Stage 2 weights Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25; Stage 3: top 5 per track, demo videos watched live | §8 row 1: same weights, no MAXXING change. Stage 3 means the video itself is the finals pitch |
| Building period | Kickoff is Mon Oct 26 12:00 PM ET; the "Building period" row says Oct 27 – Nov 4 | Our boundary is kickoff, Oct 26 16:00 UTC (AGENTS rule 1); WP0 and WP6 committed product code on Oct 26 after 16:00 UTC. Claude quotes the full rules' clause on when work may start once they're read; the owner asks in Discord #office-hours (BLOCKED-PRE-B) by Nov 3, the last day for technical questions. Default: keep the kickoff boundary, and the README's "Built during the event" paragraph lists the exact commit timestamps, including the Oct 26 ones, so judges can see them. If the answer is that work starts Oct 27, Claude lists the Oct 26 commits in the README and the owner decides then |
| Deadline (§5) | Nov 4 9:00 PM ET = Nov 5 02:00 UTC; Nov 3 is the last full day for technical questions | As planned: submit by Nov 4 23:00 EAT (20:00 UTC) |
| Most Viral ($20k, §6) | Post the demo on X and submit the post link; engagement counted up to Nov 8 EOD | Post the demo on X **before** submitting, so the post link goes into the submission; then the launch thread. This replaces §6's "hold all posts until after submission" default for the X demo post |
| Community Vote ($10k, §6) | Public gallery, one vote per verified account, announced Nov 16 | §6 row 1: the launch thread links to our gallery page from Nov 9. Voters after Nov 10 see the landing page's replay demo (the Live product row) |
| Best Agentic Use-Case ($5k) | Autonomy, task completion, practical usefulness | Target it: the miss loop, the self-audit with its patch loop and the fail-closed holds are autonomous steps with a human approval gate. WP8's submission names them in one paragraph |
| Best Build on Meta Open-Weight Models ($10k) | Muse Glimmer or Muse Spark Open, own hardware or partner inference (Baseten id `meta-models/muse-spark-open-1026`); the partner verifies it | **Decided by PRE-A** (`docs/API-NOTES.md` §3.8, 2026-10-26): Muse Spark Open on Baseten as an additive **second opinion in the audit** (WP4), after the Muse Spark red team; it can only add leaks, `SAFECUT_OPEN_WEIGHT_AUDIT` off until WP0's probe h (the Baseten probe) passes, and `SAFECUT_OPEN_WEIGHT_CODE_KINDS` empty until the hero and dev cast sign the Baseten addendum (BLOCKED-PRE-B). PRE-B names it from `audit.open_weight.model` wherever the auditors are named (UI-SPEC §1.3 auditor name rule, the §5 models line, STORYBOARD 9.1). Owner steps (credits, `BASETEN_API_KEY`) are in [BLOCKED-PRE-B.md](BLOCKED-PRE-B.md) and PRE-A's `docs/BLOCKED-PRE-A.md` |
| Best Creative Build ($5k) | Muse Image or Muse Wonder | Not targeted (Muse Wonder only if WP0 adopts it for its own reasons) |
| Rights to code, data and assets | "Banned: … any code, data or assets you don't have the rights to" | Every asset's licence is named in the README (WP8): EgoBlur weights under the licence shown with the download (PRE-A `docs/research/egoblur-gen2.md`: Apache 2.0 on the project page; access requires an agreement), SA-Co/VEval SmartGlasses under CC BY 4.0 with attribution, the hero clips under signed releases ([SHOTLIST.md](SHOTLIST.md)), no music. `SR-10`'s editor appears only as the owner's own tool, unbranded where possible, and is named as not ours |
| Models listed | Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe, SAM 3.1; Muse Glimmer, Muse Spark Open; Muse Code | The "Meta models used" line (§5) names only these, plus EgoBlur as Meta's open-source detector when it runs, and Muse Spark Open (`meta-models/muse-spark-open-1026` on Baseten) only when the final run's `audit.open_weight.status` is `ok`, with the scope note "Muse Spark Open's second opinion ran only on consented hero and dev footage, where `audit.open_weight.status` is `ok`; the test-split numbers were measured without it" (named from `audit.open_weight.model`, PRE-A §3.8) |

## 1. Pre-existing code

Look for: "pre-existing", "previously built", "prior work", "must be created during", "open-source libraries", "existing projects".

| If the rules say | We do |
|---|---|
| Everything must be built during the event; libraries and APIs are fine | As planned: before kickoff this repo has planning docs plus README, LICENSE, AGENTS.md, `.gitignore` and agent tooling under `.agent/` (including one short calculation script in PRE-A's history, since removed, which the README's "Built during the event" paragraph discloses), and every product-code commit is after Oct 26 16:00 UTC ([AGENTS.md](../AGENTS.md) rule 1). The README keeps "What existed before Oct 26" ([README.md](../README.md)), which lists Sigmora's pre-existing parts and says none was copied |
| Pre-existing work is allowed if disclosed | The same, plus a dated "Prior work" paragraph in `docs/SUBMISSION.md` (WP8) naming Sigmora and the pre-event design docs |
| 🚩 Even design docs or planning before the event aren't allowed | Never rewrite history to hide dates. Submit from a **fresh repo created at kickoff**: every code commit there is after kickoff, and the pre-event docs are re-added in one commit whose message gives their original dates and this repo's link. That's reversible, and the full history will stay public here. Add "owner creates the fresh repo" to [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md) |
| 🚩 Projects connected to an existing company product are excluded | Present Safe Cut as standalone (it is: [ARCHITECTURE.md](ARCHITECTURE.md) §1). Drop "Publish to Sigmora" from the demo (STORYBOARD shot 8.1 ends on the download, `SR-09` isn't recorded) and from the README and submission; keep the Sigmora integration out of the submitted repo |
| Silent | Act as in the first row, and keep the disclosure (it costs nothing) |

## 2. More than one submission per participant

Look for: "one submission per", "multiple projects", "per team", "per participant".

| If the rules say | We do |
|---|---|
| One submission per participant or team | Safe Cut is the only entry (the plan already). Make sure no other project by the owner is submitted to this event |
| Multiple submissions allowed | Still one entry: the owner chose depth over breadth ([MAXXING.md](MAXXING.md) §0) |
| One per track | Startup track only. Check whether "Build for Your World" is a theme (applies to all) or its own track (see §7) |
| Silent | One entry |

## 3. Repo visibility and licence

Look for: "public repository", "GitHub", "open source", "licence/license", "judges must have access".

| If the rules say | We do |
|---|---|
| Public repo required | Owner step O7: the owner makes `sigmora-safe-cut` public before submitting, once they OK it (in [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md)); until then it stays private. Before that, Claude checks the repo has no secrets, footage or private data ([AGENTS.md](../AGENTS.md) rule 4) and posts the result |
| A specific open-source licence (e.g. MIT, Apache-2.0) | MIT already ([LICENSE](../LICENSE)). If they require another licence, Claude switches `LICENSE` to it at kickoff in its own commit (it covers only this repo's code, all written for the event) |
| Private repo with judge access allowed | Still public: it supports the "holds up in production" story and the bonus prizes |
| Repo must be created after kickoff | 🚩 This repo predates kickoff (docs only). Same action as "even design docs aren't allowed" in §1: a fresh repo at kickoff, the docs re-added in one dated commit, and "owner creates the fresh repo" in [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md) |
| Silent | Public, MIT |

## 4. Video length and hosting

Look for: "video", "demo", "minutes", "YouTube", "Loom", "unlisted".

| If the rules say | We do |
|---|---|
| A limit of 3 minutes or more | Keep the 2:50 cut ([STORYBOARD.md](STORYBOARD.md)) |
| A limit under 2:50 | Cut in two stages, re-timing the VO at ≤ 150 wpm each time (durations from [STORYBOARD.md](STORYBOARD.md) §1, which totals 170 s). **Stage A → 2:22:** drop 8.3 (pilot card, −5 s) and 4.2 (guest drawer, −9 s); shorten 5.2 to 5 s (−5), 2.2 to 5 s (−5), 6.1 to 6 s (−4). **Stage B → 2:00:** also drop 3.1 (open on the progress list, −7 s) and 7.2 (fold the over-blur line into 7.1, which grows from 12 to 14 s, net −6 s); shorten 9.1 to 5 s (−5), 3.3 to 7 s (−3), 8.2 to 6 s (−1). That keeps the hook, the review panel, the context test, the re-entry guarantee, the numbers and the close. **Below 2:00:** keep only 1.1–1.2, 2.1, 3.2–3.3, 4.1, 5.1, 6.1 (6 s), 7.1 (14 s) and 9.1 (5 s), about 1:20 in total, and trim each shot evenly to fit. That still puts one shot of each judging criterion on screen |
| A longer maximum (e.g. 5 min) | Still ≤ 2:50 ([DEMO.md](DEMO.md): judges skim long videos) |
| YouTube required | Upload to the owner's channel (Silicon Savannah Guy), unlisted, then public at submission ([DEMO.md](DEMO.md)) |
| A specific host (Loom, Vimeo, upload to the form) | Use it; keep a YouTube copy for the bonus prizes if the rules allow |
| Video must not include AI voice, or AI voice must be disclosed | Already met: the VO is the owner's own recorded voice, not the clone (decision in [STORYBOARD.md](STORYBOARD.md) rule 6), so there's nothing to disclose |
| Silent | YouTube, unlisted until submission, ≤ 2:50 |

### VO for the cut versions

Shortened shots get these lines, so every cut version stays at or under 150 wpm (STORYBOARD rule 6). Word counts include placeholders as one word each, and wpm = words ÷ seconds × 60.

| Shot | Length after cut | VO | Words | wpm |
|---|---|---|---|---|
| 2.2 | 5 s | "or mask by hand for `{manual_minutes}` minutes. Most just publish." | 10 | 120 |
| 5.2 | 5 s | "It asks you before showing it. Blur tools don't make that call." | 12 | 144 |
| 6.1 | 6 s | "If the tracker loses someone, they come back hidden, until you say otherwise." | 13 | 130 |
| 3.3 | 7 s | "Muse Spark decides who's part of the story. Anything uncertain stays hidden, with a reason." | 15 | 129 |
| 7.1 (+7.2) | 14 s | "On `{n_test_clips}` labelled test clips, Safe Cut hid `{recall_full}` of what should be hidden, with `{leak_bursts_full}` leak bursts, and over-blur at `{overblur_full}`, against `{overblur_blur_all}` for blur-every-face." | 26 | 111 |
| 8.2 | 6 s | "You keep a privacy receipt: what was hidden, why, and who approved it." | 13 | 130 |

Below 2:00, each kept shot's VO is cut to at most 2.5 words per second of its new length, and the same rule applies.

## 5. Required form fields

Look for: the submission form itself (Cerebral Valley), "submission requirements", "include".

| What to capture | We do |
|---|---|
| The exact field list, in order, with character limits | Copy it verbatim into `docs/SUBMISSION.md` first thing (WP8 step 3) so WP8 fills the real fields, not guessed ones |
| A required "Meta models used" field or tag | List exactly what runs: Muse Spark 1.3 (and 1.2 if the speech fallback is used), SAM 3.1, Muse Voice Transcribe, and the auditor named in the final run's `audit.json` `egoblur.model` (EgoBlur Gen 2, or EgoBlur Gen 1 if WP4 picked it, or under PRE-A's Oct 28 fallback no EgoBlur at all: YuNet isn't a Meta model, so it's not listed); Muse Wonder only if WP0 adopted it ([ARCHITECTURE.md](ARCHITECTURE.md) §4). Add Muse Spark Open (`meta-models/muse-spark-open-1026`, on Baseten) only when the final run's `audit.open_weight.status` is `ok`, with the scope note "Muse Spark Open's second opinion ran only on consented hero and dev footage, where `audit.open_weight.status` is `ok`; the test-split numbers were measured without it", named from `audit.open_weight.model` (PRE-A §3.8). The WP8 README and `SUBMISSION.md` name the auditors the same way (UI-SPEC §1.3 auditor name rule). |
| A demo link judges must open without a login | Check that the landing page plays the precomputed hero result with no code, and put the judge access code in the testing-instructions field ([UI-SPEC.md](UI-SPEC.md) §1, §2) |
| Required screenshots or a slide deck | Add them to the WP8 brief; screenshots come from WP6's PR |
| Team member details or a company name | See §10 |
| Deadline time zone wording | Confirm it's Nov 4 21:00 ET (= Nov 5 02:00 UTC, after US clocks change on Nov 1 = Nov 5 05:00 EAT). We submit by Nov 4 23:00 EAT anyway ([MAXXING.md](MAXXING.md) §4) |

## 6. Bonus prizes: community vote and most viral

Look for: "community vote", "people's choice", "most viral", "social", "views", "likes", "hashtag", "tag".

| If the rules say | We do |
|---|---|
| Community vote happens on a platform page (e.g. upvotes on the gallery) | The launch thread (WP8 `docs/LAUNCH.md`) links straight to our gallery page; ask people to vote, never offer anything in return |
| "Most viral" is measured by views or engagement on a named platform, with a required hashtag or tag | Post the 20 s side-by-side Short and the X thread there with the exact hashtag/tag, inside the stated window (planned Nov 4–8) |
| Votes must come from registered participants only | Ask other participants in the event community, not the general public |
| 🚩 Buying views, vote-trading or bots disqualify | We do none of these. Note it in LAUNCH.md so nobody "helps" that way |
| Posting before the deadline isn't allowed | Hold all posts until after submission |
| Silent | Post the demo on X just before submitting (the guide asks for the post link, §0); everything else after submitting, with plain claims and every number from RESULTS.md ([AGENTS.md](../AGENTS.md) rule 9) |

## 7. Team and track rules

Look for: "team size", "solo", "track", "Startup track", "Build for Your World", "eligible to compete in".

| If the rules say | We do |
|---|---|
| Solo entries allowed | The owner enters alone (Claude is a tool, not a team member) |
| A minimum team size above 1 | 🚩 Add a real contributor as a teammate: labeller B is the natural one, because they contribute the second set of labels. Recruiting is the owner's step ([`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md), default: labeller B). Claude never counts as a team member |
| Startup track needs an incorporated company, a pitch deck, traction or a business model | Gather what's true. Sigmora's legal status is a fact only the owner holds, so it's in [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md). Default: enter as an individual and present Sigmora as the product Safe Cut plugs into; switch to the company entry only if the track requires it (§10). Also gather the Sigmora integration, the pilots ([PILOTS.md](PILOTS.md)), a short business section in SUBMISSION.md. Never overstate traction |
| "Build for Your World" is a separate track, not a theme | Enter the **Startup track**. It has the biggest prizes and is judged on "holds up in production", which is what WP5/WP6 build. Name the theme in the description only if it's allowed there |
| Judging is on the deployed product ("holds up in production") | Matches the plan (WP5 deploys; WP6 on the custom domain) |
| Silent | Startup track, solo, theme stated in the submission |

## 8. Judging criteria wording

Look for: the exact criteria, weights and descriptions; and whether finals judging differs from the first round.

| If the rules say | We do |
|---|---|
| The same four criteria and weights (Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25) | No change to [MAXXING.md](MAXXING.md) §3 |
| Different weights or extra criteria (e.g. "originality", "responsible AI", "use of open models") | Update MAXXING §3's judging map the same evening and re-check what [EVAL.md](EVAL.md) measures; add a row that names the evidence and the WP that produces it |
| Specific Meta tools are rewarded (e.g. Llama, Muse Code, open weights) | Check whether we use them honestly already (EgoBlur is Meta's; the Muse Glimmer local mode is a stretch in [DESIGN.md](DESIGN.md) §4). Don't bolt on a model for points; the owner's preference is depth, not a tour ([MAXXING.md](MAXXING.md) §2) |
| The live finals have their own format or length | Update the finals rehearsal plan in [DEMO.md](DEMO.md) (live run on hero clip 1, labelled demo-mode fallback) |

## 9. IP licence

Look for: "licence to Meta/Cerebral Valley", "ownership", "confidential", "publicity", "use your name".

| If the rules say | We do |
|---|---|
| We keep ownership; organisers get a licence to show and promote it (matches the waiver) | No change. Treat everything submitted as public ([MAXXING.md](MAXXING.md) §1, Waiver) |
| 🚩 The organisers take ownership or an exclusive licence | Submit **only this repo**, which will be public under MIT before submission (if this clause applies, the owner makes it public at once) (a licence granted to everyone can't be made exclusive afterwards), and keep Sigmora's own code out of anything submitted. Record the clause in the Decisions section of the MAXXING update |
| Rights to the video and the people in it | The hero clips' releases already cover "may be shared with Meta and Cerebral Valley and published online" ([SHOTLIST.md](SHOTLIST.md) release form). Check the release wording matches any extra rights the rules ask for; if not, get the actors to sign an addendum |
| Third-party assets (music, fonts) must be licensed | No music in the video, or royalty-free with its licence noted |
| Silent | Keep MIT; nothing confidential goes in |

## 10. Eligibility: Kenya, individual vs company

Look for: "eligible countries", "excluded", "sanctions", "age", "individual", "company", "employees", "taxes", "prize payment".

| If the rules say | We do |
|---|---|
| Open worldwide except listed countries, and Kenya isn't listed | Continue. Kenya is also not in Meta's Restricted Territories (Geographic Use Policy, updated Oct 12; [MAXXING.md](MAXXING.md) §1). Calls go direct, never through a proxy ([AGENTS.md](../AGENTS.md) rule 7) |
| 🚩 Kenya is excluded, or only some countries can win prizes | Comply exactly; never work around it (no VPN, no proxy, no entering from another country). If Kenyan residents can take part but not win some prizes, still submit and compete for what's open. If they can't enter at all, stop the submission work (WP8) and keep building the product, which still ships in Sigmora |
| Individuals only | The owner enters as an individual; Sigmora is described as the product Safe Cut plugs into |
| Companies may enter / the Startup track expects one | Enter as an individual unless the Startup track **requires** a company; then enter as Sigmora's company, and the legal name and country go into [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md) for the owner to supply |
| Prize payment needs tax forms or a bank in a given country | Write down what a Kenyan winner needs and add it to [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md) as an after-judging item; nothing to do before then |
| Employees of Meta, Cerebral Valley or partners are excluded | Confirm nobody on the entry is one |
| Age or identity checks | Owner's step ([`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md)) |

## 11. Also check (quick)

| Question | Default if silent |
|---|---|
| Can the $150 Meta credits be topped up with our own money, and is spending outside credits allowed? | Stay within $150 ([AGENTS.md](../AGENTS.md) rule 10) |
| Are other APIs or hosts (Modal, Vercel) allowed alongside Meta's? | Yes; the README says what each one does |
| Must the demo stay live through judging and finals (Nov 9)? | Keep it live, with judge codes valid, from Nov 5 00:00 to Nov 10 23:59 UTC (or until the Meta credits expire, if earlier: the owner notes the expiry when claiming them, PRE-A `docs/API-NOTES.md` §9.2) (PRE-A `docs/API-NOTES.md` §9.2's public window, 6 days × $3; MAXXING §4's "live to Nov 9" is stale, a request to its owner). From Nov 11 (the community vote runs to Nov 16, [OFFICIAL-GUIDE.md](OFFICIAL-GUIDE.md)) the landing page's replay demo (`GET /v1/demo/{hero_id}`, UI-SPEC §8 request 19, no Meta calls) stays up and judge codes are **not** extended, because another $3 day would use PRE-A's whole $3.00 headroom, which is shared with every other overrun |
| Any rules on processing personal data or footage of real people? | Our rules already go further: consented hero clips only on screen; real-public clips stored only on the owner's machines, their frames sent to Meta's Model API during the test runs (Standard model IDs, `store: false`, files deleted), and only metrics published ([AGENTS.md](../AGENTS.md) rule 5) |
| Can the submission be edited after the deadline (e.g. the video link)? | Assume no: submit complete by Nov 4 23:00 EAT |

## 12. After reading the rules

- [ ] Every item above has a quote + URL in the MAXXING update PR, or "silent".
- [ ] Every 🚩 that applies has its action carried out on Oct 26, and any owner-only step is in [`BLOCKED-PRE-B.md`](BLOCKED-PRE-B.md).
- [ ] `docs/SUBMISSION.md` has the exact form fields (WP8 owns the file; Claude may seed it with the field list).
- [ ] [STORYBOARD.md](STORYBOARD.md) is adjusted if the video limit is under 2:50.
- [ ] [MAXXING.md](MAXXING.md) §1 and §3 are updated.
