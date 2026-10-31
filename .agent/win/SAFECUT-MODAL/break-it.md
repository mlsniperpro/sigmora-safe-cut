TESTED_COMMIT: e52c5be

# SAFECUT-MODAL break-it

What I did to break the lane's two halves (scale-to-zero and the GPU auditor), on `7962115` (the README run on
`4783aeb`, which only adds an audit note), and what came back. `e52c5be` changes only two `noqa` comments' text in
`tests/test_deploy.py` (see `reaudit.md`), which none of these runs reads.
Every command runs from the repo root; outputs are quoted from the runs.

## 1. Kill soak: SIGKILL the scale-to-zero API mid-job, over and over

`N=4 KILLS=2 SEED=7 uv run --no-sync python .agent/win/SAFECUT-MODAL/break-it/killsoak.py` (6 m 35 s).

Each round starts a real local API (uvicorn, replay, the real stages on the synthetic demo clip) on one jobs folder,
starts a job, SIGKILLs the process at a random moment during analysis and again during publishing, restarts it, and
repeats until the job is done. This is a container being reclaimed with no warning, the worst a sleep or a redeploy
can do.

```text
{"job": 0, "job_id": "j_wHBqtoT6kVHyTCQwC7OCNw", "kills_so_far": 3, "stages_done": 10}
{"job": 1, "job_id": "j_0ne3d7kl1zfIM-7OiVc77w", "kills_so_far": 5, "stages_done": 10}
{"job": 2, "job_id": "j_uxTj6S4vgizBOjug8lrkgg", "kills_so_far": 8, "stages_done": 10}
{"job": 3, "job_id": "j_d8Z_Po2eNbob_Gp0u5pqDw", "kills_so_far": 11, "stages_done": 10}
KILLSOAK: PASS (4 jobs, 11 SIGKILLs, every job done, receipts verify, no stage twice)
```

Every job ended `done` with a receipt that verifies; every stage logged exactly one `done` (no finished stage paid
for twice); no job was left mid-action. The suite's own
`test_a_job_finishes_when_its_container_is_killed_mid_analysis_and_mid_audit` does one such kill per phase on every
run.

## 2. GPU fault fuzz: any sequence of GPU failures, the audit still completes and names what ran

`EXAMPLES=300 uv run --no-sync python .agent/win/SAFECUT-MODAL/break-it/gpufuzz.py` (8 m 53 s).

Hypothesis draws a sequence of per-call faults (none, timeout, error, stale Volume) and a weights or GPU problem
(missing weights, altered weights, no GPU), injects a 3-frame leak half the time (so the auto-patch loop re-scans
through the same GPU path), and runs the real audit and receipt against the fake Modal call of
`tests/test_audit_gpu.py`.

```text
GPUFUZZ: PASS (300 examples: every audit completed, named the detector that ran, receipts verify)
```

Invariants held in all 300: `validate_job_dir` passes, `unresolved == 0`, and EgoBlur is named in `audit.json`, the
receipt and `gpu.json` exactly when every scan of the final audit was answered by the GPU; otherwise YuNet, with the
fallback's reason.

## 3. Failure injection in the suite

Beyond the two scripts, the suite injects each failure the brief cares about, and each injection was mutation-checked
during the re-audits (`reaudit.md`): a GPU timeout, an error (retried once), a stale Volume view, missing and altered
weights, no GPU, a cap that can't cover the GPU, a GPU that stops mid-audit (the whole audit re-runs on YuNet), a
handoff commit that hangs, a control plane that stalls on spawn or on cancel, a spawn that returns after the bound, a
keepalive that fails (retried, then left to the cron), a container replaced mid-job and mid-demo-build, a stalled job,
a corrupt rate-limit database, a corrupt job state, a GPU meter whose ledger and cost file fail, a retried render
or audit after "stopped N times", and a restart across the daily cap and the per-hour paid limit. Full suite on
`7962115`: `1646 passed, 12 deselected` in 39 m 3 s.

## 4. The replay end-to-end path, and the cold start

- `uv run safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --out <tmp>/demo --replay --auto-approve-policy`:
  every stage done, audit on YuNet here (no EgoBlur weights in this sandbox), receipt written.
- Web, on `7962115`: `pnpm lint` clean, `pnpm typecheck` clean, `pnpm test` `918 passed (918)`, `pnpm e2e`
  `79/79 checks passed`, including the cold-start scenario against a delayed fake API: the "waking up" line shows,
  nothing errors, axe finds no serious or critical issue, the code is accepted once the API answers, and the waking
  line goes.

## 5. A fresh-clone README run

`git clone --branch claude/charming-meitner-bzjfsz` into an empty folder (HEAD `4783aeb`), then the README's
"Run it yourself" block verbatim (`uv sync --locked`, `safecut run … --replay --auto-approve-policy`,
`eval/run.py --split dev --variant full --replay`): exit 0 in 1 m 35 s; `safecut run` printed
`render done`, `audit done`, `receipt done` and `job demo: done`, and the eval wrote
`20261031T201125Z-dev-full-4783aeb`.

## What this can't break here

A real Modal deploy (the cold wake on Modal's scheduler, EgoBlur on a real L4 or T4): this sandbox can't reach
modal.com. The deploy workflow does both on the owner's next push to main (`BLOCKED.md`, "The Modal deploy").
