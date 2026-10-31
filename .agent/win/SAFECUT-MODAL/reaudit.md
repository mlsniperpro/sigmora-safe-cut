AUDITED_COMMIT: f6f8945
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
  (`test_a_gpu_call_we_stop_waiting_for_is_cancelled[failure0]` and `[failure1]`).
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

## Round 15 (on 4f6f52f): 0 critical, 0 high, 0 medium, 1 low. Closed. Not clean.

Every round-14 test was mutation-checked by the reviewer (each fails on its mutant); 25 of 27 GPU-path mutants
read were killed, and the two survivors were equivalent mutants.

- L1 a keepalive's `hold` could read the job's state before the request that queued it had saved "processing", and
  return at once on the stale "created" → `hold` waits on any job this process is tracking, whatever its state says
  (`test_a_keepalive_that_arrives_before_the_state_is_saved_still_holds`, reproduced with a zero-latency keepalive).

## Round 16 (on 64b38b1): 0 critical, 0 high, 2 medium, 1 low. All closed. Not clean.

The round-15 `hold` fix was mutation-checked (its test failed 3 of 3 with the fix reverted).

- M1 the Modal glue (`SafeCutApi.hold`/`boot`/`shutdown`, `_keepalive`, the cron's body) was only shape-checked →
  run for real through modal 1.6.2's raw functions with stand-ins:
  `test_the_hold_input_lasts_as_long_as_the_services_hold`,
  `test_boot_refuses_weak_secrets_and_otherwise_starts_a_held_service`,
  `test_the_keepalive_spawns_this_containers_hold_inside_the_modal_permit`,
  `test_the_cron_sweeps_jobs_and_handoffs_commits_and_wakes_jobs_mid_action`.
- M2 `gpu.modal_commit` had no test → `test_the_handoff_commit_commits_the_handoff_volume_inside_the_permit`.
- L1 the handoff copy of `job.json` carried the upload's own file name → the copy's `source` is a neutral name
  (`test_the_handoff_copy_never_carries_the_uploads_file_name`); the privacy page says so.

## Round 17 (on e9690c3): 0 critical, 0 high, 1 medium, 2 low. All closed. Not clean.

No wrong behaviour; gaps in the proof, found by mutation.

- M1 the boot test didn't pin that `boot` keeps the service on the instance → it asserts `api.service` and runs
  `hold` through the booted object.
- L1 `egoblur_detect` and `ledger_smoke` bodies never ran in a test (swapped `GpuServer` arguments, a reload after
  serving) → `test_the_gpu_function_reloads_the_handoff_then_serves_from_it` (call order and constructor arguments),
  `test_the_ledger_smoke_proves_the_ledger_and_the_limiter`.
- L2 nothing pinned the cold-start import cut → `test_the_api_imports_nothing_heavy` (no scipy, torch or Modal on
  `import safecut.api.app`, in a fresh interpreter).
- Noted by the reviewer and closed too: a handoff folder's age now refreshes on every reuse, so an audit longer
  than the sweep's 35 minutes never loses its render mid-scan (`test_each_render_is_copied_to_the_handoff_once`).

## Round 18 (on 1b5db0f): 0 critical, 0 high, 0 medium, 1 low. Closed. Not clean.

The round-17 tests were mutation-checked (each fails on its mutant); 16 of 17 further mutants were killed, the
survivor equivalent.

- L1 the docs and the workflow comment said `recreate` stops the old container before new work starts; modal 1.6.2
  publishes first, then stops the old containers, waiting up to 40 s and only warning past that → DEPLOY-COSTS,
  BLOCKED.md and deploy.yml say so (the overlap is the seconds before the old API exits, which it does without
  waiting for jobs; pushes during judging are barred).

## Round 19 (on d124d7e): 0 critical, 0 high, 0 medium, 3 low. All closed. Not clean.

- L1 the "recreate stops it first" and "never two copies" wording survived in `deploy/modal_app.py` and a test name
  → reworded (a deploy can overlap two briefly; it never scales out), the test renamed
  (`test_the_api_scales_to_zero_and_never_scales_out_to_two_copies`), BLOCKED.md's number matches DEPLOY-COSTS.
- L2 documented bounds weren't pinned → `AWAKE_FOR_MS < 300 s` (`wake.test.ts`), the cold timeout under Modal's
  150 s and above the warm one (`api.test.ts`), `STALL_LIMIT` 45 min inside `HOLD_LIMIT_S` inside the hour and
  `MAX_RESUMES` 3 (`test_the_documented_limits_hold_their_order`).
- L3 the keepalive on the re-queue timer path was untested →
  `test_a_re_queue_waiting_out_its_delay_also_holds_the_container`.

## Round 20 (on 3e5431b): 0 critical, 0 high, 0 medium, 1 low. Closed. Not clean.

The round-19 changes checked against modal 1.6.2's `runner.py`; the re-queue keepalive test fails with its fix
removed.

- L1 `WIN-CHECKLIST.md` gave a stale web test count (916, now 918) → the count is dropped, so it can't drift again.
- Noted by the reviewer and closed too: the web bounds tests compared against literals, not the API's
  `scaledown_window` → `test_the_web_app_counts_the_api_awake_only_inside_its_scaledown_window` reads
  `AWAKE_FOR_MS` from the web source and checks it against the Modal class's `scaledown_window`, and the other three
  timings (`WAKING_AFTER_MS`, `REQUEST_TIMEOUT_MS`, `COLD_START_TIMEOUT_MS`) against each other (fails with
  `AWAKE_FOR_MS = 300_000`).

## Round 21 (on 6fe0e04): 0 critical, 0 high, 1 medium, 4 low. All closed. Not clean.

- M1 only the GPU call's wait was bounded: a control plane stalling on the spawn, or on the cancel after a timeout,
  held the audit (and its job) until the hold's limit → the whole call runs within `timeout + CALL_MARGIN_S` (60 s)
  as a `TimeoutError` (priced as a timeout: the spawn may have gone through) →
  `test_a_control_plane_that_stalls_is_a_timeout_not_a_hung_audit[spawn|cancel]` (both fail on the old wrapper).
- L1 the checklist cited parametrize ids that don't exist → the collected ids (`[setup2-stale_volume]`,
  `[setup4-altered_weights]`).
