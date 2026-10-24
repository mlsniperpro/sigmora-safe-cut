# HANDOFF: SAFECUT-PRE-A (docs-only research package)

**Released by** session_01LDnKxUxPsHrPFZ4j6gXzqA, 2026-10-24 ~22:55 UTC (the account ran out). **Branch** `pre-a-research` · **PR #1** (the one and only PRE-A PR; do not open another) · **Brief** `docs/work-packages/PRE-A.md` · **Rules** `AGENTS.md` (no code before 2026-10-26 16:00 UTC; docs only).

## Goal (owner /goal, still open)
Make the PRE-A docs package build-ready and win-grade. The goal is met only when the transcript shows, after the last docs change:
1. `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` → 0 (it is 0 now);
2. **two consecutive full hostile audits that find nothing new**, recorded in PR #1;
3. PRE-A and PRE-B (PR #2, branch `pre-b-product`) reconciled on shared facts;
4. `git status -sb` showing the branch pushed;
5. a final docs status comment posted on PR #1.

Stop at 2026-10-26 16:00 UTC at the latest. Pushes must be ≥45 min apart (the stop hook does not override that); squash WIP before pushing. Don't comment on or retitle other PRs or issues.

## Done (evidence)
- Deliverables: `docs/API-NOTES.md` (§1–§12: APIs, grid rule, time model, prices, cost model + **§9.2 full $150 ledger**, client spec, vectors, contract table), `docs/prompts/*.md` (6 specs + `TEST-VECTORS.md`), `docs/research/*.md` (egoblur-gen2, sa-co-veval, modal, muse-wonder-vs-spark, prior-art, winning-patterns), `docs/BLOCKED-PRE-A.md`, `docs/WIN-CHECKLIST-PRE-A.md`.
- 23 full hostile audits, each by a fresh agent, all logged in WIN-CHECKLIST §6. Clean results: #17 (later broken by #18), #22 at `f598f22` (broken by #23). Every finding is fixed.
- Ledger: $147.14 planned, $2.86 headroom. Reproduce with `python3 -I .agent/win/SAFECUT-PRE-A/calc/ledger.py`. Per-clip cost is $1.12 per 30 s at 8 fps (the stage table is in API-NOTES §9.1).
- The PR #1 body was refreshed at 22:19 UTC. Its figures ($147.00 / $3.00) are now slightly stale; current is $147.14 / $2.86.

## In flight
- **Audit #24** was started on `4bb3cec` (= the handoff commit's parent docs) and **killed unfinished**. No result. Re-run it.
- Since audit #23, these changes have not been audited: §12 adopts PR #2 UI-SPEC request 18 @ `74bb9d2` (`leaks[].unresolved`, `sample_step` = `round(job.fps)`, `spots[]`, `cover_spot` by `spot_id`); the redteam.md pass-3 wording; the winning-patterns R2 held-out rule; the [P] shas bumped to `74bb9d2`.

## Next steps (in order)
1. `git fetch origin pre-b-product`; read PR #2's latest UI-SPEC §4/§5.3/§8 requests (1, 11, 18, 20), STORYBOARD §3 and BLOCKED-PRE-B. PR #2 cites PRE-A at the old `948b678` because PRE-A's work wasn't pushed until this handoff, so expect PRE-B to update now.
2. Run a fresh full hostile audit (one subagent at a time; the prompt pattern is in the checklist's audit lines: whole package vs brief, AGENTS, MAXXING, ARCHITECTURE §3/§4, WP0–WP8, DESIGN/EVAL, PR #2; only builder-impacting defects; quote both sides). Fix, log in WIN-CHECKLIST §6, commit, and repeat until two consecutive audits on the **same HEAD** find nothing. Record the last clean audit only in the PR comment, so no docs change follows it.
3. Recheck the three [P] items in WIN-CHECKLIST §4 against PR #2; mark them [x] once PR #2 fixes them.
4. Refresh the PR #1 body (current numbers, evidence output), push (≥45 min spacing), show `git status -sb`, and post the final docs status comment on PR #1.

## Open items (PR #2 side, filed as requests in API-NOTES §12 "Requests to PRE-B"; [P] in WIN-CHECKLIST §4)
1. STORYBOARD §3 still says recordings come out of "PRE-A's hero line (18 runs × $1.12 = $20.16)" with overruns from PRE-A headroom. PRE-A has no hero line: the $12 recording code pays.
2. UI-SPEC request 20, STORYBOARD §3 and BLOCKED-PRE-B let the owner raise the recording code's cap with no bound. PRE-A bounds it at +$2.86 (the headroom).
3. UI-SPEC §5.3 "Audit detail link" row says EgoBlur runs "otherwise on a sample…". PRE-A: EgoBlur always scans every frame (no sampled mode); fewer scanned frames are unresolved, `audit_failed` (vector L10).
- Also requested from PRE-B: keep the test split's mean clip length ≤ 30 s.

## Key decisions (why)
- **Time model:** a constant-frame-rate prepared clip; `times` holds source seconds (non-decreasing); the SAM proxy runs at `min(SAFECUT_SAM_FPS=8, job.fps)` via ffmpeg's fps slot rule (§5b). This converges with PR #2, and is verified by ffmpeg checksums.
- **Audit contract** follows PR #2 @ `32a349f`/`74bb9d2`: `audit.blocked_reason` (⇔ `unresolved > 0`) plus `audit_budget_cause` (mirrored at the job's top level with `retry_at`) and "Run the audit again"; `failure.reason` ∈ job_cap/daily_cap/code_cap/pilot_pool_cap; `cost.jsonl` gains `cap`, `code_kind` (incl. `system`), `code_id` and budget lines. `unresolved == 0` is the single publish gate.
- **Budget:** every WP is counted at its full cap. The test line ($43.20) is a caller cap checked on every reservation, with one eval job at a time; run k = baseline 3 then `full`; a job stopped by the line cap is excluded from metrics, while a job-cap outcome is scored (AGENTS rule 9). Recording code $12 (until Nov 3); pilots $6 per code with a $20 pool; daily $3 for public codes, service keys and `/healthz` only; public window Nov 5 00:00 – Nov 10 23:59 UTC (covers the Nov 9 finals); `JOB_USD_CAP` $3.00 requested.
- **Fail-closed rules:** an in-bar red-team box is dropped only if it reads our label; a child ruling in any escalation window locks the track; unswept miss items get static hidden boxes; there is no sampled EgoBlur mode (the CPU fallback is every frame with one test run).
- Wonder isn't pre-approved (the costs of each option are in §9.2). Escalation is advisory only.

## Commands
- Docs-only before kickoff. Gates: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` (must be 0); `git diff --name-only main..HEAD | grep -vcE '\.md$'` (must be 0, docs only; `.agent/` files are tooling handoff state, also `.md`/`.py`, so exclude `.agent/` when checking); `python3 -I .agent/win/SAFECUT-PRE-A/calc/ledger.py`.
- After kickoff (code WPs): `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test` (AGENTS rule 12).

## Owner-only blockers (docs/BLOCKED-PRE-A.md)
SA-Co/VEval HF access (manual approval) + `HF_TOKEN`; the EgoBlur weights via the email form; a Linux NVIDIA GPU box for the test split; the network allowlist (dev.meta.ai, api.meta.ai, projectaria.com, modal.com, huggingface.co); `MODEL_API_KEY`. PRE-B's are in BLOCKED-PRE-B.md.

## Scratch not in the repo (lost with the old session)
ffmpeg verification logs, `cost2.py` and the SAM vector scripts. Their outputs are quoted in API-NOTES §11 and the PR #1 body. Only `ledger.py` was saved (above).
