AUDITED_COMMIT: ae004d8
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 2

# SAFECUT-SENSE re-audit log

Each audit is a full, independent, read-only pass by two Sonnet reviewers (effort high; perception, and reasoning
with go-live) over the lane's code against its specs, at one commit. Every finding was verified here before it was
fixed; each fix has a named test that fails without it. **Clean** means no Critical, High or Medium finding: Lows are
still fixed (or recorded as decisions below), but every full pass finds some, so they don't reset the count.

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

## Audit 5 (two auditors) at b27847c: 0 critical, 0 high, 3 medium (perception), 10 low
Not clean (perception mediums). Reasoning half: clean (0 C/H/M, 7 lows). All verified; fixed with failing-first tests.
- M a long, tiny upload hit the packet cap first and was refused as bad_media → the header's duration is checked before packets (`test_an_over_long_upload_is_too_long_even_past_the_packet_cap`)
- M ffmpeg itself indexes every declared sample before printing (crafted 50 KB MP4 → 1.8 GB RSS, reproduced by the auditor) → every read of an upload runs under a 1 GiB address-space limit via `sh ulimit` (`test_every_read_of_an_upload_runs_under_the_probe_memory_limit`)
- M a proxy under SAM's 15-frame hot start would return no tracks → track fails before any call (`test_a_clip_too_short_for_sam_fails_before_any_call`)
- L a SAM object id of thousands of digits → over 9 digits fails closed (`test_a_huge_object_id_fails_closed`); ffmpeg banner in error text → the header's last line only
- L re-running `roles` alone on its own output re-billed → earlier miss-loop tracks set aside first (`test_roles_run_again_on_its_own_output_re_bills_nothing`)
- L escalation evidence by completion order → time order (`test_escalation_evidence_follows_time_order_not_completion`)
- L corrupt recording crashed the Muse checkpoint → asked again (`test_a_corrupt_recording_is_no_checkpoint`)
- L a child vote on an unasked label or in a window not showing it was dropped → it locks (`test_a_child_vote_locks_even_where_the_track_was_not_shown_or_asked`)
- L go-live: another id's leftover failed `rmdir`; a recording set aside by a killed swap didn't count → both fixed (`test_another_ids_leftover_does_not_fail_a_good_swap`, `test_a_set_aside_recording_still_needs_replace`)
- L child words missing (schoolgirl, newborn, tween, …) → added; stricter only (`test_more_child_words_lock`)
- Decision: SAM recordings without `source_sha256` (the committed synthetic fixtures) still replay: they are bound to their clip by the manifest's `source_sha256`, which `pipeline.find_recording` matches before any replay.
- Decision: speech-fallback's `self_intro`/`addresses` sanity check is not applied: the fields are dropped by design, the role pass reads `text` (the same evidence), and speech can never create a keep.