- L2 round 20's entry overstated what the new test compares → reworded.
- L3 the keepalive spawn made one attempt, so one control-plane blip left a running job without a hold → two retries
  with 0.5 s and 2 s backoff (`HOLD_RETRY_DELAYS_S`), then the cron →
  `test_a_keepalive_is_retried_briefly_before_the_job_is_left_to_the_cron`.
- L4 `break-it.md` missing → written on the final commit, after the last audit.

## Round 22 (on 1aea68a): 0 critical, 0 high, 0 medium, 5 low. All closed. Not clean.

The round-21 tests were mutation-checked (every mutant killed).

- L1 a cited parametrize id didn't exist → `[failure0]` and `[failure1]`.
- L2 a spawn that returned after the call's bound still ran its scan, unwatched and unpriced → the caller marks the
  call abandoned and a late spawn is cancelled at once → `test_a_spawn_that_returns_after_the_bound_is_cancelled`.
- L3 round 21's margin let a call settle up to 60 s past what the meter reserved → the whole call now fits inside
  `SAFECUT_AUDIT_GPU_TIMEOUT_S` itself (the wait keeps `CANCEL_MARGIN_S`, at most a quarter of the bound, for the
  cancel), so the reservation, the estimate and the cost tables hold unchanged →
  `test_a_timed_out_call_and_its_cancel_fit_inside_the_reserved_bound` (fails if the wait takes the whole bound).
- L4 the demo build's hold ignored a stop, so a replaced container's input stayed open until the build ended →
  it returns on stop, like a job's hold → `test_the_demo_hold_ends_when_the_container_is_replaced`.
- L5 DEPLOY-COSTS said "after three restarts" in one place and "on its fourth restart" in another → both say the
  fourth (the code: `MAX_RESUMES = 3` resumes, then a failure).

## Round 23 (on 6437b5a): 0 critical, 0 high, 0 medium, 3 low. All closed. Not clean.

The round-22 tests were mutation-checked (14 of 17 mutants killed; the three survivors are L1 and L2), and the bound
test ran 12 times under CPU stress without a flake.

- L1 the cancel margin's quarter cap was untested (the test's margin never hit it) →
  `test_a_short_timeout_keeps_most_of_its_bound_for_the_scan` (default margin, 1.6 s bound: the wait is about three
  quarters of it; fails with the cap removed or a whole-bound margin).
- L2 the demo hold's time limit was untested → `test_the_demo_hold_gives_up_at_its_limit`.
- L3 two comments disagreed on a clip's GPU model time → `safecut/config.py` uses `deploy/costs.py`'s derivation.

## Round 24 (on f6f8945): 0 critical, 0 high, 0 medium, 2 low. All closed. Not clean.

The round-23 tests killed every margin and deadline mutant (and 8 more `gpu.py` mutants); they passed 6 of 6 under
8 CPU hogs. Every cited test id resolves against the collected 1,618.

