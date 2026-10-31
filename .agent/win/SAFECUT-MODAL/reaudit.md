AUDITED_COMMIT: 8237813
OPEN_CRITICAL: 0
OPEN_HIGH: 0
CLEAN_AUDITS_IN_A_ROW: 0

# SAFECUT-MODAL re-audit log

Each round is a full pass over the lane's whole diff (`git diff c37af44..HEAD`) by a fresh, read-only reviewer
(a Sonnet subagent at high effort) given the brief, the code and the specs, not my conclusions. Every finding was
verified against the code (and, for Modal, against the installed modal 1.6.2 source) before it was fixed, and each
fix has a test that fails without it.

## Round 1 (on 63588b3): 2 high, 7 medium, 7 low. All closed or decided.

- H1 committing the jobs Volume from the API reloads it (modal `volume.py` `commit` → `_do_reload`), which fails
  while the ledger's SQLite files are open there → the render goes through a separate handoff Volume
  `safecut-audit` (`Handoff`). Tests: `test_the_handoff_copies_each_render_once_and_names_every_gpu`,
  `test_a_handoff_commit_that_fails_is_retried_then_falls_back`.
- H2/M1 no deploy check exercised the API container's own GPU path → `deploy-check.sh` asserts the demo job (built
  in the API container through the same path) names `egoblur-gen2` on `cuda:`
  (`test_deploy_check_proves_the_api_containers_own_gpu_path`).
- M2 a job that kills its container loops forever → persisted `resumes`, failed after `MAX_RESUMES`
  (`test_a_job_that_keeps_taking_its_container_down_fails`).
