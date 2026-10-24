# What wins: evidence from past events, and what it means for Safe Cut

Researched 2026-10-24 through web search (a research sub-agent, plus this doc's own checks). **(fetched)** = the page itself was read; **(summary)** = only a search-engine summary was seen. No source publishes judge comments or rubric weights for these events, so everything under "implication" is our inference, labelled as such.

## 1. Evidence
| Finding | Source | Implication for Safe Cut (inference) |
|---|---|---|
| LlamaCon Hackathon (May 2025): 6 finalists presented live after two judging rounds. Podium: a knowledge graph over Jira/GitHub/docs; fraud detection ending in an email plus a voice-agent action; a "Llama CCTV Operator" checking plain-language surveillance events every 5 frames with Llama 4 multimodal. A separate "Best Llama API Usage" award went to Geo-ML | [ai.meta.com/blog/llamacon-hackathon](https://ai.meta.com/blog/llamacon-hackathon/) (fetched) | Winners close a loop from real input to a concrete user action, and a multimodal **video** pipeline made the podium. Depth of use of the API was judged on its own. Show the whole loop: upload → decisions with reasons → audit → receipt → publish-ready file |
| Meta × Cerebral Valley Llama 3 Hackathon (May 2024): 1st place was OpenGlass, $20 smart glasses that describe what you see | [ai.meta.com/blog/llama-3-hackathon-recap-cerebral-valley](https://ai.meta.com/blog/llama-3-hackathon-recap-cerebral-valley/) (fetched); criteria "creativity, future potential, technical implementation, pitch" (summary) | A **visual** before/after demo wins attention. The raw-vs-Safe-Cut toggle belongs in the first 20 s (PR #2 STORYBOARD) |
| Llama Impact Hackathon SF (Nov 2024): winners were narrow, practical domain tools | [lablab.ai summary](https://lablab.ai/blog/llama-impact-hackathon-sf-summary) (fetched) | Name the user: the street-interview and walking-tour creator, plus the 5 pilots |
| This event: the Startup track is judged on "technical execution and whether it holds up in production"; judging Nov 4–8, **live finals Nov 9** | [cerebralvalley.ai/e/meta-ai-developer-hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (fetched) | Plan and rehearse a **live** run for Nov 9, not just the recorded video (MAXXING §4 already has 2 rehearsals) |
| Devfolio's AI-assisted judging ("Push to Prod") checks pitch claims against the repo, with file and line citations | [devfolio.co/blog/the-discerning-machine](https://devfolio.co/blog/the-discerning-machine/) (fetched) | Assume the repo will be read against the pitch. **Add a "claims → code → test" table to the README** (request to WP8): every claim (deny by default, 3× votes, escalation never keeps, EgoBlur audit, `store:false`, file deletion, 24 h purge, caps) links to the function and the test that proves it |
| Public tutorial: DataCamp, "SAM 3 privacy filter" (Nov 2025), prompts SAM 3 with faces / license plates / screens and blurs every match; it notes filters "don't replace consent" | [datacamp.com tutorial](https://www.datacamp.com/tutorial/sam3-tutorial-segment-everything-3-build-a-privacy-filter) (fetched) | Judges may know "SAM + blur everything" as the obvious build. EVAL.md rows 1 and 2 (blur every face; detector-only) **are** that baseline, so name it as such in the results table ("SAM 3.1 blur-everything, like the public tutorials"). Our gap is the participant decision, deny-by-default, the audit and the receipt |
| Consumer "choose who to keep" tools exist (Vidio.ai face anonymizer; Bystander Video Blur on iPad with tap-to-unblur) | (summary) [vidio.ai](https://www.vidio.ai/en-au/tools/ai-face-anonymizer), [App Store](https://apps.apple.com/app/id6758543644) | Don't pitch "selective blur" as new. Pitch **automatic decisions with reasons**, where the creator only confirms |
| Enterprise redaction already has audit trails: Pimloc Secure Redact added chain of custody (Sep 2025); Veritone Redact logs every redaction | (summary) [sdmmag.com](https://www.sdmmag.com/articles/104605-pimloc-strengthens-secure-redact-with-new-chain-of-custody-and-audit-trail-features) | **Don't claim audit trails are new.** Claim enterprise-grade evidence for individual creators, at per-clip cost |
| `deface` is an open-source face-anonymisation CLI | [pypi.org/project/deface](https://pypi.org/project/deface/) (summary) | An optional cheap extra baseline row if WP7 has time; not required |
| Academic: bystander detection in photos (Hasan et al., IEEE S&P 2020; 93% accuracy when raters fully agree, 80% at 67% agreement); bystander privacy called "understudied" (arXiv 2501.11756) | [CISPA PDF](https://publications.cispa.saarland/3051/1/bystander-oakland-2020.pdf), [arXiv](https://arxiv.org/html/2501.11756v1) (summary) | Cite them. Humans disagree too, which supports deny-by-default and reporting κ (EVAL.md §1 already plans it) |
| EgoBlur paper: face recall 0.998 on CCV2 and 0.938 on Aria Pilot RGB; plate recall 0.992. EgoBlur's README says to use **Gen 2 models on Aria Gen 2 data** | [arXiv 2308.13093](https://arxiv.org/abs/2308.13093) (fetched via ar5iv), [GitHub](https://github.com/facebookresearch/EgoBlur) (fetched) | Phone footage is neither Aria generation. **Measure the auditor itself** (see §2 R2) |
| No 2025–26 public benchmark covers participant-vs-bystander in video | (searched; nothing found) | Our labelled set is a contribution. Say so plainly, with its size and κ |
| Common failure modes: over-claiming numbers; a "thin wrapper" over an API; the live demo breaking | Devfolio (fetched); vendor blogs (summary, weak) | AGENTS rule 9 covers the numbers (show the run ID on screen). The measured gain over the blur-everything baselines answers "thin wrapper". Replay mode is a *declared* fallback, never a silent mock |

## 2. What this changes (recommendations to the build WPs)
**R1. Eval (WP7).**
- Label EVAL rows 1–2 in results as "SAM 3.1 blur-everything (the public-tutorial approach)" and row 1b as EgoBlur, so the comparison judges expect is explicit.
- Report κ and the test split's size next to every number. Only measured, committed `metrics.json` values may appear (AGENTS rule 9).
- If time allows, add `deface` as one extra baseline row.

**R2. Audit detector choice (WP4).**
- EgoBlur says Gen 2 is for Aria Gen 2 data; our footage is phone video. Choose between Gen 1 and Gen 2 with the **held-out rule in `egoblur-gen2.md`**: pick on hero clip 1 (higher face and plate recall, at most 2 false detections per minute), and report recall only on hero clips 2–3 and the dev split, never on the clip used to pick. The extra cost is local compute only.
- Report the auditor's own recall in the results ("the audit's detector misses X% of labelled faces on our set"), so a judge can see the second look isn't over-claimed.
- Both models are listed in `research/egoblur-gen2.md`.

**R3. README claims table (WP8).** One row per claim: claim → code path → test name → evidence (run ID or receipt field). Judges or their tools check the repo against the pitch.

**R4. Demo (owner, WP6/WP8; PR #2 owns the storyboard).**
- The before/after toggle in the first 20 s.
- One live run on hero clip 1 at finals (Nov 9), with the replay "demo mode" **announced** if used.
- Show one audit catch (a reflection or a mosaic read-through, `prompts/redteam.md` cases) and the receipt.
- Run IDs on screen for any number shown.

**R5. Positioning (WP8 README, PR #2 copy).**
- Say: "automatic participant-vs-bystander decisions with reasons, deny-by-default, a second-look audit, and an evidence receipt for creators".
- Avoid: "first audit trail", "first selective blur" (prior art exists).

## 3. Risks this adds (beyond MAXXING §7)
| # | Risk | Mitigation |
|---|---|---|
| 11 | Judges dismiss it as "SAM + blur, like the tutorial" | Lead with the participant decision. Show the context test (inbox hidden, menu clear) and the baseline gap in one table |
| 12 | The repo doesn't back a claim made in the video | R3 claims table; WP8 checks every claim against code before submitting |
| 13 | The EgoBlur auditor underperforms on phone footage | R2: measure Gen 1 vs Gen 2; the red-team audit and deny-by-default don't depend on it |
| 14 | The live finals demo fails | Rehearsed hero clip, declared replay fallback, and a code freeze before finals (MAXXING §4) |
