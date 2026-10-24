# Official rules checklist (for Oct 26)

Status: **v1, 2026-10-24 (PRE-B, docs only).** The official rules publish at kickoff (Oct 26 12:00 ET = 16:00 UTC = 19:00 EAT). Claude reads them that evening, answers every question below with a **quote and the URL**, applies the matching plan, and updates the event table in [MAXXING.md](MAXXING.md) §1 (the "to confirm" line there is this list). What we assume today is in MAXXING §1 and [AGENTS.md](../AGENTS.md); nothing below is a fact about the rules until it's checked.

**How to use this:** for each item, find the clause, paste it into the "Found" line in the PR that updates MAXXING, pick the matching row, and do the action. If the rules are silent, take the "silent" row. If an answer could disqualify us, **stop and tell the owner the same evening** (marked 🚩).

## 1. Pre-existing code

Look for: "pre-existing", "previously built", "prior work", "must be created during", "open-source libraries", "existing projects".

| If the rules say | We do |
|---|---|
| Everything must be built during the event; libraries and APIs are fine | As planned: this repo has docs only before kickoff and every code commit is after Oct 26 16:00 UTC ([AGENTS.md](../AGENTS.md) rule 1). The README keeps "What existed before Oct 26" ([README.md](../README.md)), which lists Sigmora's pre-existing parts and says none was copied |
| Pre-existing work is allowed if disclosed | The same, plus a dated "Prior work" paragraph in `docs/SUBMISSION.md` (WP8) naming Sigmora and the pre-event design docs |
| 🚩 Even design docs or planning before the event aren't allowed | Tell the owner. Options: keep the docs but mark them clearly as pre-event planning in the README; or squash them into the kickoff commit with an honest note. The owner decides; never rewrite history to hide dates |
| 🚩 Projects connected to an existing company product are excluded | Tell the owner. Safe Cut is standalone; Sigmora is only a caller. Be ready to drop "Publish to Sigmora" from the demo ([STORYBOARD.md](STORYBOARD.md) shot 8.1) |
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
| Public repo required | Owner step O7: make `sigmora-safe-cut` public at kickoff. Check before flipping that the repo has no secrets, footage or private data ([AGENTS.md](../AGENTS.md) rule 4) |
| A specific open-source licence (e.g. MIT, Apache-2.0) | MIT already ([LICENSE](../LICENSE)). If they require Apache-2.0 or another, change the licence file at kickoff (the owner approves) |
| Private repo with judge access allowed | Still public: it supports the "holds up in production" story and the bonus prizes |
| Repo must be created after kickoff | 🚩 This repo was created before kickoff (docs only). Tell the owner; options: a fresh repo at kickoff with the docs re-added in one commit that says where they came from, or a written note if a judge-facing explanation is allowed |
| Silent | Public, MIT |

## 4. Video length and hosting

Look for: "video", "demo", "minutes", "YouTube", "Loom", "unlisted".

| If the rules say | We do |
|---|---|
| A limit of 3 minutes or more | Keep the 2:50 cut ([STORYBOARD.md](STORYBOARD.md)) |
| A limit under 2:50 (e.g. 2:00) | Cut beats in this order until it fits: 8.3 (pilot card), 4.2 (guest drawer), 5.2 (shorten to 5 s), 2.2 (shorten to 5 s), 6.1 (shorten to 6 s). Keep the hook, the review panel, the context test, the numbers and the close |
| A longer maximum (e.g. 5 min) | Still ≤ 2:50 ([DEMO.md](DEMO.md): judges skim long videos) |
| YouTube required | Upload to the owner's channel (Silicon Savannah Guy), unlisted, then public at submission ([DEMO.md](DEMO.md)) |
| A specific host (Loom, Vimeo, upload to the form) | Use it; keep a YouTube copy for the bonus prizes if the rules allow |
| Video must not include AI voice, or AI voice must be disclosed | VO in the owner's own voice (O9). If the cloned voice is used, disclose it as the rule asks |
| Silent | YouTube, unlisted until submission, ≤ 2:50 |

## 5. Required form fields

Look for: the submission form itself (Cerebral Valley), "submission requirements", "include".

