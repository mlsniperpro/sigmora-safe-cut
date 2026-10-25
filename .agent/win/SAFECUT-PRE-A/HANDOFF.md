# HANDOFF: SAFECUT-PRE-A (docs-only research package)

**Held by** session_015NHPSLCF7hCdxi6Q9v8srB (resumed on the owner's RESUME after a brief wind-down at 09:22 UTC). Took over at 2026-10-25 08:10 UTC from session_01LDnKxUxPsHrPFZ4j6gXzqA.

## Goal, deadline, PR
- **Branch** `pre-a-research` · **PR #1** (the only PRE-A PR; never open another) · **Brief** `docs/work-packages/PRE-A.md` · **Rules** `AGENTS.md`: docs only, **no code, config or scaffolding before 2026-10-26 16:00 UTC**; stop the win loop by then at the latest.
- Owner /goal: met only when the transcript shows, after the last docs change: (1) `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` → 0; (2) **two consecutive full audits with nothing new**; (3) PRE-A and PRE-B (PR #2, `pre-b-product`) reconciled on shared facts; (4) `git status -sb` showing the branch pushed; (5) a final docs status comment on PR #1. Push rule below (Commands). Don't comment on or retitle other PRs or issues. Never ask the owner; decide and record decisions.
- Gate: PICK UP names `.agent/WIN-GATE.md` / `win-gate.sh`; neither exists on any branch, and a script would break AGENTS rule 1, so the gate is the five conditions above.

## Done (evidence)
- Deliverables: `docs/API-NOTES.md` (§1–§12; §9.2 the $150 ledger; §12 = **one list** of contract rows, a config/env table, "Deliberate differences from the WP files", and "Requests to PRE-B"), `docs/prompts/*.md` (6 specs + `TEST-VECTORS.md`), `docs/research/*.md`, `docs/BLOCKED-PRE-A.md`, `docs/WIN-CHECKLIST-PRE-A.md` (criteria map, §4 PRE-A↔PRE-B facts, §5/§6 full audit trail).
- Ledger **$147.00 planned, $3.00 headroom** (pre-window `/healthz` budget line $0.80, plan $0.47; PR #2 @ `43e250f` carries the matching "recording code at most $15.00"): `awk` line in `.agent/win/SAFECUT-PRE-A/calc/ledger.md` (mirrors API-NOTES §9.2). Per clip: $1.12 / 30 s at 8 fps; $2.02–2.09 / 60 s ($2.26–2.34 no cache, A10).
- Audits #1–#33 logged in WIN-CHECKLIST §6 (end of file). Each audit = three fresh agents in parallel (A internal arithmetic/consistency, B brief + repo specs, C vs PR #2 incl. a status table of every [P]); since 13:15 UTC they run as `sonnet`/`high` (owner rule). #31 20, #32 18, #33 ~11 findings; all fixed or filed. **Clean count: 0.** Audit #33 B was still running at the push; collect or re-run it.
- Last pushes: `071da22` (08:55 UTC), then the wind-down push (this commit's parent chain). PR #1 body was refreshed ~09:00 UTC and still shows `071da22` and audits to #27.

## In flight
- Audits #32–#33's fixes are in this push. **Audit #34 is next** on the pushed HEAD (sonnet/high).

## Next steps (in order)
1. Claim the lease (`LEASE` → `status=active`), commit `lease: claim SAFECUT-PRE-A`, push.
2. Run audit #34 on HEAD: three parallel fresh agents with the lens prompts above, read-only, "report ONLY builder-impacting defects … if nothing, say exactly NO NEW FINDINGS", pointing them at the newest edits (#29/#30: `transcript.json`/`roles.json` `status`, `hold` enum and precedence, `child_phrase` + WP3 rule 0 + token-wise phrase sets, YuNet fallback, checkpoint keys, empty-transcript rule, pinned-job purge exemption).
3. Fix findings, log them in WIN-CHECKLIST §6, commit; repeat until **two consecutive rounds on the same HEAD** find nothing. Record the last clean audit only in the PR comment, so no docs change follows it.
4. Re-check PR #2 (`git fetch origin pre-b-product`); if PRE-B fixed any [P] item, mark it [x] in WIN-CHECKLIST §4 and in API-NOTES §12 "Requests to PRE-B".
5. Refresh the PR #1 body (status, Decisions, Requests, Evidence with real command output), push, show `git status -sb`, post the final docs status comment on PR #1.

## Open audit findings / open items
- PRE-A side: none open (all audit findings fixed).
- PRE-B side ([P] in WIN-CHECKLIST §4; API-NOTES §12 "Requests to PRE-B" opens with a status line): at PR #2 `43e250f` everything earlier is done; open are UI-SPEC §3.5 row 0's stale `429 job_cap` and branching the EgoBlur copy on `egoblur.model` for the YuNet fallback. A PRE-B session (lease `session_01Tjy33tfkpth8jMhhnhhcYL`) was active at 13:03 UTC; it reads PRE-A as the owner of cost/API facts.

## Key decisions (why) — details in API-NOTES and the PR #1 Decisions section
- Headroom $3.00 / recording ≤ $15.00. **PRE-A owns cost and API facts and doesn't adopt PR #2's copies of them**: between `5bb95f0` and `43e250f` the packages crossed (each adopted the other's older values); PRE-A restored its own and PR #2 @ `43e250f` carries them.
- `422 job_cap`, `429` caller caps on `/start`. Code windows: kind defaults in `SAFECUT_CODE_WINDOWS` (pilot until Nov 2 23:59:59 UTC), entries may only narrow (optional `valid_from`/`valid_until`), checked on every paid request and the re-queue for every kind; service keys `401` outside Nov 5–10 (no forced replay); daily cap $0 after Nov 10. Window opens Nov 5 00:00 UTC (a sixth cap day would spend the headroom).
- `blocked_reason` precedence `over_budget` > `audit_failed` > `unresolved_leaks`; unresolved leaks end `done`; keep-only stops leave items `needs_you`, job continues to `review`.
- Audit patches are locked hidden **decision items** (`origin: "audit_patch"`, `A<n>`), static boxes, rebuilt on every re-plan; WP4's loop calls WP3's guard between passes.
- Track ids `<concept>:<n>` numbered per concept across the job; person/child phrase sets token-wise; `child_phrase` tracks locked as children (WP3 rule 0), never escalated, not counted toward the scene-children gate.
- Children/speech gates fail closed: `hold` when a scene child is unmatched, the scene or speech or role stage didn't run, or a 3/3 participant has no speech/introduction link while a transcript exists (even an empty one).
- EgoBlur weights needed by Oct 31; else YuNet face fallback (`SAFECUT_EGOBLUR_MODEL=yunet-face`), plates by red-team only, disclosed. Live `/start` refused (`503 auditor_unavailable`) without an auditor; stub only in tests/replay.
- v1 has no creator note; `languageBias` from `SAFECUT_ASR_LANGUAGE_BIAS`. Checkpoint reuse keyed by stage + input hash, never `SAFECUT_REPLAY`.
- Wonder not pre-approved; probe f ≤ $3.00 ($2.44 priced).

## Commands
- **Owner push rule (2026-10-25, replaces the 45-minute spacing everywhere):** push when a substantial task is complete and green (a set of audit findings fixed and checked, the gate run); don't wait for a timer. Each push is a meaningful squashed commit set (never empty, format-only or "wip"); exactly one PR. Never sit idle or end a turn to wait: while subagents run, work on the next HANDOFF item and collect results as they arrive. The only reasons to stop are the API usage limit or the /goal being met.
- **Owner rule (2026-10-25, keep across hand-offs):** every subagent launched with the Agent tool sets `model: "sonnet"` and `effort: "high"` (auditors, reviewers, fixers, researchers, watchers). The main session keeps integration, self-review of the diff, deciding which findings are real, and the gate. Verify every Sonnet finding before fixing it, and never drop one without checking it.
- Gates: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` (0); `git diff --name-only main..HEAD | grep -v '^\.agent/' | grep -vcE '\.md$'` (0); `awk -F'|' '/^\| / && $3 ~ /[0-9]/{s+=$3} END{printf "TOTAL %.2f headroom %.2f\n", s, 150-s}' .agent/win/SAFECUT-PRE-A/calc/ledger.md` (147.00 / 3.00).
- No install/test/run before kickoff (docs only). After kickoff (code WPs): `uv sync`, `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test` (AGENTS rule 12).

## Owner-only blockers (docs/BLOCKED-PRE-A.md)
SA-Co/VEval HF access + `HF_TOKEN`; EgoBlur weights (email form) by Oct 31; Linux NVIDIA box for the test split; network allowlist (dev.meta.ai, developer.meta.com, api.meta.ai, projectaria.com, modal.com, huggingface.co); `MODEL_API_KEY`; an `owner` access code for WP5; setup script `--no-group audit`; test-split mean clip ≤ 30 s; optional consented Swahili/Sheng clip.
