AUDITED_COMMIT: e3305d8
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
