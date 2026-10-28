AUDITED_COMMIT: 5c72c49
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# Re-audit log

## Audit 1 (independent Sonnet reviewer, read-only, at f7f712e): 0 critical, 3 high, 5 medium, 8 low
I reproduced or confirmed every finding against the code and PRE-A §10. All are fixed in 6808b71 (plus f87b5ab for H2/H3), each with a test:
- H1 missing usage logged as $0 → the estimate is kept, `estimated: true` (test_completed_without_usage_keeps_the_estimate, test_meter_treats_missing_usage_as_unknown)
- H2 half-open trial leak → abandon_trial / record_success (test_half_open_trial_*)
- H3 orphan from a retried upload → recovery when `maybe_orphaned` (test_retried_upload_deletes_the_copy_an_earlier_attempt_left)
- M4 504 / slow 5xx counted as rejected → charged (test_504_and_slow_5xx_count_as_accepted)
- M5 cancellation accounting → `sent` flag, the throttle wait inside the try (test_cancel_*)
- M6 no MetaFileGone recovery → FileStore.reupload / mark_gone (test_reupload_after_file_gone)
- M7 a 200 upload without an id left an unrecorded copy → recovery before raising (test_upload_without_an_id_recovers_the_copy)
- M8 deletes blocked by a spent cap → free calls skip cap checks (test_delete_all_works_after_the_job_cap_is_spent, test_free_calls_pass_a_spent_cap)
- L9 orphan recorded when nothing was sent → only when `maybe_processed` (test_breaker_refusal_records_no_orphan)
- L10 base URL SSRF / key exfiltration → host allowlist, no userinfo or port (test_bad_env_is_refused cases)
- L11 per-job concurrency unused → SAM and Responses lanes per client; the process bound is a shared semaphore WP5 passes
- L12 no total timeout on plain calls → asyncio.timeout on every attempt (test_total_timeout_on_plain_requests)
- L13 rule-6 guards only in build_body → guard_body in the transport (test_stream_guards_agents_rule_6, test_request_refuses_contributor_models)
- L14 job_id/system mismatch failed after the call → checked in __init__ (test_job_id_and_system_caller_must_agree)
- L15 numeric ASR speaker → coerced (test_asr_tolerates_numeric_speakers_and_float_durations)
- L16 .env.example lacked BASETEN_API_KEY (added); orphan matching could hit a recorded sibling (recorded IDs excluded); the ledger read outside its transaction (BEGIN IMMEDIATE; test_ledger_file_is_shared_safely); docs/API-NOTES-WP0.md naming (a recorded decision: PR #1 owns docs/API-NOTES.md)

## Audit 2 (independent Sonnet reviewer at 8cbaf93): 0 critical, 2 high, 4 medium, 4 low. All fixed in bd114c7 and the follow-up, with tests in tests/test_hardening.py
- H1 x264 bytes depend on CPU count → `-threads 1`, clips regenerated (test_fixtures_clips passes under `taskset -c 0`)
- H2 cancel during backoff wedged the breaker → `_run` frees the trial on any exit (test_cancel_during_backoff_frees_the_trial)
- M3 cancelled upload unrecorded → orphan entry under `asyncio.shield` (test_cancelled_upload_records_an_orphan)
- M4 cleanup through the breaker → `files:cleanup` calls skip it (test_cleanup_works_while_the_breaker_is_open)
- M5 store-less bodies passed the guard → `store` must be explicitly false; SAM opts out via `store_param` (test_guard_requires_an_explicit_store_false, test_sam_without_store_param_passes_the_guard)
- M6 probe f role calls missing → `--keyframes=<dir>` role-call probe, Spark vs Wonder at max (test_role_call_probe); the footage is in BLOCKED.md
- L7 naive datetimes, inf caps, unpriced models → AwareDatetime, allow_inf_nan=False, priced-model check (test_config_rejects_unsafe_values)
- L8 API notes wording on HTTP errors → corrected in docs/API-NOTES-WP0.md §13.4
- L9 brittle probe runner → per-probe `except Exception`, output_text errors caught, WAV unlinked in finally (test_probe_runner_survives_any_exception)
- L10 HTTPS_PROXY trusted, base_url unchecked in the client → `trust_env=False`, `trusted_base_url` in MetaClient (test_client_ignores_proxy_env, test_client_refuses_untrusted_base_urls)

## Code-review skill (medium) on origin/main...HEAD: 10 findings, all verified and fixed
cancelled or malformed-id upload (orphan entry, FILE_ID_PATTERN), streamed refusal billed at usage (test_streamed_refusal_is_billed_at_usage), non-transport httpx errors typed (test_non_transport_httpx_errors_are_typed), the count call off the breaker (test_best_effort_calls_ignore_the_breaker), dotted config params (test_dotted_params_are_config_errors), probe runner robustness, a late failure admitting a second trial (test_a_late_failure_does_not_admit_a_second_trial), WAV cleanup, the Files lock held across uploads (per-name locks; test_concurrent_uploads_are_all_recorded), one shared ensure_standard_model.

## Audit 3 (independent Sonnet reviewer at 2d81848): 0 critical, 2 high, 4 medium, 6 low. NOT CLEAN; all verified and handled
- H1 `trust_env=False` dropped the sandbox CA bundle and proxy, so no live call could connect here → reverted to httpx's default (a decision: operator infrastructure, not the geo-workaround AGENTS rule 7 bans; the key still only goes to the pinned host) (test_client_uses_the_operators_tls_and_proxy_settings)
- H2 PRE-A §3.8/§12 open-weight rows (added to PR #1 today) missing → implemented: safecut/open_weight.py, `provider`, `baseten_job`, `consented`, `open_weight`, `redteam_open`, `redteam_open` detector, the SAFECUT_OPEN_WEIGHT_* config (tests/test_open_weight.py)
- M3 ledger faults untyped → `_ledger` (to_thread + 10 s timeout → MetaUnavailable, no request sent); settle/release after a call log first and never lose the result (test_ledger_faults_are_typed_and_never_lose_a_call)
- M4 a 504 never opened the breaker → MetaUnavailable counts as a failure (test_504s_open_the_breaker)
- M5 cancel during orphan recovery → `_recover_or_record` shields an orphan entry (test_cancel_during_orphan_recovery_still_records)
- M6 probe h against §3.8 → rewritten: streamed, no response_format, max_tokens 16k, 4 frames, grid check, omit comparison (test_all_probes_replay, test_probe_h_grid_mapping)
- L7 probe h needed the Meta key → `_run_h` builds only the Baseten client (test_probe_h_runs_without_the_meta_key)
- L8 plain `uv run pytest` ran live tests → `-m 'not live'` in addopts
- L9 CUDA torch in the audit group → not a defect: PRE-A §12's documented deviation (EgoBlur 2.0.1 pins torch==2.9.1; the CPU index can't use the Modal GPU)
- L10 config hygiene → codes are SecretStr, service keys ≥ 16 chars, strict booleans, case-insensitive Contributor check, ASR request guard (test_config_hygiene, test_asr_request_refuses_contributor_models)
- L11 3xx treated as success → MetaConfigError (test_redirects_are_never_success)
- L12 the speech-fallback pair was missing from the startup probe set → `Settings.speech_fallback_pair()` (non-fatal by spec)

## Audit 4 (independent Sonnet reviewer at 421d112): 0 critical, 1 high, 5 medium, 7 low. NOT CLEAN; all verified and fixed
- H1 the open-weight estimate counted base64 images as text (≥ 8 frames could never fit $0.50) → `_parts` counts image_url parts as images (test_image_data_urls_are_not_counted_as_text, test_fifty_frames_fit_the_default_cap)
- M2 probe h didn't use redteam.md's prompt or schema → `open_weight.REDTEAM_*`, `RedteamAnswer`, `complete_answer` (missing frames fail; duplicates merged; unsent dropped) (test_complete_answer_rules, test_redteam_messages_bounds)
- M3 probe h reported "not run" as "failed", and its cap accumulated across runs → `grid_ok: null` plus `error` unless 3 tries answered; a per-run job id (test_probe_h_reports_not_run_honestly)
- M4 `stream()` treated 3xx as eof → `_status_failure` maps redirects to MetaConfigError on every path (test_stream_redirects_are_config_errors)
- M5 settle/release blocked the event loop → `_ledger_after` runs off the loop with a 10 s bound (test_settle_runs_off_the_event_loop)
- M6 keys could cross providers → each provider's base URL is pinned to its own host (test_keys_never_cross_providers)
- L7 cancel during reserve leaked the reservation → `_reserve` shields it and releases a late reserve (test_cancel_during_reserve_releases_it)
- L8 reserve wasn't retried once → `_ledger` retries a raising call once; a timeout isn't retried, because the call may still land (test_reserve_is_retried_once)
- L9 weak new contract fields → StrictBool consented, OpenWeightSummary consistency, redteam_open needs status ok, validate_job_dir checks redteam/redteam_open frames and boxes (test_open_weight_contract_rules)
- L10 the privacy gate was advisory → `open_weight.second_opinion` enforces `enabled_for`; `create` is transport-level (probe h, synthetic only) (test_second_opinion_enforces_the_privacy_gate)
- L11 `probes.py a h` died without the Meta key → per-probe client construction inside the try (test_probes_without_the_meta_key_still_run_h)
- L12 probe h saved no raw answers → `h/baseten.answers.json`, plus a trim entry `fixtures/open_weight/live-probe-h.json`
- L13 doc mismatches → API notes row h, §13.2b worst case ($0.358; 50 frames reserve $0.163), §13.4 baseten_job, ARCHITECTURE detector; HANDOFF's open-findings list cleaned up

## Audit 5 (independent Sonnet reviewer at 44a24e5): 0 critical, 0 high, 4 medium, 10 low. NOT CLEAN; all verified and handled
I reproduced or confirmed each against the code and PRE-A (`origin/pre-a-research` 7f7ab67, which added the §12 rows below at 18:57 UTC, after WP0's last sync). Tests are in tests/test_audit5.py unless named.
- M1 a retried reserve after a lost ack raised a raw ValueError and left the reservation stuck → `LocalLedger.reserve` is idempotent on the same terms (§10.2), conflicting terms raise, and `_ledger` maps KeyError/ValueError to MetaUnavailable (test_a_retried_reserve_reuses_the_reservation, test_ledger_reserve_is_idempotent_only_on_the_same_terms, test_ledger_refusals_are_typed)
- M2 a cancel or fault between a 200 upload and its files.json record lost the file ID → the record runs to completion under a shield; a failed record deletes the copy by ID, else records an orphan (test_cancel_while_recording_an_upload_keeps_its_id, test_a_failed_record_deletes_the_upload_by_id, test_a_failed_record_and_delete_leave_an_orphan)
- M3 validate_job_dir missed ids, frames, boxes and receipt consistency → job_id = dir name; roles/plan/decisions/audit spots/receipt ids and bounds; receipt vs decisions, audit, files (files_deleted), responses and cost.jsonl; the example fixture's job_id fixed to `j_example` and the receipt re-sealed (tests/test_contracts.py, 30+ cases)
- M4 PRE-A §12 rows missing → `job.open_weight_attempted`, `receipt.cost_usd_baseten`, `data_handling.responses_delete_requested`, `responses.json` (ResponsesIndex, in JOB_FILES), `SAFECUT_SAM_DELETE_RESPONSES` (unset = on when SAM_SEND_STORE is false) and `sam.ResponseLog` (note before parsing, delete_pending after, 404 = done; SAM refuses to run without a log when deletion is on, before spending); ARCHITECTURE §3.1/§3.9/§3.12/§4 and .env.example (test_sam_responses_are_logged_and_deleted, test_sam_without_a_log_is_refused_before_spending, test_receipt_counts_match_responses_json, test_new_section_12_fields, test_sam_delete_responses_follows_send_store)
- L1 checklist claimed a stale break-it → the line now points at break-it.md's TESTED_COMMIT, which is rewritten at the final head
- L2 orphans could never be resolved → `FileStore.reconcile_orphans` (run by delete_all) lists /files, deletes unrecorded copies of the orphan's name under its upload lock, then sets deleted_at; `all_deleted` = every entry has deleted_at (test_cancelled_upload_records_an_orphan, test_reconcile_*)
- L3 SAFECUT_REPLAY not enforced at the transport → MetaClient refuses every call in replay mode before reserving (test_replay_mode_refuses_live_calls)
- L4 a cost.jsonl write fault after a billed call discarded the result → the write is logged on OSError and the ledger still settles (test_a_failed_cost_write_keeps_the_result_and_the_charge)
- L5 every 5xx but 504 was retried → only 429/500/502/503 (test_only_documented_5xx_are_retried, the fuzz property tightened). ASR 504/slow-5xx stays charged as estimated: a recorded decision, stricter than R14, now stated in API-NOTES-WP0 §13.4
- L6 effort argument could disagree with the body → `responses.create` refuses a mismatch before any call (test_effort_must_match_the_body)
- L7 Caller.daily froze its day bucket → `Caller.limits_at(now)` keys the daily cap per call (test_daily_caller_bucket)
- L8 hero-clip probe output in jobs/probes-hero → kept on purpose (consent covers processing, not publishing raw masks/transcripts); recorded in API-NOTES-WP0 and the checklist
- L9 path-like fields unconstrained → `RelPath` on job.prepared, roles.keyframes, receipt thumbnails; `SourceName` (no NUL, no `..`) on job.source (tests/test_contracts.py)
- L10 clip determinism compared container bytes against the committed files → run-to-run bytes plus decoded-frame MD5s against the committed clips (tests/test_fixtures_clips.py)
- Not acted on: `sam.image_body` passing an https URL to Meta (the auditor's "no action": it's Meta's fetch, and only WP code builds these bodies)

## Audit 6 (independent Sonnet reviewer at 8cc543c): 0 critical, 1 high, 3 medium, 5 low. NOT CLEAN; all verified and handled
I verified each finding against PRE-A (origin/pre-a-research 7f7ab67, §3.8, §10.4, §12) and the code. Tests are in tests/test_audit6.py, tests/test_open_weight.py and tests/test_contracts.py.
- H1 open weights sent ≤ 50 images per call; §3.8 says ≤ 8 (Baseten "Max images per request 8"), ⌈N/8⌉ calls ≤ 4 in parallel, all or nothing, and probe h must send an 8- and a 9-image call. Fixed: `MAX_IMAGES = 8`. `second_opinion` batches, preflights the whole set's estimate against the cap (`MetaClient.preflight`: reserve then release, a `budget:` line on a stop) and fails whole on any batch failure. Probe h adds the 8/9-image calls and `image_limit_holds`. (test_a_frame_set_is_split_into_calls_of_at_most_8, test_a_frame_set_over_the_cap_is_skipped_whole, test_one_failed_batch_fails_the_whole_opinion, test_all_probes_replay)
- M2 Baseten calls retried 4×; §3.8 says "no transport retry". Fixed: attempts=1 (test_stream_without_finish_fails_without_a_retry)
- M3 SAM response IDs were lost on incomplete, retried and cancelled calls. Fixed: `MetaClient.stream(on_response_id=…)` reports each attempt's ID from the first event that carries it (`response.created`), and `ResponseLog.note` is synchronous (test_an_incomplete_sam_response_is_still_logged, test_a_retried_sam_attempt_logs_both_responses, test_a_cancelled_sam_stream_is_still_logged)
- M4 an empty-body 404 (wrong path) on a response DELETE counted as done. Fixed: only a 404 with an error body counts (test_an_empty_404_on_a_response_delete_is_a_failure)
- L5 receipt cross-checks were weak. Fixed: items are compared field by field (all but thumbnail); `cost_usd_baseten` is checked against Baseten lines; another job's or a system line in a job's cost.jsonl is rejected; the example gets a coherent cost.jsonl (receipt cost_usd now $0.031848, re-sealed). Kept as decisions: evidence files stay "checked when present" (ARCHITECTURE §3), and `leaks_patched` stays unchecked because no doc defines it (distinct patch items vs patched leaks)
- L6 negative usage crashed `_log_cost` with a raw ValidationError. Fixed: `chat_units` treats a negative or non-int count as unknown, and `_log_cost` also survives an invalid line (test_negative_usage_is_unknown_not_a_crash)
- L7 a server echoing our key put it in error text. Fixed: `MetaClient._scrub` masks the key in every error body before classifying (test_our_key_is_masked_in_server_error_text)
- L8 the §3.8 gate trusted a code_kind argument. Fixed: `second_opinion` takes it from `client.caller.code_kind` (test_second_opinion_enforces_the_privacy_gate)
- L9 the effort check was one-sided. Fixed: a body without reasoning needs effort="omit" (test_effort_without_reasoning_must_be_omit)
- Test gaps noted: a client call across midnight (`limits_at` is per call, covered by test_daily_caller_bucket plus `_limits` calling `now_utc()`), and cancellation in the chaos test (covered by the cancel tests in test_meta_client/test_hardening/test_audit5/test_audit6). Not acted on further.

## Audits 7 and 8 (two independent Sonnet reviewers in parallel at 2568819): 0 critical, 0 high, 1 medium, 8 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit7.py unless named.
- A8-M1 httpx `aiter_lines` splits on U+2028/U+2029/U+0085. Verified: `LineDecoder` cut `data: {"t":"a b"}` in two, so a Muse answer containing one failed every attempt and was charged each time. Fixed: `sse.aiter_sse_lines` reads bytes, splits only on `\r\n`/`\r`/`\n` (holding a trailing `\r` across chunks), decodes UTF-8 incrementally, and is used by both streams (test_unicode_line_separators_stay_inside_an_event ×3, test_line_endings_split_across_chunks, test_a_stream_with_u2028_in_the_answer_completes_once)
- A8-L2 settle/release could be cancelled while queued, leaving the reservation open against cost.jsonl. Fixed: `_ledger_after` is shielded, the same pattern as `_reserve` (test_a_cancel_never_skips_the_ledger_settle)
- A8-L3 any success cleared the breaker's failure window, so R6's "5 failed calls within 60 s" became "5 in a row". Fixed: a success closes an open or half-open breaker and changes nothing while closed (test_the_breaker_counts_failures_in_60_s_not_in_a_row)
- A8-L4 / A7-L4 stale claims: ARCHITECTURE §3.12, the probe h cost in the API-NOTES table and BLOCKED.md ($0.53 reserved worst case), fixtures/README "byte for byte", and the HANDOFF and checklist fresh-clone line. All updated; break-it is rewritten at the final head
- A8-L5 WP0's SA-Co fallback clips not mentioned → BLOCKED.md says why they weren't fetched (b and d need the key anyway; synthetic clips carry exact truth)
- A7-L1 a failing `ResponseLog.note` aborted a paid SAM stream. Fixed: `note` never raises (an unwritable ID stays in memory and `delete_pending` still deletes and counts it), and a corrupt responses.json is refused before any spend (test_a_corrupt_response_log_is_refused_before_spending, test_an_unwritable_response_log_keeps_the_result_and_the_id)
- A7-L2 a server-supplied response ID went unvalidated into the DELETE path (`resp_1/../../files/file-abc`). Fixed: `RESPONSE_ID_PATTERN` `^[A-Za-z0-9_-]{1,128}$` on note and on `ResponseEntry` (test_response_ids_must_be_plain_tokens ×5)
- A7-L3 open-weight parallelism was really 3 (the Responses lane). Fixed: a Baseten client's lane is `config.BASETEN_INFLIGHT` = 4 = `open_weight.MAX_PARALLEL` (test_four_open_weight_batches_run_at_once)
- A8 note: reaudit.md quoted two tests that no longer exist (`test_client_ignores_proxy_env`, removed by the audit 3 H1 revert; `test_fifty_frames_fit_the_default_cap`, replaced in audit 6 by test_a_frame_set_is_split_into_calls_of_at_most_8 / test_a_frame_set_over_the_cap_is_skipped_whole). Recorded here; the historical entries stay as written

## Audits 9 and 10 (two independent Sonnet reviewers in parallel at 5bba04c): 0 critical, 0 high, 4 medium, 10 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit9.py and tests/test_audit10.py unless named.
- A9-M1 `aiter_sse_lines` re-scanned the carried buffer on every chunk (quadratic: 8 MB took ~7 s). Fixed: `_LineSplitter` scans each text once (test_a_multi_megabyte_line_splits_in_linear_time). The new hypothesis property against a reference splitter then caught a real edge (`\r`, `\n`, `\n` in 1-byte chunks swallowed a line), also fixed (test_splitting_matches_the_reference_for_any_chunking)
- A9-M2 PRE-A §12 dependency rows missing. Verified (PRE-A lines 710, 737, 741). Fixed: `matplotlib`; the audit group is `egoblur==2.0.1`, `torch==2.9.1`, `torchvision==0.24.1`, `vrs==1.2.2`; deploy is `modal==1.6.2`; re-locked. EgoBlur caps opencv below 5, so the lock moved opencv-python-headless 5.0.0.93 → 4.14.0.94, which changes the counter-text pixels: the synthetic clips are regenerated (truth.json byte-identical; bytes identical on 1 and 4 CPUs)
- A9-M3 probe b couldn't run with `SAFECUT_SAM_SEND_STORE=false` (no ResponseLog) and never recorded the SAM DELETE behaviour. Fixed: probe b passes a log, deletes after parsing, and adds `delete_without_store` (a store-less call, its IDs, the delete, and a repeat delete expecting 404) (test_probe_b_runs_without_store_and_deletes, test_all_probes_replay)
- A9-L4 a late non-trial success closed an open breaker. Fixed: only the half-open trial (or a success while half-open) closes it (test_a_late_success_never_closes_an_open_breaker)
- A9-L5 `delete_pending` lost in-memory IDs when responses.json was unreadable and undercounted across calls. Fixed: unreadable reads fall back to in-memory IDs, and requested-but-unrecorded IDs are a cumulative set, never re-requested (test_an_unreadable_log_still_deletes_in_memory_ids_and_counts_once)
- A9-L6 refused (non-token) response IDs vanished. Fixed: kept in `ResponseLog.refused`, logged at error, reported by probe b (test_refused_ids_stay_visible)
- A9-L7 the shield test didn't exercise the shield. Fixed: the executor is saturated so the settle is still queued when cancelled (test_the_settle_runs_even_when_cancelled_while_queued)
- A9-L8 / A10-L6 stale claims: break-it, the PR body, ARCHITECTURE `/healthz` ("1-token" → `max_output_tokens: 16`, PRE-A §12 line 744), fixtures/README's live-twin claim. All corrected. **Decision recorded:** PRE-A §12 (line 739) wants the synthetic clips generated by a pytest fixture and never committed. They stay committed (two files under 64 KB) because the probe CLI and `trim.py` run outside pytest and need them at a stable path. `test_generator_is_deterministic` regenerates them on every run and checks run-to-run bytes plus decoded frames against the committed files, so a committed clip can't drift from its generator.
- A10-M1 orphan recovery stopped at the first failed delete and never recorded later copies, so `files_deleted` could be claimed over a live upload. Fixed: every found copy is recorded before any delete, and every delete is tried; the same applies in `reconcile_orphans` (test_a_failed_orphan_delete_never_leaves_a_later_copy_unrecorded)
- A10-L2 unchecked cross-file pointers. Fixed: `matches_participant` against scene participants, `introduced_in_turn` against transcript turns, and leak `patched_item`/`through_item`, spot `covered_by` and red-team `excluded_by` against decisions items (test_cross_file_pointers_must_resolve ×4)
- A10-L3 the example plan didn't cover its hidden items. Fixed: the plan is densified over every hidden item's span (old entries reproduced exactly), and `validate_job_dir` now requires a plan entry for every hide/needs_you item on every frame of its span (test_every_hidden_item_is_planned_on_every_frame_of_its_span)
- A10-L4 the open-weight failure rule was all-or-nothing; redteam.md says per batch. Verified (redteam.md "Second opinion → Failure"). Fixed: `second_opinion` returns a `SecondOpinion` (finished batches' frames, `failed_batches`, `status`, `summary()`), and `OpenWeightSummary` allows `failed` with findings. All-or-nothing now applies only to the budget preflight, as §3.8 says. `status: failed` still names its model (it ran), a recorded decision (test_a_failed_batch_leaves_the_others_their_findings)
- A10-L5 contracts accepted NaN, infinity and negative times. Fixed: `allow_inf_nan=False` on every contract, and `times` ≥ 0 (test_times_must_be_finite_and_non_negative, test_cost_lines_refuse_nan)

## Audit 11 (independent Sonnet reviewer at 5c72c49): 0 critical, 0 high, 1 medium, 3 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit11.py unless named.
- M1 `Audit._gate` rejected `redteam_open` entries unless the opinion was `ok`, contradicting the audit #10 per-batch fix (a failed opinion keeps its finished batches' findings, redteam.md). Fixed: only `status: off` forbids entries and leaks (test_a_failed_opinion_keeps_its_entries, test_an_opinion_that_never_ran_has_no_entries)
- L2 probe b left SAM responses undeleted: the fps-hint call came after `delete_pending`, and failure paths skipped deletion; the replay mock's constant id hid it. Fixed: probe b deletes in a `finally` after every call, `_sam_delete_check` deletes on its failure path too, and the replay server mints a unique id per call so the test asserts created == deleted (test_probe_b_runs_without_store_and_deletes)
- L3 a malformed box (a float, 3 numbers, a string) or an omitted `text` failed the whole open-weight batch; redteam.md "Validation" keeps the finding with a whole-frame box. Fixed: `RedteamFinding.box` is a 4-int tuple or `None` (= the whole frame, fail closed), and `text` defaults to null (test_a_malformed_box_is_a_whole_frame_finding ×5)
- L4 stale wording: the breaker docstring and API-NOTES now say "a success while half-open (the trial's) closes it", matching the code and decision A9-L4; the checklist's package count (now 117, all groups) is updated; break-it is rewritten at the final head before the gate

## Audit 12 (independent Sonnet reviewer at 2012ed0): 0 critical, 0 high, 2 medium, 3 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit12.py unless named.
- M1 the publish gate was fail-open: `unresolved` wasn't tied to the leaks (PRE-A §12 row 643: "each unresolved row counts 1 in `unresolved`"). Verified with the auditor's repros. Fixed:
  - `Audit` requires `unresolved` ≥ the unresolved leaks;
  - every leak is patched, flagged through an item, or unresolved;
  - `open_weight.frames`/`findings` equal the `redteam_open` entries;
  - `_check_patches` requires a leak's patch to be a non-kept item whose `first..last` (when set) holds the leak's frame;
  - `ReceiptAudit` requires a publishable audit (unresolved 0, no blocked_reason).
  (test_an_unresolved_leak_must_be_counted, test_a_leak_is_patched_flagged_or_unresolved, test_open_weight_counts_match_its_entries, test_a_receipt_needs_a_publishable_audit, test_a_patch_must_hide_the_leak_frame ×2)
- M2 a reserve failure after an accepted attempt lost `maybe_processed`, so `FileStore` neither listed nor recorded an orphan, and `files_deleted` could be claimed over a live upload. Fixed: `_attempts` stamps the attempt history's `maybe_processed` on any MetaError from `_reserve` (test_a_ledger_fault_after_an_accepted_upload_still_finds_the_copy)
- L3 a finding with no `box` key still failed its batch. Fixed: `box` defaults to `None` (= the whole frame) (test_a_missing_box_is_a_whole_frame_finding)
- L4 API-NOTES §13.2b still said one failed batch fails the opinion. Rewritten: the budget is all-or-nothing, failure is per batch, and a malformed or missing box means the whole frame
- L5 probe b's failure-path deletion had no test. Added: SAM attempts that fail after `response.created` are retried, and every created response, failed or not, is deleted (test_probe_b_deletes_sam_responses_on_failure_paths)
- Also: `test_settle_runs_off_the_event_loop` flaked under a parallel soak (it asserted ≥ 10 loop ticks in a 0.3 s settle). A blocked loop gives ~0 and a free one ~30, so the bound is now 5. The property still fails a blocking settle; it was made robust, not weakened

## Audit 13 (independent Sonnet reviewer at 2012ed0, parallel to #12): 0 critical, 0 high, 5 medium, 3 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit13.py unless named.
- M1 a second cancellation during cleanup (`await task` inside the CancelledError handler) cancelled the shielded ledger task, stranding a release or a landed reservation, so ledger != Σ cost.jsonl. Fixed: `client.outlive_cancel` waits with `asyncio.wait` through any number of cancellations; used by `_reserve`, `_ledger_after` and `files._finish` (test_a_second_cancel_never_strands_the_release)
- M2 attempts reserved before taking their lane and process slots, so queued calls held budget and triggered false `BudgetExceeded`. Fixed: an attempt reserves inside `async with lane, inflight`; backoff sleeps happen outside it; a call cancelled while queued now reserves and logs nothing (test_queued_calls_hold_no_budget; test_cancel_before_send_releases_and_after_send_charges updated)
- M3 `delete_pending` could DELETE a response another SAM stream of the job was still reading. Fixed: `ResponseLog.begin`/`ended` track open streams, and `delete_pending` skips them until their stream ends however it ends (test_an_open_sam_stream_is_never_deleted)
- M4 maybe_processed lost on a reserve fault: already fixed in ed2ddae (audit #12 M2)
- M5 free calls (file and response deletes, listings, token counts) went through the ledger, so cleanup failed while it was down. Fixed: a zero estimate never reserves or settles; the usd-0 cost line is still written (test_cleanup_works_while_the_ledger_is_down)
- L6 a finding with no box failed its batch: already fixed in ed2ddae
- L7 docs:
  - probe b's cost is now 6 SAM calls ($0.11);
  - the breaker sentence says an exhausted 429 counts;
  - WP0 probe c's "max length" wasn't measured. Fixed: probe c generates 60 s and 180 s test-pattern clips and records acceptance and billed input tokens (test_probe_c_length_clips_have_the_asked_length, test_all_probes_replay);
  - the modelled worst case is ≤ $2.29
- L8 probe spend split across two cost files. Fixed: every probe run, hero runs included, writes to `fixtures/probes/cost.jsonl`
- Caution taken: ed2ddae's `ReceiptAudit` rule (a receipt only for a publishable audit) contradicted PRE-A §10.3 (the receipt stage runs after [Run the audit again] on a blocked audit too). Reverted, with a test that a receipt may carry a blocked audit (test_a_receipt_may_record_a_blocked_audit); publishing stays gated on `unresolved == 0`

## Audit 14 (independent Sonnet reviewer at a77fb92): 0 critical, 0 high, 2 medium, 3 low. NOT CLEAN; all verified and handled
The auditor also ran a 600-seed concurrent stress harness (2–12 streams, random outcomes, double cancels): ledger == Σ cost.jsonl every time, no open reservations. Tests are in tests/test_audit14.py unless named.
- M1 `Audit._gate` accepted a leak with a `through_item` but no `flag` (neither patched, flagged nor unresolved), because ed2ddae tested `through_item` where it meant `flag`. Fixed: the gate tests `flag`, and `Leak` requires `through_item` exactly when flagged (test_a_through_item_needs_a_flag)
- M2 a failure in probe c's new max-length check (a 413 on the 180 s upload, an ffmpeg error) replaced the whole probe c result, including the paid frame answer. Fixed: the clip build, upload and call are one try returning `{"accepted": false, "error"}`, and a null `usage` is handled (test_a_failed_long_clip_keeps_probe_c_frame_answer)
- L3 a multipart factory that failed (a missing file) was charged as a sent request. Fixed: the body is built before `mark_sent` (test_a_failing_multipart_factory_is_never_charged)
- L4 the audit #12 M2 test had gone vacuous: uploads are free calls since audit #13 and never reserve. Rewritten on a paid call: attempt 1 times out after sending, attempt 2's reserve fails, and the error is `maybe_processed` (test_a_ledger_fault_after_an_accepted_attempt_keeps_maybe_processed)
- L5 stale status: the checklist line for audits #11–#12 now notes the reverted receipt rule; the PR body, break-it and the reaudit header are rewritten at the final head before the gate

## Audit 15 (independent Sonnet reviewer at a77fb92, parallel to #14): 0 critical, 0 high, 0 medium, 2 low. NOT CLEAN; both verified and fixed
The auditor ran ~750 seeds of two clients sharing a ledger, with random outcomes, 1–3 cancels per task and forced half-open breaker trials: ledger == Σ cost.jsonl every time, no open reservation, no stuck trial. A further 600 upload-chaos seeds left no unrecorded copy outside finding 1.
- L1 a copy could escape `files_deleted`: a fast 5xx after the server stored the file never triggered a listing, and a timeout's copy could land after the one immediate listing. This is a gap in PRE-A §10.4 rather than a deviation. Fixed: any failed upload (all but a `BreakerOpen` refusal, now its own error type), and any upload that succeeded after a failed attempt, recovers what the listing shows and then always records an orphan, so `delete_all` re-lists at the segment's end before `files_deleted` can be true. ARCHITECTURE §3.11 is updated (tests/test_audit15.py: test_a_copy_left_by_a_fast_5xx_is_deleted, test_a_copy_that_lands_after_the_listing_is_found_at_the_end; three older tests now also expect the orphan entry and a clean `delete_all`)
- L2 tests/test_live.py built its status client with `trust_env=False`, which drops the operator proxy and CA bundle (audit #3 H1), so the first `-m live` run would fail on `/status`. Fixed: the default `trust_env`

## Audits 16 and 17 (two independent Sonnet reviewers in parallel at 2ca6ba8): 0 critical, 0 high, 2 medium, 7 low. NOT CLEAN; all verified and handled
Both auditors also ran their own concurrent stress harnesses (150 and 300 seeds: shared ledger and breaker, random 5xx/429/504/eof/timeout/connect failures, single and double cancels). In every seed ledger == Σ cost.jsonl, no reservation stayed open, and no trial slot or semaphore leaked. Tests are in tests/test_audit16.py unless named.
- A16-M1 the audit gate let a flag alone resolve a leak, and checked `through_item` (and a non-audit `patched_item`) only for existence. Verified with the auditor's three accepted-but-leaking repros. Fixed: every leak is patched or unresolved (a flagged leak names the item re-rendered as its patch), and `_check_patches` requires both `patched_item` and `through_item` to be hidden items whose span holds the leak's frame (an audit patch's first..last, else its tracks' first..last) (test_patches_and_through_items_must_cover_the_leak ×3, test_a_flagged_leak_without_a_patch_is_refused; test_a_through_item_needs_a_flag updated)
- A17-M1 `httpx.ProxyError` (an egress proxy refusing CONNECT) and `UnsupportedProtocol` never reach Meta but were billed as accepted, with estimates kept on every retry. Fixed: both count as never sent (test_a_proxy_refusal_is_never_billed)
- A17-L1 probes b and f lost paid results on a non-Meta error (a parser error, a missing keyframe, a null `usage`). Fixed: per-concept and per-role-call errors are recorded in place, probe f's role calls can't cost its video answers, and `_usage` handles null (test_a_parser_error_on_one_concept_keeps_the_others)
- A17-L2 probe a aborted on a status-page outage before checking the key and models. Fixed: `status_error` is recorded, and `/models` always runs (test_probe_a_survives_a_status_outage)
- A17-L3 `--clip` moved every probe's output into the git-ignored hero folder. Fixed: only b and d go to `hero_root` (test_a_hero_clip_moves_only_b_and_d)
- A16-L2 probe c's length check reported any failure as "Meta refused this length". Fixed: `accepted: false` only for a Meta 4xx about the clip, and `null` (not measured) for budget, outage or local failures (test_an_outage_during_the_length_check_is_not_measured; the audit #14 test now expects `null`)
- A17-L4 "about $0.05 measured" for probe h was modelled, not measured. Reworded in API-NOTES and BLOCKED.md: ≈ $0.06 modelled, unmeasured
- A16-L3 WP0's "CI green on the PR" was unmet without a line saying so. Added as `- [P]` in the checklist; BLOCKED.md already lists the runner block
- A17-L5 the first-commit time is corrected to 16:20:07 UTC. The status files (break-it, the reaudit header, the PR body) are rewritten at the final head

## Audit 18 (independent Sonnet reviewer at ee0fc9a): 0 critical, 0 high, 2 medium, 4 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit18.py unless named.
- M1 `reconcile_orphans` stopped at the first name whose listing or delete failed, stranding later names' copies (unrecorded, so the sweeper couldn't find them either). Fixed: each name is reconciled on its own, and the first failure is raised after all of them (test_one_names_failed_reconcile_never_strands_the_next)
- M2 the publish gate let a red-team hit vanish: a `redteam` hit with no `excluded_by` and no leak on its frame validated as publishable (redteam.md: every hit is a leak unless the kept-clear rule excluded it). Fixed: `Audit` requires a leak on each non-excluded `redteam` hit's frame; `redteam_open` stays advisory until the grid check (test_a_red_team_hit_needs_a_leak_or_an_exclusion; tests that swap the example's leaks now drop its hit)
- L3 when an upload succeeded after a failed attempt but its record failed (not a cancel), the earlier copy went unrecorded. Fixed: any failure of `_keep` after an earlier failed attempt records an orphan (test_an_earlier_copy_survives_a_failed_record)
- L4 `_video_question` crashed on a non-object JSON answer or a non-integer frame, losing the probe's other paid results. Fixed: `_json_object` and a tolerant `frame_error` keep the row (test_a_non_object_answer_keeps_probe_c_running)
- L5 probe c's `accepted: false` also covered misconfiguration (`MetaConfigError`). Now only a `MetaBadRequest` about the clip is "refused"; everything else is `null`
- L6 spots: `first` wasn't bounds-checked, `first <= last` and boxes inside `first..last` weren't required, and `covered_by` was existence-only. Fixed in `Spot` and `_check_patches` (test_a_spot_is_consistent ×2, test_a_spot_cover_must_hide_its_frames)
- Docs: ARCHITECTURE §3 "Types and rules" now states the audit rules (patch or unresolved, flag and through_item, spans, red-team hits, open-weight counts, spots), so they no longer live only in Python (AGENTS rule 3)

## Audit 19 (independent Sonnet reviewer at ee0fc9a, parallel to #18): 0 critical, 0 high, 2 medium, 4 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit19.py unless named.
- F1 (medium) the span checks used a track item's tracks' first..last, but the guard also renders an item over its extend/backfill frames, where a flagged leak names it (PRE-A §12 row 642). Valid patches and through_items there were refused. Separately, an item merging time-disjoint tracks could never validate its plan. Fixed: a patch, through_item or spot cover must hide the frame, meaning the item exists there or the plan renders it there. Plan coverage requires entries only where some member track (or an audit patch) is present (test_a_patch_on_an_extend_frame_validates, test_a_merged_item_needs_no_entry_in_its_tracks_gap)
- F2 (medium) at the PRE-A defaults (16,000 `max_tokens`, $0.50 cap) a typical 64-frame clip's second opinion is skipped as over the cap. **Decision:** this is §3.8's prescribed behaviour (skip, never run partially). The consequence is now stated in API-NOTES §13.2b: ≤ 40 frames run, and probe h's measured output lets §3.8 lower `max_tokens` (at ~6,000, 64 frames reserve $0.33). No code change before probe h measures
- F3 (low-medium, privacy) `create_json`'s error quoted the model output via the ValidationError text. Fixed: only the error count (test_invalid_model_output_never_reaches_the_error_text)
- F4 (low) a failed cost write turned a budget stop into a raw OSError. Fixed: `_log_budget_stop` logs the write failure, and the `BudgetExceeded` stands (test_a_budget_stop_survives_a_failed_cost_write)
- F5 (low) the $6 probe cap lived in a git-ignored SQLite file, so a new container started at $0. Fixed: `seeded_ledger` starts every run from the committed `fixtures/probes/cost.jsonl` spend, and refuses to start once it is spent (test_the_probe_cap_counts_earlier_runs)
- F6 (low) stale status files: rewritten at the final head before the gate (break-it at ee0fc9a is already current for the soak; the reaudit header and PR body come with the gate run)

## Audits 20 and 21 (two independent Sonnet reviewers in parallel at 44316ee): 0 critical, 0 high, 5 medium, 9 low, 1 process. NOT CLEAN; all verified and handled
Tests are in tests/test_audit20.py and tests/test_audit21.py unless named.
- A20-M1 / A21-M1 `excluded_by` accepted any item id, so a hide item could "exclude" a red-team hit and the hit vanished. Fixed: an exclusion must be a kept item present on the hit's frame, for `redteam` and `redteam_open` (test_only_a_kept_item_can_exclude_a_hit ×3)
- A20-M2 a red-team hit counted as covered by any leak on its frame, even an unrelated one. Fixed: a non-excluded hit needs a leak whose box overlaps its own on that frame (positive-area intersection, redteam.md's "on") (test_a_hit_needs_a_leak_on_its_own_box)
- A20-M3 / A21-M1 patches were checked by frame only, so a patch somewhere else on the frame "fixed" a leak. Fixed: an audit patch's box must contain the leak's box; a track item's planned box on that frame must overlap it. The same applies to spot covers on every frame with a box. A spot's cover must also hide all of `first..last` (test_a_patch_must_cover_the_leak_box, test_a_spot_cover_must_hide_all_its_frames; A20-L4, the missing spot test)
- A21-M2 a key with a pasted newline made h11 refuse the request (`LocalProtocolError`) before sending, and every attempt was billed as accepted. Fixed: keys are stripped at load, inner whitespace or non-ASCII is refused (never echoed), and `LocalProtocolError` counts as never sent (test_a_pasted_newline_is_stripped_and_bad_keys_are_refused, test_a_request_h11_refuses_to_write_is_never_billed)
- A20-L5 ARCHITECTURE §3's rules sentence was stale. Rewritten with the region rules, the exclusion rule and plan coverage
- A20-L6 a damaged `fixtures/probes/cost.jsonl` crashed the probe start-up. Now it prints why and exits 2; the in-memory ledger means one probe process at a time, noted in the code (test_a_damaged_cost_record_stops_the_probes_cleanly)
- A20-L7 refusal text (model output) went into exception messages. Fixed: `MetaRefusal.of` keeps the text on `refusal_text`, never in the message (test_a_refusal_never_carries_the_model_text; test_streamed_refusal_is_billed_at_usage updated)
- A21-L1 a disk fault in the delete sweep (writing files.json) abandoned the remaining deletes, and the probe runner's `finally` let it escape. Fixed: sweep steps catch Meta, OS and contract errors and re-raise the first after the rest; the runner catches them too (test_a_disk_fault_never_stops_the_delete_sweep)
- A21-L2 a second hero clip overwrote the first's paid results. Fixed: each hero clip gets `hero_root/<clip stem>/` (test_a_hero_clip_moves_only_b_and_d updated)
- A21-L3 receipt `leaks_patched` was unchecked. It now equals the leaks with a `patched_item` (test_receipt_leaks_patched_matches_the_audit)
- A21-L4 `SAFECUT_SAM_SEND_STORE=false` with `SAFECUT_SAM_DELETE_RESPONSES=false` silently kept SAM responses stored forever. That combination is now refused at load (test_sam_delete_responses_follows_send_store updated)
- A21-L5 probe g never exercised clamping. It now also points at a dot in the bottom-right corner and records `edge` (test_probe_g_also_points_at_an_edge)
- A21-P1 stale status: the reaudit header, break-it and the PR body are rewritten at the final head before the gate. The PR body's `FileStore.live` becomes `FileStore.index().live()`, and the files WP0 adds beyond its list (.gitignore, docs/OFFICIAL-GUIDE.md, scripts/make_synthetic_clips.py, scripts/__init__.py, typings/) are listed there

## Audit 22 (independent Sonnet reviewer at 3bbc186): 0 critical, 0 high, 1 medium, 2 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit20.py (the "valid side" section) unless named.
- M1 the new containment rule refused valid writer output. A flagged leak, or a `through_item`, at the edge of an earlier audit patch is valid: PRE-A §12's `through_item` is the hidden item whose planned region touches the finding (any positive overlap). The rule demanded the leak box sit inside the patch's raw box. Fixed: containment applies only to an unflagged leak's own audit patch, and to a spot's cover (cover_spot's patch is the union of the spot's boxes). Flags and through_items need any overlap with the item's planned (padded) region or its own box (test_a_flagged_leak_on_an_audit_patch_edge_validates ×2)
- L2 the region rules had no tests for their valid side. Added: a partly overlapping track `through_item`, a kept item present on the frame excluding a hit, and a kept item absent on the frame refused for `redteam` and `redteam_open` (test_a_partly_overlapping_track_item_validates_as_through_item, test_a_kept_item_present_on_the_frame_excludes_a_hit, test_a_kept_item_absent_on_the_frame_cannot_exclude ×2)
- L3 docs updated:
  - probe g's two calls (≤ $0.14), the modelled total (≤ $2.36) and the per-clip hero folders, in API-NOTES and the checklist;
  - ARCHITECTURE §4 and .env.example: the key validation at load and the refused SAM store/delete combination, a deliberate tightening of PRE-A's plain bool;
  - the ARCHITECTURE §3 rules sentence: containment vs overlap

## Audit 23 (independent Sonnet reviewer at 3bbc186, finished at 8797774): 0 critical, 0 high, 2 medium, 3 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit23.py unless named. It also reported audit #22's M1 and probe g's cost row, already fixed in 8797774.
- M1 `excluded_by` accepted any kept item present on the frame. redteam.md "Leak decision" also requires the finding to overlap the item's visible region and its kind to match the track concept (face→`face`, person→`person`, text/screen→any other concept, plate→`license plate`; `misaligned_redaction` and `other` are never excluded). Fixed: the gate refuses an exclusion with no matching-concept track of the item on that frame, or whose track box there doesn't overlap the finding. It checks positive overlap, not IoU > 0.3, because the visible region lies inside the track box, so the box IoU can be lower than WP4's region IoU; demanding it would refuse valid output (test_an_exclusion_needs_the_items_concept_and_box ×5, test_a_matching_overlapping_exclusion_validates; test_audit20's valid exclusion is now a face on face:1's box)
- M2 nothing tied `frames_scanned`/`passes` to the job, so an audit that scanned nothing was publishable. Fixed per PRE-A §12 and vector L10: `frames_scanned ≤ job.frames`, every unscanned frame counts in `unresolved`, and a publishable audit ran at least one pass (test_an_audit_accounts_for_every_frame ×3, test_an_unscanned_audit_that_blocks_publishing_validates)
- L3 a late non-trial success closed a half-open breaker, and the trial's later failure then didn't reopen it. Fixed: only the trial's success closes it, as API-NOTES-WP0 says (test_a_late_success_never_closes_a_half_open_breaker)
- L4 `.gitignore` `jobs/` was unanchored, so `web/src/app/jobs/` would be ignored. Now `/jobs/` (PRE-A §12)
- L5 HANDOFF's state lines were stale (372/432 passed, audits #6–#11), and BLOCKED.md implied code reads `SAFECUT_CLIPS_URL`. HANDOFF is updated; BLOCKED.md now says the hero clips are a manual download passed with `--clip=<path>`. The reaudit and break-it headers are rewritten at the final head, as planned

## Audit 24 (independent Sonnet reviewer at 8797774): 0 critical, 0 high, 3 medium, 2 low. NOT CLEAN; all verified and handled
Tests are in tests/test_audit24.py unless named.
- M1 `excluded_by` accepted any kept item on the frame: the same defect as audit #23 M1, already fixed in 958f992
- M2 an unflagged leak counted as patched by a track item overlapping it by a sliver (i_3 over 6 px). redteam.md and PRE-A §12: every leak becomes a new `audit_patch` item; only a flagged leak may instead be fixed by re-rendering its `through_item` solid. Fixed: a non-audit-patch `patched_item` must be the leak's `through_item` (test_a_track_item_overlapping_a_sliver_never_patches_an_unflagged_leak, test_a_flagged_leak_may_name_another_item_only_as_its_through_item)
- M3 containment was judged against the patch's declared `box`, so a plan rendering [0,0,2,2] passed. Fixed: with a plan present, the boxes the plan renders on that frame are the region; the declared box is used only where no plan entry exists. The guard pads outward, so valid output is unaffected (test_containment_uses_the_rendered_box_not_the_declared_one)
- L4 API-NOTES §13.2b said ≤ 40 open-weight frames fit the $0.50 cap. With the code's own estimate, 46 frames reserve $0.498 and 47 reserve $0.500, which is refused. The docs and the PR now say 46 (computed with `open_weight._spec`)
- L5 the stale break-it and reaudit headers are rewritten at the final head, as planned

## Audit 25 (independent Sonnet reviewer at 8797774, reviewed through 958f992): 0 critical, 0 high, 0 medium open, 2 low. NOT CLEAN; both verified and fixed
It also reproduced audit #23 M2 at 8797774 and confirmed the fix at 958f992. Its 2,800-scenario cancel enumeration and its check of the #23 rules found no false refusal.
- L1 Files cost lines logged `units: {}`. PRE-A §10.5 says `{"bytes": n}`. Fixed: the upload's spec and meter carry its bytes, at $0 (tests/test_audit24.py::test_an_upload_cost_line_records_its_bytes)
- L2 `safecut/meta/sam.py` sits in WP1's owned paths ("stream parser"). Handled as AGENTS rule 2 says: PR #3's "Requests for other WPs" and HANDOFF now ask WP1 to extend `sam.py` (`ResponseLog`, `video_body`, `segment_video` with response deletion), never replace it

## Audit 26 (independent Sonnet reviewer at b99e529): 0 critical, 0 high, 1 medium, 4 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #26 section) unless named.
- M1 probe d's "raw" ASR fixture was the parsed model re-serialised, which dropped every field the parser ignores, and probe d exists to learn the real shape. Fixed: `asr.transcribe_raw` returns the body as sent and `asr.parse_response` parses it; `transcribe` is unchanged for WP2. Probe d saves the raw body (test_probe_d_saves_the_asr_body_as_sent). Probe h's `baseten.answers.json` holds the assembled streamed answers; the docs now say so rather than "raw"
- L2 the `unresolved` lower bound was a max, not a sum. PRE-A §12: each unresolved leak and each unscanned frame count 1. Fixed (test_unresolved_counts_leaks_and_unscanned_frames_together)
- L3 `tests/test_audit16.py`'s `# noqa: F811` had no reason, which the gate scan counts as unjustified. A reason is added; the same pattern in the new test has one
- L4 fixtures/README.md said the Muse fixtures have no live twin, but trim.py writes `muse/live-scene.events.json`. The README now lists it, notes that no test reads it yet, and says probe d's file is the raw body
- L5 the 21,600 s `expires_after` (WP0.md says 3,600) is now recorded as a deviation in API-NOTES §13.4, citing PRE-A §10.4. Also: the CI-duration wording ("within a few seconds") and `open_weight.py` in ARCHITECTURE §2's layout

## Audit 27 (at b99e529): stopped by the API session limit before reporting. Not counted

## Audit 28 (independent Sonnet reviewer at 81c73b2): 0 critical, 0 high, 0 medium, 1 low. NOT CLEAN; verified and fixed
It ran ~14 hand-built valid job directories through `validate_job_dir` (blocked and unscanned audits, cover_spot, flagged and through_item patches, merged EgoBlur patches, edge clamps, exclusions): all accepted, and every wrong-side case refused.
- L1 PRE-A §10.3 / vector R10 (a `file_not_found` re-uploads once and repeats the call; a second one is `MetaBadRequest`) had only `FileStore.reupload`, with no repeat and no test. Fixed: `FileStore.call_with_reupload(path, name, file_id, call)` does the once-only re-upload and repeat, and raises `MetaBadRequest` on the second `file_not_found`. The checklist's vector list now includes R10 (tests/test_audit24.py::test_r10_reuploads_once_then_fails_closed ×2)

## Audit 29 (independent Sonnet reviewer at 81c73b2): 0 critical, 0 high, 1 medium, 1 low. NOT CLEAN; both verified and fixed
Tests are in tests/test_audit24.py (the audit #29 section). It skipped audit #28's R10, already in the tree.
- M1 Files cleanup took "no evidence" as proof of deletion:
  - a `/files` listing without a `data` list, or a truncated page (`has_more`), matched nothing, so the orphan was marked resolved and `files_deleted` could be claimed over a live copy (PRE-A §10.4: an unusable listing keeps the receipt false);
  - a 2xx DELETE body was never read, so `{"deleted": false}` marked the file deleted.
  Fixed: the listing parser raises `MetaConfigError` on an unknown shape or `has_more: true`, and both callers then keep the orphan open. Every Files DELETE goes through `_delete_request`, which requires `deleted: true` (PRE-A §10.6). For SAM responses, whose DELETE body PRE-A leaves unspecified, only an explicit `deleted: false` keeps the id pending, since the receipt counts requests. Existing mocks now return the documented `{"deleted": true}` (test_a_listing_that_cant_rule_out_copies_keeps_the_orphan_open ×2, test_a_delete_without_deleted_true_leaves_the_entry_undeleted ×3, test_an_explicitly_refused_response_delete_stays_pending)
- L2 a ledger call that stalled past 10 s was never retried, but PRE-A §10.2 retries "a reserve that errors or gets no answer within 10 s" once. The recorded reason (a late first attempt would double the reservation) no longer holds: the retry reuses the `call_id`, and `reserve`, `settle` and `release` are idempotent per `call_id` (audit #5 M1). Fixed: a timeout takes the same one retry (test_a_stalled_ledger_call_is_retried_once, which also checks the late first attempt leaves the ledger equal to Σ cost.jsonl)

## Audit 31 (independent Sonnet reviewer at 32525dd): 0 critical, 0 high, 0 medium, 4 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #31 section).
- L1 a `/files` listing item with our job-unique name but a field the parser couldn't read (an ISO `created_at`, a string `bytes`) was silently skipped, so the orphan could be resolved over a live copy. Fixed: an item named ours counts unless a readable field proves it's another upload (a different size, or created before ours); an unusable id raises `MetaConfigError` and keeps the orphan open (test_an_unreadable_field_never_hides_our_copy ×2, test_a_copy_with_an_unusable_id_keeps_the_orphan_open)
- L2 `SecondOpinion.summary()` counted raw answers, but the audit gate checks the `redteam_open` entries WP4 keeps. Example: a frame label dropped in the bar (PRE-A §5) made the audit invalid. Fixed: `summary(kept)` counts the kept entries, and the PR's WP4 request says to pass them (test_the_open_weight_summary_counts_the_kept_entries)
- L3 `ResponseLog.requested()` added deletes whose record failed, so the receipt disagreed with responses.json after a disk fault. Fixed: `requested()` counts only recorded requests (PRE-A §10.4); `unrecorded()` reports the rest for the receipt note; `delete_pending` still returns every request made (test_the_receipt_count_is_only_what_responses_json_records)
- L4 `responses.create` with an `input_video` part and no `video_seconds` reserved only the output when the free count failed. Fixed: such a call is refused with `ValueError` before any spend (test_a_video_body_needs_its_length_for_the_fallback_estimate)
- Docs: the hero-run cost now says it assumes a 30 s, 30 fps clip and scales with frames

## Audit 30 (independent Sonnet reviewer at 32525dd, finished at 7018ca7): 0 critical, 0 high, 1 medium, 3 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #30 section). It also hit audit #31's three items, already fixed in 7018ca7. Its 150-seed stress run (3 jobs sharing a ledger and breaker, random faults, double cancels, ledger stalls) found nothing.
- M1 a listing item of another shape (`name`/`size` instead of `filename`/`bytes`) was skipped as "not ours", so the orphan could be resolved over a live copy; audit #31's fix covered unreadable fields only, not a missing `filename`. Fixed: an item without a string `filename` and `id` raises `MetaConfigError`, which keeps the orphan open (test_a_listing_item_of_another_shape_keeps_the_orphan_open)
- L2 `PlanEntry.grid`'s `(x0, y0, cell_px)` triple was undocumented. It is now in ARCHITECTURE §3.7. The ≤ 6-blocks rule is DESIGN §2.7's for faces; the fixture's 16 px grid is on a screen item
- L3 R10 is a helper that nothing in WP0 calls (WP0 makes no file-referencing call). API-NOTES §13.4 now says so, and PR #3 and HANDOFF ask WP1 and WP2 to wrap their file-referencing calls in `call_with_reupload`. The SAM-path R4 vector now has its own test (test_r4_a_sam_sweep_that_times_out_twice_keeps_both_charges)
- L4 probe d called `dict(body)` before saving, so an empty or list body crashed the probe and lost the paid response. Fixed: it saves the body as sent, then parses; `transcribe_raw` is typed `Any` (test_probe_d_saves_an_empty_body_before_parsing)

## Audit 32 (independent Sonnet reviewer at 7018ca7): 0 critical, 0 high, 1 medium, 3 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #32 section) unless named. Its 400-scenario stress harness (concurrent uploads and Responses calls, repeated cancels, 500/429/eof) kept ledger == Σ cost.jsonl with no open reservation.
- M1 a base URL with a trailing newline or space passed `trusted_base_url` (urlsplit strips it for parsing; the value kept it). httpx then raised `InvalidURL` after `mark_sent`, so every call was billed its estimate for a request that never left. This is the same class as audit #21's key whitespace. Fixed: `trusted_base_url` refuses any whitespace or control character, at load and in the client (test_a_base_url_with_whitespace_is_refused_at_load ×3)
- L1 audit #30's fail-closed rule raised on any unreadable item in the team-wide `/files` listing, so one unrelated item would block every job's orphan reconcile forever. Fixed: an unreadable item fails closed only when one of its string values is our job-unique name, and is skipped otherwise (test_an_unrelated_unreadable_item_never_blocks_cleanup; test_a_listing_item_of_another_shape_keeps_the_orphan_open now lists an unrelated item too)
- L2 the hero-run cost was wrong: on a hero clip, probe b runs only the 4 base concepts (no delete check or fps hint). The figure is now ≈ $0.72 for 900 frames, scaling with the frame count
- L3 the ARCHITECTURE §3.8 example's unflagged leak named `i_9` as its patch, which the gate refuses (only an audit patch may patch an unflagged leak). It now names `p_1`

## Audit 33 (independent Sonnet reviewer at 9d53096 plus the audit #32 tree): 0 critical, 0 high, 2 medium, 1 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #33 section).
- M1 the audit #32 skip was fail-open for listings that hide our name: bare-id items (`["file-777"]`) or our name nested a level down were skipped, and the orphan was resolved. Fixed:
  - a listing with no item carrying a string `filename` is unusable and raises;
  - a non-object item raises;
  - an unreadable object item raises when our job-unique name appears anywhere inside it (searched recursively), and is skipped otherwise.
  Unrelated unreadable items in an otherwise documented listing still never block cleanup (test_a_listing_that_hides_our_name_keeps_the_orphan_open ×4)
- M2 a `MetaClient(provider="baseten")` built without `api_key` defaulted to the Meta key, and to the Meta base URL. Only `open_weight_client` passed the right ones. Fixed: the defaults follow the provider, so a Baseten client takes `BASETEN_API_KEY` (or refuses without it) and the Baseten URL (test_a_baseten_client_never_defaults_to_the_meta_key)
- L3 `.gitignore` lacked PRE-A §12's `*.jit`, `*.zip`, `*.tar.gz` and `/models/` (EgoBlur Gen 2 weights, O8 archives). Added; no tracked file is newly ignored

## Audit 34 (independent Sonnet reviewer, launched at 8f6c12b, reviewed fe0ff7b): 0 critical, 0 high, 2 medium, 2 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #34 section) unless named.
- M1 a flagged leak counted as fixed while its `through_item` was still a mosaic. redteam.md: the item is re-rendered solid, and WP3's guard reads the flag on every re-plan. Also, audit patches weren't held to PRE-A §12's row (`style: "solid"`, `decided_by: "policy"`, one evidence frame). Fixed:
  - a flagged leak that isn't unresolved needs its `through_item` solid on every `plan.json` frame;
  - `DecisionItem` requires an audit patch to be solid and policy-decided, with exactly one evidence frame inside `first..last`.
  test_contracts' span-move case now moves its evidence frame too (test_a_flagged_leak_needs_its_through_item_rendered_solid, test_an_audit_patch_follows_its_spec_row ×4)
- M2 a publishable audit could have no red-team entries at all. redteam.md: 1 frame per second, one entry per frame sent, never silently skipped. Fixed: with `unresolved == 0`, `redteam` must cover at least `max(1, job.frames // sample_step)` distinct frames. That is the 1 fps floor whatever the sampling phase, so a valid writer is never refused (test_a_publishable_audit_has_its_red_team_frames)
- L3 a body JSON can't carry (NaN, a set, a lone surrogate) failed inside httpx after `mark_sent`, so it was billed as an estimated charge. Fixed: `request`, `stream` and `stream_chat` encode the payload as httpx does before any reservation, and refuse it as `MetaBadRequest` (test_a_body_json_cant_carry_is_refused_before_any_charge)
- L4 ARCHITECTURE §3.9's receipt example elided `audit` and `items`. It now shows the `ReceiptAudit` fields and the item-plus-thumbnail shape. §3 lists the new rules

## Audit 35 (independent Sonnet reviewer at fe0ff7b, re-checked at fde9708): 0 critical, 0 high, 0 medium, 1 low (docs only). NOT CLEAN; verified and fixed
Its own stress runs found nothing: 150 concurrency/cancel seeds, 200 Files seeds against a fake file server, 3,000 mutation-fuzz seeds of `validate_job_dir`, and an independent receipt-hash verifier.
- L1 the ARCHITECTURE §3.8 `audit.json` example (900 frames, step 30) had one red-team entry, which audit #34's 1 fps floor refuses. The example now shows the sampled set and says pass 1's entries are kept across later passes. That assumption is also a WP4 request in PR #3 and HANDOFF: `redteam[]` keeps pass 1's full sample set across passes and re-runs. The change is docs only (`*.md`, outside the gate's code diff)

## Audit 36 (independent Sonnet reviewer at fde9708, finished at 9c4db61): 0 critical, 0 high, 0 medium, 3 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #36 section). It found no false refusal in the newest gate rules.
- L1 the red-team floor trusted the audit's own `sample_step`, so `sample_step: 900` on a 900-frame, 30 fps job let one entry pass. Fixed: PRE-A §12 fixes `sample_step = round(job.fps)` (an int), so the gate requires `sample_step == job.fps` and computes the floor from `job.fps` (test_the_red_team_step_is_the_jobs_fps)
- L2 the ARCHITECTURE §3.9 receipt example's `store_by_model` listed only Spark, though its `models` name Wonder and SAM too (PRE-A §12: every Responses-API model). The example now lists all three
- L3 probes a and f hard-coded the Spark/Wonder comparison pair (AGENTS rule 8). The pair is now named in config.py (`COMPARE_SPARK_MODEL`, `COMPARE_WONDER_MODEL`), and the checklist line now says the pipeline's models come from env while probe f's fixed pair lives in config (test_probe_f_compares_the_named_pair)

## Audit 37 (independent Sonnet reviewer at 9c4db61, still valid at fc14859): 0 critical, 0 high, 1 medium, 3 low. NOT CLEAN; all verified and fixed
Tests are in tests/test_audit24.py (the audit #37 section) unless named.
- M1 `plan.json` styles were never compared with `decisions.json`. An audit patch rendered as a mosaic passed, and so did any solid decision rendered pixelated. Fixed: `_check_plan_styles` requires each entry to render its decision's style. The exception is a flagged leak's `through_item`, which renders solid once re-planned (not while the leak is unresolved, since the last pass comes after the last re-plan). Audit-patch entries must carry `source: "audit_patch"`. This replaces the narrower solid-through-item check from audit #34 (test_a_plan_entry_renders_its_decisions_style ×2, test_an_audit_patch_entry_is_marked_as_one, test_a_flagged_leak_needs_its_through_item_rendered_solid reworked on a pixelated person item, test_an_unresolved_flagged_leaks_item_may_still_be_soft)
- L2 the ARCHITECTURE §3.7 example's `temporal.backfill: 15` contradicted PRE-A §5b/T10 for its own 30 → 8 fps job. It is now 57, and the prepared-frame rule is stated
- L3 the example job pixelated a sensitive screen (`i_3`), against DESIGN §2.7 and WP3.md ("text, screens, plates, documents → solid"), and gave escalated `i_2` a `no_roles` hold that escalation.md doesn't allow. Fixed:
  - `DecisionItem` refuses `pixelate` for plates, screens and documents;
  - the fixture's `i_3` is solid with no grid, and `i_2`'s hold is null, with the receipt re-sealed;
  - the ARCHITECTURE grid sentence is reworded.
  test_contracts' receipt item-by-item case now changes the style to `person_solid` (test_text_screens_plates_and_documents_are_never_pixelated ×3)
- L4 no probe checked the `GET /v1/files` listing that orphan cleanup relies on (PRE-A §10.4: "its paging is checked in WP0's probes"). Fixed: probe a lists files with the cleanup's own parameters and records the keys, `has_more` and item fields, never the names. The replay test checks it (tests/test_probes_replay.py::test_all_probes_replay)

## Audit 38 (independent Sonnet reviewer at fc14859): 0 critical, 0 high, 0 medium, 2 low. NOT CLEAN; both verified and fixed
Tests are in tests/test_audit24.py (the audit #38 section). It also reproduced audit #37's plan-style gap and the pixelated screen, both already fixed in the working tree it saw.
- L1 nothing tied decisions to child evidence across files: a kept `person` item over a `child_phrase` track, or over a track that roles.json rules a child, validated. Fixed per PRE-A §12 (WP3 rule 0) and WP3.md: an item over a `child_phrase` track must be `kind: child` (which already forces a locked hide), and an item with a track ruled `child` is never `keep` (test_an_item_over_a_child_phrase_track_is_a_child, test_a_track_ruled_a_child_is_never_kept)
- L2 ARCHITECTURE §3 examples contradicted their own numbers. Fixed:
  - `crowded_frames`/`crowd_fills` [312, 313] could not be a 30 → 8 fps crowded span (T11). It is now 310–315, proxy frame 83's span;
  - the mask and `conf` key 120 isn't a T1 anchor. It is now 121;
  - the `times` elision is now marked;
  - the participant who says "Hi, I'm Amina" is S1, not S2.
  The §3 rules sentence states the child rules
