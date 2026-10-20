# Safe Cut: how we win the Meta Global AI Developer Hackathon

**Status: APPROVED (2026-10-20).** Entry: **Sigmora Safe Cut**, Startup track, theme "Build for Your World". The design was settled on 2026-10-14 (`DESIGN.md`). This file turns it into a build that parallel cloud agents can execute, with the owner's steps alongside.

## 0. The answer in one screen

1. **One entry, built deep:** Muse Spark decides *who* shouldn't be published, SAM 3.1 keeps them hidden frame by frame, anything uncertain stays hidden, and an audit pass checks the final render. Every decision comes with a reason the creator can see.
2. **Win the Startup track on "holds up in production":** a live service (API on Modal, review app on Vercel, a custom domain), real spend caps, 24 h data deletion, a privacy receipt, cost and latency per minute measured, and Sigmora actually calling it.
3. **Win Impact (30%) with evidence, not adjectives:** a labelled public-scene test set (we publish the numbers only), a side-by-side against "blur every face" and Meta's EgoBlur, and **5 creator pilots** with time saved measured.
4. **Win Meta tooling (25%) with depth:** a closed loop in which SAM numbers the objects, Muse Spark rules on them by number, and Muse Spark writes new SAM prompts for what it missed. SAM's weaknesses (no scores, IDs lost) become a deny-by-default guarantee. Meta's own EgoBlur audits the output. Muse Voice Transcribe supplies the speech evidence Muse Spark 1.3 can't hear well.
5. **Win Demo (25%):** the 2:50 video in `DEMO.md`, a live demo with a labelled replay fallback, and the hero clips filmed with consenting actors.
6. **Go for the bonus prizes too** (community vote, most viral): a launch thread plus a 20 s side-by-side Short on Nov 4–8.

## 1. Event facts (re-check on Oct 26 when the official rules publish)

| | |
|---|---|
| Build window | Oct 26 12:00 ET (kickoff livestream) → **Nov 4 21:00 ET = Nov 5 05:00 EAT** |
| Judging / finals | Nov 4–8 / Nov 9 (live finals, winners announced) |
| Criteria | Impact 30 · Use of Meta AI tooling 25 · Technical depth & execution 20 · Demo 25 |
| Startup prizes | $250k / $150k / $75k / $50k / $25k, plus bonus prizes (community vote, most viral) |
| Credits | $150 Meta Model API per participant. Partners for open weights (select participants): Baseten $100, Modal $100, Fireworks $25 |
| Models on offer | Muse Wonder (preview), Muse Spark 1.1–1.3, Muse Image, Muse Voice Transcribe, SAM 3.1 (all on the Model API); Muse Glimmer and Muse Spark Open (open weights); Muse Code (coding agent) |
| Waiver | Meta and Cerebral Valley get a licence, and **nothing submitted is confidential** |
| Kenya | Not in Meta's Restricted Territories (Geographic Use Policy, updated Oct 12). **No geo-workarounds, ever** (§2.1 of that policy) |

**To confirm in the official rules on Oct 26** (Claude reads them and updates this table): the pre-existing-code policy, whether one participant may submit more than one project, the video length limit, repo requirements, how the bonus prizes are judged, and the submission form fields.

## 2. What changed since the Oct 14 design

| Change | Effect |
|---|---|
| Meta's docs: **Muse Spark 1.3 audio understanding is "not fully supported"** | The participant call depends on speech. Add **Muse Voice Transcribe** (diarized turns with timestamps) as the speech sensor. The fallback is Muse Spark 1.2 audio. WP0 compares the two on the probe clips |
| **Muse Wonder 1.0** (preview), Meta's most capable model | Candidate for the scene pass and dispute escalation only. Kept behind env flags, and adopted only if the D1 probe shows a real gain (the owner's preference is depth, not a model tour) |
| The geo policy forbids circumventing availability | Removed the old "route through a US server if blocked" mitigation. Kenya is allowed, so call directly |
| Cloud agents see one repo | Standalone repo, data contracts between stages, parallel work packages (`ARCHITECTURE.md`) |
| `~/SafeCutEval/` doesn't exist on the owner's Mac | **Footage is the critical path.** See O1 below |

## 3. Judging map: criterion → evidence → who builds it

