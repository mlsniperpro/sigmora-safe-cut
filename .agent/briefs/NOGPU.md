# Lane NOGPU: deploy to Modal with no GPU function (2026-11-04)

Deadline: the hackathon closes **2026-11-05 02:00 UTC**. This lane must be **merged to `main` by 2026-11-04 14:30 UTC**.
Read `AGENTS.md`, `.agent/briefs/COMMON.md` and `BLOCKED.md` first. Branch: `lane/nogpu` (this file is its first commit).

## Why

Modal refuses the owner's card. Without a payment method Modal refuses **the whole app** when it merely *defines*
a GPU function: `modal deploy` / `modal run` of any app with `@app.function(gpu=...)` fails with
`InvalidError: Please add a payment method to use T4 GPU functions.` (verified 2026-11-04 with a probe app that
defines a GPU function it never calls). CPU-only functions run fine without a card (also verified). Every deploy run
since 2026-11-01 passed all release checks and then died on exactly this (runs 41455209402, 41337733883).

The owner may still get a card accepted. So the fallback must be a **deploy-time switch whose default keeps today's
behaviour** (GPU on, EgoBlur Gen 2 on L4/T4): merging this lane must change nothing unless the switch is flipped.

## What to build

1. **A deploy-time switch in `deploy/modal_app.py`**: an environment variable read at import time on the deploying
   machine, `SAFECUT_DEPLOY_GPU` (default `"1"`). With `"0"`:
   - `egoblur_detect` (the `gpu=["L4", "T4"]` function) and the `gpu_image` it needs are **not registered on the app at
     all** (no `@app.function(gpu=...)` anywhere in the app), so Modal accepts the deploy with no payment method;
   - the API image's env sets `SAFECUT_AUDIT_GPU=0`, so the audit runs the bundled YuNet face detector in the API
     container (plates left to the Muse Spark red team, exactly as the existing GPU-outage fallback already does);
   - the pre-deploy smoke (`smoke`, `pipeline_worker_smoke`, `_probe_gpu`) skips the GPU probe and reports
     `gpu: none (SAFECUT_DEPLOY_GPU=0)` instead of failing; `deploy/checks.py` and `deploy/verify_deploy.py` accept a
     YuNet audit in this mode (the existing `SAFECUT_DEPLOY_GPU_OPTIONAL` / `DEPLOY_YUNET_OK` paths show how);
   - the deletion cron, volumes, secret, scale-to-zero (`min_containers=0`, scaledown windows) stay exactly as they are.
   Check that the API container (cpu/memory/timeout in `modal_app.py`) has enough headroom to run YuNet over a 60 s
   clip in-process; size it up only if a measured or reasoned need says so, and update `docs/DEPLOY-COSTS.md` /
   `deploy/costs.py` if you do.
2. **The workflow**: `.github/workflows/deploy.yml` passes `SAFECUT_DEPLOY_GPU: ${{ vars.SAFECUT_DEPLOY_GPU }}` into
   the job env (empty = default on), and every GPU-specific step/assertion follows it (with `0`, GPU checks are skipped,
   not warned). If the cloud git proxy refuses a push that touches `.github/workflows/`, do NOT fight it: make the
   switch also honour `SAFECUT_DEPLOY_GPU_OPTIONAL=nogpu` (the variable the workflow already passes) and say so in
   the PR and BLOCKED.md.
3. **Honesty in the product and docs**: the receipt and `audit.json` already name the detector that ran; make sure
   nothing user-facing (web copy, README "What each Meta model does here", `docs/SUBMISSION.md` "Meta models used")
   claims EgoBlur ran live when the switch is off. In `docs/SUBMISSION.md`, give the owner two paste-ready variants of
   the EgoBlur sentence: GPU on (as today) and GPU off ("EgoBlur Gen 2 runs in the offline/GPU deployment path; the
   hackathon's live service audits every frame with YuNet because …" — keep it factual and short).
4. **BLOCKED.md**: replace the Modal payment item's text with the two routes: (a) card added → re-run deploy;
   (b) no card → set repository variable `SAFECUT_DEPLOY_GPU=0` (and whatever else your design needs), re-run the
   `deploy` workflow on `main`. Keep `scripts/entry-check.sh` E12 passing (it greps for certain phrases; read `e12` in
   `scripts/entry_check.py`).

## Tests and gate

- Unit tests: importing `deploy.modal_app` with `SAFECUT_DEPLOY_GPU=0` registers no function with a `gpu` setting and
  sets `SAFECUT_AUDIT_GPU=0` in the API image env; with it unset the app is unchanged (GPU function present). Test the
  checks/verify code paths for both modes. Follow the existing deploy tests' style (`tests/`).
- Green before merging, on a fresh clone of the merge result: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pyright`, the offline `uv run pytest`, `uv run python eval/report.py --check`, and `bash scripts/entry-check.sh`
  (ENTRY: PASS). You cannot reach modal.com from the sandbox; do not try to deploy.
- Merge: rebase on `main`, `--no-ff` merge into `main`, push. One squashed, substantial commit on the branch plus the
  merge is ideal. Every push to `main` starts the deploy workflow; that is expected (it will fail at the GPU step
  until the owner flips the variable or adds a card; not your problem).

## Rules

- Do not set repository variables or secrets, do not touch Modal, do not change `safecut-secrets`. The owner side does.
- Do not change behaviour with the switch unset. Do not refactor unrelated code. No new dependencies.
- Never ask, never wait: decide by the principles in COMMON.md. When merged with ENTRY: PASS, write a 5-line summary
  as the last message (commit SHA, what the owner must set, test count) and stop.
