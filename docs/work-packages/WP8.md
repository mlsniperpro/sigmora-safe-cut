# WP8: submission package

**Branch** `wp8-submission` · **Wave** D · **Starts** Nov 3 EAT · **Depends on** WP1–WP7 merged, the service deployed, and at least one test-split run committed by the owner/Claude · **Budget** $0

**Owns:** `README.md` (full rewrite), `docs/SUBMISSION.md`, `docs/VIDEO-SCRIPT.md`, `docs/LAUNCH.md`, `docs/AGENTIC-LOOP.md`.

## Goal

The judges read the README first and watch the video second. Make both land every criterion, with every claim traceable to code or a run ID.

## Steps

1. **README.md:**
   - The one-line problem; the live demo link + judge access instructions; a 20 s GIF.
   - "How it works" (diagram).
   - **"What each Meta model does here"**: a table of the model, its job, why it and not something else, and its calls/cost per minute.
   - The results table from `eval/RESULTS.md` (run IDs linked), with the honest worst failures.
   - Production notes: architecture, caps, deletion, receipt, measured latency/cost.
   - "Run it yourself" (CLI, API, replay); "What existed before Oct 26"; licence.
2. **`docs/AGENTIC-LOOP.md`:** the closed loop, step by step. Use one real trace from hero clip 1 (raw responses from fixtures), annotated "SAM output → Muse decision → policy → creator".
3. **`docs/SUBMISSION.md`:** paste-ready fields for the Cerebral Valley form (take the field list from the official rules page and copy it here first): title, tagline, description, track, theme, Meta models used, the links (repo, demo, video), the team, and testing instructions for judges.
4. **`docs/VIDEO-SCRIPT.md`:** a final version of DEMO.md's beats, timed to ≤ 2:50 at 150 wpm, with every number pulled from RESULTS.md. List each screen recording needed and the hero clip for each beat.
5. **`docs/LAUNCH.md`:** posts for the bonus prizes (community vote, most viral):
   - an X thread (6 posts) for @algocracked;
   - a LinkedIn post;
   - a 20 s vertical side-by-side (script + shot list);
   - a YouTube description.

   Plain, specific claims; no hype words.

## Done when

- [ ] Every number in the README, SUBMISSION and VIDEO-SCRIPT appears in RESULTS.md or a committed `metrics.json`.
- [ ] The README renders cleanly on GitHub, all links work, and the demo link opens.
- [ ] The PR lists what's waiting on the owner (video link, the final VO, the submit click).
