# PRE-B: pre-event product prep (labelling guide, UI spec, storyboard, pilots, rules checklist). DOCS ONLY

**Branch** `pre-b-product` · **Runs** NOW (before kickoff) · **Budget** $0

This package is allowed before Oct 26 12:00 ET **because it produces documents only**: no code, no config, no scaffolding. Markdown (with ASCII wireframes) only. WP6/WP7/WP8 build from it at kickoff.

**Owns:** `docs/labeling/`, `docs/UI-SPEC.md`, `docs/STORYBOARD.md`, `docs/PILOTS.md`, `docs/RULES-CHECKLIST.md`.

## Steps

1. **`docs/labeling/`:**
   - `LABELING-GUIDE.md`: from EVAL.md §1/§6. Entity categories, `should_hide` rules with 15+ worked edge cases (looks at the camera but doesn't speak; shop worker in the background; reflections in windows; a poster with a face; a TV showing a person; a partly visible plate; a participant who leaves and returns; a child who is a participant's own child with consent), box conventions, and how to resolve disagreements.
   - `CVAT-SETUP.md`: run CVAT with Docker on a build box (not the Intel dev Mac), create the project and labels, the interpolation workflow, MOT export, and the privacy rules (never upload real-public clips to hosted services).
   - `LABEL-FORMAT.md`: the label JSON and the MOT file, plus a fully worked example for a 10 s clip.
   - `SCHEDULE.md`: the owner's hours estimate per clip and a realistic plan for ~18 clips by Oct 26, including a reduced plan if footage is late.
2. **`docs/UI-SPEC.md`:** for every screen in WP6:
   - an ASCII wireframe (desktop + mobile);
   - every UI string (the copy deck), in plain, calm language;
   - the states (loading, empty, error, replay/demo banner, locked child, needs-you);
   - keyboard and accessibility behaviour;
   - which contract field feeds each element (ARCHITECTURE.md §3).

   Include the "Why?" drawer in detail and the progress-stage labels.
3. **`docs/STORYBOARD.md`:** shot by shot for DEMO.md's 2:50 video: frame description, on-screen text, VO line, duration, the source (hero clip # / screen recording / chart), and the exact screen recordings to capture on Nov 3. Mark where real numbers from RESULTS.md go (placeholders like `{recall_full}`, never invented numbers).
4. **`docs/PILOTS.md`:** the creator pilot programme (Impact evidence):
   - the target profile (street interviewers, vloggers, real-estate tours, local news creators; global, not one country);
   - where to find 15 candidates, with public channel types, not named private individuals;
   - 2 outreach message drafts (DM + email), each under 120 words, honest that it's a hackathon build;
   - a consent and data note (their footage, deleted after 24 h, Standard mode);
   - the pilot protocol: time their usual masking vs Safe Cut on one clip, then 3 questions;
   - how results and quotes appear in the submission (with permission only).
5. **`docs/RULES-CHECKLIST.md`:** what Claude must check on the official rules on Oct 26: pre-existing code; multiple submissions per participant; repo visibility and licence; video length and hosting; required form fields; bonus-prize mechanics (community vote, most viral); team and track rules; judging criteria wording; the IP licence; eligibility (Kenya, individual vs company). For each, say what we do under each possible answer.

## Done when

- [ ] All files exist, cross-link to DESIGN, EVAL and DEMO where relevant, and contain no executable code.
- [ ] The PR lists the open questions for the owner (e.g., labeller availability, pilot sending).
