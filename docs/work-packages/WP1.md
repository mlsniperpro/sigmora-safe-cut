# WP1: prepare + SAM 3.1 tracking

**Branch** `wp1-track` · **Wave** B · **Starts** after WP0 merges · **Depends on** WP0 · **Budget** ≤ $8

**Owns:** `safecut/prepare.py`, `safecut/track/`, `safecut/meta/sam.py` (stream parser), `tests/test_prepare.py`, `tests/test_track*.py`, `fixtures/sam/*` (additions), and the CLI subcommands `prepare` and `track`.

## Goal

From a source clip to `job.json` + `tracks.json` (ARCHITECTURE.md §3.1–3.2) that the rest of the pipeline trusts: every sensitive object found by SAM 3.1, per concept, with stable track IDs, and with re-acquired objects always as **new** IDs.

## Steps

1. **`prepare.py`:**
   - ffprobe, then transcode to H.264 MP4 with `-movflags +faststart`, the long edge ≤ 1280 (tune per API-NOTES), and constant fps, keeping audio.
   - Write per-frame source times, extract keyframes at 1 fps, record `source_sha256`.
   - Reject clips > 60 s or > 150 MB with a clear error.
2. **`meta/sam.py`:** a streaming parser for SAM 3.1's special-token output (the grammar in API-NOTES.md / DESIGN §2.2): frame index, boxes, and masks (decode to RLE, upscale masks to the frame size). Handle skipped frames and partial chunks. Property-test it with hypothesis over random valid streams and malformed chunks.
3. **`track/sweep.py`:**
   - Upload once (Files API), then run **one request per concept** in parallel: `face`, `person`, `license plate`, `screen`, `phone`, `document`, `name badge`, plus any extra phrases passed in (the miss loop from WP2 calls this with Muse-proposed phrases).
   - Record `frames_billed` and USD per request. Delete the file afterwards.
4. **`track/link.py`:**
   - Turn the per-frame detections into tracks: `concept:id`, first/last frame, boxes and masks per frame.
   - **Never merge across a gap longer than `gap_merge_frames` (default 2)**; a re-acquired object is a new track, with `reentry_of` set as a hint only.
   - Densify short gaps by linear box interpolation, marked as interpolated.
5. **Crowd detection:** a frame whose detections hit the 16-object cap for a concept is listed in `crowded_frames`. Optionally (P1), run a windowed second pass over tiles for those frames.
6. **CLI:** `safecut prepare <clip> --job jobs/<id>` and `safecut track --job jobs/<id> [--concepts …] [--replay]`.
7. **Replay:** with `--replay` or `SAFECUT_REPLAY=1`, read saved responses from `jobs/<id>/raw/sam/` instead of calling the API. Save every live response there.

## Tests

Unit tests on WP0 fixtures (no network), then one `-m live` integration test on a consented hero clip. On a synthetic clip with known boxes: per-frame box IoU ≥ 0.8 with ground truth, and re-entry produces a new ID.

## Done when

- [ ] `safecut prepare` + `safecut track --replay` produce valid `job.json` / `tracks.json` from fixtures; the contracts validate.
- [ ] The live test on hero clip 1 passes and records the cost; `tracks.json` for it is committed under `fixtures/jobs/hero1/` (consented clip only).
- [ ] The PR reports latency and cost per concept for a 30 s clip.
