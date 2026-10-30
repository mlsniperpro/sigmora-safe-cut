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

## Round 2 (on bf05010): 1 high, 4 medium, 6 low, 3 entry-check gaps. All closed in 2fd65da / 0b1b364.

"Clean" for the count above means no critical, high or medium finding (lows are fixed or decided too).

| # | Sev | Finding | Resolution | Test |
|---|---|---|---|---|
| 1 | high | `deploy.yml`: `workflow_run` with `branches: [main]` also matches a fork PR's head branch named main, so a fork's code could run `modal deploy` with the Modal secrets | The job requires `workflow_run.event == 'push'`, `head_branch == 'main'` and `head_repository.full_name == github.repository` | `test_deploy_never_runs_a_forks_code_with_the_secrets` |
| 2 | medium | The Modal image never installed the `audit` group, so the deployed audit stays on YuNet even with the EgoBlur weights; SUBMISSION claimed EgoBlur without the caveat | `SAFECUT_DEPLOY_AUDIT=1` (a repo variable) builds with the group; BLOCKED step added; SUBMISSION names the YuNet fallback | E7 import; doc review |
| 3 | medium | AGENTIC-LOOP stale (13 tracks, one needs-you) | Re-traced from the current demo run: 15 tracks, Kev's re-entry `face:6` needs you | E10; manual diff against `safecut run --replay` |
| 4 | medium | `JobStore.delete` raced a writing stage (OSError, 500, data left); a stage's `dump` re-created the dir | Rename to `.deleting-<id>-<rand>` under the lock, reap with retries; the sweep reaps stateless dirs over a minute old and leftovers | `test_delete_succeeds_while_a_stage_is_still_writing` |
| 5 | medium | VIDEO-SCRIPT claimed about 330 VO words (about 246 quoted) | Corrected to about 235 words (one of the two 2:00 lines) | review |
| 6 | low | `recover` resumed jobs without re-checking their code, and sent `retry_later` jobs straight back | `paid_grant` per job (fails `code_not_active`); `Worker.submit_later` keeps the remaining delay | `test_a_restart_refuses_jobs_whose_code_was_revoked_and_keeps_retry_delays` |
| 7 | low | `JobNotFound` between a handler's first look and its update was a 500 | App-level handler → 404 `not_found`/`expired`; the upload's final rename too | `test_a_job_deleted_mid_request_is_a_404_not_a_500` |
| 8 | low | Web `synthetic` defaulted to false, so a replay that omitted it would be bannered as a real run | Optional in the schemas; `useReportMode` treats a missing value on a replay as synthetic; the mock generator says `synthetic: false` explicitly | `mode.test.tsx` "labels a replay synthetic when the response doesn't say" |
| 9 | low | Short access codes / URL secret accepted | The Modal entry point refuses to start on a code < 12 chars, a URL secret < 32 or a non-https public URL (`production_problems`); tests keep short codes | `test_production_refuses_weak_secrets` |
| 10 | low | README overstated revocation, "DELETE in every state" and the per-thread guard | Reworded to what the code does | review |
| 11 | low | Live eval runs had no run-level ceiling; dirty-tree runs were accepted | `--max-usd` (default $15) stops before the next clip; live runs refuse a dirty tree; the report refuses `-dirty` runs | `test_a_live_run_needs_committed_code_and_stops_at_its_ceiling`, `test_the_report_refuses_a_run_made_from_uncommitted_code` |
| E3 | gap | Could pass on a truth file with nothing to hide | Requires a visible should-hide and a visible keep entity | `test_e3_never_passes_on_a_truth_file_with_nothing_to_check` |
| E10 | gap | Integer counts and untagged fences unchecked | `COUNT` (leaks, clips, bursts, entities…) checked; only command/data fences are skipped | `test_counts_reported_as_results_are_checked_too`, the fence case |
| E12 | gap | Bare-word patterns (`public`, `EgoBlur`) | Match the real owner lines | `test_owner_inputs_need_their_real_lines_not_a_bare_word` |
| E7 | gap | A placeholder `*.modal.run` URL counted as deployed | Placeholder hosts are ignored | review |

Peer-lane findings in SHIP's paths, closed in the same commit: approval vs audit patches, private red-team text, the audit's cap path (SAFETY); `track` freshness after `roles` (SENSE); `apply_review` gets `tracks`/`job`. Kept by decision: the review ack still returns the plan (UI-SPEC §8; the overlay draws from it).

Also fixed: `tests/test_meta_client.py::test_cancel_before_send_releases_and_after_send_charges` raced a 50 ms sleep and failed E1 on a loaded fresh clone; it now waits for the request to be sent.