- L1 `safecut/config.py` stated the assumed GPU time per pass as fact, and $0.94 beside a $0.95 default →
  "assumed, not measured" (Meta's ~21 ms is on an unnamed GPU) and "rounded up to $0.95".
- L2 `deploy.verify_deploy.main` was only checked by text → `test_the_post_deploy_check_runs_the_deployed_job_with_the_gpu_audit`
  (a stand-in `modal.Function`: called with `audit_gpu=True`, exit 0 or 1 by the checks, the GPU-optional switch
  relaxing only the GPU part; fails without `audit_gpu=True`, without the exit code, or with the switch inverted).

## Round 25 (on 55cb6ca): 0 critical, 0 high, 0 medium, 0 low. CLEAN.

The round-24 test killed all 7 mutants of `verify_deploy.main` (the `audit_gpu=True` flag, the exit code, the FAIL
line, the function name, the switch both ways). Gate scans clean on the added lines; every cited id resolves against
the 1,622 collected; cost tables, BLOCKED.md's caps and the weight hashes reproduce; the cold-start import
re-measured at 0.70–0.75 s and a replay run's RSS at 206 MiB, against the claimed 0.74 s and 210 MiB. (The
reviewer's mutation script briefly edited `deploy/verify_deploy.py` in place and restored it at once; `git status`
and the blob at HEAD confirmed nothing changed, and no commit carries it.)

## Round 26 (on 2b6548b, code as 55cb6ca): 0 critical, 0 high, 1 medium, 0 low. Closed. Not clean.

- M1 the pre-deploy gate's own glue (`modal_app.smoke`, the workflow's `modal run`) had no behavioural test: dropping
  the ledger check, printing instead of raising, or inverting the GPU-optional switch all kept CI green; nor was
  `pipeline_worker_smoke`'s `SAFECUT_AUDIT_GPU` wiring pinned →
  `test_the_pre_deploy_smoke_blocks_the_deploy_on_any_problem` (the raw local entrypoint with stand-in remote
  functions: a healthy run passes; a broken ledger, a refused GPU probe or a failed job raises; the switch only turns
  a GPU problem into a warning) and `test_the_worker_smoke_reaches_the_deployed_gpu_only_when_asked` (the raw
  function with a stand-in `subprocess.run`: replay, its own ledger, the GPU audit exactly when asked). All five
  mutants named above, plus a pre-deploy smoke that asks for the deployed GPU path, now fail.

## Round 27 (on d8af516): 0 critical, 0 high, 1 medium, 1 low. All closed. Not clean.

The round-26 tests killed their mutants (the ledger check dropped, the switch forced, the GPU env hard-wired).

- M1 the pre-deploy GPU probe inside `pipeline_worker_smoke` was still unpinned (the stand-in run wrote no audit, so
  the probe block never ran) → the stand-in run now writes the job's outputs, and the test checks the probe runs
  exactly before a deploy, on the run's render (its SHA-256), through a handoff on the `/audit` Volume that it then
  closes. Fails when the condition is inverted, the close dropped, or the jobs Volume's commit passed.
- L1 the ledger-folder check didn't rule out the jobs Volume → it must be under the temp root and not under `JOBS`.

## Round 28 (on 79fb98b): 0 critical, 0 high, 3 medium, 3 low. All closed. Not clean.

The reviewer mutated the Modal glue one function at a time (`cleanup`, `egoblur_detect`, the ledger smoke,
`_keepalive`, the `SafeCutApi` methods, the local entrypoint): all killed but the survivors below. Each survivor
below now fails its test (11 mutants, re-run after the fix).

- M1 `pipeline_worker_smoke`'s result keys and its failed-run path were unpinned (a renamed key would fail or be
  waived only on a live deploy; round 27's change had dropped the failed-run case) → the test runs four cases (GPU
  audit on or off, the run passing or failing), checks the exact key set, and feeds the result through
  `pre_deploy_problems` / `post_deploy_problems` (a healthy result has no problems; a failed run is reported, not
  raised).
- M2 the `child_env` wiring was unpinned at both call sites (in this sandbox it is the identity) → a stand-in
  `child_env` must reach the child's environment in `pipeline_worker_smoke` and in the demo build
  (`test_the_demo_build_runs_in_an_environment_that_reaches_modal`).
- M3 `egoblur_detect` could gain Modal-level `retries` or a longer `timeout` unnoticed → no `retries`, a 10-minute
  limit above the API's 300 s wait.
