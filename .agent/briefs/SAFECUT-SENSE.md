# Lane SAFECUT-SENSE: perception (WP1 + WP2 + the live path)

**TAG** `SAFECUT-SENSE` · **Branch** `lane-sense` · Read `.agent/briefs/COMMON.md` first; it applies in full.

## Scope

Turn a source clip into `job.json`, `tracks.json`, `transcript.json`, `scene.json` and `roles.json` (ARCHITECTURE §3.1–3.5) that the safety core can trust.

- Execute `docs/work-packages/WP1.md` and `docs/work-packages/WP2.md` in full.
- Use the prompt specs and test vectors in `docs/prompts/` and the API grammar in `docs/API-NOTES.md`.

## Order (highest score impact first)

1. **`prepare`** (WP1 step 1): probe, transcode, per-frame times, 1 fps keyframes, `source_sha256`, limits. Then extend WP0's `safecut/meta/sam.py` into the full streaming parser: hypothesis tests over random valid streams and malformed chunks.
2. **`track`**:
   - a sweep per concept, in parallel;
   - linking that never merges across a gap longer than `gap_merge_frames`, with re-entry as a new ID;
   - densified, labelled gaps and the crowd list;
   - replay from `jobs/<id>/raw/sam/`.

   Prove it on the synthetic counter clips: per-frame IoU ≥ 0.8 against `truth.json`, and a re-entry that yields a new ID.
3. **The synthetic demo job.** A generator writes replay responses for every SENSE call (SAM, Voice Transcribe, scene, role ×3, escalation) from the synthetic clip's `truth.json`. Each is labelled `"synthetic": true` and validated against the same schemas as live responses. This is what E2/E3 and the web demo run on until the key arrives, so build it early and merge it.
4. **`transcribe`**: Voice Transcribe, with the spark-1.2 fallback; turns mapped to frames.
5. **`scene`**: the scene pass, with structured output and `store: false`.
6. **Set-of-Mark keyframes**: deterministic pixel tests; labels legible at 320 px.
7. **`roles`**:
   - three independent votes per track: a track is a participant only on 3/3, and any disagreement makes it `unsure`;
   - escalation at max effort;
   - a child flag on any child vote;
   - screens and documents with a content description.

   The self-consistency logic is pure functions with hypothesis tests.
8. **The miss loop**: at most 2 loops of 3 phrases each, bound by WP3's binding helper once SAFETY merges it, with a local nearest-box fallback until then.
9. **The live path (E8):**
   - a `pytest -m live` test for every Meta call;
   - `scripts/go-live.sh <clip>`, which records a full job's raw responses into `fixtures/jobs/<id>/raw/` under a USD cap and exits 2 with a clear message when `MODEL_API_KEY` is missing.

   If the key is in the environment, run it on the synthetic clips and on any consented hero clip available. Commit the responses and their cost, and replace synthetic replays with real ones where they exist.

## Done for this lane

- Every SENSE stage runs in replay with valid contracts, merged into `main`.
- E2's SENSE stages are OK, and E8 is OK.

Then take failing E-lines in this order: E3 (anything perception-side), E9 (the `detector_only` and `muse_no_track` baselines), E11.
