# WP0: foundation (scaffold, contracts, Meta client base, D1 probes)

**Branch** `wp0-foundation` · **Wave** A · **Starts** Oct 26 16:00 UTC (kickoff) · **Depends on** nothing · **Budget** ≤ $6 of Meta credits

**Owns:** `pyproject.toml`, `uv.lock`, `safecut/__init__.py`, `safecut/config.py`, `safecut/contracts.py`, `safecut/meta/` (base client), `fixtures/`, `docs/API-NOTES.md`, `scripts/probes/`, `.github/workflows/ci.yml`, `.env.example`, `tests/test_contracts.py`, `tests/test_meta_client.py`.

## Goal

Everything the parallel WPs need on day 1: a package that installs, contracts every stage codes against, a Meta client that works and logs cost, and **real API responses saved as fixtures** so the others can build without spending credits.

## Steps

1. **Scaffold and push first (within about 1 hour, as its own commit):**
   - `pyproject.toml` (Python 3.12, uv) with dependency groups:
     - main: `httpx`, `pydantic>=2`, `numpy`, `opencv-python-headless`, `pillow`, `imageio-ffmpeg`, `typer`, `fastapi`, `uvicorn`, `orjson`;
     - `dev`: `pytest`, `hypothesis`, `ruff`, `respx`;
     - `audit`: `torch` (CPU wheels), `torchvision`;
     - `deploy`: `modal`.
   - `safecut/config.py` with every env var in ARCHITECTURE.md §4, typed, with defaults.
   - `safecut/contracts.py` with a pydantic model for every JSON in ARCHITECTURE.md §3, plus `load(path)` / `dump(model, path)` helpers.
   - Round-trip tests for every contract, using the example JSON from the doc.
   - `.github/workflows/ci.yml`: `uv sync`, `ruff check`, `pytest -m "not live"`, and the web job (`pnpm lint typecheck test` in `web/` if it exists).
   - Open the PR as a draft right away, so Claude can merge the scaffold early for Wave B if the probes take long.
2. **Meta client base (`safecut/meta/`):**
   - `client.py`: httpx, base URL `https://api.meta.ai/v1`, `MODEL_API_KEY`, retries with backoff on 429/5xx, request IDs.
   - `files.py`: upload with `purpose=user_data` and `expires_after: 3600`; delete.
   - `responses.py`: create with `store: false`, streaming, and `text.format` JSON schema.
   - `asr.py`: `POST /v1/asr/transcribe`.
   - `cost.py`: append to `cost.jsonl`; price table from the pricing page as of Oct 26, with the date.
   - Refuse any model ID ending in `-contributor`.
3. **Probes** (`scripts/probes/`, each saving raw responses under `fixtures/probes/<name>/`). Use **consented hero clips only** (from `SAFECUT_CLIPS_URL`). If none exist yet, use 2 short clips from the SA-Co/VEval SmartGlasses split (CC BY 4.0), and record the source and licence in `fixtures/README.md`.
   - **a. Kenya / key check:** `GET /v1/models`, and record which model IDs are enabled.
   - **b. SAM 3.1 video:** 3 clips × concepts `face`, `person`, `license plate`, `screen`. Record the stream format, mask size vs frame size, skipped frames, latency, frames billed, and what `input_video.fps` does. Check whether Meta publishes a Python parser; otherwise document the token grammar exactly for WP1.
   - **c. Muse Spark 1.3 video scene pass** on one clip: max length, whether it handles audio (docs say degraded), and the **frame-number probe**: burn a frame counter into a clip and ask which number is visible when an event happens.
   - **d. Muse Voice Transcribe** on the same clip: diarization quality and turn timestamps vs the burned-in counter.
   - **e. Muse Spark 1.2 audio** on the same clip, as the speech fallback. Compare it with (d).
   - **f. Muse Wonder 1.0 vs Muse Spark 1.3 (max effort):** the same scene question on one clip, plus 5 hard role calls from SoM keyframes (hand-drawn boxes are fine). Compare quality, latency and cost.
   - **g. Image points:** ask Muse Spark for a point on a named object and confirm the 0–1000 grid and the clamping.
4. **`docs/API-NOTES.md`:** exact request and response shapes, limits, latencies, prices, surprises, and **a recommendation with numbers** for `SAFECUT_SCENE_MODEL`, `SAFECUT_ESCALATE_MODEL` and `SAFECUT_SPEECH_SOURCE`. Set those defaults in `config.py` to match.
5. **Fixtures for the others:** trim the saved responses into small, deterministic fixtures (`fixtures/sam/`, `fixtures/muse/`, `fixtures/asr/`), plus 2 tiny synthetic clips (≤3 s, generated with ffmpeg: moving coloured boxes, a burned-in frame counter) for unit tests.

## Done when

- [ ] `uv sync && uv run pytest -m "not live" && uv run ruff check` is green; CI is green on the PR.
- [ ] All contracts are implemented and round-trip tested.
- [ ] Probes a–g ran (or `BLOCKED.md` says exactly which and why). Raw responses for consented clips are under `fixtures/probes/`. API-NOTES.md has the recommendations, with numbers.
- [ ] The PR lists total probe spend from `cost.jsonl`.
