AUDITED_COMMIT: 145fbfb
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# SAFECUT-SENSE re-audit log

Each audit is a full, independent, read-only pass by a Sonnet reviewer (effort high) over the lane's code against
its specs. Every finding was verified here before it was fixed; each fix has a named test.

## Audit 1 (perception: prepare, track, SAM parser, replay) at 6ccbb3a: 0 critical, 1 high, 3 medium, 5 low
- H1 detections past the proxy dropped silently → `TrackError` in `build`; replay refuses a recording made for another proxy (`test_a_detection_past_the_proxy_fails_the_stage`, `test_a_recording_for_another_proxy_is_refused`)
- M1 coordinate space and mask size unchecked → SAM must answer in the proxy's w×h with box-sized masks (`test_sam_must_answer_in_the_proxys_space_with_box_sized_masks`)
- M2 a failed sweep left siblings running past the uploads' deletion → `asyncio.TaskGroup` (`test_a_failed_sweep_fails_the_track_stage`)
- M3 a re-run re-billed every sweep → this job's successful live answers are reused (`test_a_rerun_reuses_this_jobs_sam_answers`)
- L1 AAC priming read as an audio lead (42 ms trimmed) → first decoded audio frame (`test_aac_priming_is_not_mistaken_for_an_audio_lead`, T9 now within 1 ms)
- L2 the miss loop trusted a leftover proxy → `proxy_for` rebuilds and checks it against `tracks.json`
- L3 replayed `requests[].usd` is 0 → decided: replay spends nothing (asserted in `test_every_sense_stage_runs_live_and_matches_its_replay`)
- L4 recording-key collisions → a hash suffix whenever the slug loses information
- L5 bare `MediaError` from keyframes → `PrepareError("unreadable") (since renamed `bad_media` for SHIP's intake API)`; partial proxy removed on failure; pools per request accepted (spawn cost < 1 s)

