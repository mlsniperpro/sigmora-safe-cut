# HANDOFF: SAFECUT-PRE-B (docs-only product-prep package)

**Updated 2026-10-26 17:10 UTC** by session_01Tjy33tfkpth8jMhhnhhcYL (resumed: wind-down cancelled; lease active). **Branch** `pre-b-product` · **PR #2** (the only PRE-B PR; never open another) · **Brief** `docs/work-packages/PRE-B.md` · **Rules** `AGENTS.md` (docs only; no code before 2026-10-26 16:00 UTC). Short form: `docs/HANDOFF-PRE-B.md`.

## Goal (owner /goal, re-armed hourly)
Met only when the transcript shows, after the last docs change: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0; **two consecutive full audits that find nothing new**; PRE-B and PRE-A reconciled on shared facts; `git status -sb` pushed; a final docs status comment on PR #2. Deadline: kickoff 2026-10-26 16:00 UTC. Never comment on other PRs. A WIND DOWN message: write handoff, release lease, push, delete own check-ins.

## Done (evidence)
- Deliverables: `docs/labeling/{LABELING-GUIDE,CVAT-SETUP,LABEL-FORMAT,SCHEDULE}.md`, `docs/UI-SPEC.md`, `docs/STORYBOARD.md`, `docs/PILOTS.md`, `docs/RULES-CHECKLIST.md`, `docs/BLOCKED-PRE-B.md`, `docs/WIN-CHECKLIST-PRE-B.md` (0 unchecked; #1–#354 in §3).
- Reconciled with PRE-A docs @ `df5b1dc` (#450–#451 upload contract and audit-patch reason; earlier #204–#211 vs `4bb3cec`; #331–#332 vs `565eee3`; #409–#415 now: scene `introduced_in_turn`/`introduction_quote`, service keys `401` outside the judge window, auditor name rule for the YuNet fallback, `503 billing`, prompt-cache consent sentence and receipt check, `T23:59:59Z` fixtures): `422 job_cap` on `/start`, `429` caller caps, $1.12 floor on `POST /v1/jobs`; $3.00 headroom, recording $12 raise ≤ $15.00; per-kind code windows (judge/public Nov 5 00:00–Nov 10 23:59 UTC, recording to Nov 3 23:59, pilot to Nov 2 23:59, owner to Nov 10 23:59), entries may only narrow, window checked on every paid request; `owner` kind; `code_valid_until`; `code_not_active` failure; `503 auditor_unavailable`; 60 s cost $2.02–2.09 ($2.34 no-cache); hold and static Why rows; union-box `cover_spot`; `other` object rulings; "Voice S1" labels; stage-file `status` in mocks. PRE-A's WIN-CHECKLIST §4 `[P]` rows and §12 "Requests to PRE-B" are satisfied here; PRE-A marks them (AGENTS rule 2).
- Audit rounds 24–48 this session (A cross-package; B UI-SPEC internal; C labels/pilots/storyboard/BLOCKED timeline and privacy), each on a fixed sha; round 39 found 22, round 40 found 21 (#388–#408); round 41 found 34 (#416–#449); round 42 found 24 (#453–#476); round 43 found 17 (#480–#496); round 44 found 30 (#504–#533); round 45 found 30 (#534–#563); round 47 found 24 (#570–#593); round 48 found 14 (#594–#607). No clean round yet.

- Official participant guide (owner, 2026-10-26) committed verbatim as `docs/OFFICIAL-GUIDE.md` and reconciled (#497–#503): theme Build for Your World, new-work boundary (STORYBOARD 9.1 `{first_code_commit}`, Sigmora label), repo public only after the owner's OK, demo on X before submitting, bonus targets (agentic; open-weight via Baseten `meta-models/muse-spark-open-1026` is a request to PRE-A/WPs).

## In flight
- Nothing running. Round 49: **A reported and is fixed (#608–#613, pushed)**; **B (UI-SPEC) and C (labels/pilots/storyboard) were stopped by the wind-down before reporting**: **full round 50 launched on HEAD after resume**; log as #614+. Check-in armed.
- **PR #2 body is one step behind:** HANDOFF-PRE-B says the WP7 (guide link, CVAT-zip loader) and EVAL (summed creator time) requests are in it; add those three bullets to the live body under "Requests for other WPs" (the draft `.agent/win/SAFECUT-PRE-B/pr2-body-draft.md` and the live body differ; the live one was posted from a condensed version).
- PRE-A head last seen: `6e2ca00`.
- Owner rules (keep): every Agent subagent uses model sonnet, effort high; main session verifies each finding before fixing; push when a substantial task is complete and green (no timer, no wip commits, exactly one PR #2); never idle; stop only for usage limit or met /goal; WIND DOWN steps when told.
- Gates used: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0; a relative-link checker over docs (recreate: resolve every `](path)` in PRE-B files; last 0 broken); parse every ```json block in docs/UI-SPEC.md (last: all parse); PILOTS word counts DM 106 / email 113 (placeholders one word).
- Key decisions this session: OFFICIAL-GUIDE.md committed verbatim and reconciled (RULES-CHECKLIST §0); repo stays private until the owner OKs it, public by Nov 4 20:00 EAT; demo on X before submitting; end card states first product-code commit, hero 1 filming date, labelling during the event, Sigmora line only if 8.1 shows Sigmora; PRE-A's open-weight audit second opinion (Muse Spark Open on Baseten) named from `audit.open_weight.model` and disclosed (Data bullet 4, consent note); "Standard model IDs" wording; deletion "from Safe Cut's servers".

## Next steps (in order)
1. Audit round 49 (same 3 scopes, fresh agents, fixed sha; hot zone = latest fix diff, then `git diff 5bb95f0..HEAD -- docs/`). Log as #614+. Repeat until two consecutive rounds find nothing new. Findings cluster in UI-SPEC §2.6.1/§3.5/§10.3–§10.5 and mock fixtures, and in the Nov 3 sequence (STORYBOARD §3, BLOCKED); re-read neighbouring rules before each fix.
2. The PR #2 body was refreshed this session (Decisions 1–19, requests incl. request 22); update its finding counts, then push, show `git status -sb`, post the final docs status comment.
3. Before merge: remove `.agent/` (#257).

## Open audit findings
None known (#1–#613 fixed).

## Key decisions (why)
- PRE-A owns API, cost, model, ffmpeg/time-axis and access-window facts; PRE-B adopts them and only files requests (AGENTS rule 2). Reconciled to PRE-A `02c605e`; `b6fa465` added no new requests to PRE-B.
- Docs-only until Oct 26 16:00 UTC (AGENTS rule 1); deadline Nov 4 21:00 ET (Nov 5 02:00 UTC). One PR only (#2, branch `pre-b-product`).
- Fail-closed UI rules: auditor named from `audit.json` `egoblur.model` (YuNet fallback), blocking refusals vs `code_cap` note, per-kind code windows, no number without a committed `metrics.json` (AGENTS rule 9).
- Footage: only signed cast in published clips, fake plates and fictional numbers; real-public test clips stay in owner custody, labelled in person.
- Every finding is logged in `docs/WIN-CHECKLIST-PRE-B.md` §3 (#1–#613, all `[x]`).

## Install / test
- Docs-only: no install. Gates: below (python3 scripts for link check and JSON parse of UI-SPEC ```json blocks; recreate them if the scratchpad is gone).

## Commands / gates (docs only)
- **Owner push rule (2026-10-25, replaces the 45-minute spacing everywhere):** push when a substantial task is complete and green (a set of audit findings fixed and checked, the gate run); never wait for a timer. Each push is a meaningful, squashed commit set (no empty, format-only or wip commits); exactly one PR. Never sit idle or end a turn to wait: while subagents run, work on the next HANDOFF item. Stop only for the API usage limit or a met /goal.
- **Owner rule (2026-10-25, keep across hand-offs):** every subagent launched with the Agent tool sets `model: "sonnet"` and `effort: "high"` (auditors, reviewers, fixers, researchers, watchers). The main session keeps integration, self-review of the diff, deciding which findings are real, and the gate. Verify every Sonnet finding before fixing it; never drop one unchecked.
- `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-B.md` → 0 (grep exits 1 on 0; don't chain with &&).
- `git diff --name-only main...HEAD | grep -v '^\.agent/' | grep -vc '\.md$'` → 0.
- Relative-link check over PRE-B files (last: 0 broken).
- Outreach word counts with placeholders as one word: DM 106, email 113.
- PRE-A: `git show origin/pre-a-research:docs/API-NOTES.md` (§9.2, §10.3, §12).
- After kickoff: `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test`.

## Owner-only blockers
`docs/BLOCKED-PRE-B.md`: film hero clips (cast only); label as labeller A (~18 h: hero 1 by Oct 26 19:00 EAT, hero 2–3 + dev by Oct 27); freeze the test split on the eval box by Oct 29 23:59 (commit only test.sha256); run the test split Oct 30 – Nov 1 and hand over metrics.json; recruit labeller B (~5.5 h, by Oct 26 08:00 EAT); create the private bucket + write/read tokens and upload hero 1 by Oct 26 19:00 EAT (O3); Oct 26 kickoff: accept the rules, get MODEL_API_KEY; CVAT machine in owner custody; outreach Oct 27, codes after the live deletion check; codes in SAFECUT_ACCESS_CODES (no dates needed; kind windows apply); time manual masking of H1A/H1B; Nov 3 recordings (live runs by 16:00 EAT), then VO after the script; final cut on YouTube (unlisted) by Nov 4 18:00 EAT; judge codes and submission by Nov 4 23:00 EAT; make the repo public after the secrets/footage check.
