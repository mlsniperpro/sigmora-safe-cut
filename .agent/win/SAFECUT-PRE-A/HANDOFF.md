# HANDOFF: SAFECUT-PRE-A (docs-only research package)

**Held by** session_015NHPSLCF7hCdxi6Q9v8srB (resumed on the owner's RESUME, 2026-10-26).

## Goal, deadline, PR
- **Branch** `pre-a-research` · **PR #1** (the only PRE-A PR; never open another) · **Brief** `docs/work-packages/PRE-A.md` · **Rules** `AGENTS.md`: docs only, **no code, config or scaffolding before 2026-10-26 16:00 UTC**; stop the win loop by then at the latest.
- Owner /goal: met only when the transcript shows, after the last docs change: (1) `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` → 0; (2) **two consecutive full audits with nothing new**; (3) PRE-A and PRE-B (PR #2, `pre-b-product`) reconciled on shared facts; (4) `git status -sb` showing the branch pushed; (5) a final docs status comment on PR #1. Push rule below (Commands). Don't comment on or retitle other PRs or issues. Never ask the owner; decide and record decisions.
- Gate: PICK UP names `.agent/WIN-GATE.md` / `win-gate.sh`; neither exists on any branch, and a script would break AGENTS rule 1, so the gate is the five conditions above.

## Done (evidence)
- Deliverables: `docs/API-NOTES.md` (§1–§12; §9.2 the $150 ledger; §12 = **one list** of contract rows, a config/env table, "Deliberate differences from the WP files", and "Requests to PRE-B"), `docs/prompts/*.md` (6 specs + `TEST-VECTORS.md`), `docs/research/*.md`, `docs/BLOCKED-PRE-A.md`, `docs/WIN-CHECKLIST-PRE-A.md` (criteria map, §4 PRE-A↔PRE-B facts, §5/§6 full audit trail).
- Ledger **$147.00 planned, $3.00 headroom** (pre-window `/healthz` budget line $0.80, plan $0.41; PR #2 @ `43e250f` carries the matching "recording code at most $15.00"): `awk` line in `.agent/win/SAFECUT-PRE-A/calc/ledger.md` (mirrors API-NOTES §9.2). Per clip: $1.12 / 30 s at 8 fps; $2.02–2.09 / 60 s ($2.26–2.34 no cache, A10).
- Audits #1–#35 logged in WIN-CHECKLIST §6 (end of file), plus a WP0 builder walk-through (#34) and a full live-docs sweep (every `dev.meta.ai/docs` page; applied). Each audit = three fresh Sonnet/high agents (A internal, B brief + repo specs + live docs, C vs PR #2 with a [P] status table). **Clean count: 0.** Findings are now mostly edge-case specifications, each verified before fixing.
- Last pushes: `7ca667d` (audit #35 fixes), `b6fa465` (concurrency row). The PR #1 body still shows an older push; refresh it at the end (step 5).

## In flight
- **Full audit #47 re-launched 18:02 UTC on `de22f10`** (A, B, C; sonnet/high) after the RESUME; collect, verify, fix, push, then #48.
- Everything else is pushed: audits #36–#46 applied and logged in WIN-CHECKLIST §6 (#42–#46 were full three-lens passes with 21, 22, 21, 18, 21 findings; none clean). Official guide committed verbatim (`docs/OFFICIAL-GUIDE.md`, authoritative) and reconciled (WIN-CHECKLIST §7; API-NOTES §3.8 open-weight second opinion on Baseten, §9.2 window vs schedule).
- The PR #1 body (refreshed 15:50 UTC) and the 15:57 UTC status comment predate audits #42–#46 and the guide; refresh both at the end.

## Next steps (in order)
0. Claim LEASE. Run full audit #47 on HEAD: three parallel Agent subagents with model `sonnet`, effort `high` (A internal + arithmetic by script, B brief/AGENTS/WP files/OFFICIAL-GUIDE/live pages, C vs `origin/pre-b-product`), read-only, "report ONLY builder-impacting defects … else NO NEW FINDINGS". Verify each finding (live page, grep, script) before fixing; fix, log in WIN-CHECKLIST §6, gate, push; repeat until two consecutive full audits find nothing new. Then refresh the PR #1 body (latest sha, audits, PR #2 status, evidence output) and post the final docs status comment on PR #1 (no docs change after it).
1. Lease is claimed (`status=active`); keep it so until a WIND DOWN.
2. Run the next audit on HEAD: three parallel fresh agents (model sonnet, effort high), read-only, "report ONLY builder-impacting defects … if nothing, say exactly NO NEW FINDINGS", pointing them at the newest edits.
3. Fix findings, log them in WIN-CHECKLIST §6, commit; repeat until **two consecutive rounds on the same HEAD** find nothing. Record the last clean audit only in the PR comment, so no docs change follows it.
4. Re-check PR #2 (`git fetch origin pre-b-product`); if PRE-B fixed any [P] item, mark it [x] in WIN-CHECKLIST §4 and in API-NOTES §12 "Requests to PRE-B".
5. Refresh the PR #1 body (status, Decisions, Requests, Evidence with real command output), push, show `git status -sb`, post the final docs status comment on PR #1.

## Open audit findings / open items
- PRE-A side: none open (all audit findings fixed).
- PRE-B side ([P] in WIN-CHECKLIST §4; API-NOTES §12 "Requests to PRE-B" opens with a status line): at PR #2 `c944a4f` open are the "PRE-A's additions" sentence (introduction fields), the upload rows, ffprobe → `framemd5`, the empty-transcript copy and the cover-spot mock `reason`. No number PRE-B builds on differs (the 157,286,400-byte limit matches).

## Key decisions (why) — details in API-NOTES and the PR #1 Decisions section
- Headroom $3.00 / recording ≤ $15.00. **PRE-A owns cost and API facts and doesn't adopt PR #2's copies of them**: between `5bb95f0` and `43e250f` the packages crossed (each adopted the other's older values); PRE-A restored its own and PR #2 @ `43e250f` carries them.
- `422 job_cap`, `429` caller caps on `/start`. Code windows: kind defaults in `SAFECUT_CODE_WINDOWS` (pilot until Nov 2 23:59:59 UTC), entries may only narrow (optional `valid_from`/`valid_until`), checked on every paid request and the re-queue for every kind; service keys `401` outside Nov 5–10 (no forced replay); daily cap $0 after Nov 10. Window opens Nov 5 00:00 UTC (a sixth cap day would spend the headroom).
- `blocked_reason` precedence `over_budget` > `audit_failed` > `unresolved_leaks`; unresolved leaks end `done`; keep-only stops leave items `needs_you`, job continues to `review`.
- Audit patches are locked hidden **decision items** (`origin: "audit_patch"`, `A<n>`), static boxes, rebuilt on every re-plan; WP4's loop calls WP3's guard between passes.
- Track ids `<concept>:<n>` numbered per concept across the job; person/child phrase sets token-wise; `child_phrase` tracks locked as children (WP3 rule 0), never escalated, not counted toward the scene-children gate.
- Children/speech gates fail closed: `hold` when a scene child is unmatched, the scene or speech or role stage didn't run, or a 3/3 participant has no speech/introduction link while a transcript exists (even an empty one).
- EgoBlur weights needed by Oct 28; else YuNet face fallback (`SAFECUT_EGOBLUR_MODEL=yunet-face`), plates by red-team only, disclosed. Live `/start` refused (`503 auditor_unavailable`) without an auditor; stub only in tests/replay.
- v1 has no creator note; `languageBias` from `SAFECUT_ASR_LANGUAGE_BIAS`. Checkpoint reuse keyed by stage + input hash, never `SAFECUT_REPLAY`.
- Wonder not pre-approved; probe f ≤ $3.00 ($2.44 priced).

## Commands
- **Owner push rule (2026-10-25, replaces the 45-minute spacing everywhere):** push when a substantial task is complete and green (a set of audit findings fixed and checked, the gate run); don't wait for a timer. Each push is a meaningful squashed commit set (never empty, format-only or "wip"); exactly one PR. Never sit idle or end a turn to wait: while subagents run, work on the next HANDOFF item and collect results as they arrive. The only reasons to stop are the API usage limit or the /goal being met.
- **Owner rule (2026-10-25, keep across hand-offs):** every subagent launched with the Agent tool sets `model: "sonnet"` and `effort: "high"` (auditors, reviewers, fixers, researchers, watchers). The main session keeps integration, self-review of the diff, deciding which findings are real, and the gate. Verify every Sonnet finding before fixing it, and never drop one without checking it.
- Gates: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` (0); `git diff --name-only main..HEAD | grep -v '^\.agent/' | grep -vcE '\.md$'` (0); `awk -F'|' '/^\| / && $3 ~ /[0-9]/{s+=$3} END{printf "TOTAL %.2f headroom %.2f\n", s, 150-s}' .agent/win/SAFECUT-PRE-A/calc/ledger.md` (147.00 / 3.00).
- No install/test/run before kickoff (docs only). After kickoff (code WPs): `uv sync`, `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test` (AGENTS rule 12).

## Owner-only blockers (docs/BLOCKED-PRE-A.md)
SA-Co/VEval HF access + `HF_TOKEN`; EgoBlur weights (email form) by Oct 28; Linux NVIDIA box for the test split; network allowlist (dev.meta.ai, developer.meta.com, api.meta.ai, projectaria.com, modal.com, huggingface.co); `MODEL_API_KEY`; an `owner` access code for WP5; setup script `--no-group audit`; test-split mean clip ≤ 30 s; optional consented Swahili/Sheng clip.
