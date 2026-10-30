# Lane SAFECUT-SHIP: integration, service, web, eval, submission (WP5 + WP6 finish + WP7 + WP8)

**TAG** `SAFECUT-SHIP` · **Branch** `lane-ship` · Read `.agent/briefs/COMMON.md` first; it applies in full.

**You are the integrator.** The entry is done only when `scripts/entry-check.sh` passes on `main`. You own that script and you keep `main` green.

## Order (do 1 and 2 within your first two hours and merge them)

1. **`scripts/entry-check.sh`**: one check per E-line in `.agent/ENTRY-DONE.md`, printing `E<n>: OK|FAIL <reason>` and then `ENTRY: PASS|FAIL (<n>)`. It runs from a fresh clone, blocks the network for E3, and is bounded in time. It must fail honestly today. Add a test that the script refuses to report PASS when any check fails.
2. **`safecut/cli.py`**:
   - the subcommand registry;
   - `run(job_dir, *, replay)` stubs for every stage that SENSE and SAFETY replace;
   - `safecut run <clip> --out <dir> [--replay] [--auto-approve-policy]`.

   Merge both to `main` so the other lanes build against them.
3. **`pipeline.py`** (WP5 step 1):
   - idempotent, resumable stages;
   - `job_log.jsonl` timings;
   - the USD cap before each paid stage;
   - zero network in replay;
   - a stop for review, then render.

   Wire in each real stage as SENSE and SAFETY merge, and keep E2 and E3 green on `main` after every merge.
4. **The API** (WP5 step 2) and **demo mode** (step 5): every route, both auth paths, the rate limit, caps, upload limits, CORS, deletion and `/healthz`. Precomputed hero/demo jobs replay through the same API with `"mode": "replay"`. This is E5.
5. **The web app on the real API (E6):**
   - Finish the WP6 handoff items: run its Playwright e2e and fix it, and write `web/README.md`.
   - Switch `/try` and the job pages to the real `SafeCutClient` against the API, keeping `MockBackend` for unit tests only.
   - Implement WP6's "Requests for other WPs" in the API: `eta_s`, `stage_reason`, the result and demo route shapes, the publish postMessage contract, `removed_by_creator`, `spot_id`.
   - Playwright against a locally started API in replay, with axe clean.
6. **Deploy-ready (E7):**
   - `deploy/modal_app.py`: ASGI, a worker, a Volume, the 24 h deletion cron, and an optional GPU EgoBlur function;
   - `.github/workflows/deploy.yml`, which skips with a notice when its secrets are missing;
   - the web app's Vercel settings;
   - `scripts/deploy-check.sh`.

   If the Modal or Vercel secrets exist, deploy and put the URLs in the README.
7. **Eval (E9, WP7):**
   - label loader and validator, and the split freezer;
   - pure metrics with unit tests;
   - the six variants;
   - `eval/run.py`, including the 3-run cap and refusal on a hash mismatch for `test`;
   - the SA-Co/VEval SmartGlasses public-split loader (CC BY 4.0), if the network allows it;
   - `eval/report.py` → `eval/RESULTS.md` plus charts.

   Commit at least one run per variant on synthetic/public data. SENSE and SAFETY build the baselines that sit in their stages; you own the harness.
8. **The submission package (E10, WP8), drafted from Nov 2 and final by Nov 3 18:00 UTC:**
   - `README.md`;
   - `docs/AGENTIC-LOOP.md`, from a real (or clearly labelled synthetic) trace;
   - `docs/SUBMISSION.md`, with fields from `docs/OFFICIAL-GUIDE.md`;
   - `docs/VIDEO-SCRIPT.md` (≤ 3:00, every number from RESULTS);
   - `docs/LAUNCH.md` (an X thread for the Most Viral bonus, LinkedIn, a 20 s vertical, YouTube).

   Also plan for the bonus prizes that fit: Best Agentic Use-Case (the closed loop), Best Build on Meta Open-Weight Models (the `open_weight.py` path), Community Vote.
9. **E11 hygiene and E12**: the root `BLOCKED.md`, merged from every lane, with exact owner steps.

## Done for this lane

`ENTRY: PASS` on a fresh clone of `origin/main`. Until then, take failing E-lines in this order: E3, E2, E5, E6, E7, E9, E10, E11, E12.

After every merge by any lane, re-run the entry check on `main`. Repair integration breakage first, whoever caused it.
