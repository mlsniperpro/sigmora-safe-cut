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

## Round 3 (on 0b1b364): 1 high, 6 medium, lows. All closed or decided in 17e2e9a.

| # | Sev | Finding | Resolution | Test |
|---|---|---|---|---|
| 1 | high | `SAFECUT_DAILY_USD_CAP=3` with a $2.24 worst case lets judges run about one 60 s clip a day | **Decided, kept as the default** (API-NOTES §9.2 budgets 6 × $3 of the $150; raising it spends credits, the owner's call). BLOCKED now has the decision with its capacity math and the two options (raise it within the credits, or ask judges for ≤ 30 s clips); the landing demo never spends | n/a (owner input) |
| 2 | medium | E3 scored only `plan.json`: a renderer that drew nothing passed | `render_hides`: in `redacted.mp4` every should-hide truth box changes by ≥ 8 levels on ≥ 99 % of its visible frames (the demo's covers change 15–190, codec noise about 2.5) | `test_e3_checks_the_rendered_pixels_not_only_the_plan`; checked on the real demo and on a copy whose render is the source (all five should-hide entities 0/N) |
| 3 | medium | README prose claimed over-blur the table shows as zero | Reworded to the metric (zero; the guest's hidden frames are under the threshold, in `per_clip.csv`) | review |
| 4 | medium | SQLite (WAL) ledger on a Modal Volume unproven | `ledger_smoke` reserves, settles, releases and re-reads from a fresh connection on the Volume; the deploy's `modal run` fails without it | runs in the deploy workflow (owner input: Modal tokens) |
| 5 | medium | Always-on 4 CPU / 8 GB container | 2 CPU / 4 GB (remote models; ffmpeg, render and YuNet locally, two workers) | review |
| 6 | medium | A stage finishing after DELETE re-created data for up to 16 min | The worker reaps a stateless job dir as soon as its action returns | `test_what_a_stage_writes_after_delete_is_removed_when_it_returns` |
| 7 | medium | The deploy went green without a live check when the URL variables were unset | It now fails red ("Deploy not checked"); BLOCKED lists the two variables | review |
| L | low | `exp`/Content-Length accepted non-ASCII digits (500); concurrent PUTs interleaved; public `/docs`; the probe lacked the demuxer whitelist; README revocation wording; unreadable state reaped after a minute; E11 `gate-allow` and skip forms; `git_sha` ignored untracked files and a missing git; report defaults read the env; LAUNCH tense | Each fixed (see 17e2e9a); E11 had in fact been failing on its own test strings, now spelt in pieces | `test_a_non_ascii_digit_in_a_signed_url_is_a_refusal_not_a_500`, `test_the_api_publishes_no_docs_or_schema`, `test_a_second_upload_on_the_same_job_waits_its_turn`, `test_the_sweep_trusts_a_valid_created_at_in_an_unreadable_state` |
| L | low | e2e proves hide/undo/merge by the toast, not by reading the API back | **Kept**: the toast appears only on the server's ack (`ReviewPanel`), and `tests/test_api.py` reads the state back for every edit type | n/a |
| L | low | E10 checks that a figure appears in RESULTS, not that it's the right row | **Kept**: every doc figure today is a whole-token match, and the README table is generated (`--check`); row-level matching would need the docs to cite rows | n/a |

Round 3 was not clean (one high, decided; six medium, fixed), so the clean count stays at 0.

## Round 4 (on 17e2e9a): 0 critical, 0 high, 3 medium, 4 low. All closed in 7f066ea.

| # | Sev | Finding | Resolution | Test |
|---|---|---|---|---|
| 1 | medium | A non-ASCII `sig` made `hmac.compare_digest` raise: unauthenticated 500 on `/media`, `/uploads` | `verify` refuses a non-ASCII signature | `test_a_non_ascii_signature_is_a_refusal_not_a_500` |
| 2 | medium | A dirty-tree refusal on the test split still counted one of its 3 runs | Dirty check and variant pre-flight run before the counter is written | `test_a_refused_test_run_is_never_counted` |
| 3 | medium | E3's pixel check measured change, not hiding (a +10 tint or a cover over 5 % of the box passed; kept entities unchecked) | Hidden = the content's contrast with its background in the render is ≤ 25 % of the source's on 99 % of frames (the demo's covers: 0.00; a tint: 1.00); kept entities change < 8 on 75 % of frames | `test_e3_checks_the_rendered_pixels_not_only_the_plan` (cover, nothing, sliver, tint) |
| 4 | low | E11 never saw merge-commit diffs, nor the tree | `git log -p --cc`, plus every tracked text file scanned; only the scanner and its tests may hold key shapes | E11 run |
| 5 | low | E7's "worker" matched any `*work*` function | Requires the ASGI function to return `create_app(` and the Service to build its `Worker(`, plus the worker smoke | E7 run |
| 6 | low | Service keys had no production minimum | `production_problems` requires 32 characters | `test_production_refuses_weak_secrets` |
| 7 | low | No global ceiling on jobs at work | `SAFECUT_MAX_ACTIVE_JOBS` (8): start and render answer 429, Retry-After 60 | `test_a_busy_service_asks_new_work_to_wait` |

Also from SAFETY's round 6, in SHIP's files (d52980b): `safecut run`/`publish` exit 6 on a blocked audit (`test_cli_never_reports_a_blocked_audit_as_done`); an edit to a done job retires its receipt (`test_edits_after_done_move_back_to_review_and_needs_a_new_render`).

Round 4 was not clean (three medium), so the clean count stays at 0.
