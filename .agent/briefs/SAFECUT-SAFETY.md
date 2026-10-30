# Lane SAFECUT-SAFETY: decide, guard, render, audit, receipt (WP3 + WP4)

**TAG** `SAFECUT-SAFETY` · **Branch** `lane-safety` · Read `.agent/briefs/COMMON.md` first; it applies in full.

## Scope

Turn `tracks.json` + `roles.json` into `decisions.json` (deny by default), then `plan.json` (leak guard). Render a redacted MP4 that can't be reversed, prove it frame by frame with an audit that patches its own leaks, and write the hash-chained privacy receipt.

- Execute `docs/work-packages/WP3.md` and `docs/work-packages/WP4.md` in full.
- Rules come from `docs/DESIGN.md` §2.5–2.7. Red-team prompts come from `docs/prompts/redteam.md`, and EgoBlur notes from `docs/research/egoblur-gen2.md`.

## Order (highest score impact first)

1. **`decide`:**
   - binding: mask dilation, the nearest box within 0.1 × the diagonal, keyframe votes, Hungarian assignment for conflicts, ties → `unsure`;
   - grouping face + person;
   - the full policy;
   - `apply_review` for creator edits (locked children stay hidden).

   Every rule gets a table test. `policy.py` needs 100% branch coverage. Merge early: SENSE's miss loop and SHIP's review API depend on it.
2. **`guard`** (WP3 step 5):
   - spatial padding;
   - ±8 frames, plus a 15-frame back-fill;
   - a gap hold up to 2 s that grows 2% a frame;
   - the crowd fallback;
   - locked grids.

   The five E4 properties need ≥2000 hypothesis examples each.
3. **`render`**:
   - `solid`, mask-shaped when a mask exists;
   - locked-grid `pixelate` with ≤6 blocks plus noise;
   - `person_solid`;
   - H.264 with the original audio muxed back;
   - thumbnails taken only from redacted frames.

   Pixel tests on the synthetic clip. A reversibility check: a face detector on rendered pixelated faces finds ≈0.
4. **`audit`**:
   - EgoBlur Gen 2 face and plate detectors on every output frame, with weights from Meta's official source. If the download is gated, list it as an owner step and keep a local detector (e.g. OpenCV YuNet) behind the same interface. The audit always runs.
   - CPU timing, with a Modal GPU stub if a 30 s clip at 1280 px takes over 3 minutes.
   - The Muse Spark red-team, replayed from SENSE's synthetic demo job until live.
   - The auto-patch loop: at most 3 passes, the rest into `unresolved`.
   - An injected 3-frame leak must be found and patched.
5. **`receipt`**:
   - `receipt.json` (§3.9);
   - a self-contained `receipt.html`;
   - a hash chain with a verifier, and a tamper test.
6. **Ground-truth scoring for E3**, as a pure function shared with WP7's metrics (coordinate with SHIP; the metric itself lives in `eval/metrics.py`). Coverage per GT box per frame, computed from `plan.json` + audit patches exactly as the renderer applies them.

## Done for this lane

- Every SAFETY stage runs in replay with valid contracts, merged into `main`.
- E2's SAFETY stages are OK, and E4 is OK.
- E3 passes its coverage, over-blur and leak-burst thresholds on the synthetic demo job.

Then take failing E-lines in this order: E3, E9 (the `blur_all`, `egoblur` and `no_audit` baselines), E5's review path, E11.