- M3 a mid-audit GPU failure repays the red team → decided and documented (`docs/DEPLOY-COSTS.md`, "What a crash
  or a fallback costs"): the re-audit is of a new render, so new answers are needed; caps bound it.
- M4 `choose_detector` caught too narrowly → any setup error falls back
  (`test_anything_that_stops_the_gpu_path_being_set_up_still_audits`).
- M5 unbounded pre-deploy GPU probe, no override → `spawn().get(timeout)`, `SAFECUT_DEPLOY_GPU_OPTIONAL`.
- M6 a corrupt limiter file stops boot → moved aside (`test_a_corrupt_limit_store_is_moved_aside_never_taking_the_api_down`).
- M7 "no double spend" only for finished stages → stated exactly in DEPLOY-COSTS.
- Lows: wake.ts comment; keepalive spawned off the request thread (`test_a_slow_keepalive_never_holds_up_the_request`);
  no hashing without torch (`test_without_torch_the_weights_are_never_hashed`); GPU `max_containers=4`; every GPU
  named (`cuda:NVIDIA L4+Tesla T4`); docstring claim softened to Meta's figure.

## Round 2 (on 62c90f3): 1 high, 5 medium, 6 low. All closed or decided.

- F1 (high, a regression of this lane) a GPU-audited replay or synthetic receipt lost its label, because Modal
  cost lines counted as "billed" → `billed` ignores `provider: "modal"`, and new notes name EgoBlur as the one
  model that ran (`test_a_replayed_job_audited_on_the_gpu_keeps_its_label[synthetic|replay]`).
- F2 the YuNet note said "weights weren't installed" after a GPU timeout → `YUNET_FALLBACK_NOTE` with the
  recorded reason (`test_a_gpu_fallback_receipt_says_why_yunet_ran`).
- F3 the handoff lock was per process, but the demo build runs in a child → `flock` on a container-local file
  (`test_the_handoff_waits_for_another_process_writing_the_same_mount`).
- F4 an unbounded commit under the lock could hang every audit → commit bounded at 120 s, mapped to a timeout
  fallback, lock released (`test_a_commit_that_hangs_falls_back_instead_of_holding_every_audit`).
- F5 the demo stamp ignored the GPU setting, and a YuNet demo was permanent → the stamp covers `audit_gpu`; a demo
  YuNet audited is rebuilt at most every 6 h (`test_a_demo_the_gpu_couldnt_audit_is_rebuilt_but_not_on_every_wake`).
  Residual, decided: a change only in `deploy/modal_app.py` doesn't rebuild the demo; `deploy/verify_deploy.py`
  re-proves the deployed GPU path on every deploy.
- F6 the GPU-optional switch wasn't wired → workflow env, `verify_deploy`, the URL check, BLOCKED.md
  (`test_the_gpu_optional_switch_reaches_every_gpu_check`).
- Lows: `resumes` reset on a restart and on `needs_you` (`test_a_restarted_job_starts_its_resume_count_afresh`);
  a transient `OperationalError` counts in memory instead of quarantining
  (`test_a_locked_limit_store_counts_in_memory_without_moving_the_file`); the ledger is closed on shutdown; the
  container is held up while the demo builds (`test_the_container_stays_up_while_the_demo_job_builds`); BLOCKED.md
  and DEPLOY-COSTS figures and wording; the demo child gets the Modal client on `PYTHONPATH`
  (`test_the_demo_builds_child_can_import_modal_as_this_process_does`).

## Round 3 (on 529fa8b): 1 high, 3 medium, 9 low. All closed or decided.

- H1 Modal's default `rolling` deploy keeps the old container draining (a `hold` input lasts the job) while a new
  one's start resumes the same job → `modal deploy --strategy recreate` (modal 1.6.2 `cli/run.py`, `app.py` deploy);
  `test_the_deploy_workflow_proves_the_gpu_audit_and_a_cold_wake_after_deploying`.
- M1 the demo was deleted before its rebuild → built in a scratch folder and swapped in (made atomic in round 4).
- M2 the demo child shared the service's SQLite ledger → the child keeps a ledger of its own.
- M3 the post-deploy smoke's child lacked `child_env`; an unresolved GPU audit couldn't be waived → both fixed.
- Lows: a timed-out GPU call is cancelled with `terminate_containers=True`; a stale handoff copy is discarded before
  the retry (`test_a_stale_handoff_copy_is_discarded_before_the_retry`); the cron's handoff sweep moved to
  `safecut.api.store` (no pipeline import in a 128 MiB container); a ledger runbook line; unmeasured cold start
  labelled an estimate; checklist names, mounts and counts corrected; the deploy job may take 60 minutes. Decided:
  the GPU timeout stays 300 s until a deploy measures EgoBlur (the fallback is YuNet, named, never a hang).

## Round 4 (on 56f8061): 0 high, 2 medium, 6 low. All closed.

- M1 the demo "swap" deleted the old folder before renaming the new one in (23,266 misses measured by the reviewer)
  → `JobStore.replace_pinned`: state written into the build, two renames under a swap lock that `get` honours on a
  miss, the old job restored if the second rename fails
  (`test_readers_never_see_the_demo_missing_while_it_is_swapped`: 0 misses over the reads of a full rebuild;
  `test_a_swap_that_fails_halfway_puts_the_old_demo_back`; `test_the_served_demo_stays_up_while_it_is_rebuilt_and_if_the_rebuild_fails`).
- M2 the deploy check could judge the previous deploy's demo → `/healthz` reports `demos_building` and
  `demos_current`; `deploy-check.sh` waits for this code's build and fails on a demo only an earlier deploy built
  (`test_deploy_check_judges_this_deploys_demo_never_an_earlier_one`).
- Lows: the API's exit hook doesn't wait for running jobs (`stop(wait=False)`,
  `test_a_replaced_container_stops_without_waiting_for_its_jobs`) and the `recreate` wording says what Modal does; a
  paid GPU call that didn't answer still gets the GPU replay/synthetic note
  (`test_a_paid_gpu_call_that_didnt_answer_still_isnt_no_model_called`); Modal calls run off the audit's event loop;
  an unreadable render is refused, not retried (`test_an_unreadable_render_is_refused_not_retried`); the estimate is
  tied to `MAX_PASSES` (`test_the_estimate_counts_one_gpu_scan_per_audit_pass`) and the docs say how retries are
  reserved; `run.json` records `gpu_calls` and `gpu_wall_s`; stale `.building` folders are swept
  (`test_the_sweep_removes_a_demo_build_a_dead_container_left`); FP32 sources linked; BLOCKED.md's cron output.

## Round 5 (on e3305d8): 0 high, 1 medium, 6 low. All closed.

- M1 the "exit doesn't wait" fix was unreachable: Modal ends the ASGI lifespan (which stopped the service with
  `wait=True`) before `@modal.exit` (modal 1.6.2 `_runtime/user_code_imports.py` `function_execution_context`), and
  `ThreadPoolExecutor` threads are joined at interpreter exit → `Service(wait_on_stop=False)` on Modal, honoured by
  the lifespan, and the worker runs jobs on a `DaemonPool`
  (`test_a_replaced_container_closes_its_app_without_waiting_for_a_running_job`,
  `test_job_threads_never_keep_a_finished_interpreter_alive`, `test_the_daemon_pool_runs_cancels_and_reports_like_an_executor`;
  the SIGKILL test passes on it).
- Lows: `JobStore.get` re-reads under the swap lock when the file vanishes between its check and its read; the API's
  own JSON 503s no longer read as a waking gateway in the web client (`api.test.ts`); the cost table's worst-case row
  priced at the configured rate (all three copies regenerated); the GPU probe bounded at 5 minutes inside the
  smoke's 25; no Modal-level retries on `egoblur_detect` (every billed attempt is reserved and priced); a test renamed
  to what it shows.

## Round 6 (on e167e0d): 0 critical, 0 high, 0 medium, 2 low. Both closed. Not counted as clean (it found something).

- L1 the GPU call and the handoff commit waited on `ThreadPoolExecutor` threads, which are joined at interpreter exit,
  so a container replaced mid-scan could linger up to the scan's timeout → `gpu.on_daemon` (a daemon thread and an
  event) for both (`test_a_job_waiting_on_the_gpu_never_keeps_a_finished_interpreter_alive`,
  `test_on_daemon_answers_raises_and_times_out`).