- L1 the pre-deploy probe's request wasn't validated → it must pass `GpuRequest` (every frame, EgoBlur Gen 2).
- L2 the probe's wait and the smoke's run timeout were unpinned → the probe waits `GPU_PROBE_TIMEOUT_S`, the run 15
  minutes, both (with two handoff commits) inside the function's 25.
- L3 `_retry_gpu` rebuilt a `yunet-face` demo every six hours though the GPU is never meant to audit it → one
  predicate, `safecut.audit.gpu_wanted`, decides for both `choose_detector` and `_retry_gpu`
  (`test_a_yunet_demo_is_never_rebuilt_for_the_gpu_when_the_gpu_isnt_meant_to_audit`).

## Round 29 (on 8142cb4): 0 critical, 0 high, 0 medium, 3 low. All closed. Not clean.

Round 28's `_retry_gpu` predicate and reworked smoke tests were mutation-checked (killed). Full suite on 8142cb4:
`1634 passed, 12 deselected`.

- L1 the GPU predicate was only used in two of its six places: with `yunet-face` and `SAFECUT_AUDIT_GPU=1` (the API
  image's default) the up-front estimate still reserved $0.245 of GPU per job, `/healthz` claimed the GPU auditor
  and the demo carried the GPU stamp → one property, `Settings.audit_on_gpu` (replacing round 28's `gpu_wanted`), for
  the detector, the audit record, the estimate, the demo's rebuild and stamp, and `/healthz`
  (`test_a_yunet_auditor_is_never_priced_or_reported_as_the_gpu`).
- L2 the GPU meter's never-raise paths, the non-object answer, a failing cancel, and a demo whose audit can't be read
  were unpinned → `test_the_gpu_meter_never_raises_after_a_call`, `test_a_gpu_answer_that_isnt_an_object_is_an_error`,
  `test_a_cancel_that_fails_still_reports_the_timeout`, `test_a_demo_whose_audit_cant_be_read_is_rebuilt`.
- L3 `JobStore.get`'s corrupt-state fallback was unpinned → `test_a_corrupt_job_state_reads_as_not_found` (404, not
  500). All 11 mutants named here fail their tests.

## Round 30 (on 71354e3): 0 critical, 0 high, 1 medium, 4 low. All closed. Not clean.

The round-29 tests killed five of the seven `audit_on_gpu` consumer mutants; about 30 more glue mutants were killed.
Full suite on 71354e3: `1640 passed, 12 deselected`.

- M1 `test_a_render_queued_after_a_long_review_is_resumed_not_failed_as_stalled` was flaky (reproduced under load):
  its stand-in "dead" container still ran the render after the gate opened, racing the successor on one job folder →
  the old container's action never runs (as a container that went away); 9 of 9 runs pass with three at once.
- L1 `hold`'s two-poll guard was unpinned → `test_hold_waits_two_polls_before_it_resumes_a_job` (untracked once,
  then tracked: no resume; fails with a one-poll guard).
- L2 a retried render or audit kept its resume count, so a job failed as "stopped 4 times" failed again at the next
  container loss → `render` and `audit` reset it as `start` does; all three pinned
  (`test_a_retry_starts_the_resume_count_afresh[start|render|audit]`, each failing without its reset).
- L3 the deploy check's cold-wake margin was unpinned → a container up 60 s with no wait must fail
  `DEPLOY_EXPECT_COLD=1`.
- L4 round 29's "audit record" claim was unpinned (`_record` could take `audit_gpu` again) →
  `test_a_yunet_auditor_never_reaches_or_records_the_gpu` (an audit run with `yunet-face` and `SAFECUT_AUDIT_GPU=1`:
  no GPU call, no `gpu.json`).

## Round 31 (on 7962115): 0 critical, 0 high, 0 medium, 0 defects. CLEAN.

From here each round reports defects (bugs, races, flaky tests, wrong claims, gate-scan hits, weakened tests); an
untested path in correct code is recorded as a note, not a finding. Rounds 26–30 had turned into an open-ended
mutation hunt that always surfaces one more unpinned path; the defects it found are fixed and logged above.

Round 30's fixes checked: each `resumes` reset fails exactly its own case when removed; the deflaked resume test
passed every parallel run; the two-poll, cold-wake-margin and `yunet-face` audit tests fail on their mutants. About
45 more mutants killed; the survivors are equivalent or log-only. Full suite on 7962115: `1646 passed, 12 deselected`.

- Note (not a defect): `Worker._requeue`'s code re-check when a delayed re-queue fires has no test of its own (it
  predates this lane: SHIP's 5c79cfe; this lane's `recover` relies on it, and the code is correct). Left as a
  follow-up in the PR rather than reset the audits for a test of SHIP's code.
