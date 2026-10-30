# SAFECUT-SAFETY win checklist (WP3 + WP4; brief `.agent/briefs/SAFECUT-SAFETY.md`)

Evidence is a test name, a command run in this session, or a commit. Owner inputs are `[P]` and listed in `BLOCKED.md`.

## Judging criteria
- [x] **Impact (30%)**: deny-by-default redaction that can't be reversed, proven per clip: on the synthetic demo job every should-hide object is 100 % covered on every visible frame, zero leak bursts, participants never hidden (`tests/test_e3_demo.py`, `entry-check --only E3` → OK).
- [x] **Use of Meta AI tooling (25%)**: Muse Spark red-teams the rendered output (`audit/redteam.py`, strict schema, `store: false`); Muse Spark Open on Baseten gives the second opinion (`audit/opinion.py`); EgoBlur Gen 2 (Meta) is the auditor when its weights are installed (`audit/detectors.py`); SAM masks shape the redaction (`guard/regions.py`).
- [x] **Technical depth (20%)**: Hungarian binding and grouping, a leak guard with motion-following back-fill, locked-grid mosaics, a ≤ 3-pass self-patching audit, a hash-chained receipt; E4 properties at 2000 examples each (`entry-check --only E4` → OK).
- [x] **Demo (25%)**: `receipt.html` is a self-contained page a judge can open (verdict, per-item redacted thumbnails, models, data handling, seal); `safecut run … --replay --auto-approve-policy` runs offline in ~15 s.

## WP3 (decide + guard)
- [x] Binding: dilated-mask hit, nearest box within 0.1 × diagonal, keyframe votes, Hungarian, ties → none (`tests/test_binding.py`).
- [x] Grouping face + person when the face is inside on ≥ 80 % of shared frames (`test_a_face_inside_a_body_on_80_percent_of_frames_groups`).
- [x] Policy, a table test per rule including PRE-A vectors P1–P12, A1–A5, E1–E7, B1–B3 (`tests/test_policy.py`); 100 % branch coverage of `policy.py` (`--cov=safecut.decide.policy --cov-fail-under=100`).
- [x] `apply_review`: keep/hide/merge/remove_person/cover_spot/undo; locked children never kept (`tests/test_policy_review.py`, property at 2000 examples).
- [x] Leak guard: padding, back-fill `ceil(15·fps/sam_fps)`, extend 8, gap hold ≤ 2 s growing 2 %/frame (also across a re-entry split), crowd fills, locked grids, mask-shaped regions with a sliver fallback (`tests/test_guard.py`).
- [x] E4 properties ≥ 2000 examples: non-participants never kept, children never kept after edits, padded boxes covered, back-fill and gap hold, grids fixed (`entry-check --only E4` → OK).
- [x] `decide` and `guard` stages run on the example and demo jobs and validate (`test_the_example_job_decides_validly`, `test_guard_stage_on_the_example_job`, E2 OK).

