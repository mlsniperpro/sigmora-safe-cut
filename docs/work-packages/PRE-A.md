# PRE-A: pre-event research (API notes, prompt specs, infrastructure facts). DOCS ONLY

**Branch** `pre-a-research` · **Runs** NOW (before kickoff) · **Budget** $0 (no API key; no paid calls)

This package is allowed before Oct 26 12:00 ET **because it produces documents only**. Don't write Python, TypeScript, notebooks, config files, or anything executable. Markdown and JSON-schema examples inside markdown only. WP0 turns this into code at kickoff.

**Owns:** `docs/API-NOTES.md`, `docs/prompts/` (markdown specs), `docs/research/` (markdown).

## Steps

1. **`docs/API-NOTES.md`, from Meta's public docs at `dev.meta.ai/docs`.** Record what each page says (with the URL and the date read) for:
   - **SAM 3.1:** segmenting video and images, reading the special-token stream (the exact grammar for frame, box and mask tokens; mask encoding options), client libraries (is there a Python parser? its package name and API), limits (frames per request, objects per frame, file types), the `input_video.fps` field, and pricing.
   - **Files API:** upload (`purpose`, `expires_after`), retrieve, delete, size limits.
   - **Responses API:** video, image, audio and PDF input parts; `text.format` json_schema with `strict`; `store: false`; `reasoning.effort` levels per model; streaming; error codes; rate limits.
   - **Muse Voice Transcribe:** `POST /v1/asr/transcribe` request and response (diarization flags, turn timestamps, languages, file limits) and pricing.
   - **Image understanding:** the point/box output format, the 0–1000 grid and its edge cases.
   - **Pricing and rate limits** for `muse-spark-1.3`, `muse-spark-1.2`, `muse-wonder-1.0`, `muse-voice-transcribe-1.0` and `sam-3.1`.
   - **Data policies:** Standard vs Contributor, retention, `store`.

   Mark every item "per docs, unverified; WP0 verifies live". End with a **cost model for one 30 s clip** through the full pipeline (ARCHITECTURE.md §4 models), and for the whole eval plan (EVAL.md §5), against the $150 budget.
2. **`docs/prompts/` (specs, not code):** for each model call, write the purpose, inputs, the exact prompt text (draft v0), the JSON schema of the expected output (as a markdown code block), failure handling, and 3 tricky cases it must get right:
   - `scene-pass.md`
   - `role-pass.md` (SoM keyframes; the 3× self-consistency rules)
   - `escalation.md`
   - `miss-loop.md` (proposing SAM noun phrases + points)
   - `redteam.md` (reading or identifying anything in rendered frames)
   - `speech-fallback.md` (Muse Spark 1.2 speaker-attributed transcript)

   Base them on DESIGN.md §2.3 and §2.8 and on Meta's prompting guidance for Muse models (link it).
3. **`docs/research/`:**
   - `egoblur-gen2.md`: where Meta publishes EgoBlur Gen 2, its licence, whether the weights download is gated (form? HF?), model files and sizes, input preprocessing, thresholds, CPU vs GPU speed reported, and how it differs from Gen 1. If gated, write the exact owner steps.
   - `sa-co-veval.md`: the SA-Co/VEval SmartGlasses split. Where to get it, licence (confirm CC BY 4.0), size, annotation format, and how it maps to EVAL.md's metrics (tracking and leak guard only).
   - `modal.md`: Modal plans and free credits, CPU/GPU pricing, Volumes, cron, secrets, web endpoints and request limits, cold starts. Estimate the cost of a 3-minute CPU job per 30 s clip, plus 1 GPU-minute for EgoBlur.
   - `muse-wonder-vs-spark.md`: what Meta says about each (model cards and pages): capabilities, effort levels, latency and price. List the hypotheses WP0 should test.
   - `prior-art.md`: existing face- and object-blurring tools for creators (YouTube Studio blur, CapCut, Descript, PrivacyVideo, Blurize, EgoBlur, Brighter AI). What each one does and doesn't do (context, participants vs bystanders, screens, audit), with sources. Feeds the README's "why this is new".

## Done when

- [ ] Every file above exists, is sourced (URL + date), and contains no executable code.
- [ ] The PR summary lists the 5 facts most likely to change WP0's plan.
