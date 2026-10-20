# WP4: render + audit + privacy receipt

**Branch** `wp4-render-audit` · **Wave** B · **Starts** after WP0 merges · **Depends on** WP0 contracts (`plan.json` comes from WP3; use a fixture until then) · **Budget** ≤ $6

**Owns:** `safecut/render/`, `safecut/audit/`, `safecut/receipt/`, `tests/test_render*.py`, `tests/test_audit*.py`, `tests/test_receipt*.py`, and the CLI subcommands `render`, `audit` and `receipt`.

## Goal

Turn `plan.json` into a redacted MP4 that **can't be reversed**, prove it with an audit over every output frame (patching leaks automatically), and write the privacy receipt the creator can show if a complaint arrives.

## Steps

1. **Render (`render/`):**
   - Read frames (OpenCV), apply each frame's regions: `solid` (opaque fill, mask-shaped when a mask exists), `pixelate` (grid locked to `grid`, ≤6 blocks across, plus per-block noise), and `person_solid` (whole-person mask).
   - Encode H.264 and mux the original audio back (`imageio-ffmpeg`).
   - Gaussian blur exists only as `cosmetic` and is never used by the policy (DESIGN §2.7).
   - Write `redacted.mp4` plus preview thumbnails per item (from the redacted frames only).
2. **Audit (`audit/`):**
   - **EgoBlur Gen 2** (Meta, Apache-2.0) face and plate detectors on **every output frame**. Get the weights from Meta's official source. If the download is gated, write `BLOCKED.md` (owner step O8) and continue with the red-team part.
   - Measure CPU speed. If a 30 s clip at 1280 px takes longer than 3 minutes on CPU, add a Modal GPU function stub for WP5 and note it.
   - A detection that isn't inside an approved-participant region is a **leak**.
   - **Muse Spark red-team:** sample output frames (1 fps, plus all frames near item boundaries) and ask the model to read or identify anything: names, numbers, faces, plates. Use structured output; any hit is a leak.
   - **Auto-patch:** each leak becomes a new hidden item (a box from the detector, padded), then re-render. At most 3 passes; anything left goes in `unresolved`.
   - Write `audit.json`.
3. **Receipt (`receipt/`):** `receipt.json` per ARCHITECTURE.md §3.9 and a self-contained `receipt.html`:
   - every item with a redacted thumbnail, the reason, frames, and who decided;
   - the audit summary;
   - models and versions;
   - data handling;
   - cost.

   Hash chain: `hash = sha256(prev_hash + canonical_json(body))`, with a verifier function plus a test that tampering breaks it.
4. **CLI:** `safecut render|audit|receipt --job …`.

## Tests

- Render: pixel tests on the synthetic clip (inside a solid region = fill colour; grid cells identical across frames for a static object; audio stream present).
- Reversibility check: run a face detector (OpenCV YuNet or EgoBlur) on rendered pixelated faces; detection rate must be ≈0 on the hero fixture.
- Audit: inject a 3-frame leak into a plan and confirm it's found and patched.
- Receipt: hash-chain tests.

## Done when

- [ ] Render → audit → receipt run on the fixture job; `unresolved == 0` on hero clip 1 (live), with the cost recorded.
- [ ] The PR has before/after frames from the consented hero clip, the audit stats, a receipt.html screenshot, and CPU timing for EgoBlur.
