# HANDOFF: SAFECUT-PRE-A (docs-only research package)

**Held by** session_015NHPSLCF7hCdxi6Q9v8srB (resumed on the owner's RESUME after a brief wind-down at 09:22 UTC). Took over at 2026-10-25 08:10 UTC from session_01LDnKxUxPsHrPFZ4j6gXzqA.

## Goal, deadline, PR
- **Branch** `pre-a-research` · **PR #1** (the only PRE-A PR; never open another) · **Brief** `docs/work-packages/PRE-A.md` · **Rules** `AGENTS.md`: docs only, **no code, config or scaffolding before 2026-10-26 16:00 UTC**; stop the win loop by then at the latest.
- Owner /goal: met only when the transcript shows, after the last docs change: (1) `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` → 0; (2) **two consecutive full audits with nothing new**; (3) PRE-A and PRE-B (PR #2, `pre-b-product`) reconciled on shared facts; (4) `git status -sb` showing the branch pushed; (5) a final docs status comment on PR #1. Pushes ≥ 45 min apart (squash WIP first). Don't comment on or retitle other PRs or issues. Never ask the owner; decide and record decisions.
- Gate: PICK UP names `.agent/WIN-GATE.md` / `win-gate.sh`; neither exists on any branch, and a script would break AGENTS rule 1, so the gate is the five conditions above.

## Done (evidence)
- Deliverables: `docs/API-NOTES.md` (§1–§12; §9.2 the $150 ledger; §12 = **one list** of contract rows, a config/env table, "Deliberate differences from the WP files", and "Requests to PRE-B"), `docs/prompts/*.md` (6 specs + `TEST-VECTORS.md`), `docs/research/*.md`, `docs/BLOCKED-PRE-A.md`, `docs/WIN-CHECKLIST-PRE-A.md` (criteria map, §4 PRE-A↔PRE-B facts, §5/§6 full audit trail).
- Ledger **$147.14 planned, $2.86 headroom** (pre-window `/healthz` line booked at its $0.94 worst case, plan $0.47; matches PR #2 @ `5bb95f0`'s "recording code at most $14.86"): `awk` line in `.agent/win/SAFECUT-PRE-A/calc/ledger.md` (mirrors API-NOTES §9.2). Per clip: $1.12 / 30 s at 8 fps; $2.02–2.09 / 60 s ($2.26–2.34 no cache, A10).
- Audits #1–#31 logged in WIN-CHECKLIST §6 (end of file). Since #24 each audit = **three fresh agents in parallel**: A internal arithmetic/consistency, B brief + ARCHITECTURE/DESIGN/EVAL/WP0–WP8, C vs PR #2 (`git show origin/pre-b-product:<path>`; C also reports the status of every [P] item). Findings per round: #24 25 … #30 17, #31 20 (mostly PR #2 @ `5bb95f0` convergence); **all fixed or filed. Clean count: 0.**
- Last pushes: `071da22` (08:55 UTC), then the wind-down push (this commit's parent chain). PR #1 body was refreshed ~09:00 UTC and still shows `071da22` and audits to #27.

## In flight
- Nothing partial. Audit #31's fixes are in this push. **Audit #32 is next** (on the pushed HEAD).

## Next steps (in order)
1. Claim the lease (`LEASE` → `status=active`), commit `lease: claim SAFECUT-PRE-A`, push.
2. Run audit #32 on HEAD: three parallel fresh agents with the lens prompts above, read-only, "report ONLY builder-impacting defects … if nothing, say exactly NO NEW FINDINGS", pointing them at the newest edits (#29/#30: `transcript.json`/`roles.json` `status`, `hold` enum and precedence, `child_phrase` + WP3 rule 0 + token-wise phrase sets, YuNet fallback, checkpoint keys, empty-transcript rule, pinned-job purge exemption).
3. Fix findings, log them in WIN-CHECKLIST §6, commit; repeat until **two consecutive rounds on the same HEAD** find nothing. Record the last clean audit only in the PR comment, so no docs change follows it.
4. Re-check PR #2 (`git fetch origin pre-b-product`); if PRE-B fixed any [P] item, mark it [x] in WIN-CHECKLIST §4 and in API-NOTES §12 "Requests to PRE-B".
5. Refresh the PR #1 body (status, Decisions, Requests, Evidence with real command output), push (≥ 45 min spacing), show `git status -sb`, post the final docs status comment on PR #1.

## Open audit findings / open items
- PRE-A side: none open (all audit findings fixed).
- PRE-B side ([P] in WIN-CHECKLIST §4; full text in API-NOTES §12 "Requests to PRE-B"): sampled-EgoBlur copy (UI-SPEC §5.3/§3.3); `sample_step` = `round(job.fps)`; `/start` refuses when a cap can't cover the §9.1 estimate; HANDOFF-PRE-B's stale `429 job_cap` bullet; `code_not_active` copy (`/try`, job pages, `failure.reason`) + window fields + `owner` kind + `code_cap` definition; `503 auditor_unavailable` copy; `cover_spot` span and union box; `U` speaker vs `U{n}` chips; Why rows for `hold` (`no_scene`, `no_speech`, `no_roles`, `unmatched_child`, `no_speech_link`), static items, café mock fix; audit-patch field names (`origin`, `audit_label`); `other` items' object rulings; request 14 `child` kind for `child_phrase`; 60 s figures in PILOTS/STORYBOARD. PRE-A can't edit PRE-B (AGENTS rule 2). No PRE-B session was active at 08:15 UTC.

## Key decisions (why) — details in API-NOTES and the PR #1 Decisions section
- Headroom $2.86 (PR #2 @ `5bb95f0` adopted it from PRE-A @ `4bb3cec`; PRE-A converged back): `/healthz` probe ≤ once / 2 min before Nov 5, line $0.94.
- `429 job_cap` and `429` caller caps on `/start` (PR #2 @ `5bb95f0`). Code windows: `valid_until` required per entry, kind outer bounds in `SAFECUT_CODE_WINDOWS` (pilot until Nov 3 11:59:59 UTC); judge/public/service gate every paid request and the re-queue, pilot/recording/owner gate creation only; service keys `401` outside Nov 5–10 (no forced replay); daily cap $0 after Nov 10. Window opens Nov 5 00:00 UTC (a sixth cap day would spend the headroom).
- `blocked_reason` precedence `over_budget` > `audit_failed` > `unresolved_leaks`; unresolved leaks end `done`; keep-only stops leave items `needs_you`, job continues to `review`.
- Audit patches are locked hidden **decision items** (`origin: "audit_patch"`, `A<n>`), static boxes, rebuilt on every re-plan; WP4's loop calls WP3's guard between passes.
- Track ids `<concept>:<n>` numbered per concept across the job; person/child phrase sets token-wise; `child_phrase` tracks locked as children (WP3 rule 0), never escalated, not counted toward the scene-children gate.
- Children/speech gates fail closed: `hold` when a scene child is unmatched, the scene or speech or role stage didn't run, or a 3/3 participant has no speech/introduction link while a transcript exists (even an empty one).
- EgoBlur weights needed by Oct 31; else YuNet face fallback (`SAFECUT_EGOBLUR_MODEL=yunet-face`), plates by red-team only, disclosed. Live `/start` refused (`503 auditor_unavailable`) without an auditor; stub only in tests/replay.
- v1 has no creator note; `languageBias` from `SAFECUT_ASR_LANGUAGE_BIAS`. Checkpoint reuse keyed by stage + input hash, never `SAFECUT_REPLAY`.
- Wonder not pre-approved; probe f ≤ $3.00 ($2.44 priced).

## Commands
- Gates: `grep -c '^- \[ \]' docs/WIN-CHECKLIST-PRE-A.md` (0); `git diff --name-only main..HEAD | grep -v '^\.agent/' | grep -vcE '\.md$'` (0); `awk -F'|' '/^\| / && $3 ~ /[0-9]/{s+=$3} END{printf "TOTAL %.2f headroom %.2f\n", s, 150-s}' .agent/win/SAFECUT-PRE-A/calc/ledger.md` (147.00 / 3.00).
- No install/test/run before kickoff (docs only). After kickoff (code WPs): `uv sync`, `uv run pytest`, `uv run ruff check`, `pnpm lint && pnpm typecheck && pnpm test` (AGENTS rule 12).

## Owner-only blockers (docs/BLOCKED-PRE-A.md)
SA-Co/VEval HF access + `HF_TOKEN`; EgoBlur weights (email form) by Oct 31; Linux NVIDIA box for the test split; network allowlist (dev.meta.ai, developer.meta.com, api.meta.ai, projectaria.com, modal.com, huggingface.co); `MODEL_API_KEY`; an `owner` access code for WP5; setup script `--no-group audit`; test-split mean clip ≤ 30 s; optional consented Swahili/Sheng clip.
