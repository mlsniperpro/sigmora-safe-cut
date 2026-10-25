# HANDOFF: SAFECUT-PRE-B (docs-only product-prep package)

**Updated 2026-10-25 13:09 UTC** by session_01Tjy33tfkpth8jMhhnhhcYL (lease active). **Branch** `pre-b-product` · **PR #2** (the only PRE-B PR; never open another) · **Brief** `docs/work-packages/PRE-B.md` · **Rules** `AGENTS.md` (docs only; no code before 2026-10-26 16:00 UTC). Short form: `docs/HANDOFF-PRE-B.md`.

## Goal (owner /goal, re-armed hourly)
Met only when the transcript shows, after the last docs change: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0; **two consecutive full audits that find nothing new**; PRE-B and PRE-A reconciled on shared facts; `git status -sb` pushed; a final docs status comment on PR #2. Deadline: kickoff 2026-10-26 16:00 UTC. Never comment on other PRs. A WIND DOWN message: write handoff, release lease, push, delete own check-ins.

## Done (evidence)
- Deliverables: `docs/labeling/{LABELING-GUIDE,CVAT-SETUP,LABEL-FORMAT,SCHEDULE}.md`, `docs/UI-SPEC.md`, `docs/STORYBOARD.md`, `docs/PILOTS.md`, `docs/RULES-CHECKLIST.md`, `docs/BLOCKED-PRE-B.md`, `docs/WIN-CHECKLIST-PRE-B.md` (0 unchecked; #1–#354 in §3).
- Reconciled with PRE-A docs @ `565eee3` (#204–#211 earlier vs `4bb3cec`; #331–#332 now): `422 job_cap` on `/start`, `429` caller caps, $1.12 floor on `POST /v1/jobs`; $3.00 headroom, recording $12 raise ≤ $15.00; per-kind code windows (judge/public Nov 5 00:00–Nov 10 23:59 UTC, recording to Nov 3 23:59, pilot to Nov 2 23:59, owner to Nov 10 23:59), entries may only narrow, window checked on every paid request; `owner` kind; `code_valid_until`; `code_not_active` failure; `503 auditor_unavailable`; 60 s cost $2.02–2.09 ($2.34 no-cache); hold and static Why rows; union-box `cover_spot`; `other` object rulings; "Voice S1" labels; stage-file `status` in mocks. PRE-A's WIN-CHECKLIST §4 `[P]` rows and §12 "Requests to PRE-B" are satisfied here; PRE-A marks them (AGENTS rule 2).
- Audit rounds 24–39 this session (A cross-package; B UI-SPEC internal; C labels/pilots/storyboard/BLOCKED timeline and privacy), each on a fixed sha; round 39 found 22 (#364–#385). No clean round yet.

## In flight
- Nothing running at this write. The refreshed PR #2 body is a scratch draft only (lost if the container goes): rebuild from the Decisions in the docs (STORYBOARD rules, PILOTS §4–§6, UI-SPEC §2.6.1/§8, SCHEDULE §3–§4, CVAT-SETUP §2) and the requests lists (UI-SPEC §8 requests 1–21; EVAL owner: 12/3 split and creator time n=2 summed parts; SHOTLIST owner: line 15 storage; DEMO owner: beats 5 and 7; ARCHITECTURE §4 owner: SAFECUT_ACCESS_CODES, SAFECUT_PILOT_POOL_USD; WP7: `n_clips`).

## Next steps (in order)
1. Audit round 40 (same 3 scopes, fresh agents, fixed sha; hot zone = latest fix diff, then `git diff 5bb95f0..HEAD -- docs/`). Log as #387+. Repeat until two consecutive rounds find nothing new. Findings cluster in UI-SPEC §2.6.1/§3.5/§10.3–§10.5 and mock fixtures, and in the Nov 3 sequence (STORYBOARD §3, BLOCKED); re-read neighbouring rules before each fix.
2. The PR #2 body was refreshed this session (Decisions 1–19, requests incl. request 22); update its finding counts, then push, show `git status -sb`, post the final docs status comment.
3. Before merge: remove `.agent/` (#257).

## Open audit findings
None known (#1–#386 fixed).

## Commands / gates (docs only)
- **Owner push rule (2026-10-25, replaces the 45-minute spacing everywhere):** push when a substantial task is complete and green (a set of audit findings fixed and checked, the gate run); never wait for a timer. Each push is a meaningful, squashed commit set (no empty, format-only or wip commits); exactly one PR. Never sit idle or end a turn to wait: while subagents run, work on the next HANDOFF item. Stop only for the API usage limit or a met /goal.
- **Owner rule (2026-10-25, keep across hand-offs):** every subagent launched with the Agent tool sets `model: "sonnet"` and `effort: "high"` (auditors, reviewers, fixers, researchers, watchers). The main session keeps integration, self-review of the diff, deciding which findings are real, and the gate. Verify every Sonnet finding before fixing it; never drop one unchecked.
- `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0 (grep exits 1 on 0; don't chain with &&).
- `git diff --name-only main...HEAD | grep -v '^\.agent/' | grep -vc '\.md$'` → 0.
- Relative-link check over PRE-B files (last: 0 broken).
- Outreach word counts with placeholders as one word: DM 102, email 109.
- PRE-A: `git show origin/pre-a-research:docs/API-NOTES.md` (§9.2, §10.3, §12).
- After kickoff: `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test`.

## Owner-only blockers
`docs/BLOCKED-PRE-B.md`: film hero clips (cast only); recruit labeller B (~5.5 h, by Oct 26 08:00 EAT); CVAT machine in owner custody; outreach Oct 27, codes after the live deletion check; codes in SAFECUT_ACCESS_CODES (no dates needed; kind windows apply); time manual masking of H1A/H1B; Nov 3 recordings (live runs by 16:00 EAT), then VO after the script; judge codes and submission by Nov 4 23:00 EAT; make the repo public after the secrets/footage check.
