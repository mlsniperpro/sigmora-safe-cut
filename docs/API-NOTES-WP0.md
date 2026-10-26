# Meta Model API notes: WP0 results (D1)

This file extends PRE-A's `docs/API-NOTES.md` (PR #1, not merged yet). It becomes that file's §13 once PR #1 lands; it's a separate file until then so the two PRs don't conflict.

**Status on 2026-10-26:** the client, probe runner and replay tests are built and green. **The live probes haven't run**, because this cloud environment has no `MODEL_API_KEY` (`.agent/win/SAFECUT-WP0/BLOCKED.md`). Every number below is labelled with where it comes from. Nothing here is a measured model-quality result yet.

## 13.1 What was verified live today (no key needed)

| Check | Result | How |
|---|---|---|
| `GET https://api.meta.ai/v1/status` (free, unauthenticated) | `{"is_alive": true, "service_status": "operational", "model_statuses": []}` | `curl` from this sandbox, 2026-10-26 16:2x UTC |
| Prices on [dev.meta.ai/docs/pricing-rate-limits](https://dev.meta.ai/docs/pricing-rate-limits) | Spark 1.3: $1.25 / $0.15 cached / $4.25 per M; Wonder 1.0: $4.00 / $0.20 / $20.00; Voice Transcribe $0.18/h; SAM $0.20 per 1k video frames, $2.50 per 1k images. **Same as PRE-A's 2026-10-25 read** | Page fetched 2026-10-26; `config.PRICE_TABLE_DATE = "2026-10-26"` |
| Muse Spark Open on Baseten ([library page](https://www.baseten.co/library/muse-spark-open/)) | $1.25 / $0.15 cached / $4.25 per M; inputs text, image, video and audio; OpenAI Chat Completions at `https://inference.baseten.co/v1/chat/completions`; hackathon model ID `meta-models/muse-spark-open-1026` (official guide) | Page fetched 2026-10-26 |
| `meta-sam-parser` 0.1.0 API names (PRE-A §1.5) | Confirmed: `parse_responses_stream`, `video_segmentation_format`, `SegmentationBoxRecord` (`object_id`, `frame.frame_index`, half-open `left/top/right/bottom`, `confidence`), `SegmentationMaskRecord`, `build_object_prompt`, `decode_mask_to_rle`. Delta events need `item_id`, `output_index` and `content_index` | Installed package; `tests/test_fixtures_api.py` reproduces vectors S1 and S3–S7 |

## 13.2 Probes a–h: built, waiting on the key

`uv run python -m scripts.probes.probes all` runs them in order. Each writes `fixtures/probes/<x>/summary.json` plus its raw responses, logs spend to `fixtures/probes/cost.jsonl` under a $6.00 cap (enforced by the ledger, with a `budget:` line if hit), and deletes its uploads. `tests/test_probes_replay.py` runs all eight against mocked APIs on every CI run.

| Probe | What it measures | Clip or input | Modelled cost |
|---|---|---|---|
| a | `GET /v1/models`: enabled IDs, missing ones, any `-contributor` listed | none | $0 |
| b | SAM 3.1 per concept (`red square`, `blue square`, `face`, `license plate`): latency, records, frame order, confidence presence, mask encoding, **mask size = box size**, `usage.video_frames_processed`, mean IoU against `truth.json`; whether `input_video.fps` is accepted and what it bills | `counter_30fps_audio.mp4` (90 frames) | 5 × 90 × $0.0002 = $0.09 |
| c | Muse Spark 1.3 (`medium`) on the video: **the frame-number probe** (the number visible in the bar when the red square's centre crosses the middle; truth: frame 65), whether the beep is heard and its frames (truth 30–44), input tokens (the hosted sampling rate) | same clip | ≤ $0.08 |
| d | Voice Transcribe `DIARIZATION`: request shape, `audioDurationMs`, turns on a tone (diarization quality needs speech, so hero clips) | WAV from the clip | $0.0001 |
| e | Muse Spark 1.2 (effort `omit`) on the same video: does it hear the beep through `input_video` | same clip | ≤ $0.08 |
| f | Spark 1.3 `max` vs Wonder 1.0 `max` vs Wonder `medium` on probe c's question: accuracy, latency, cost | same clip | ≤ $1.07 |
| g | Muse Spark 1.3 point on a red dot in a 1280×760 image (40 px bar): the 0–1000 grid, clamping, error in px after PRE-A §5's mapping | synthetic image | ≤ $0.07 |
| h | The same point question on Muse Spark Open (Baseten) | synthetic image | ≤ $0.07 |

Modelled worst case ≤ $1.47 (the reservations; real usage is lower), well under the $6 WP0 budget. Hero-clip runs of b, d and f (real faces, real speech) add about $1.20 and wait on `SAFECUT_CLIPS_URL` (BLOCKED.md).

## 13.3 Recommendations (provisional: from prices and PRE-A's research, not yet from probes)

| Setting | Default in `config.py` | Why, with numbers | What would change it |
|---|---|---|---|
| `SAFECUT_SCENE_MODEL` | `muse-spark-1.3` (`medium`) | Wonder costs 3.2× per input token ($4.00 vs $1.25) and 4.7× per output token ($20 vs $4.25). A 30 s scene pass (≈ 65k input, 4k output, PRE-A A4) costs ≈ $0.10 on Spark and ≈ $0.34 on Wonder. Wonder is a preview | Probe f: Wonder `medium` beats Spark `medium` on frame error by ≥ 2 frames, or catches what Spark misses on the hero clips |
| `SAFECUT_ESCALATE_MODEL` | `muse-spark-1.3` (`max`) | Worst case per escalation: Spark `max` ≈ $0.23 (17k in, 48k out cap, vector C4) vs Wonder `max` ≈ $0.55 (24k out cap). Escalation runs once per disputed track per window, so the gap multiplies | Probe f at `max` plus PRE-A's H2 role sets |
| `SAFECUT_SPEECH_SOURCE` | `asr` (Muse Voice Transcribe) | $0.0015 per 30 s vs ≈ $0.10 for the Spark 1.2 soundtrack fallback (≈ 2,200 tokens/s of video); it gives diarized turns with ms timestamps; Spark 1.3's audio is documented as not fully supported | Probe d on hero speech: diarization error, or turn times off by > 0.5 s against the burned-in counter |

## 13.4 Client facts other WPs build on

- **Retries:** 4 attempts (Responses up to `high`, ASR, Files); 2 (Responses `xhigh`/`max`, SAM, ASR 500). Backoff 1, 2, 4… s capped at 30 s, plus jitter; `Retry-After` is honoured up to 120 s and a longer one stops the call. 504 is never retried.
- **Breaker:** 5 calls failed after all their attempts within 60 s open it for 60 s; then one trial call. Auth, billing and 4xx errors don't count.
- **Cost lines:** rejected before processing (any HTTP error status, connect errors) → `usd 0`; accepted then lost (read timeout, a stream cut after it started, cancellation) → the reserved estimate with `estimated: true`; completed → the measured `usage` cost. `contracts.measured_usd` sums them apart (AGENTS rule 9).
- **Budget stop:** a call whose worst-case estimate doesn't fit a cap is never sent; a `budget:<stage>` line names the cap (`job`, `daily`, `code`, `pilot_pool`, `test_line`).
- **Files:** idempotent by SHA-256 through `files.json`; the multipart filename is `<job_id>-<name>`; `expires_after` is 21,600 s; a timed-out upload lists `/v1/files` to find and delete its orphan, or records `orphan: true` (so `files_deleted` can't be claimed).
- **Streaming:** Responses and SAM always stream. A stream with no terminal event is `MetaIncomplete(eof=True)` and retried; a server `incomplete` or a refusal is billed at its usage and not retried.