## WP4 (render + audit + receipt)
- [x] Render: solid / person_solid / locked-grid pixelate (≤ 6 blocks + fixed per-cell noise), H.264 with the source audio, thumbnails from redacted frames (`tests/test_render.py`).
- [x] Reversibility: YuNet finds the synthetic bystander in the source on ≥ 80 % of frames and on 0 rendered frames; a 16-block mosaic is still found (`test_reversibility_a_face_detector_finds_no_pixelated_face`).
- [x] Audit: detector on every frame, red-team on 1 fps + track edges + gaps + flagged frames, auto-patch ≤ 3 passes, spots for the rest (`tests/test_audit_loop.py`).
- [x] Injected 3-frame leak found and patched (`test_an_injected_3_frame_leak_is_found_and_patched`, E4 key `injected_leak_patched`).
- [x] Fail closed: unscanned frames (any pass), unanswered or silently skipped red-team frames, budget stops (`test_a_detector_crash_leaves_frames_unscanned`, `test_a_crash_while_rechecking_a_fix_is_never_clean`, `test_frames_a_red_team_silently_skips_are_unresolved`, `test_a_budget_stop_blocks_as_over_budget`).
- [x] Leak decision and grid mapping vectors L1–L14, G7–G14 (`tests/test_audit_rules.py`).
- [x] Live red-team logic: ≤ 50 frames a call, one re-ask in total, one follow-up for missing frames, answers recorded for replay (`test_live_*` in `tests/test_audit_loop.py`).
- [x] Open-weight second opinion: once per job, advisory until the grid is confirmed, budget stop → off (`tests/test_audit_opinion.py`).
- [x] Receipt: §3.9 JSON cross-validated with every job file, self-contained HTML, hash chain + verifier + tamper test, synthetic and YuNet notes (`tests/test_receipt.py`).
- [x] CPU timing recorded per job (`raw/audit/run.json`; YuNet ≈ 2–3 ms/frame); GPU hook for EgoBlur (`audit/gpu.py`, `tests/test_audit_gpu.py`).
- [x] GT scoring shared with eval (`render/coverage.py`, `audit/truth.py`; E3 OK with SHIP's `eval/metrics.py`).
- [x] E8 live tests exist for the SAFETY calls (`tests/test_live_safety.py` `E8:muse_redteam`; `E8:open_weight` is covered by `tests/test_live_audit_calls.py`).
- [P] EgoBlur Gen 2 weights (gated download, owner step O8): the audit records `yunet-face` until they're installed.
- [P] Live runs with `MODEL_API_KEY` / `BASETEN_API_KEY`: `unresolved == 0` on hero clip 1, red-team recordings.
- [P] Consented hero footage for the before/after frames and the reversibility check on real faces.

## Audit findings (round 1, both fixed with tests at 318dfd6)
- [x] WP4-1 detector crash in pass 2–3 was clean → unresolved (`test_a_crash_while_rechecking_a_fix_is_never_clean`).
- [x] WP4-2 synthetic demo receipt unmarked → manifest detected, oracle named (`test_e3_the_demo_job_is_redacted_audited_and_receipted`).
- [x] WP4-3 replay recording overwrote answers → per-ask answers (`test_a_replay_without_recordings_answers_nothing`).
- [x] WP4-4 two re-asks → one (`test_live_reasks_at_most_once_per_call`).
- [x] WP4-5 red-team model named before answering (`test_live_reasks_at_most_once_per_call` asserts `model is None`).
- [x] WP4-6 re-run dropped fixed leaks (`test_a_re_run_keeps_the_earlier_fixes_on_record`).
- [x] WP4-7 receipt without approval (`test_no_receipt_without_the_creators_approval`).
- [x] WP4-8 memory on large clips: streamed per call, extras capped.
- [x] WP3-1 sliver mask in a small box (`test_a_sliver_mask_in_a_small_box_falls_back_to_the_box`).
- [x] WP3-2 merge origin (`test_merging_into_a_kept_static_item_makes_it_a_sam_item`).
- [x] WP3-3 dilation cost (`test_property_coarse_dilation_contains_the_exact_one`).
- [x] WP3-4 gap hold across re-entry (`test_a_reentry_gap_is_held_up_to_2_s`).
- [x] WP3-5 cited frames off the track (`test_cited_frames_must_be_on_the_track`).
- [x] WP3-7 cross-key binding tie (`test_two_keys_that_want_one_track_equally_bind_neither`).
- [-] WP3-6 crowd fill covers only tracked objects: the contract asks for hidden tracked objects; untracked crowd members beyond SAM's cap aren't localised by anything, and the fill is padded per object.
- [x] WP4-9 a re-render re-encodes frames it didn't redraw: every pass after a re-render re-scans the whole video (`settle` in `audit/loop.py`).
- [-] WP4-16 a frame-fixed grid samples a moving face at shifting phases: the locked grid is DESIGN §2.7's requirement, and the fixed per-cell noise is the mitigation.

## Audit findings (round 2, fixed with tests at 90b9f71, merged dd92749)
- [x] WP3 locked hide refused (`test_a_locked_item_can_not_be_hidden_by_the_creator_either`).
- [x] WP3 cover_spot replay and undo (`test_undoing_a_cover_spot_removes_its_patch_and_reopens_the_spot`).
- [x] WP3 stale edits never abort the stage; undo of unknown/later edits (`test_a_stale_last_edit_never_aborts_the_decide_stage`, `test_an_undo_of_an_unknown_or_later_edit_reverts_nothing`).
- [x] WP3 two-sided gap hold (`test_a_gap_is_held_from_both_ends`).
- [x] WP3 child re-entries locked (`test_every_id_of_a_child_is_locked_across_reentries`).
- [x] WP3 hold precedence on role failures (`test_a_role_failure_still_writes_the_first_hold_in_order`).
- [-] WP3 review latency in the API: guard sped up here (51a67bb); the API's threadpool and mask-free payloads are SHIP's paths, filed with SHIP.
- [-] WP3 `bind.py` has no production importer: SENSE binds in its own stage; kept as the tested reference.
- [x] WP4 unplaceable findings never excused (`test_a_finding_that_cannot_be_placed_is_never_excused_by_the_host`).
- [x] WP4 client-raised refusal re-asked (`test_live_reasks_a_refusal_the_client_raises`).
- [x] WP4 opinion failures recorded, saved, reused; read-through flagged (`test_a_failed_opinion_is_recorded_once_and_never_blocks`, `test_text_the_opinion_reads_through_a_mosaic_is_flagged_and_patched`).
- [x] WP4 receipt honesty: wording, synthetic note on billed jobs, Baseten disclosure (`test_a_second_opinion_on_baseten_is_disclosed`).
- [-] WP4 approval hash bound to decisions: SHIP's `pipeline.approve`, filed with SHIP.

## Audit findings (round 3, fixed with tests at 225d9c6, merged ede3dc1; details in reaudit.md)
- [x] Re-render retires the old receipt (`test_a_re_render_retires_the_old_receipt_until_a_new_one_is_sealed`).
- [x] Visible-mask exclusion, every flagged frame red-teamed, IoU ≥ 0.3 grouping, 40 px bar (`tests/test_audit_rules.py`, `test_an_injected_3_frame_leak_is_found_and_patched`).
- [x] Sealed auto-approve and audio notes; seal wording (`test_a_human_review_is_not_noted_as_auto_approved`).
- [x] Second opinion can't run twice after a rebuilt job.json (`test_a_rebuilt_job_json_never_makes_the_opinion_eligible_again`).
- [x] Crowd fills over every tracked object; face-only remove_person covers a body; region cache and faster encoding (`tests/test_guard.py`, `tests/test_binding.py`).
- [x] Re-hide style, hide clears hold, reason format, kind map (`tests/test_policy_review.py`, `tests/test_policy.py`).
- [x] E9 `no_audit` baseline (`test_no_audit_is_the_policy_and_guard_without_any_audit_patch`).
- [-] Mid-clip IDs without `reentry_of`: ARCHITECTURE §3.2 and the contract define "new ID" as `reentry_of` (see reaudit.md).
- [-] Approval hash vs audit patches; private red-team text in API views: SHIP's paths, filed with SHIP.
- [-] Mosaic noise is deterministic by design (DESIGN §2.7 fixed per-block noise; the ≤ 6-block grid protects).

## Audit findings (round 4, fixed with tests at 6e83d9b, merged 2b5aacf; details in reaudit.md)
- [x] Replay never inherits a recorded opinion (`test_a_replayed_recording_never_brings_its_opinion_into_another_job`).
- [x] Receipt gated on `validate_job_dir` (`test_no_receipt_on_a_job_directory_that_does_not_validate`).
- [x] Replay disclosure, banner wording (`test_a_replayed_recording_is_disclosed`, `test_the_banner_names_the_checks_that_actually_ran`).
- [x] Malformed red-team boxes per finding (`test_a_malformed_box_keeps_its_finding_as_a_whole_frame_leak`).
- [x] YuNet fallback without torch; cached availability (`tests/test_audit_gpu.py`).
- [x] Whole-person body cover per frame (`test_a_whole_person_item_covers_a_body_where_only_its_face_is_tracked`); cache lock.
- [-] Job-cap pre-check before the audit: SHIP's `pipeline.run_stage` (fails closed), filed with SHIP.

## Audit findings (round 5, fixed with tests at dd1312d, merged d126234; details in reaudit.md)
- [x] Child carried by an adult; unpaired child face locks bodies (`tests/test_policy.py`, `tests/test_binding.py`).
- [x] Read-through keeps whole-person cover; spot numbers stable (`tests/test_guard.py`, `tests/test_policy_review.py`).
- [x] Fail-closed audit on a crash; receipt validated before it stands (`test_a_crash_part_way_never_leaves_the_old_clean_verdict`).
- [x] Crash-safe second-opinion record; manifest and files_deleted honesty (`tests/test_audit_opinion.py`, `tests/test_receipt.py`).
- [-] go_live.py recording replacement: SENSE's script, already fixed by SENSE (0dd5d1e).
- [-] Frame-label spill, `detector` literal, unhashed video: spec-literal or outside the contract (reaudit.md).

## Audit findings (round 6, fixed with tests at a9e3b34, merged 362379f; details in reaudit.md)
- [x] Child closure over items, re-entries and unpaired face/body links; duplicate rows fail closed (`tests/test_policy.py`).
- [x] Close-up faces hidden whole; body grows from the padded face box (`test_a_close_up_face_without_a_body_is_hidden_whole`, E4 coverage property).
- [x] Renders stamped with their plan; audits with their video; receipts refuse a mismatch (`test_the_audit_redraws_a_video_drawn_from_another_plan`, `test_a_receipt_never_seals_an_audit_of_another_video`).
- [x] Receipt for `.`; scanned only after judging (`test_a_receipt_for_the_current_directory_by_its_dot`, `test_a_frame_whose_detections_were_not_all_judged_is_unscanned`).
- [-] CLI "done" on a blocked audit; `_review` and a standing receipt: SHIP's files, filed with SHIP.