| Criterion | What judges must see | Evidence | WP |
|---|---|---|---|
| **Impact 30%** | A real problem, real users, measured gains | `CREATOR-PROBLEMS.md` quotes; the results table (recall, exposure, leak bursts, over-blur vs baselines); 5 creator pilots with minutes saved; live in Sigmora | WP7, WP8, owner (pilots) |
| **Meta tooling 25%** | Meta models doing things only they can, used deeply | The closed loop (SAM IDs → Muse role calls → new SAM prompts); deny-by-default from SAM's limits; 3× self-consistency; EgoBlur Gen 2 audit; Voice Transcribe evidence; the README table "what each Meta model does here" | WP1, WP2, WP4 |
| **Technical depth 20%** | Hard parts solved, not glued | Set-of-Mark binding, the leak guard (back-fill, gap hold, crowd fallback), locked-grid pixelation (reversibility research), the hash-chained receipt, replay mode, the eval harness with frozen splits | WP3, WP4, WP7 |
| **Demo 25%** | It works live and the video lands | The hero clips, the review panel with reasons, the context test (inbox hidden, menu clear), the re-entry guarantee, the audit catching a leak, publish via Sigmora | WP6, WP8, owner (footage, VO) |
| **Startup: holds up in production** | A deployed, safe, observable service | Modal API + Vercel app on a custom domain; caps; 24 h deletion; `/healthz`; cost and latency per minute in the README; CI green; a Sigmora integration PR merged | WP5, WP6, Sigmora brief |

## 4. Schedule (EAT) and who runs what

Other deadlines in the same window: Build With AI Oct 27 00:00 · OpenCV Oct 27 09:45 · GitLab Oct 27 16:00 · Nebius Oct 30 20:00 · **Qloo Oct 31 06:45** · The Search Nov 1 · **YouCam Nov 2 19:45** · PayPal Nov 12.

| When (EAT) | Cloud agents (parallel) | Owner / Claude (local) |
|---|---|---|
| **Now → Oct 25** | none (no code before kickoff) | **O1 footage + labels**, O2 Modal account, O3 cloud environment, O4 creator pilot list, O5 domain choice |
| Oct 26 19:00 | — | Kickoff. Claude reads the official rules and updates §1. Owner: accept the rules, get the API key (O6), make the repo public (O7) |
| **Oct 26 20:00** | **Wave A:** WP0 (scaffold, contracts, live probes) + WP6 (web shell on mock JSON) | Claude merges WP0 as soon as it's green |
| **Oct 27 morning** | **Wave B:** WP1 track · WP2 scout+speech · WP3 decide+guard · WP4 render+audit+receipt · WP7 eval harness | Claude merges as green; integration smoke test on hero clip 1 |
| Oct 29 | **Wave C:** WP5 pipeline + API + Modal deploy + replay/demo mode (stubs earlier if needed) | Domain + env for web (Claude); first end-to-end run |
| Oct 30 – Nov 1 | Fix waves from the first dev runs; Sigmora integration brief (in sigmora-platform) | **Test-split runs on the owner's Mac** (`eval/run.py --split test`, max 3); creator pilots run |
| Nov 2 | Light day (YouCam due 19:45) | Freeze features at 23:59 |
| Nov 3 | WP8 submission package (README results, SUBMISSION.md, video script final, launch posts) | **Owner records the VO** and the screen captures; Claude assembles the video |
| **Nov 4** | Buffer only | **Submit by 23:00 EAT** (6 h before the Nov 5 05:00 deadline). Keep the demo live to Nov 9 |
| Nov 4–9 | — | Launch posts for the community vote and most-viral prizes; finals rehearsal ×2 |

## 5. Owner steps (status as of 2026-10-20)

