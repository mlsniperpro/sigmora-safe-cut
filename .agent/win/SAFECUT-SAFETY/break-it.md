TESTED_COMMIT: a6702a7

# SAFECUT-SAFETY: what I did to break it

Every item is a command run in this session (results quoted), or a named test that fails without the fix it
guards. The soak and the fresh-clone run are repeated at the final commit; `TESTED_COMMIT` names it.

## Soak (property tests at 10× volume)
- `HYPOTHESIS_PROFILE=soak uv run pytest --entry-only=E4` (20,000 examples per property, 7 E4 properties: non-
  participants never kept, children never kept after any creator edits, padded boxes covered, back-fill and gap
  hold, locked grids, an injected 3-frame leak patched, ≤ 6 blocks): **7 passed** at 90b9f71 (12 min), 225d9c6
  (14 min), 6e83d9b (12 min), dd1312d (12.5 min), a9e3b34 (12 min); log in the session scratchpad.
- The E4 coverage property caught a real gap during round 6 (an estimated body grown from a mask outline's box
  sat inside the padded box on one frame): fixed at a9e3b34, now in the soak.

## Failure injection (each a test; each fails without its fix)
- Detector crash on any pass, on the first re-check, while judging a frame's detections → frames unscanned,
  `audit_failed` (`test_a_detector_crash_leaves_frames_unscanned`, `test_a_crash_while_rechecking_a_fix_is_never_clean`,
  `test_a_frame_whose_detections_were_not_all_judged_is_unscanned`).
- Red team silent, skipping frames, refusing (in the message or raised by the client), returning malformed boxes,
  stopped by a budget cap → unanswered frames unresolved, one re-ask, whole-frame leaks, `over_budget`
  (`test_frames_a_red_team_silently_skips_are_unresolved`, `test_live_reasks_a_refusal_the_client_raises`,
  `test_a_malformed_box_keeps_its_finding_as_a_whole_frame_leak`, `test_a_budget_stop_blocks_as_over_budget`).
- An uncaught crash in the middle of an audit, and a render dying while patches land → a blocked audit.json, no
  receipt, the leaks kept in `raw/audit/pending.json` and re-checked on the next run
  (`test_a_crash_part_way_never_leaves_the_old_clean_verdict`, `test_a_crash_while_patching_keeps_the_leaks_and_rechecks_the_fixes`).
- A second opinion killed mid-call, a torn opinion record, a recording's opinion replayed into another job →
  `failed`, never `off`; never inherited (`test_a_crash_during_the_opinion_is_recorded_as_failed_not_off`,
  `test_a_replayed_recording_never_brings_its_opinion_into_another_job`).
- A video drawn from another plan, an audit of another video, a plan changed after the render, a torn run record,
  a tampered receipt → redrawn / no receipt (`test_the_audit_redraws_a_video_drawn_from_another_plan`,
  `test_a_receipt_never_seals_an_audit_of_another_video`, `test_a_receipt_never_seals_a_plan_the_video_was_not_drawn_from`,
  `test_a_torn_audit_run_record_vouches_for_nothing`, `test_tampering_with_any_field_breaks_the_hash`).
- Manual: the rendered video cut in half, then re-audited → `RenderError: redacted.mp4 has 135 frames, the job
  360` (the stage fails, nothing reads clean).

## Replay end-to-end
- `uv run safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --out <dir> --replay --auto-approve-policy`
  on a fresh clone of main (dd92749): done in 17 s; `python -m safecut.receipt verify` → `chain ok`;
  `validate_job_dir` → valid; audit: 1 pass, 0 unresolved, auditor `yunet-face`.
- `checks.sh` runs the same path on every gate run, plus `entry-check --only E2,E3,E4` (all OK).

## Fresh clone
- Full test suite on a fresh clone of main at ede3dc1: **1278 passed**.
- Full `bash scripts/entry-check.sh` on a fresh clone of main at d126234: E1–E10 and E12 OK; E11 failed only on
  a skip-shaped string inside SHIP's own `tests/test_entry_check.py` (reported to SHIP).

## Adversarial audits
- Eight rounds of two independent full audits (WP3, WP4); every finding verified and fixed with a test or
  accepted with a reason (`reaudit.md`). The auditors' own fuzzers (thousands of random jobs, review logs, RLE
  masks and red-team scripts through `validate_job_dir`) are recorded there.
