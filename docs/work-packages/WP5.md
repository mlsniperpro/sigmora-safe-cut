# WP5: pipeline, API service, Modal deploy, replay/demo mode

**Branch** `wp5-service` · **Wave** C · **Starts** Oct 29, or earlier against stubs · **Depends on** WP1–WP4 interfaces (use their CLI entry points; stub any that haven't merged) · **Budget** ≤ $6

**Owns:** `safecut/pipeline.py`, `safecut/api/`, `safecut/cli.py` (the `run` command and the shared CLI wiring), `deploy/`, `.github/workflows/deploy.yml`, `tests/test_pipeline*.py`, `tests/test_api*.py`.

## Goal

The production service judges and Sigmora call: upload a clip, watch progress, get the review items, submit the creator's decisions, render, and download the redacted video plus the receipt. It has to be safe for the public (caps, access codes, deletion) and observable.

## Steps

1. **Pipeline (`pipeline.py`):**
   - `run(job, until=stage)` orchestrates prepare → track → transcribe → scene → roles (+ miss loop) → decide → guard. It **stops for review**, then `render(job)` runs render → audit (+ patch loop) → receipt.
   - Stages are idempotent and resumable from the job directory, with timings per stage in `job_log.jsonl`.
   - It enforces `SAFECUT_JOB_USD_CAP` before each paid stage. In replay mode it never calls the network.
2. **API (`api/`, FastAPI):**
   - `POST /v1/jobs` → a presigned upload URL plus the job ID.
   - `POST /v1/jobs/{id}/start`.
   - `GET /v1/jobs/{id}` → stage, progress, and the items once ready (decisions + SoM keyframe URLs + reasons).
   - `POST /v1/jobs/{id}/review` → creator edits, through WP3's `apply_review`.
   - `POST /v1/jobs/{id}/render`.
   - `GET /v1/jobs/{id}/result` → signed URLs for `redacted.mp4`, `receipt.html` and `receipt.json`.
   - `DELETE /v1/jobs/{id}`.
   - `GET /healthz`.
   - Auth: either a judge access code (`SAFECUT_ACCESS_CODES`) or a server-to-server key for Sigmora (`SAFECUT_SERVICE_KEYS`). Per-IP rate limit; `SAFECUT_DAILY_USD_CAP`; ≤60 s and ≤150 MB uploads. CORS limited to the web domain.
3. **Modal (`deploy/modal_app.py`):**
   - An image with ffmpeg and the package; the ASGI app; a worker function per job (CPU); an optional GPU function for EgoBlur if WP4 measured CPU as too slow.
   - A Volume for job directories, and a **cron that deletes jobs older than 24 h**.
   - Secrets come from Modal secrets (`MODEL_API_KEY`, access codes, service keys). Never put them in code.
4. **Deploy workflow:** `.github/workflows/deploy.yml` runs `modal deploy` on push to `main`, using the `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` repo secrets (owner step O2). If the secrets are missing, the workflow skips with a notice instead of failing.
5. **Demo mode:**
   - Hero jobs are precomputed and stored with their raw responses.
   - `?demo=1` (or `SAFECUT_REPLAY=1`) replays them through the same API.
   - The response carries `"mode": "replay"` so the UI can label it.
6. **CLI `safecut run <clip> --out <dir> [--replay] [--auto-approve-policy]`:** the full local run, so judges can reproduce results without the web app.

## Tests

- API tests with httpx TestClient in replay mode: the full flow (create → start → review → render → result).
- Auth and cap tests.
- The deletion cron unit test.
- A `-m live` end-to-end run on hero clip 1 through the deployed URL (once O2 is done).

## Done when

- [ ] The full flow passes in replay locally and in CI.
- [ ] Deployed on Modal (or `BLOCKED.md` naming the missing secret), with the URL in the PR. The live end-to-end run on hero clip 1 passes, recording latency and cost.
- [ ] The README gets a "Run it yourself" section (CLI + API) and measured cost/latency per minute of footage, with run IDs.