| # | Step | Due (EAT) | Status |
|---|---|---|---|
| **O1** | **Footage.** Minimum: 3 hero clips × 2 takes with signed releases (`SHOTLIST.md`), then about 15 eval clips (categories A, C, D, G, J first). Label the dev + test splits (CVAT, `EVAL.md` §1); a second labeller for κ if possible. Upload consented clips to the private bucket for agents; real-public clips stay on the Mac | Hero clips by **Oct 24**, labels by **Oct 26** | ⚠️ `~/SafeCutEval/` doesn't exist; filming planned for Oct 17–18 appears not done. **Confirm** |
| O2 | Modal account (free tier) → `! gh secret set MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` on this repo; claim the partner credits if offered | Oct 25 | open |
| O3 | Cloud environment for this repo (claude.ai/code): repo access, secrets `MODEL_API_KEY` (from O6), `SAFECUT_CLIPS_URL` + read token for the private consented-clips bucket; network allowlist §6 | Oct 26 19:30 | open |
| O4 | 5 creator pilots: Claude drafts the outreach, the owner sends it. Pilots use their own consented footage; with permission we record time saved and a quote | sent Oct 27, run Oct 30 – Nov 2 | open |
| O5 | Domain: `safecut.sigmora.org` (Claude sets DNS in whichever Cloudflare account holds sigmora.org, and the Vercel domain) | Oct 29 | open |
| O6 | Meta Model API key with the hackathon credits. Create a separate low-limit key for cloud agents if the console allows | Oct 26 at kickoff | open |
| O7 | Approve making this repo **public** at kickoff (it holds docs only until then) | Oct 26 | open |
| O8 | EgoBlur Gen 2 weights: if the download is gated behind a form, the owner fills it in (Claude checks on Oct 26) | Oct 26 | open |
| O9 | Record the VO (your own voice) + any on-camera intro | Nov 3 | open |
| O10 | Submit on Cerebral Valley; post the launch thread (X @algocracked, LinkedIn, YouTube) | Nov 4 23:00 | open |

## 6. Launching the cloud agents

```bash
claude --cloud "Read AGENTS.md, docs/MAXXING.md and docs/ARCHITECTURE.md, then execute docs/work-packages/WP<N>.md exactly. Check the time first: no code before 2026-10-26 16:00 UTC. Work on the branch the WP names, commit and push after every green step, run the checks AGENTS.md lists before each push, and open a PR with the evidence the WP asks for. If a prerequisite is missing, add BLOCKED.md to the PR and stop."
```

**Cloud environment** (claude.ai/code, this repo):
- Network: Custom, allowing `api.meta.ai`, `dev.meta.ai`, `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`, `github.com`, `raw.githubusercontent.com`, `objects.githubusercontent.com`, `huggingface.co`, `download.pytorch.org`, `www.projectaria.com` (EgoBlur), `modal.com`, `api.modal.com`, plus the private clips bucket host.
- Setup script: `pip install uv && uv sync --all-groups || true; corepack enable && (cd web && pnpm install || true)`. The `|| true` lets WP0 run before the lockfiles exist.
- Secrets: `MODEL_API_KEY`, `SAFECUT_CLIPS_URL`, `SAFECUT_CLIPS_TOKEN`, and `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` for WP5.

| Wave | WPs | Branch | Start |
|---|---|---|---|
| A | WP0, WP6 | `wp0-foundation`, `wp6-web` | Oct 26 20:00 EAT |
| B | WP1, WP2, WP3, WP4, WP7 | `wp1-track`, `wp2-scout`, `wp3-decide`, `wp4-render-audit`, `wp7-eval` | after WP0 merges |
| C | WP5 | `wp5-service` | Oct 29 (or earlier against stubs) |
| D | WP8 | `wp8-submission` | Nov 3 |

## 7. Risks (updated)

| # | Risk | Mitigation |
|---|---|---|
| 1 | **No footage or labels by kickoff** | Hero clips first (a phone is fine). Use SA-Co/VEval SmartGlasses (CC BY 4.0) for tracking and leak-guard dev numbers. Shrink the test split to what's labelled and say so honestly |
| 2 | API key or credits arrive late on Oct 26 | WP0 builds the scaffold and contracts first and probes when the key lands. WP3/WP6 need no key. Replay fixtures unblock everyone after the first probe |
| 3 | Muse video timestamps are vague | Set-of-Mark keyframes with burned-in frame numbers; never trust free-text times (DESIGN §2.3) |
| 4 | SAM loses IDs; 16-object cap | Deny-by-default for new IDs; crowd fallback; windowed second pass |
| 5 | Leak frames at track edges | Back-fill, temporal extend, padding, and the audit loop; target leak bursts = 0 on hero clips |
| 6 | Over-blur of the guest | 3/3 votes + ≥2 keyframes + speech evidence to keep; one-tap un-hide in review |
| 7 | Spend overrun | Per-job and daily caps; replay mode in tests; a budget per WP |
| 8 | Live demo fails at finals | Replay "demo mode" (labelled) on the cached hero results; the video carries the story |
| 9 | Overlap with Qloo and YouCam | Cloud agents carry the build; the owner's time goes to footage, pilots, VO and submits |
| 10 | Pre-existing-code rule | Standalone repo, everything dated after kickoff, and the README's "What existed before Oct 26" |
