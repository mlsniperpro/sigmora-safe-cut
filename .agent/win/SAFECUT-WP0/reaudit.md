AUDITED_COMMIT: 6afd9ea
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
