# HANDOFF: SAFECUT-PRE-B (docs-only product-prep package)

**Resumed 2026-10-25 12:57 UTC by** session_01Tjy33tfkpth8jMhhnhhcYL (lease active; earlier released at the 09:20 wind-down). **Latest state: see `docs/HANDOFF-PRE-B.md`**, which supersedes the In-flight and Next-steps sections below. Originally released by session_01Tjy33tfkpth8jMhhnhhcYL at Sun Oct 25 09:22:38 UTC 2026 (account usage ended). **Branch** `pre-b-product` · **PR #2** (the only PRE-B PR; never open another) · **Brief** `docs/work-packages/PRE-B.md` · **Rules** `AGENTS.md` (docs only; no code before 2026-10-26 16:00 UTC). Also see `docs/HANDOFF-PRE-B.md` (same state, short form).

## Goal (owner /goal, still open)
Met only when the transcript shows, after the last docs change: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0; **two consecutive full audits that find nothing new**; PRE-B and PRE-A (PR #1, `origin/pre-a-research`) reconciled on shared facts; `git status -sb` showing the branch pushed; a final docs status comment posted on PR #2. Deadline for this package: kickoff 2026-10-26 16:00 UTC. Pushes ≥ 45 min apart (squash fixups first); never comment on or retitle other PRs.

## Done (evidence)
- Deliverables: `docs/labeling/{LABELING-GUIDE,CVAT-SETUP,LABEL-FORMAT,SCHEDULE}.md`, `docs/UI-SPEC.md`, `docs/STORYBOARD.md`, `docs/PILOTS.md`, `docs/RULES-CHECKLIST.md`, `docs/BLOCKED-PRE-B.md`, `docs/WIN-CHECKLIST-PRE-B.md` (0 unchecked; findings #1–#330 logged in §3).
- Reconciled with PRE-A docs @ `4bb3cec` (#204–#211): 429 with cap reason on POST /start, $1.12 floor on POST /v1/jobs, required `valid_until` on every access code with PRE-A §9.2 windows (judge/public Nov 5 00:00–Nov 10 23:59 UTC; recording to Nov 3 23:59 UTC, $12, raise ≤ $14.86; pilots to Nov 3 11:59 UTC), no sampled EgoBlur copy, `sample_step = round(job.fps)`, §5b step 4/6, test mean ≤ 30 s. PRE-A's three `[P]` rows (WIN-CHECKLIST-PRE-A §4, lines ~71–73) are satisfied by PRE-B text; marking them `[x]` is PRE-A's edit.
- Audit rounds 24–35 this session: 3 parallel fresh auditors per round (A cross-package facts vs PRE-A + base docs; B UI-SPEC internal consistency; C labels/pilots/storyboard/BLOCKED timeline + privacy), each on a fixed commit; all findings fixed and logged. **No round was clean yet.**

## In flight
- Audit round 36 was launched on `5fe8291` (docs identical to this commit) and **killed unfinished: no result**. Re-run it.
- Scratch, not committed (lost): a refreshed PR #2 body draft. Its content: Decisions 1–19 (footage R4→R1; labeller B trigger Oct 26 08:00 EAT; test clips only in owner custody, in person, encrypted local backup; 12/3/3 split, test mean ≤ 30 s; $6/code + $20 pool, pool never refills; 30-min manual cap; deletion promise after live check; anonymous credit default, anonymous-only with ≤ 2 pilots, withdrawal to Nov 3 12:00 UTC; café menu Needs-you then kept; fabricated video call; remove person = cover; owner's voice; disputed = hide; every number from committed metrics.json by Nov 3 18:00 EAT, no literature numbers on charts; creator time = H1A+H1B n=2 summed parts; PRE-A §5b time model; access-code windows; refusal patterns; demo live Nov 5–10 UTC then replay only) and Requests for other WPs (WP1, WP2, WP3, WP4/5, WP5 incl. request 21 POST /v1/codes/check, WP0/WP7, WP8, EVAL owner: 12/3 split and creator time n=2 summed parts, SHOTLIST owner: line 15 storage, DEMO owner: beats 5 and 7, ARCHITECTURE §4 owner: SAFECUT_ACCESS_CODES + SAFECUT_PILOT_POOL_USD). Rebuild it from the docs and `git log`.

## Next steps (in order)
1. Re-run a full audit round (same 3 scopes, fresh agents, on a fixed sha; hot zone `git diff 22283eb..HEAD -- docs/` plus the latest fix diff). Fix, log as #331+, commit, repeat until **two consecutive rounds find nothing new**. Recent findings clustered in UI-SPEC §10.5 (undo/pending/RETRY model) and the Nov 3 recording sequence (STORYBOARD §3, BLOCKED); re-read neighbouring rules before each fix, since many findings were regressions of earlier fixes.
2. Refresh the PR #2 body (above), push (≥ 45 min after the last push), show `git status -sb`, post the final docs status comment on PR #2 (with the clean-audit evidence and the PRE-A `[P]` note).
3. Before PR #2 merges: remove `.agent/` (#257).

## Open audit findings
None known: #1–#330 are fixed. Round 36 result unknown.

## Commands / gates (docs only)
- `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0 (note: grep exits 1 on 0, don't chain with &&).
- `git diff --name-only main...HEAD | grep -v '^\.agent/' | grep -vc '\.md$'` → 0.
- Link check: every relative `](…)` link in PRE-B files resolves (last run: 0 broken).
- PRE-A: `git show origin/pre-a-research:docs/API-NOTES.md` (§9.2 ledger, §10.3, §12 requests to PRE-B).
- After kickoff (code WPs): `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test`.

## Owner-only blockers
`docs/BLOCKED-PRE-B.md`: film hero clips (cast only), recruit labeller B (~5.5 h, by Oct 26 08:00 EAT), CVAT machine in owner custody, send pilot outreach Oct 27 and codes after the live deletion check, create recording/pilot/judge codes in the SAFECUT_ACCESS_CODES secret with valid_until, time manual masking of H1A/H1B, Nov 3 recordings then VO, submit by Nov 4 23:00 EAT, make the repo public after the secrets/footage check.