## Audit 6 (two auditors) at 7db7881: 0 critical, 0 high, 3 medium (perception), 11 low
Not clean (perception mediums; none can under-hide). Reasoning half: clean (0 C/H/M; one Low+ fixed exactly).
- M an 8192² upload passed the probe and its transcode used 2.2 GB unbounded → sources over 40 Mpx refused before any full decode; the transcode runs under a 6 GiB limit with fixed thread counts (`test_a_resolution_bomb_is_refused_before_any_full_decode`, `test_the_transcode_runs_under_its_own_memory_limit`)
- M non-UTF-8 container metadata crashed `facts` with a UnicodeDecodeError (service: "internal") → stderr decoded with replacement; header facts read from ffmpeg's own lines only, so a title can't fake the duration either (`test_metadata_bytes_and_lies_never_break_the_stream_facts`)
- M a clip under ~1.75 s passed prepare and failed track as an untyped TrackError ("internal") → `ClipTooShort` carries reason bad_media, which the service maps (`test_a_clip_too_short_for_sam_fails_before_any_call`)
- L probe decodes on many-core hosts → one thread and one filter thread, 2 GiB; 1080p and 4K60 phone-style clips prepare end to end (checked by hand: 1.5 s and 2.8 s)
- L a 10+ digit SAM field (mask size) reached Meta's int() → fails closed first; an unusable checkpoint (ValueError) is asked again (`test_a_huge_mask_size_fails_closed`)
- L one parse pool per SAM stream could start dozens of interpreters → one pool at a time per process
- Low+ (reasoning) a roles re-run after a phrase sweep re-billed pass 1 (concepts/crowded frames not restored) → roles keeps a copy of its input and stamps its output; a re-run on its own output restores the exact input (`test_a_re_run_after_a_phrase_sweep_re_bills_nothing`)
- L a child ruling on a label escalation wasn't asked about was dropped → locks (`test_a_child_ruling_on_an_unasked_label_locks_it`); `schoolchildren's`, youth, adolescent, preschooler, kindergartener lock (`test_possessives_and_more_child_words_lock`); corrupt scene/transcript → no context, roles.json still written (`test_a_corrupt_scene_file_still_writes_roles`); WAV disk error → fallback; go-live: a stopped run exits 1 (`test_a_stopped_run_is_not_reported_as_success`), `--id` keeps dots as separators (`test_ids_keep_their_dots_as_separators`)

## Audit 7 (two auditors) at 1c94c2f: 0 critical, 0 high, 1 medium (reasoning), 9 low
Not clean (one reasoning medium, introduced by audit 6's fix). Perception half: clean (0 C/H/M, 4 lows).
- M a child ruling on an unasked, matched participant made `role_track` emit a matched child, which the contract rejects: roles crashed with no roles.json → a child is never matched (`test_a_child_ruling_on_the_host_still_writes_roles`)
- L (perception) U+2028/\x1e/\x85 in metadata forged header lines through `splitlines()` (bypassing the pixel cap; still bounded by the transcode limit) → split on `\n` only; size from the first video stream (`test_unicode_line_breaks_in_metadata_cannot_forge_header_lines`)
- L a stream line imageio can't parse (AttributeError) → bad_media (`test_a_stream_line_the_parser_cannot_read_is_bad_media`); the encoder gets its own `-threads 4` (checked: `threads=4 lookahead_threads=1` in the prepared clip); negative 10+ digit SAM fields fail closed (`test_a_huge_negative_number_fails_closed`)
- L a corrupt transcript.json crashed `scene` → no speech, scene.json written (`test_a_corrupt_transcript_still_writes_scene`); roles' input copy/restore atomic; speaker labels bounded (`test_a_speaker_label_that_is_a_huge_number_is_relabelled`); fixture ids never end in a separator
- Decision: an `unsure` escalation ruling citing no frames counts as no ruling (`escalated: false`), the same rule as a role vote without citations (role-pass rule 5); advisory only.

## Audit 8 (two auditors) at 5e6eaa7: 0 critical, 0 high, 1 medium (perception), 5 low
Not clean (one perception medium: audit 7's header fix was incomplete). Reasoning half: clean (0 C/H/M; its contract
fuzz ran 9 full jobs on hostile schema-valid answers, all valid).
- M a newline in a metadata key is printed unescaped and forged ffmpeg header lines: a 3 s video with 20 min of audio was accepted, and an 81 Mpx frame passed as 100×100 → the header is a hint only: duration from the longest stream's packet span, pixels from the first decoded frame, the prepared clip cut to its video's span (`test_a_forged_header_cannot_hide_a_long_soundtrack`, `test_a_forged_header_cannot_hide_a_huge_frame`, `test_the_prepared_clip_never_runs_past_its_video`)
- L whitespace before a 4,300+ digit SAM field reached Meta's int() → any ValueError from the parser is MetaIncomplete (`test_a_huge_number_with_spaces_fails_closed`); box-token keys trimmed like Meta's parser (`test_a_space_key_with_whitespace_is_read_like_metas_parser`)
- L (reasoning) `clip_id` could end in a separator → stripped (`test_clip_ids_never_end_in_a_separator`); fallback turns unbounded → at most 300 (`test_the_fallback_keeps_a_bounded_number_of_turns`)
- Decision: person misses inside a same-concept track's box are tracked by it (audit 3's rule; a child miss counts only for a child_phrase track); per-word phrase length, non-ASCII SoM tags drawn as `?`, replay failure text in a scene summary, a hand-edited corrupt ASR recording, and `--usd-cap` rounding are cosmetic or need tampered input: recorded, not changed.
- Added after audit 7: a hypothesis property that any schema-valid votes and rulings assemble into a roles.json the contracts accept (`test_any_schema_valid_answers_assemble_into_a_valid_roles_file`).

## Audit 9 (two auditors) at 3b6d537: 0 critical, 0 high, 0 medium, 7 low: CLEAN
Both halves clean at Medium and above (interrupted by a usage limit at 18:05 UTC and resumed at 19:23 from their saved
state). The reasoning half fuzzed ~45 full speech/scene/roles runs with hostile schema-valid answers and 3,000
multi-window cases against an independent oracle: every output valid, every participant on 3/3 valid votes over ≥ 2
distinct non-crowded frames. The perception half prepared 20+ legitimate clip shapes (rates, rotation, 10-bit HDR,
8K, fragmented MP4, edit-list trims, audio first or longer) with no regression from the `-t` cut.
- L (reasoning) the roles property was a weak oracle → it now asserts the keep rule itself (≥ 2 distinct cited frames, none crowded or unsent); A1–A16 and the crowded-frame tests already covered the rules
- L a WAV half-written by a failed extract stayed in the job → removed (`test_a_failed_wav_extract_leaves_no_partial_file`)
- Decision: a stream that changes resolution mid-stream (crafted: small first frame, huge later ones) is bounded by the 6 GiB transcode limit and the timeout; `times` still match the read-back frames' own count. Not refused upfront (that would need a full decode).
- Decision: `-t` at the video span could drop a final frame only if the last packet reports a zero duration (not reproducible with a normal muxer; at most 1/fps).
- Decision: an attached picture (cover art) as the first video stream is refused as bad_media (typed, fail closed).
- Decision: a track with one failed vote in each of several windows counts as all-failed and isn't escalated: it stays hidden (fail closed); escalation is advisory.
- Decision: votes 2 and 3 start when vote 1 answers or after 20 s; the "first output item" trigger needs a streaming hook the client doesn't expose. Latency only.

## Audit 10 (two auditors, full fresh passes) at 86be73c, the final SENSE code: 0 critical, 0 high, 0 medium in SENSE: CLEAN
Second clean audit in a row (9 at 3b6d537, 10 at 86be73c; between them only the two audit-9 lows and a merge of main).
The perception half measured `job.times` and the proxy table on burned-in frame barcodes across 14 rates, offsets and
VFR (0 mismatches), and 171 rate × length combinations. The reasoning half ran ~400 full speech → scene → roles →
decide → guard jobs with hostile schema-valid answers (multi-window, crowded, random SAM answers, live client path
with fault injection): every job valid, with an independent oracle finding no keep without 3/3 valid votes over ≥ 2
distinct present non-crowded frames, no lost child, every miss covered.
- Outside SENSE (reported to SHIP, its owner): `deploy/modal_app.py` mounts `safecut` with `add_local_python_source`, whose default ignore drops non-.py files, so the deployed image would lack the prompt templates (and SAFETY's YuNet weights).
- Decisions (lows, no change at the final head): `data= H,W` with a space slips the mask-size pre-check (malformed Meta answer; Meta's parser still refuses it as not box-sized, CPU bounded); the demo's synthetic person boxes stop one row above the drawn feet (synthetic fixture only; E3 scores faces); a truncated upload prepares to the frames that decode (typed, times stay exact); non-square SAR is kept (SAM's space check fails closed if Meta answers in display space; needs the live probe); a turn wholly before the clip clamps to t = 0 (cannot create a keep); counts of scene participants and swept phrase characters are unbounded in prompts (cost only); quotes and brackets inside one quoted line aren't escaped (needs adversarial speech; cannot create a keep); the role-pass agreement-rate logging and order-shuffle contingency aren't built (advisory); a malformed ASR body with a lone surrogate or a 400-digit time fails the primary path loudly (Meta-only); no total cap on static misses beyond the spec's M8 (linear: 300 items stayed small); `make_demo_job` rebuilds the demo in place; escalation affordability is all-or-nothing (advisory).

## Audit 11 (diff check) at ae004d8: behaviour-neutral
After audit 10 the gate's older system ruff (0.16.9) asked for two lint changes; ae004d8 is them and nothing else
(`git diff 86be73c ae004d8 -- . ':(exclude).agent'`: `safecut/track/media.py` loads imageio's header parser with
`importlib` instead of a long suppressed import, and four test-local `noqa` lines gain their reason). An independent
auditor verified it changes no behaviour: `media.parse_ffmpeg_header is imageio_ffmpeg._parsing.parse_ffmpeg_header`;
the old and new `facts()` agree field for field on every fixture clip; the test file's AST is unchanged; the monkeypatch
path still reaches the real call site; pytest (prepare, track, scout logic: 133 passed) and pyright clean. So the
AUDITED_COMMIT moves to ae004d8 with audits 9 and 10 standing: the code they audited is the code at ae004d8.