## Audit 2 (reasoning: speech, scout, go-live) at 6ccbb3a: 0 critical, 4 high, 7 medium, several low
- H1 a phrase sweep's unrelated track could "cover" a miss → only a track holding the point near the reported frame (`test_a_sweep_track_covers_a_miss_only_where_it_was_reported`)
- H2 crowded frames counted as evidence → excluded from `Window.present` (`test_crowded_frames_are_never_evidence`)
- H3 a duplicate entry could hide a child or sensitive flag → fail-closed merge (`test_a_label_answered_twice_merges_fail_closed`)
- H4 a miss-loop upload failure crashed `roles` → falls back to static boxes (`test_a_failed_proxy_upload_in_the_miss_loop_leaves_a_static_box`)
- M1 out-of-range `matches_participant` → dropped unless within the scene's list (`test_a_participant_index_outside_the_scene_is_dropped`)
- M2 `child_phrase` tracks escalated; `children's` not a child phrase → never disputed; possessive plurals added (`test_possessive_plurals_still_lock_a_child`)
- M3 a child ruling with bad citations discarded → kept, frames dropped (`test_a_child_ruling_counts_even_with_bad_citations`)
- M4 audit reserve ignored the track count → redteam.md sampling (`test_the_audit_reserve_grows_with_the_tracks`)
- M5 go-live `--id` path escape and destructive re-runs → sanitised ids, `--replace`, atomic swap (`test_ids_never_escape_fixtures`, `test_an_existing_recording_is_kept_unless_replaced`); `--consented` stays the owner's attestation (documented in the script and BLOCKED.md)
- M6 replay ignored the prompt version → logged when it differs (recordings stay usable: prompts change, the recorded answers are what they are)
- M7 prompt-injection hygiene → `prompts.inline` (one line, bounded) for every quoted model/transcript text; whole-word introductions (`test_inlined_text_cannot_forge_prompt_lines`, `test_an_introduction_must_be_whole_words`)
- Low: speech `has_speech`, unique `U` labels, WAV failure → fallback (`test_fallback_turns_respect_has_speech_and_never_reuse_u`); `three_votes` cancels vote 1 if 2/3 fail; dense-frame SoM tag displacement and the dropped-soundtrack floor are documented limits (a tag stays inside its own box's column; the floor only detects un-ingested media until probe e measures it).

## Audit 3 (two auditors: perception; reasoning and go-live) at b7269be: 0 critical, 2 high, 6 medium, 9 low
Not clean. All verified here (each repro rerun or the code read) and fixed with a test that fails without the fix.
- H1 (perception) an MP4 edit-list trim's hidden frames moved the video origin: audio delayed 0.5 s in the repro → the clock starts at the first decoded frame, read in the stream's own time base (`test_an_edit_list_trim_keeps_audio_on_the_first_shown_frame`)
- H1 (reasoning) a window showing a track only on crowded frames was skipped, losing a child vote → judged with no valid evidence (`test_a_window_with_the_track_only_on_crowded_frames_still_counts`)
- M (perception) a recorded answer that never parsed was reused forever → asked again (`test_a_recorded_answer_that_never_parsed_is_asked_again`)
- M a miss-loop SAM answer `build` rejects crashed `roles` → static boxes (`test_an_unusable_miss_loop_answer_leaves_a_static_box`)
- M `untracked` dropped a child miss inside an adult's box → only a `child_phrase` track tracks a child; a boxed miss needs half its box covered (`test_a_child_miss_inside_an_adults_box_is_still_a_miss`)
- M go-live `--replace` could swap an empty run over a paid recording → a failed or empty run never replaces one (`test_a_failed_run_never_replaces_an_earlier_recording`)
- M an escalation ruling twice on a label kept the last → fail-closed merge (`test_a_label_ruled_on_twice_merges_fail_closed`)
- L the role re-pass could spend the audit reserve → checked like the SAM requests (`test_the_role_re_pass_never_spends_the_audit_reserve`)
- L scene summary raw in the escalation prompt → `prompts.inline`; model-written concepts unbounded → 40 chars (`test_a_long_phrase_makes_a_bounded_concept`)
- L go-live relative paths after `cd` → resolved from the caller (`test_relative_paths_are_the_callers`)
- L one-frame upload → `bad_media`; repeated (frame, object) records → union box without a mask (`test_a_repeated_object_on_a_frame_is_joined_never_dropped`); a sweep's mixed failures → one typed error; checkpoints keyed on the SAM model too (`test_a_checkpoint_from_another_model_is_not_reused`)
- Unverified item made real: an `.m3u8` upload makes ffmpeg's HLS demuxer read the local files it names (reproduced) → only the mov demuxer may open an upload (`test_a_playlist_upload_is_refused_before_ffmpeg_opens_what_it_names`). The other unverified item (framemd5 output held in memory) is bounded by the 150 MB / 60 s limits checked first: accepted.

## Audit 4 (two auditors: perception; reasoning and go-live) at 145fbfb: 0 critical, 0 high, 4 medium, 9 low
Not clean. Every finding verified (repro rerun, or the code read) and fixed; each new test fails on 145fbfb.
- M (perception) a tiny-frame upload held every packet in memory before any limit ran (480k packets → +190 MB reproduced) → packets read incrementally, more than 20,000 refused (`test_millions_of_tiny_frames_are_refused_without_reading_them_all`)
- M a failure outside a Meta call in the miss loop (proxy rebuild, ledger) crashed `roles` → static boxes; a ledger that can't answer refuses the spend (`test_a_proxy_that_cannot_be_rebuilt_leaves_static_boxes`, `test_a_ledger_that_cannot_answer_refuses_the_spend`)
- M `roles` appends to tracks.json, so a resumed `analyse` re-ran (and in live, re-billed) `track` and `roles` → this job's own live answers are reused (body-hash checkpoints for Muse calls, SAM checkpoints in the miss loop): the re-run is free and writes byte-identical files (`test_a_resumed_roles_stage_re_bills_nothing_and_writes_the_same_files`). The pipeline still re-runs the two stages (compute only); a Stage `also_writes` in SHIP's registry would skip them.
- M an object-prompt track away from the reported point counted as covering the miss → bound only if it holds the point near the frame (`test_a_prompt_track_away_from_the_miss_does_not_cover_it`)
- L SAM checkpoints not tied to the clip → the upload's sha256 is recorded and must match (`test_a_recording_for_another_clip_is_never_reused`)
- L a mask larger than the proxy decoded before the size check → refused first (`test_a_mask_larger_than_the_proxy_is_refused_before_decoding`)
- L the sweep docstring over-claimed what a re-run re-pays → corrected (in-flight siblings are cancelled, by design, before the uploads are deleted)
- L escalation could spend the audit reserve and cite crowded frames → reserve checked, crowded frames never evidence (covered by the ledger test; the crowded rule mirrors `Window.present`)
- L sibling votes not cancelled on a raise → `TaskGroup` in `three_votes` and the miss loop's `_send` (`test_a_vote_that_raises_cancels_its_siblings`)
- L planned sweeps counted as searched before they ran → only answered sweeps (`test_only_sweeps_that_ran_count_as_searched`)
- L transcript turns cut at 300 chars in prompts → 1,500 (`prompts.TURN_CHARS`)
- L a turn after the clip clamped to its last frame → dropped (`test_a_turn_after_the_clip_ends_is_dropped_not_clamped`)
- L go-live's swap deleted the old recording before the new one was in place → renamed aside and restored after a crash, staging outside fixtures/jobs (`test_a_swap_killed_halfway_restores_the_earlier_recording`)
