AUDITED_COMMIT: 04d8a8906a868d472237e64358d9064c5303f695
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# SAFECUT-SAFETY re-audit log

Each round is two independent full audits (Sonnet, effort high, read-only, given the code and the specs, not my
conclusions): one on WP3 (decide + guard and their callers), one on WP4 (render + audit + receipt). Every finding is
verified here before it is fixed, and fixed with a named test. The counter resets whenever a round finds anything.

## Round 1 (at 9493594): 2 high, 8 medium, lows. All verified and fixed at 318dfd6 / a18e457
- WP4 high: detector crash in pass 2–3 reported clean → fixed (`test_a_crash_while_rechecking_a_fix_is_never_clean`).
- WP4 high: demo receipt not marked synthetic → fixed (`test_e3_the_demo_job_is_redacted_audited_and_receipted`).
- WP4 medium: replay recording overwrote answers; two re-asks; model named before answering; re-run dropped fixes;
  receipt without approval; memory on large clips → all fixed with tests (WIN-CHECKLIST "Audit findings").
- WP3 medium: sliver mask in a small box; merge origin; dilation cost; gap hold across re-entry; frames off the
  track; cross-key ties → all fixed with tests.
- Lows accepted with reasons: crowd fill covers tracked objects only (the contract's requirement; nothing localises
  untracked crowd members); a frame-fixed grid on a moving face (DESIGN §2.7 requires the locked grid).

## Round 2: running on the merged code (04d8a89 lineage)