| What to capture | We do |
|---|---|
| The exact field list, in order, with character limits | Copy it verbatim into `docs/SUBMISSION.md` first thing (WP8 step 3) so WP8 fills the real fields, not guessed ones |
| A required "Meta models used" field or tag | List exactly what runs: Muse Spark 1.3 (and 1.2 if the speech fallback is used), SAM 3.1, Muse Voice Transcribe, EgoBlur Gen 2; Muse Wonder only if WP0 adopted it ([ARCHITECTURE.md](ARCHITECTURE.md) §4) |
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
| Silent | Post after submitting, with plain claims and every number from RESULTS.md ([AGENTS.md](../AGENTS.md) rule 9) |

## 7. Team and track rules

Look for: "team size", "solo", "track", "Startup track", "Build for Your World", "eligible to compete in".

| If the rules say | We do |
|---|---|
| Solo entries allowed | The owner enters alone (Claude is a tool, not a team member) |
| A minimum team size above 1 | 🚩 Tell the owner the same evening; they decide whether to add a teammate (e.g. labeller B if they'd be a real contributor) |
| Startup track needs an incorporated company, a pitch deck, traction or a business model | Gather what's true: Sigmora as the company (if it is one), the Sigmora integration, the pilots ([PILOTS.md](PILOTS.md)), a short business section in SUBMISSION.md. Never overstate traction |
| "Build for Your World" is a separate track, not a theme | Choose with the owner on Oct 26; the plan assumes Startup track with the theme |
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
| 🚩 The organisers take ownership or an exclusive licence | Tell the owner before anything is submitted; Sigmora's own code is never part of the submission, only this repo |
| Rights to the video and the people in it | The hero clips' releases already cover "may be shared with Meta and Cerebral Valley and published online" ([SHOTLIST.md](SHOTLIST.md) release form). Check the release wording matches any extra rights the rules ask for; if not, get the actors to sign an addendum |
| Third-party assets (music, fonts) must be licensed | No music in the video, or royalty-free with its licence noted |
| Silent | Keep MIT; nothing confidential goes in |

## 10. Eligibility: Kenya, individual vs company

Look for: "eligible countries", "excluded", "sanctions", "age", "individual", "company", "employees", "taxes", "prize payment".

| If the rules say | We do |
|---|---|
| Open worldwide except listed countries, and Kenya isn't listed | Continue. Kenya is also not in Meta's Restricted Territories (Geographic Use Policy, updated Oct 12; [MAXXING.md](MAXXING.md) §1). Calls go direct, never through a proxy ([AGENTS.md](../AGENTS.md) rule 7) |
| 🚩 Kenya is excluded, or only some countries can win prizes | Tell the owner at once. Never work around it (no VPN, no proxy, no entering from another country) |
| Individuals only | The owner enters as an individual; Sigmora is described as the product it plugs into |
| Companies may enter / the Startup track expects one | The owner decides whether to enter as Sigmora's company; capture its legal name and country for the form |
| Prize payment needs tax forms or a bank in a given country | Note what's needed for a Kenyan winner and tell the owner (no action until after judging) |
| Employees of Meta, Cerebral Valley or partners are excluded | Confirm nobody on the entry is one |
| Age or identity checks | The owner handles it |

## 11. Also check (quick)

| Question | Default if silent |
|---|---|
| Can the $150 Meta credits be topped up with our own money, and is spending outside credits allowed? | Stay within $150 ([AGENTS.md](../AGENTS.md) rule 10) |
| Are other APIs or hosts (Modal, Vercel) allowed alongside Meta's? | Yes; the README says what each one does |
| Must the demo stay live through judging (Nov 4–8) and finals (Nov 9)? | Keep it live to Nov 9 ([MAXXING.md](MAXXING.md) §4) |
| Any rules on processing personal data or footage of real people? | Our rules already go further: consented hero clips only on screen; real-public clips local and metrics-only ([AGENTS.md](../AGENTS.md) rule 5) |
| Can the submission be edited after the deadline (e.g. the video link)? | Assume no: submit complete by Nov 4 23:00 EAT |

## 12. After reading the rules

- [ ] Every item above has a quote + URL in the MAXXING update PR, or "silent".
- [ ] Every 🚩 that applies has been sent to the owner on Oct 26.
- [ ] `docs/SUBMISSION.md` has the exact form fields (WP8 owns the file; Claude may seed it with the field list).
- [ ] [STORYBOARD.md](STORYBOARD.md) is adjusted if the video limit is under 2:50.
- [ ] [MAXXING.md](MAXXING.md) §1 and §3 are updated.
