# HANDOFF (PRE-B), updated 2026-10-25 12:57 UTC

**State:** branch `pre-b-product`, PR #2 (the only PRE-B PR). Lease `.agent/win/SAFECUT-PRE-B/LEASE`: active, `session_01Tjy33tfkpth8jMhhnhhcYL` (resumed 12:52 UTC after the 09:20 wind-down). Long form: `.agent/win/SAFECUT-PRE-B/HANDOFF.md`.

**Done:**
- All PRE-B deliverables exist; the WIN-CHECKLIST has 0 unchecked lines and covers #1–#332.
- Reconciled with PRE-A docs @ `565eee3` (#331–#332): PRE-A moved on in parallel during the wind-down, so PRE-B adopted its `422 job_cap`, $3.00 headroom / $15.00 recording bound, per-kind code windows (pilot to Nov 2 23:59 UTC; window checked on every paid request), `owner` kind, `code_valid_until`, `code_not_active` failure, `503 auditor_unavailable`, 60 s figures $2.02–2.09, and all its §12 UI requests (hold and static Why rows, union-box `cover_spot`, `other` object rulings, "Voice S1" labels).
- Audit rounds 24–35 (three parallel fresh auditors each); every finding fixed. No round clean yet.

**Open:**
1. Run audit round 36 on the commit after this reconciliation (same three scopes; hot zone `git diff 5bb95f0..HEAD` first, then `22283eb..HEAD`). Log as #333+. Repeat until two consecutive rounds find nothing new.
2. PRE-A's WIN-CHECKLIST §4 `[P]` rows and its "Requests to PRE-B" are now satisfied by this branch; PRE-A marks them (AGENTS rule 2). Re-check `origin/pre-a-research` each round in case it moves again.
3. Refresh the PR #2 body and post the final docs status comment.
4. Push spacing ≥ 45 min; squash fixups. Before merge, remove `.agent/` (#257).