- L2 this log's header lagged the round-5 diff → updated.

## Round 7 (on e0a9eac): 0 critical, 0 high, 2 medium, 2 low. All closed. Not clean.

- M1 a handoff failure before any GPU call was still reserved and priced (`provider: modal` lines), so a synthetic
  receipt said EgoBlur was "the only model called" → the handoff runs before the reservation; only a submitted call
  is reserved, priced or counted (`test_a_handoff_commit_that_fails_is_retried_then_falls_back` now asserts no
  cost lines, nothing in the ledger, and the plain synthetic note).
- M2 `break-it.md` didn't exist yet → written from the break-it runs on the final commit.
- L1 a GPU call that errored after its spawn wasn't cancelled → `_cancel(handle)` on any exception
  (`test_a_gpu_call_we_stop_waiting_for_is_cancelled[timeout|error]`).
- L2 `deploy-check.sh` read a failed poll as "the demo build is done" → only an explicit `False` ends the wait.

## Round 8 (on 9e21278): 0 critical, 1 high, 2 medium, 3 low. All closed. Not clean.

- H1 modal 1.6.2's default `server_url` is two comma-separated URLs (`modal/config.py` `DEFAULT_SERVER_URL`), which
  the replay permit parsed into one junk host → `modal_hosts()` splits it and `modal_permitted()` lets each through
  (`test_replay_reaches_every_host_of_modals_default_server_url`, with the real default).
- M1 a call that failed before Modal accepted it (`from_name`/`spawn`) was still priced and claimed →
  `NotSubmitted`: the reservation is released, nothing priced, counted or claimed
  (`test_a_call_that_never_reached_modal_costs_and_claims_nothing`).
- M2 the gate's "unjustified suppressions" scan flagged 52 bare `noqa`/`type: ignore` lines this lane added → each
  carries its reason.
- Lows: the pre-deploy probe reports any GPU error (so `SAFECUT_DEPLOY_GPU_OPTIONAL` can waive it); BLOCKED.md
  says turning the GPU off needs the optional switch too; the stall clock starts when an action is queued (start,
  render, audit, a re-queue), so a render after a long review is resumed, not failed
  (`test_a_render_queued_after_a_long_review_is_resumed_not_failed_as_stalled`).

## Round 9 (on 324c373): 0 critical, 0 high, 0 medium, 9 low. Closed or decided. Not clean.

- L1 `gpu.json` said `gpu_calls: 0` after a paid call that timed out → it records every GPU call the audit made,
  before any fallback (`test_a_paid_gpu_call_that_didnt_answer_still_isnt_no_model_called` asserts 1).
- L2 the replay permit was outside `NotSubmitted`, and the real wrapper was untested; the pre-deploy probe let a
  handoff or spawn error escape → both inside (`test_a_modal_lookup_that_fails_is_not_submitted`, `_probe_gpu`).
- L3 a detector that had failed kept calling the GPU (a second paid timeout) → it short-circuits
  (`test_after_a_failure_the_gpu_is_never_called_again_in_that_audit`).
- L4 the round-8 tests didn't run `recover` or the audit route; a checklist test name was wrong → strengthened
  (`test_a_render_queued_after_a_long_review_is_resumed_not_failed_as_stalled` now resumes it in a successor;
  `test_queueing_an_audit_starts_its_stall_clock`).
- L5 the handoff copy outlived "Delete everything now" → the audit commits its removal; the privacy page and
  DEPLOY-COSTS say a copy of the redacted result sits with the GPU during the check and is gone within the hour if
  the check is cut short.
- L6 a GPU answer over 2 MiB comes back through blob storage, which replay's guard blocks → documented (a replayed
  crowded clip falls back to YuNet, named; live jobs aren't guarded).
- L7 `PYTHONPATH` could let the Modal mount shadow the child's packages → `SAFECUT_MODAL_PATH`, appended last to
  `sys.path` on first use (`test_the_demo_builds_child_can_import_modal_as_this_process_does`).
