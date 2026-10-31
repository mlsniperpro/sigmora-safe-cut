TESTED_COMMIT: 7a533a6

# SAFECUT-SHIP: what we did to break it

Everything here ran against the real service code: `uvicorn --factory safecut.api.app:create_app` in demo mode
(`SAFECUT_REPLAY=1`, the real stages replaying the synthetic demo job, no network), driven over HTTP by
`.agent/win/SAFECUT-SHIP/break-it/breakit.py`, from a git worktree pinned to the tested commit so nothing changed
underneath it. Reproduce with `W=3 N=3 uv run python .agent/win/SAFECUT-SHIP/break-it/breakit.py .`
(`BREAKIT_ONLY=kill` for the restart part alone).

## 1. Soak: concurrent judges, full flows

3 clients × 3 full flows each, concurrently: create (judge code) → signed PUT of the demo clip → start → poll →
2–8 random review edits (keep, hide, merge, remove a person, undo of an earlier edit; every accepted edit
replayed once to prove idempotency) → render → poll → `/result` → GET every signed media URL → DELETE → 404.

| Commit | Flows | Failures | Wall time |
|---|---|---|---|
| 0b1b364 | 9 | **0** | 750 s (two workers per API, on a machine also running the test suite) |
| 5fa2f33 | 9 | **0** | 683 s |
| c3fee0c | 9 | **0** | 665 s |
| cda38bc, 3a029bd, 73806ec | 9 each | **0** | 650–820 s |
| b296a92 | 9 | **0** | |
| 2286b91 | 9 | **0** on the re-run (see the note below) | 521 s |
| eff4422 | 9 | **0** | 561 s |
| 7a533a6 | 9 | **0** | 593 s: the tested commit (= origin/main, all three lanes' final code) |

An earlier 4 × 5 attempt (at f881924's parent) had 2 failures, both `no_recording`: the demo clip changed on disk
mid-run when main was merged into the tree it ran from. That is why every later run uses a pinned worktree.

An unexplained failure, recorded: the first soak at 2286b91 lost its API mid-run (4 of 9 flows: connection reset, then refused), with no server log kept at the time. The harness now keeps the API's own output (`API_LOG`) and prints it on any failure; the re-run on the same commit, with other heavy jobs and two auditors running alongside, passed 9/9, the fuzz and both kill -9 recoveries. No crash path was found in the code; an external kill (an auditor's repro on the same machine) is the likeliest cause, but it isn't proven.

## 2. Fuzz: malformed and hostile requests on every route

1,500 random requests across `codes/check`, `jobs`, uploads, `start`, `review`, `render`, `audit`, `result`,
`DELETE`, media and `demo`, with junk bodies (nulls, 5,000-char strings, NUL, `../../etc/passwd`, huge and negative
sizes, wrong content types, self-merges, undo of unknown edits, cover-spots of unknown spots), forged signatures,
random upload bytes, traversal in media names and IDs.

| Commit | Requests | 5xx | Status mix |
|---|---|---|---|
| 0b1b364 | 1,500 | **0** | 200 ×55, 201 ×3, 202 ×1, 307 ×9, 401 ×13, 403 ×84, 404 ×956, 409 ×66, 413 ×9, 415 ×5, 422 ×299 |
| 5fa2f33 | 1,500 | **0** | the same mix |
| c3fee0c | 1,500 | **0** | 200 ×55, 201 ×3, 202 ×1, 307 ×9, 401 ×13, 403 ×84, 404 ×956, 409 ×66, 413 ×9, 415 ×5, 422 ×299 |
| cda38bc, 3a029bd, 73806ec, b296a92, 2286b91, eff4422, 7a533a6 | 1,500 each | **0** | the same mix |

After the fuzz the fuzzed job and the pinned demo were both intact, and the API process was still alive.

## 3. Failure injection: kill -9 mid-job, twice

A job is started, the API is `kill -9`ed (its whole process group) during analysis, restarted on the same jobs
directory, the job is driven to review and rendered, the API is killed again mid-render and restarted.

| Commit | Result |
|---|---|
| 17e2e9a | **PASS**: killed in analysis at `prepare`, then in render; `Service.recover()` re-queued it both times and it ended `done` |
| 5fa2f33 | **PASS** (the same) |
| c3fee0c | **PASS** (the same) |
| cda38bc, 3a029bd, 73806ec, b296a92, 2286b91, eff4422, 7a533a6 | **PASS** each (killed during `prepare` or `track`, then in render; every job ended `done`) |

The first attempt (0b1b364) failed in the harness, not the service: SIGKILL reached `uv run`, not its uvicorn
child, which kept the port ("address already in use"). The harness now starts the API in its own session and
kills the group.

## 4. Other failure paths, each covered by a test that injects it

| Injected failure | Expected | Test |
|---|---|---|
| A stage thread writing while DELETE runs (20 rounds) | 204, nothing left after the sweep | `test_delete_succeeds_while_a_stage_is_still_writing` |
| DELETE while a stage runs, the stage writes afterwards | Its output is reaped when it returns | `test_what_a_stage_writes_after_delete_is_removed_when_it_returns` |
| A job deleted between a handler's first look and its update | 404, never 500 | `test_a_job_deleted_mid_request_is_a_404_not_a_500` |
| Two concurrent `start`s | The analysis runs once | `test_two_concurrent_starts_run_the_analysis_once` |
| A code revoked across a restart | The resumed job fails `code_not_active` | `test_a_restart_refuses_jobs_whose_code_was_revoked_and_keeps_retry_delays` |
| A transient Meta failure | One re-queue 5 min later | `test_a_transient_failure_retries_once_later` |
| Replay reaching the network (direct, or a loopback proxy) | `NetworkBlocked` | `test_netguard_refuses_a_local_proxy`, E3 under `unshare -rn` |
| A renderer that draws nothing | E3 fails 0/N on every should-hide entity | `test_e3_checks_the_rendered_pixels_not_only_the_plan` |
| An unreadable state file after a schema change | Expires by its own `created_at` | `test_the_sweep_trusts_a_valid_created_at_in_an_unreadable_state` |
| A forged `X-Forwarded-For` behind no proxy | 429 still applies | `scripts/deploy-check.sh` (`test_deploy_check_passes_on_a_healthy_deployment`) |
| Property tests on the policy | ≥ 2,000 examples, 100 % branch coverage | E4 |

## 5. The replay e2e path and a fresh clone

- `pnpm e2e:api` (E6): the built web app in Chromium against the real API, desktop and phone, every judge step
  including the merge of a re-entered guest, axe on every screen: 63/63 at the last run.
- `bash scripts/entry-check.sh` on a fresh clone of origin/main at 7a533a6 printed ENTRY: PASS (every E-line OK,
  including E11's run of the README's fresh-clone block); it is re-run after the final merge for the PR's status.
