AUDITED_COMMIT: dd1312d0c63a45fe20c393fa3d4d1dd9e0d4b0aa
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

## Round 3 (at 90b9f71): 0 critical, 0 high; mediums and lows verified; fixed at 225d9c6 (merged ede3dc1) or accepted
- WP4 medium (SHIP's): a patching audit breaks `check_approval` (decisions hash) → reproduced; filed with SHIP with
  the fix (hash without `audit_patch` items).
- WP4 medium (SHIP's): the API returns private red-team text in `audit` → filed with SHIP.
- WP4 medium: a re-render left the old receipt beside the new video → the render stage retires it, chained via
  `receipts/HEAD` (`test_a_re_render_retires_the_old_receipt_until_a_new_one_is_sealed`).
- WP4 low: exclusion by the whole box, not the visible region → the kept track's mask where it has one
  (`test_exclusion_uses_the_kept_tracks_visible_mask_where_it_has_one`); the IoU > 0.3 threshold itself is redteam.md's.
- WP4 low: only the first frame of a detector run went to the red team → every flagged frame (redteam.md Inputs).
- WP4 low: leaks grouped on any overlap → IoU ≥ 0.3 (`test_leaks_merge_only_at_iou_0_3_or_more`).
- WP4 low: bar scaled with the clip → 40 px like the role pass (`test_bar_height_and_frame_label`).
- WP4 low: receipt JSON couldn't say auto-approve (`approved_by` is fixed by the contract) → a sealed note; audio kept
  is disclosed; the page says only receipt.json is sealed (`test_the_receipt_matches_every_job_file`,
  `test_a_human_review_is_not_noted_as_auto_approved`).
- WP4 low: a rebuilt job.json could re-allow the second opinion → attempt also recorded in `raw/audit/`
  (`test_a_rebuilt_job_json_never_makes_the_opinion_eligible_again`).
- WP4 low accepted: per-cell mosaic noise is deterministic (DESIGN §2.7 asks for fixed per-block noise so frame
  averaging can't cancel it; the ≤ 6-block grid is the protection, not the noise); `truth.py` maps synthetic labels only.
- WP3 medium accepted: a track SAM re-acquires under a fresh object id is judged on its own votes. ARCHITECTURE §3.2
  and the contract operationalise DESIGN §2.5's "new ID" as `reentry_of` (always held); holding every mid-clip ID
  would also hide a participant who walks in (the demo's guest), failing E3, against the contract's own keep rule.
- WP3 medium: crowd fill covered hidden tracks only → every tracked object on the crowded frames
  (`test_a_crowd_fill_covers_every_tracked_object_kept_ones_too`).
- WP3 medium: review re-plans slow on busy clips → vectorised RLE (pycocotools-checked), crop decode, unvalidated
  entries (15 s → 8.8 s measured) and a per-job region cache across re-plans
  (`test_cached_regions_plan_exactly_as_fresh_ones`, `test_the_guard_stage_reuses_regions_until_the_tracks_change`).
- WP3 low: a re-hidden prominent person got the mosaic → the policy's style (`test_a_kept_prominent_person_hidden_again_is_covered_whole`).
- WP3 low: remove_person on a face-only item covered the face → an estimated body (`test_removing_a_face_only_person_covers_a_body_under_the_face`).
- WP3 low: a creator hide kept a stale hold → cleared (`test_a_creator_hide_clears_the_hold`).
- WP3 low: reasons unbounded → ≤ 90 chars, lowercase-first, no full stop (`test_reasons_are_short_lowercase_first_without_a_full_stop`).
- WP3 low: extra concepts mapped to screen/document → exactly API-NOTES §12's map (`test_kinds`).

## Round 4 (at 225d9c6): 0 critical, 0 high; verified and fixed at 6e83d9b (merged 2b5aacf) or filed
- WP4 medium: a recording's `raw/audit/opinion*` replayed into another job claimed its frames went to Baseten (and
  made the job dir invalid) → the marker and record name their job
  (`test_a_replayed_recording_never_brings_its_opinion_into_another_job`, fails without the fix).
- WP4 medium: `validate_job_dir` gated nothing in production → the receipt stage validates the whole job directory
  and withdraws the receipt when it doesn't (`test_no_receipt_on_a_job_directory_that_does_not_validate`).
- WP4 low: a replayed real recording wasn't disclosed → `REPLAY_NOTE` (`test_a_replayed_recording_is_disclosed`).
- WP4 low (SHIP's): the job-cap pre-check raises before the audit, so a cap stop is `failed`, not `over_budget`
  (fails closed) → filed with SHIP.
- WP4 low: `auditor_available` loaded models per request, and weights without torch gave 503 → cached per weights
  state; falls back to YuNet, recorded (`tests/test_audit_gpu.py`).
- WP4 low: a box that isn't 4 integers voided the response → a whole-frame leak per finding
  (`test_a_malformed_box_keeps_its_finding_as_a_whole_frame_leak`).
- WP4 low: the banner named a red team and an all-purpose detector even for the oracle / YuNet → names what ran
  (`test_the_banner_names_the_checks_that_actually_ran`). The unkeyed hash is a tamper check, as the page says.
- WP3 medium: a whole-person item left the body bare on frames its body track didn't reach → body estimate per
  frame (`test_a_whole_person_item_covers_a_body_where_only_its_face_is_tracked`, fails without the fix).
- WP3 low: the region-cache registry wasn't thread-safe → locked.

## Round 5 (at 6e83d9b): 1 high, 2 medium, lows; verified and fixed at dd1312d (merged d126234) or filed/accepted
- WP3 high: an exact face/body share tie paired nothing, so a child's body could be kept and one child counted twice
  → ties go to the body the face fills most; an unpaired child face locks every body holding it
  (`test_a_child_carried_by_an_adult_pairs_with_their_own_body`, `test_a_child_face_no_body_can_claim_locks_every_body_holding_it`,
  both fail without the fix).
- WP3 medium: a read-through solid re-render dropped the whole-person body cover → the item's own style decides
  (`test_a_read_through_whole_person_stays_whole_when_it_goes_solid`, fails without the fix).
- WP3 low: re-covering a spot after an undo renumbered it on the next replay → kept (`test_a_spot_covered_again_after_an_undo_keeps_its_patch_number`, fails without the fix).
- WP3 low: the audit loop re-planned without the region cache; the cache key was taken after the reads → both fixed.
- WP4 medium: a crash part-way through an audit left the old clean audit.json / receipt → the audit retires the receipt
  and writes a blocked audit.json first (`test_a_crash_part_way_never_leaves_the_old_clean_verdict`, fails without the fix).
- WP4 low: the receipt stood before it was validated → validated in a shadow job dir, then put in place.
- WP4 low: a crash or torn write lost the second opinion's record → atomic writes; a lost answer reads `failed`
  (`test_a_crash_during_the_opinion_is_recorded_as_failed_not_off`).
- WP4 low: an unreadable manifest read as a real run; `files_deleted: true` with no files.json after billed SAM → fixed
  (`test_an_unreadable_recording_manifest_never_reads_as_a_real_run`, `test_without_files_json_a_billed_sam_call_is_never_claimed_deleted`).
- WP4 low (SENSE's): `scripts/go_live.py` deletes the old recording before the new run is known good → filed with SENSE.
- WP4 low accepted: a frame-label text box spilling out of the bar stays a leak (G8: dropped "only if" wholly inside;
  fails closed); YuNet leaks carry the contract literal `detector: "egoblur"` (`audit.egoblur.model` names YuNet);
  the receipt doesn't hash the video (not in §3.9's contract).

## Round 6: running at dd1312d (main d126234)