- L8 DEPLOY-COSTS said an open reservation counts for 2.5 h → it counts until released (fail closed), as the code does.
- L9 `checks.sh` runs `pnpm build` → kept: `.agent/ENTRY-DONE.md` E1 requires the production build in cloud
  sessions, overriding AGENTS rule 12 (COMMON: these briefs win).

## Round 10 (on fc77dfc): 0 critical, 0 high, 1 medium, 3 low. All closed. Not clean.

- M1 round 9's edit of one test replaced a span that also held
  `test_the_served_demo_stays_up_while_it_is_rebuilt_and_if_the_rebuild_fails` → restored verbatim (it passes); a
  scan of every commit on the branch confirms no other test went missing (only the two per-frame `RemoteDetector`
  tests whose code was replaced, and one rename).
- L1 the privacy page said "within the hour" while a cut-short check's copy could live 75 minutes → the sweep takes
  copies older than 45 minutes, so with the 15-minute cron it is within the hour
  (`test_the_sweep_keeps_the_privacy_pages_hour`).
- L2 UI-SPEC's retry row said a timed-out GET is retried three times → one retry, as the code does.
- L3 the permit-failure path and `_probe_gpu` were untested; the smoke's `finally` committed unguarded →
  `test_a_permit_that_fails_is_not_submitted`, `test_the_pre_deploy_probe_reports_every_gpu_failure` (5 cases), and
  the extra commit dropped (`Handoff.close` commits best effort).

## Round 11 (on 0788906): 0 critical, 0 high, 0 medium, 3 low. All closed. Not clean.

- L1 "within the hour" had no margin for the cron's latency → copies older than 35 minutes are swept: 35 + 15
  leaves ten minutes (`test_the_sweep_keeps_the_privacy_pages_hour` asserts the margin).
- L2 stale wording (the handoff docstring's "hourly", the cron's "no-op" hold, the ARCHITECTURE contract paragraph
  missing `cost_usd_gpu` and `auditor_device`, the web test count) → corrected.
- L3 nothing proved the keepalive (`SafeCutApi.hold.spawn`) works on Modal → the worker records the last outcome,
  `/healthz` reports `keepalive`, and `deploy-check.sh` fails on `false` (or, right after a deploy, on none tried:
  every start's demo-build hold is the probe) (`test_deploy_check_proves_the_keepalive_reaches_modal`; the keepalive
  tests assert the recorded outcome).

## Round 12 (on 39ae67d): 0 critical, 0 high, 1 medium, 0 low. Closed. Not clean.

- M1 `deploy-check.sh` judged the keepalive from the first cold-wake `/healthz`, which can answer before the
  keepalive thread reaches Modal, so a healthy deploy could fail → the check waits (up to `DEPLOY_DEMO_WAIT_S`)
  for an outcome, after the demo-build wait (`test_deploy_check_waits_for_the_keepalives_outcome_after_a_cold_wake`:
  a stub that answers null first, then true).

## Round 13 (on 128a87a): 0 critical, 0 high, 0 medium, 2 low. Both closed. Not clean.

- L1 the keepalive wait ended on any unparseable poll (a gateway 503) → it waits for an explicit True or False, as
  the demo wait does (the test's stub now answers null, then a 503, then true).
- L2 the drop of a box wholly outside the frame lost its test with the old `RemoteDetector` tests → a case in
  `test_the_gpu_answer_is_schema_checked`.

## Round 14 (on 8237813): 0 critical, 0 high, 2 medium, 2 low. All closed. Not clean.

No wrong behaviour; the reviewer mutated a scratch copy and found tests that stayed green with a feature broken.
Each now has a test that fails on the mutant.

- M1 the receipt's `auditor_device` and `cost_usd_gpu` cross-checks had no negative test →
  `test_a_receipt_that_claims_another_device_or_gpu_cost_never_validates` (a re-sealed forgery of each fails
  `validate_job_dir`).
- M2 the GPU term in the up-front cap checks was tested only as a function →
  `test_the_up_front_cap_check_counts_the_gpu[False|True]` (a judge's start and a pilot's job creation refused only
  with the GPU on).
- L1 the stall-rule test passed without the rule → asserts the stage, the detail and that nothing was re-queued.
- L2 five unpinned behaviours → `test_each_render_is_copied_to_the_handoff_once`,
  `test_a_gpu_call_is_reserved_at_its_worst_case_with_the_idle_tail`, `test_switching_the_gpu_audit_on_rebuilds_the_demo`,
  `test_a_re_queued_job_restarts_its_stall_clock`, `test_the_stored_limit_uses_wall_clock_time`.

Also (d5b5efd, found by a full-suite run under load): the healthy-deployment fixture waits for its demo build before
the check's short wait, and the keepalive wait runs only where a keepalive always comes (`DEPLOY_EXPECT_COLD=1`);
the deploy-check tests pass under four CPU hogs.
