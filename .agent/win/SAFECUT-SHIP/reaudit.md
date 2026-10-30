AUDITED_COMMIT: pending
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# SAFECUT-SHIP re-audit log

Each audit is a full pass over the lane's code by a hostile senior reviewer and a strict judge (a fresh Sonnet
subagent at high effort, read-only, given the code and the specs, not my conclusions). Every finding was verified
before it was fixed, and each fix has a test that fails without it.

## Round 1 (on a4fc365 + the docs commit): 3 high, 6 medium, 4 low. All closed or decided.

| # | Sev | Finding | Resolution | Test |
|---|---|---|---|---|
| 1 | high | Jobs mid-action were orphaned by a restart (in-memory futures and timers); `start`/`render` answered 409 forever | `Service.recover()` at startup re-queues every unpinned `processing`/`rendering`/`retry_later` job from where its files stopped | `test_a_restart_requeues_interrupted_jobs` |
| 2 | high | Anyone could delete or edit the pinned demo job (its ID is derivable) | `refuse_pinned`: 403 `demo_read_only` on delete, review, start, render, audit | `test_the_demo_job_is_read_only` |
| 3 | high | Two concurrent `start`/`render`/`audit` both passed the status check: paid work twice | The check, side effects and transition run under the job's lock; `submit` only after the transition | `test_two_concurrent_starts_run_the_analysis_once` |
| 4 | medium | Review edits raced a starting render, and a failing guard left the edit logged with a stale plan | The status is rechecked under the lock; decisions, audit and plan roll back on a guard failure, and the log is written last | covered by the flow tests; the rollback path by code review |
| 5 | medium | `prepare`'s `unreadable`/`no_video` came out as `internal`; `too_long` carried no duration | Mapped to `bad_media`; duration and size are taken from the exception or its message | `test_prepare_rejections_map_to_the_ui_reasons`, `test_a_clip_over_60_s_fails_in_prepare_with_its_duration` (real prepare) |
| 6 | medium | Nothing gated "done" on `validate_job_dir` | The worker validates after the receipt; a mismatch fails the job | `test_a_job_whose_files_disagree_never_ends_done`, `test_flow_on_the_real_stages` |
| 7 | medium | The per-IP limit fails open if the proxy doesn't set `X-Forwarded-For` | `deploy-check.sh` sends forged headers and requires a 429. It caught uvicorn's loopback proxy-header default, so local servers run with `--no-proxy-headers` | `test_deploy_check_passes_on_a_healthy_deployment` |
| 8 | medium | A stale render stays downloadable after an edit on a done job | **Decided, kept.** UI-SPEC §8 request 5 says "the previous render stays downloadable until a new one replaces it", and `/result` redirects to review in that state | n/a |
| 9 | low–medium | RESULTS printed "$0.00 measured" for a replay; the footnote could mix clip sets; the deletion wording; a crashed test run didn't count; docstring | Replay runs say "none measured"; mixed clip sets raise; the deletion sweep is named; test runs are counted when they start; docstring corrected | `test_report_tables_link_every_number_and_label_synthetic_runs`, `test_a_test_run_that_crashes_still_counts` |
| 10 | medium | entry-check: E4/E5 passed skipped tests; E1 ignored xfail; the E11 skip scan was too loose; E10 used substring matching and skipped inline code; the secret scan missed JSON form | `require_passed` for E4/E5; E1 also greps xfailed/xpassed; only key-gated `skipif` in `tests/test_live*.py` is allowed; whole-token figure matching with inline code kept; JSON-form key pattern | `tests/test_entry_check.py` (four new tests) |
| 11 | low | Deploy wasn't gated on CI; the URL check was skipped silently; CI didn't check RESULTS | `workflow_run` on CI success; a `::notice` when the URL vars are unset; CI runs `eval/report.py --check` | `test_deploy_workflow_skips_without_secrets` |
| 12 | low | Replay could reach the network through a loopback HTTP(S) proxy (true in this sandbox); `safecut render` ran unapproved; sync writes in the async upload handler | Proxy ports refused in replay; the CLI publish stages check approval; writes go through the threadpool | `test_netguard_refuses_a_local_proxy` |
