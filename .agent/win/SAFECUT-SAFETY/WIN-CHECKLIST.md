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
