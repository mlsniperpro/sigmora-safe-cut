# HANDOFF: SAFECUT-PRE-A (docs-only research package)

**Released by** session_015NHPSLCF7hCdxi6Q9v8srB at 2026-10-25 ~09:22 UTC on the owner's WIND DOWN (held since 08:10 UTC; took over from session_01LDnKxUxPsHrPFZ4j6gXzqA). **Branch** `pre-a-research` · **PR #1** (the one and only PRE-A PR; never open another) · **Brief** `docs/work-packages/PRE-A.md` · **Rules** `AGENTS.md` (no code before 2026-10-26 16:00 UTC; docs only).

## Goal (owner /goal)
Met only when the transcript shows, after the last docs change: (1) `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` → 0; (2) two consecutive full hostile audits that find nothing new; (3) PRE-A and PRE-B (PR #2, `pre-b-product`) reconciled on shared facts; (4) `git status -sb` showing the branch pushed; (5) a final docs status comment on PR #1. Pushes ≥45 min apart; squash WIP. Don't comment on or retitle other PRs or issues. Stop at 2026-10-26 16:00 UTC at the latest.

**Gate:** PICK UP names `.agent/WIN-GATE.md` and `bash .agent/win-gate.sh`, but neither exists on any branch. A gate script would be executable scaffolding (AGENTS rule 1), so the gate is the five conditions above, checked with the commands below.

## State (2026-10-25)
- Ledger: **$147.00 planned, $3.00 headroom** (the awk line in `.agent/win/SAFECUT-PRE-A/calc/ledger.md`). The pre-window `/healthz` line is capped at $0.80 (Meta probe at most every 2 min before Nov 5, plan $0.47), so PR #2's "recording code raisable to at most $15 = PRE-A's whole $3.00 headroom" (@ `22283eb`) is exact.
- Reconciled with PR #2 @ `22283eb` (commit `c21922a`): no hero line; $15 recording bound; `422 job_cap` / `429` caller caps on `POST /start`; "Run the audit again" runs the receipt stage (request 11); code windows `valid_from`/`valid_until` + `401 code_not_active`.
- One PRE-B-side copy line is still open ([P] in WIN-CHECKLIST §4): UI-SPEC §5.3 "Audit detail link" says "otherwise on a sample…". PRE-B owns it (AGENTS rule 2); no contract or number differs. Also requested from PRE-B: a `code_not_active` copy row, window fields in request 20, test split mean clip ≤ 30 s. No PRE-B session is active on this account (checked 08:15 UTC).
- Audits: #1–#30 logged in WIN-CHECKLIST §6. Each audit = three fresh agents in parallel (A internal arithmetic/consistency, B brief + repo specs, C vs PR #2); prompts reusable from the §6 entries. Findings per round: #24 25, #25 29, #26 21, #27 20, #28 15, #29 16, #30 17, all fixed or filed. **Clean count: 0.** No arithmetic errors since #26; findings are now rule-level edge cases (mostly fail-closed tightening). **Audit #31 has not run**: start there, on the pushed HEAD.
- PRE-B-side [P] filings: API-NOTES §12 "Requests to PRE-B" and WIN-CHECKLIST §4. No PRE-B session was active at 08:15 UTC; builders follow PRE-A where it owns the contract.
- PR #1 body refreshed at ~09:00 UTC (pushed state `071da22`); refresh it again with the new HEAD and audits #28–#30.

## Next steps (resume here)
1. Fix every audit #24 finding, log it in WIN-CHECKLIST §6, commit; repeat audit rounds (three lenses each) until two consecutive rounds on the same HEAD find nothing.
2. Refresh the PR #1 body (numbers, Decisions, evidence), push (≥45 min after the last push), show `git status -sb`, post the final status comment on PR #1 (it records the last clean audit, so no docs change follows it).

## Commands
- `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` (must be 0); `git diff --name-only main..HEAD | grep -v '^\.agent/' | grep -vcE '\.md$'` (must be 0); the awk line in `.agent/win/SAFECUT-PRE-A/calc/ledger.md`.

## Owner-only blockers (docs/BLOCKED-PRE-A.md)
SA-Co/VEval HF access + `HF_TOKEN`; EgoBlur weights (email form); a Linux NVIDIA GPU box for the test split; the network allowlist (dev.meta.ai, api.meta.ai, projectaria.com, modal.com, huggingface.co); `MODEL_API_KEY`.

## Key decisions
See the previous handoff in git history (`git show 32a0574:.agent/win/SAFECUT-PRE-A/HANDOFF.md`) and the PR #1 body's Decisions section; all still hold, plus the `/healthz` and `422` decisions above.
