# Lane SAFECUT-MODAL: the Modal service sleeps when idle, and EgoBlur runs on a GPU (owner-set, 2026-10-31)

**TAG** `SAFECUT-MODAL` · Read `.agent/briefs/COMMON.md` and `.agent/ENTRY-DONE.md` first; both apply in full. Main is at `ENTRY: PASS` (E1–E12). Keep it there after every merge.

## Why

- **Budget.** The owner's Modal budget is small (the Starter plan's monthly credit, possibly only $1 today). The API container is always on (`min_containers=1`, 2 cores, 4 GiB). At `modal billing rates` (CPU $0.0473 per core-hour, memory $0.008 per GiB-hour) that is $0.127 an hour, about $3 a day. **Owner decision: the service sleeps when no one uses it.**
- **Meta tooling (25 points).** The deployed audit runs the bundled YuNet because the container has no GPU. EgoBlur Gen 2 on a GPU makes every judge's render "audited by Meta's EgoBlur".
- **The weights are already uploaded.** The owner's Modal Volume `safecut-models` holds them at `/egoblur/` (mounted at `/models`, so `/models/egoblur/…`). SHA-256:
  - `ego_blur_face_gen2.jit`: `2ba183ff74a66752f6457846efb4379b351727d1c9eaef461ed4be8db18cc2e8`
  - `ego_blur_lp_gen2.jit`: `1d6b3fc37fce4158d3b7d4a364290cfeeccc86a9cd84a376c443d560f11497f4`
- **Your sandbox can't reach modal.com.** Build and prove everything with fakes and tests. The owner's side deploys through `.github/workflows/deploy.yml`; its `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` repo secrets are set.

## 1. Scale to zero (`deploy/modal_app.py`, the API, the web app)

- **`api`:**
  - `min_containers=0`, with a `scaledown_window` you justify.
  - Keep `max_containers=1`: the in-process limits and the SQLite ledger depend on a single container.
  - Size cpu and memory to what one container really needs.
- **A started job always finishes, even if the browser tab closes.**
  - Modal scales a container down once it has no in-flight *inputs* for `scaledown_window`. A worker thread is not an input.
  - Research Modal's documented options and pick the most robust: keeping an input open for the job's lifetime, a spawned function on the same Volume, the 15-minute cron resuming stranded jobs, or something better.
  - Prove the pick with a test that kills or scales down the container mid-job and shows the job completes with the right result and receipt. No double spend, and no job stuck forever.
- **Cold start is a designed state, not an error.**
  - Measure the import path and cut it: lazy imports, nothing heavy at module import.
  - The web app's first request tolerates a cold start (timeouts, retries), and the UI says the service is waking up, per `docs/UI-SPEC.md` tone. Cover this in Playwright with a delayed fake API.
  - The labelled demo job still opens instantly after a wake.
- **State that must survive a sleep:**
  - The daily USD cap and the spend ledger already live on the Volume; prove it still holds across a restart.
  - Per-IP rate limits: either persist them on the Volume, or show in a test that a restart can't be abused to exceed the daily cap. Record the decision.
- **The cron.** `cleanup` stays, at the smallest cpu and memory Modal allows, so idle cost is close to $0.
- **Docs.** Write an idle and per-job cost table in `web/README.md` (or the deploy docs) and `docs/SUBMISSION.md`, from `modal billing rates` numbers, labelled as estimates.

## 2. EgoBlur Gen 2 on a GPU (`deploy/modal_app.py`, `safecut/audit/`)

- **A GPU function** (for example `egoblur_detect`):
  - the image with the `audit` group (torch + egoblur, pinned as in `pyproject.toml`);
  - `/models` from `safecut-models` and `/data` from `safecut-jobs`;
  - `min_containers=0` with a short `scaledown_window`;
  - the GPU type chosen on cost and speed (T4 $0.59 an hour, L4 $0.80 an hour), recorded in Decisions with sources.
  - It reads the rendered frames or video from the jobs Volume (commit before the call, reload inside it), not huge payloads over the wire.
  - It verifies the weights' SHA-256 before use.
- **The API container stays slim:** no torch in it.
  - The audit stage calls the GPU function when a setting (for example `SAFECUT_AUDIT_GPU=1`) is on.
  - The auto-patch loop re-audits through the same path.
  - Include GPU seconds in the per-job cost estimate, the up-front cap check and the ledger.
- **The audit always runs.**
  - If the GPU call fails, times out or finds no weights, YuNet runs instead.
  - `audit.json` and the receipt name the detector that actually ran (`audit.egoblur.model`, `auditor`). Never claim EgoBlur when it didn't run.
  - Test every branch with a fake Modal call: success, timeout, error, missing weights, hash mismatch.
- **Deploy checks.**
  - Extend `scripts/deploy-check.sh` and the workflow's smoke step so a real deploy proves:
    - a cold wake;
    - one replay job end to end;
    - EgoBlur on the GPU named in its receipt.
  - It must still skip with a notice when secrets are missing.
- **Owner list.** `BLOCKED.md` gets exact owner steps for anything new, such as the `SAFECUT_AUDIT_GPU` value in `safecut-secrets`. Drop the EgoBlur-weights line: the weights are uploaded.

## Done

Every check here only adds or tightens. Never weaken an E-line, a test or a threshold. `tests/test_deploy.py` gains assertions for `min_containers=0`, `max_containers=1`, the GPU function, the fallback and the cost accounting.

The goal is met when all of the following hold:
- **The gate passes on main.** `bash .agent/win-gate.sh SAFECUT-MODAL` prints `GATE: PASS` on the HEAD you merged into `origin/main`. Set up `.agent/win/SAFECUT-MODAL/` as the other lanes did: `checks.sh`, the checklist, re-audits with two clean in a row, and break-it.
- **The entry check passes on a fresh clone.** `bash scripts/entry-check.sh` prints `ENTRY: PASS` on a fresh clone of `origin/main`.
- **Your PR carries the final status.**

Target: merged by 2026-11-01 18:00 UTC. Hard stop: 2026-11-03 12:00 UTC (feature freeze).
