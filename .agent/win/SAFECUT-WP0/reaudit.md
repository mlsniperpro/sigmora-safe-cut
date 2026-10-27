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
