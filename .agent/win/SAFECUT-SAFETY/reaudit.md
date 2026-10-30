AUDITED_COMMIT: 90b9f714dfdb7d132c1a7eee8df5650676d21d25
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

## Round 2 (at 04d8a89): 1 high, several medium, lows. All verified; fixed at 90b9f71 (merged dd92749) or accepted
- WP3 high: review edits in the API re-run the guard inline (slow on long clips): the guard itself was already cut
  35 s → 7.7 s on a busy 60 s 720p clip at 51a67bb; the API's threadpool and mask-free payloads are SHIP's paths and
  were filed with SHIP (not fixed here, lane scope).
- WP3 medium: hide on a locked audit patch/child took the decision over → `ReviewError("locked")`
  (`test_a_locked_item_can_not_be_hidden_by_the_creator_either`).
- WP3 medium: replaying a log with `cover_spot` failed and its undo left the patch → idempotent replay, undo removes
  the patch and reopens the spot (`test_cover_spot_adds_a_locked_audit_patch_and_marks_the_spot`,
  `test_undoing_a_cover_spot_removes_its_patch_and_reopens_the_spot`).
- WP3 medium: one stale edit aborted the decide stage; an undo of an unknown or later edit → non-strict replay in the
  stage, `unknown_edit` for a sent one (`test_a_stale_last_edit_never_aborts_the_decide_stage`,
  `test_an_undo_of_an_unknown_or_later_edit_reverts_nothing`).
- WP3 medium: gap hold one-sided → held from both ends (`test_a_gap_is_held_from_both_ends`, fails without the fix).
- WP3 low: a re-entry of a child wasn't locked → every ID linked by `reentry_of` to a child is locked
  (`test_every_id_of_a_child_is_locked_across_reentries`).
- WP3 low: role-failure holds ignored `no_scene`/`no_speech` precedence → first in order
  (`test_a_role_failure_still_writes_the_first_hold_in_order`).
- WP3 low accepted: `bind.py` has no production importer (SENSE binds in its own stage; kept as the tested reference).
- WP4 medium: a whole-frame (unplaceable) finding could be excused by a frame-filling host → never excused
  (`test_a_finding_that_cannot_be_placed_is_never_excused_by_the_host`, fails without the fix).
- WP4 medium: a refusal raised by the client while streaming wasn't re-asked → re-asked once
  (`test_live_reasks_a_refusal_the_client_raises`).
- WP4 medium: an opinion exception other than a budget stop escaped into the audit; the result could be lost on a
  crash; read-through text from the opinion wasn't flagged → failures recorded as `failed`, saved at once and reused,
  read-through flagged (`test_a_failed_opinion_is_recorded_once_and_never_blocks`,
  `test_text_the_opinion_reads_through_a_mosaic_is_flagged_and_patched`); only eligible with the Baseten key and price.
- WP4 medium: receipt wording overclaimed ("every frame checked", "approved by the creator" on auto-approve) and the
  synthetic note survived paid calls; no Baseten disclosure → fixed (`test_the_page_is_self_contained_and_says_what_happened`,
  `test_a_blocked_audit_is_receipted_as_blocked_and_costs_add_up`, `test_a_second_opinion_on_baseten_is_disclosed`).
- WP4 low: detector timing divided by frames scanned, not calls → per call.
- WP4 (approval hash bound to decisions) is SHIP's `pipeline.approve`: filed with SHIP.

## Round 3: running at 90b9f71 (main dd92749)
