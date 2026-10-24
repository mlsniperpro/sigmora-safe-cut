# Meta Model API notes (PRE-A, pre-event)

**Read on 2026-10-24 (UTC) by the PRE-A cloud agent. Every item is per docs, unverified; WP0 verifies live.**

> ⚠️ **The primary source was unreachable.** The cloud environment's network policy denies `dev.meta.ai` (and `developer.meta.com`, `projectaria.com`, `modal.com`, `huggingface.co`), so none of the `dev.meta.ai/docs` pages could be opened from this session. See `BLOCKED.md`. These notes are built from the best sources that *were* reachable, and each fact is tagged with where it came from:
>
> | Tag | Source | Trust |
> |---|---|---|
> | **[GH-cookbook]** | Meta's official [`meta-models/meta-model-cookbook`](https://github.com/meta-models/meta-model-cookbook) at commit `0a99b98` (2026-10-07), read in full | High: Meta's own code and READMEs, written against the live API |
> | **[GH-sam]** | Meta's official [`meta-models/meta-sam`](https://github.com/meta-models/meta-sam) at commit `4031897` (2026-10-06), esp. [`protocol/sam3.md`](https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md) | High: the normative wire grammar the official parsers implement |
> | **[PyPI]** | `pypi.org/pypi/meta-sam-parser/json`, `registry.npmjs.org/@meta-sam/parser` | High (package metadata) |
> | **[SNIP]** | A `dev.meta.ai` page seen only through a web-search summary, not opened | Medium: paraphrased by a search tool |
> | **[3P]** | Third-party issue trackers, blogs, resellers | Low |
> | **[DESIGN]** | Carried over from `DESIGN.md` (the owner's read of dev.meta.ai on 2026-10-14) and not re-checked | Medium |
>
> WP0 must re-read every `dev.meta.ai` URL below (they're the ones the cookbook links) and replace or confirm each tagged fact.

Endpoint: `https://api.meta.ai/v1`, OpenAI-SDK compatible; key in `MODEL_API_KEY`, sent as `Authorization: Bearer …`. **[GH-cookbook]** (README, `07_sam/01_api_basics/python/sam_api.py`, `06_muse_voice/01_voice_api_fundamentals/utils.py`)

---

## 1. SAM 3.1 (`sam-3.1`)

Docs to read on D1: [segmenting](https://dev.meta.ai/docs/sam/segmenting) · [reading-segmentation](https://dev.meta.ai/docs/sam/reading-segmentation) · [client-libraries](https://dev.meta.ai/docs/sam/client-libraries) · [media-segmentation](https://dev.meta.ai/docs/media-segmentation) · [sam/overview](https://dev.meta.ai/docs/sam/overview)

### 1.1 Request **[GH-cookbook]**
- `POST /v1/responses` with `model: "sam-3.1"`, `stream: true`.
- `input` is one user message whose content is `[{"type":"input_text","text":"<noun phrase>"}, <media part>]`.
  - Image: `{"type":"input_image","image_url":"data:image/jpeg;base64,…"}`.
  - Video: upload first (`POST /v1/files`, `purpose=user_data`), then `{"type":"input_video","file_id":"file-…"}`.
- **One noun phrase per request.** The cookbook says "pass multiple concepts to run separate requests and combine their summaries in application code".
- **File IDs start with `file-`** (hyphen); the cookbook rejects anything else. `ARCHITECTURE.md` §3.2 shows `file_…`; WP0 should fix that example when it writes `contracts.py`.
- The cookbook's verified run: `ping pong ball` on a 134-frame MP4 returned one stable object across all 134 frames; `duck` on an image returned 5 masks.

### 1.2 Request metadata **[GH-sam]**
| `metadata` key | Values | Effect |
|---|---|---|
| `include_confidence` | the **string** `"true"` | Adds an optional per-record confidence `c` (0–1) to box and mask tokens |
| `propagation_direction` | `both` (default), `forward`, `backward` | For **object prompts** (below): which frames to track over |
| `mask_encoding` | `one_bit` (per DESIGN §2.2) | Not documented in the protocol file; the protocol only says payloads are `~` lossless ("the API default") or `!` one_bit. **[DESIGN]** WP0 confirms the key name |

> 🔴 **This contradicts DESIGN.md's "there are no scores".** The protocol defines a confidence `c` on request. Readers "must accept records without `c` in every response, including responses to requests that ask for it", and "a missing confidence does not mean zero". Deny-by-default still holds (scores can be absent), but WP0 should probe `include_confidence` because a per-frame score would let the leak guard extend tracks at low-confidence frames instead of guessing.

### 1.3 Object prompts (box and point prompts) **[GH-sam]**
> 🔴 **This contradicts DESIGN.md §2.2 ("text prompts only").** Instead of a noun phrase, `input_text` may carry *object prompts* in the output token vocabulary:
```text
<30f>1<|box;x1=10;y1=20;x2=39;y2=59;w=640;h=480|>-<|point;x=25;y=30;w=640;h=480|><120f>1<|point;x=20;y=40;w=640;h=480|>,2<|box;x1=5;y1=5;x2=29;y2=29;w=640;h=480|>
```
- `<Nf>` opens a block for source frame N. Segments are `id` + tokens; the same id on another frame re-prompts the same object.
- `box` = whole object (inclusive x2/y2). `point` = a positive click; `-` before `<|point…|>` = a negative click.
- Every token carries `w`/`h` = the displayed media size (after rotation). Coordinates are integer pixels inside the media.
- A request must not mix a noun phrase with object prompts. "A model may limit how many objects one request can prompt."
- The response reports each object under the id the request gave it.

**Why it matters:** the miss loop (`docs/prompts/miss-loop.md`) can send Muse Spark's *point* straight to SAM as an object prompt on the exact frame, instead of hoping a new noun phrase finds the same thing. It can also re-acquire a lost track from its last box. WP1 should support both paths.

### 1.4 Output: the special-token stream **[GH-sam]**
One `output_text` lane, **one line per frame**, newline-terminated:
```text
<7f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>
<7f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80;c=0.75|><|mask;x=0;y=0;c=0.75;data=5,5,…|>
```
Grammar (normative summary):
- `line := "<" N "f" [";" fields] ">" segment ("," segment)*`. A comma before each segment is optional, including before the first.
- `segment := objectId token+`, where the record must have **exactly one `box` and exactly one `mask`**, in any order. Other tokens are ignored (with a warning).
- `objectId` is a non-negative decimal, stable within one response. It is **not dense**, needn't start at 0, and must be kept as a string, never derived from position.
- `token := "<|" name [";" key=value]* "|>"`, with `name ~ [A-Za-z][A-Za-z0-9_.-]*`. Fields are read by name; unknown keys are ignored with a warning.
- `box` requires `x1,y1,x2,y2` (integers, may be negative in syntax) plus `w,h` (the source size). **x2/y2 are inclusive**; normalised boxes are half-open (`right = x2+1`).
- `mask` requires `x=0`, `y=0`, `data=H,W,payload`. **H×W is the box size** (in the parser's example, box `x1=211..x2=270`, `y1=228..y2=254` carries `data=27,60,…`). So the mask is cropped to the box at source resolution and is placed at the box origin. DESIGN's "masks are smaller than the frame, so upscale them" really means *place*, not scale. WP0 confirms on a real clip whether the server downsamples.
- Payload: base85 text (not base64) over the alphabet ``!#$%&'()*+-./0123456789:=?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{``. The first char is the encoding marker (`~` lossless, the API default; `!` one_bit), then a 5-digit length prefix and an arithmetic-coded body. **Treat it as opaque**: never regex it or interpolate it into a shell, since it contains `$*()[]` and backticks.
- **Frames without objects emit no line** (indices skip). **Lines may arrive out of frame order** (e.g. forward to the end, then backward to 0). Never assume indices increase.
- Zero matches is a valid completed response with no records.
- Streaming quirk: the live API emits `response.content_part.done` but **not** `response.output_text.done`. The official adapter accepts either as the lane finaliser. **[GH-cookbook]**

### 1.5 Client libraries **[GH-sam] [PyPI]**
- **Python: `meta-sam-parser` 0.1.0 on PyPI** (import `meta_sam_parser`), Python ≥3.10, with no runtime dependencies. **Licence: SAM License** (not MIT/Apache). That's fine as a dependency, but don't vendor its source into this MIT repo.
  - `parse_responses_stream(events, video_segmentation_format())` takes OpenAI-SDK events or plain dicts. Use it under `async with` and call `final_result()`.
  - The direct parser is `video_segmentation_format().create_parser()` → `.push(chunk)` / `.finish(CompletedOutcome())`.
  - Converters: `decode_mask_to_raster`, `decode_mask_to_rle` (exact COCO compressed RLE), `decode_mask_to_svg_path`. There's also an object-prompt text builder.
  - Results: `.records` (box/mask records with `object_id`, `frame.frame_index`, `left/top/right/bottom`, `mask.encoding/width/height`), `.outcome.status`, `.diagnostics` (severity `error` = data dropped).
- TypeScript: `@meta-sam/parser` 0.1.0 (npm). Also `@meta-sam/react`, `/video` and `/graphics` in the same monorepo.
- **Consequence for WP1:** no hand-written stream parser is needed. Depend on `meta-sam-parser` and use `decode_mask_to_rle` for `tracks.json` masks.

### 1.6 Limits
| Limit | Value | Source |
|---|---|---|
| Frames per request | ≤15,000 (≈8 min at 30 fps) | **[DESIGN]** |
| Objects per frame | ≤16 | **[DESIGN]** |
| Video container/codec | H.264 MP4; VP9/WebM rejected | **[DESIGN]** (the cookbook only uses MP4) |
| Files API upload size | up to 1 GiB | **[GH-cookbook]** `07_vision_input` |
| `input_video.fps` field | **undocumented**; the protocol and cookbook don't mention it | WP0 probe b |
| RPM | 3,000 | **[DESIGN]** |

### 1.7 Pricing
- Video: **$0.20 per 1,000 frames**; image: $2.50 per 1,000 images. **[3P]** (search summary of a third-party guide; the Meta pricing-page excerpt didn't include SAM figures) and **[DESIGN]**. Read [pricing-rate-limits](https://dev.meta.ai/docs/getting-started/pricing-rate-limits) on D1.
- Which frames are billed (all source frames, or only frames with output lines) is **unknown**. **Decided:** the cost model and the spend guard assume **every uploaded frame is billed** (the worst case, and the safe one). WP0 compares against real billing and relaxes this only on evidence.

---

## 2. Files API **[GH-cookbook]**, **[DESIGN]**
Docs: [file-handling](https://dev.meta.ai/docs/file-handling)
- Upload: `POST /v1/files`, multipart, `purpose=user_data` → `{"id":"file-…"}`. OpenAI SDK: `client.files.create(file=(name, bytes, mime), purpose="user_data")`.
- `expires_after` (DESIGN uses `{"anchor":"created_at","seconds":3600}`, OpenAI-style). The cookbook doesn't set it. **WP0 confirms it's accepted.**
- Size: **up to 1 GiB** via the Files API; **50 MB** per inline (base64) image. **[GH-cookbook]**
- Retrieve: `GET /v1/files/{id}`. Delete: `DELETE /v1/files/{id}` (AGENTS.md rule 6: always delete after use). Neither appears in the cookbook; it's assumed from OpenAI compatibility.

---

## 3. Responses API (`muse-spark-1.3`, `muse-spark-1.2`, `muse-wonder-1.0`)
Docs: [features/responses](https://dev.meta.ai/docs/features/responses) · [api-reference/responses](https://dev.meta.ai/docs/api-reference/responses) · [structured-output](https://dev.meta.ai/docs/features/structured-output) · [reasoning](https://dev.meta.ai/docs/features/reasoning) · [prompt-caching](https://dev.meta.ai/docs/features/prompt-caching) · [error-handling](https://dev.meta.ai/docs/getting-started/error-handling) · [image-understanding](https://dev.meta.ai/docs/features/image-understanding) · [protocols/responses](https://dev.meta.ai/docs/protocols/responses)

### 3.1 Input parts
| Part | Shape | Notes | Source |
|---|---|---|---|
| text | `{"type":"input_text","text":…}` | | [GH-cookbook] |
| image | `{"type":"input_image","image_url":"data:…" or "https://…"}` | **user-role messages only** (system/developer → HTTP 400). About **50 images per request**, 50 MB inline, 1 GiB via Files. Tokens scale with resolution. PDF page-images count toward the image budget | [GH-cookbook] `07_vision_input` |
| video | `{"type":"input_video","file_id":"file-…"}` | Supported on Muse Spark. The soundtrack *is* heard on `muse-spark-1.2(-contributor)` (verbatim transcription in issue #59) but was ignored on 1.3 ("No speech is audible") | [3P] [cookbook issue #59](https://github.com/meta-models/meta-model-cookbook/issues/59) |
| audio | `{"type":"input_audio",…}` (inline base64 WAV/MP3, or `file_id`) | 🔴 **Silently dropped** on `muse-spark-1.2-contributor`: HTTP 200, `input_tokens`=68 (text only), and the model says it got no audio. `/v1/responses/input_tokens` counts it (171 tokens), so the counter disagrees with inference | [3P] issue #59 |
| PDF | supported | | [3P] inspect_ai #5222 |

Video sampling: undocumented for the hosted model. For the open-weight **Muse Spark Open**, the HF processor samples **2 fps, capped at 96 frames by default**, interleaved with timestamp text. **[3P]** (HF transformers docs via a search summary). That suggests a 30 s clip is seen as about 60 frames, and that the hosted model may also put timestamps in the prompt. WP0 probe c tests this.

> **Speech consequence:** audio understanding on 1.3 is degraded (MAXXING §2), and **standalone `input_audio` may be silently dropped on 1.2**. The `spark-1.2` speech fallback must send **the MP4 (`input_video`) with its soundtrack**, not a WAV, and must check that `usage.input_tokens` is well above the text-only count. See `docs/prompts/speech-fallback.md`.

### 3.2 Structured output
- On Responses use `text: {"format": {"type":"json_schema","name":…,"schema":…,"strict":true}}`. Sending **`response_format` returns HTTP 400.** **[GH-cookbook]** `04_structured_output`
- Strict schemas must set `additionalProperties:false` and list **every** property in `required` (or HTTP 400). Use `enum` for closed sets. **Recursive `$ref` → 400.** Optional fields must therefore be required and nullable (`"type":["string","null"]`). **[GH-cookbook]**, **[3P]** inspect_ai #5222
- Constrained decoding "guarantees the output conforms". Still validate with pydantic (refusals and truncation exist).

### 3.3 `store: false`
- Supported. Stateless multi-turn uses `include: ["reasoning.encrypted_content"]` and replays reasoning items. That `include` can't be combined with `previous_response_id`. **[3P]** inspect_ai #5222, OpenClaw docs.
- With `store:false` there's no `previous_response_id` chaining; every Safe Cut call is single-turn anyway.

### 3.4 `reasoning.effort`
> 🔴 **DESIGN.md §2.3 and ARCHITECTURE.md §4 use `reasoning.effort: "max"` for escalation on Muse Spark. The sources disagree, and the strongest ones say `max` is not a Spark level.**

| Model | Levels | Source |
|---|---|---|
| `muse-spark-1.3` | `none` < `minimal` < `low` < `medium` < `high`; **`xhigh` = same strength as `high`**; default "still being finalized" | **[GH-cookbook]** `06_reasoning_tokens`, `09_one-shot-game_dev` |
| `muse-spark-1.3` | `minimal` … `xhigh`; **`none` and `max` → HTTP 400**; reasoning can't be disabled | [3P] inspect_ai #5222 |
| `muse-spark-1.3` | the cookbook's CUA agent maps to "the API's accepted `low|medium|high` values" | [GH-cookbook] `13_macos_cua/metacua/llm.py` |
| `muse-wonder-1.0` | `minimal` … **`max`** | [3P] (launch coverage summarised by search) |

**Plan for WP0:** probe each level on each model (`GET /v1/models` may list them). Until then, the prompt specs use **`high` for Spark escalation** and **`max` only on Wonder**. `config.py` should validate effort per model.

### 3.5 Streaming
- SSE events, OpenAI Responses style. Muse Spark reasons before any visible output, so a non-streamed call sits idle. Stream long calls, or set generous timeouts. **[3P]** inspect_ai #5222
- On a break, retrying restarts the stream from the beginning. **[GH-cookbook]** `02_streaming`
- SAM lanes finalise with `response.content_part.done` (§1.4).

### 3.6 Errors **[GH-cookbook]** `09_error_handling`
- Envelope: `{"error":{"message","type","param","code"}}`. Branch on HTTP status and `type`; **`code` is often `null`**.
- Retry (exponential backoff + jitter, capped): **429, 5xx, timeouts/connection errors**. Never retry 400/401/404.
- Unsupported OpenAI params → 400: `stop`, `n>1`, `logit_bias`, `logprobs`/`top_logprobs`, `verbosity`, `truncation:"auto"`. **`tool_choice` other than `auto` → 400.** **[GH-cookbook]**, [3P]
- Context overflow → plain 400 with a message. [3P]
- Refusals: no structural refusal signal is documented for Muse Spark ([3P]). The SAM adapter treats refusal events and parts as terminal typed failures **[GH-sam]**.
- Every response carries rate-limit budget **headers**; throttle as `remaining` drops. **[GH-cookbook]**

### 3.7 Rate limits and caching
- `muse-spark-1.3`: **3,000 RPM, 4,000,000 TPM**. **[SNIP]** [pricing-rate-limits](https://dev.meta.ai/docs/pricing-rate-limits)
- `muse-wonder-1.0`: 3,000 RPM, 4M TPM. [3P]
- Prompt caching is **automatic** (identical leading tokens). An optional `prompt_cache_key` raises the hit rate, and `prompt_cache_retention: "in_memory"|"24h"` is a hint. Read `usage.input_tokens_details.cached_tokens`. **[GH-cookbook]** `05_prompt_caching`
- **Design consequence:** put stable content (system prompt, schema, scene context, *the keyframe images*) first, and per-vote variation last. Then votes 2 and 3 of the role pass are mostly cached input (§9).

---

## 4. Muse Voice Transcribe (`muse-voice-transcribe-1.0`) **[GH-cookbook]** `06_muse_voice/01_voice_api_fundamentals`
Docs: [speech-to-text](https://dev.meta.ai/docs/speech-to-text) · [api-reference/voice](https://dev.meta.ai/docs/api-reference/voice)

### 4.1 One-shot request
`POST https://api.meta.ai/v1/asr/transcribe[?sessionId=…]`, header `Authorization: Bearer $MODEL_API_KEY`, **multipart** with two parts:
- `request`: a **JSON part** (`application/json`), not form fields:
  ```json
  {"mode": "DIARIZATION", "model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV",
   "keywords": ["Amina"], "languageBias": ["english"]}
  ```
- `audio`: the file. **Mono 16-bit WAV at 24 kHz (engine-native) or 16 kHz.** Convert with `ffmpeg -i in.mp4 -ac 1 -ar 24000 -sample_fmt s16 out.wav`.
- `mode`: `PUSH_TO_TALK` (default) | `ENDPOINTING` | `DIARIZATION`. ⚠️ **"The server ignores an unrecognised mode rather than rejecting it"**, so a typo silently transcribes in the wrong mode. Validate it client-side. A mode a model doesn't serve *is* rejected.
- `keywords` (names, jargon) and `languageBias` are lists of strings. They nudge the model and don't guarantee a spelling.

### 4.2 Response
```json
{"sessionId": "…", "transcript": "…", "audioDurationMs": 30000,
 "turns": [{"speaker": "A", "startMs": 1520, "endMs": 3100, "transcript": "How is the weather?"}]}
```
- `turns` is present only in speech modes. `speaker` appears only in `DIARIZATION` and is a **bare letter** (`"A"`, not `speaker_a`).
- `endMs` is used by the cookbook's caption recipe (`07_sam/03…/build-demo-data.py`).
- "Diarization covers non-overlapping speech." Overlapping talk is a known gap.
- **Mapping to `transcript.json` (decided):** speaker letters map to `S1`, `S2`, … in order of first appearance (`"A"` → `"S1"` if A speaks first). That keeps the ARCHITECTURE §3.3 contract and the spark-1.2 fallback on one label scheme. `startMs/1000` → `start`, `endMs/1000` → `end`, and `transcript` → `text`.

### 4.3 Limits and errors
- One-shot: **≤10 min of audio or ≤32 MB**, whichever comes first. 413 = body too big; 400 = too long (after decode) or malformed.
- Errors: 401 bad key, 404 bad endpoint, 429 rate limited, 500 "the server exceeded its processing budget".
- **25 languages.** Punctuation, endpointing and speaker attribution are done by the model.
- Streaming (`wss://api.meta.ai/v1/asr/realtime`) needs real-time pacing (a >5 s backlog → close 1008) and a 60-min cap. Not needed for Safe Cut.

### 4.4 Pricing
- **$0.18 per hour of audio** ($0.003/min), the same for streaming and one-shot, billed rounded **down** to whole seconds. **Contributor mode isn't offered.** **[SNIP]** pricing-rate-limits / model page. A 30 s clip costs **$0.0015**.

---

## 5. Image understanding (points and boxes)
Docs: [features/image-understanding](https://dev.meta.ai/docs/features/image-understanding) (the cookbook links it 6×; not opened)
- **0–1000 normalised grid** for both points and boxes, relative to the **image as sent** (after any client-side resize). Box example `[424,115,610,273]` = `[x1,y1,x2,y2]` ‰. **[3P]** Simon Willison's write-up of the meta.ai Muse Spark launch, **[DESIGN]**
- Edge case: **values of 1001 have been seen** → clamp to `[0,1000]` before mapping. **[DESIGN]**
- **The single mapping rule** (every spec points here). Keyframes are sent at the **prepared clip's own resolution** (≤1280 px; never resized again). The prompt specs add a black frame-number bar of `bar_h` **sent pixels** above the frame, so the sent image is `W × (H + bar_h)`:
  1. clamp each grid value to `[0, 1000]`;
  2. to sent-image pixels: `x_img = floor(vx / 1000 × (W − 1))`, `y_img = floor(vy / 1000 × (H + bar_h − 1))`;
  3. to frame pixels: `x = x_img`, `y = y_img − bar_h`;
  4. **point:** if `y < 0` (it's in the bar), drop it; otherwise it's valid, since it's in-bounds by construction.
     **box:** map both corners, then clamp to `[0, W−1] × [0, H−1]`. If the clamped box is under 2 px in either dimension (e.g. wholly inside the bar, or a hairline), a **red-team** box becomes a 32×32 px box centred on the clamped centre and clamped to the frame (fail closed: it still gets patched); a **miss-loop** box is discarded and its point kept.
  `floor` matches the SAM protocol's "round down to whole pixels" **[GH-sam]**. Whether the model's grid means `/1000·W` or `/1000·(W−1)` is undocumented (under 1.3 px apart at 1280); WP0 probe g checks it on a synthetic image with a known dot. WP2 implements this rule once and property-tests it: outputs are in-bounds, monotone in the input, and the round trip from frame pixels is within 1 px.
- Exact point JSON (`{"x","y"}` vs `[x,y]` vs `<point>` text) is only defined by **our** schema, because we ask for points via `text.format`. The grid convention is the model's trained prior, so the prompt must state it explicitly (see `docs/prompts/role-pass.md`).
- Note: SAM object prompts (§1.3) need **pixel** coordinates with `w`/`h`, so convert the 0–1000 points before sending.

---

## 6. Pricing and rate limits (per 1M tokens unless stated)

| Model | Input | Cached input | Output | Other | RPM / TPM | Source |
|---|---|---|---|---|---|---|
| `muse-spark-1.3` | $1.25 | $0.15 | $4.25 | Contributor: $0.10 / $0.002 / $0.20 (**never use**) | 3,000 / 4M | [SNIP] pricing page; [3P] inspect_ai #5222 |
| `muse-spark-1.2` | **not found** | | | Assume = 1.3 until read | ? | — |
| `muse-wonder-1.0` (preview) | $4.00 | $0.20 | $20.00 | web search $2.50/1k calls | 3,000 / 4M | [3P] (launch coverage; OpenRouter listing) |
| `muse-voice-transcribe-1.0` | $0.18 / audio hour | — | — | no Contributor mode | ? | [SNIP] |
| `sam-3.1` | $0.20 / 1k video frames; $2.50 / 1k images | — | — | | 3,000 RPM [DESIGN] | [3P], [DESIGN] |

Reasoning tokens are billed as output (`usage.output_tokens_details.reasoning_tokens`). **[GH-cookbook]** `06_reasoning_tokens`. Context: 1,048,576 tokens; max output 131,072 (Spark 1.3). [3P]

The cookbook README says "the preview is free" for Muse Spark. **Don't plan on it.** The hackathon credits are what we have.

---

## 7. Data policies: Standard vs Contributor
Docs: [help/policies-and-privacy/contributor-tier](https://dev.meta.ai/help/policies-and-privacy/contributor-tier) (not opened)
- Contributor model IDs end in `-contributor` and are about 10–20× cheaper. Per DESIGN §2.3, Meta's policy says **not to send personal information to Contributor mode** (its data may be used to improve models). **[DESIGN]**
- Safe Cut sends faces, so it uses **Standard mode only**: refuse `*-contributor` in `config.py` (AGENTS rule 6).
- `store:false` on every Responses call; delete every uploaded file. Retention periods for Standard-mode inputs and outputs and for uploaded files (beyond `expires_after`) were **not found**. WP0 reads the policy page and quotes the retention numbers into the receipt's `data_handling` text.
- Muse Voice Transcribe has no Contributor mode. [SNIP]

---

## 8. Surprises WP0 should know before writing code
1. **SAM can return confidences** (`metadata.include_confidence: "true"`) and **accepts box/point prompts**. Both contradict DESIGN. §1.2–1.3.
2. **There's an official Python parser** (`meta-sam-parser`, SAM License). Don't hand-roll the grammar. §1.5.
3. **SAM lines can arrive out of frame order**, and object IDs are sparse strings. §1.4.
4. **`reasoning.effort: "max"` is probably a 400 on Muse Spark.** Use `high`; `max` is Wonder only. §3.4.
5. **`input_audio` can be silently dropped** (HTTP 200, no error), so the speech fallback must use the video soundtrack and check `usage`. §3.1.
6. File IDs are `file-…`. ASR modes are case-sensitive and unknown modes are silently ignored. Speaker labels are letters.
7. Live SAM streams have no `response.output_text.done`.

---

## 9. Cost model

### 9.1 One 30 s clip through the full pipeline (ARCHITECTURE §4 defaults: Spark 1.3 everywhere, Voice Transcribe)

Assumptions (flagged; WP0 replaces them with measured `usage`):
- **A1** SAM at the prepared rate. DESIGN quotes 30 fps and an 8 fps "smart rate"; both are shown.
- **A2** 7 base concepts + up to 2 miss-loop phrases (a short window; costed as a full sweep to be safe).
- **A3** Image tokens: ≈1,500 input tokens per 1280×720 keyframe (unknown; the cookbook only says tokens scale with resolution).
- **A4** Video scene pass ≈ 60 sampled frames × 1,000 tokens + audio + prompt ≈ 65k input tokens (from Muse Spark Open's 2 fps sampling).
- **A5** 30 SoM keyframes (1 fps) in one role-pass call. Votes 2 and 3 hit the prompt cache for the image prefix.
- **A6** Output includes reasoning: medium ≈ 4k tokens per call; high ≈ 8k.

| Stage | Calc | USD (8 fps) | USD (30 fps) |
|---|---|---|---|
| SAM base sweep | 7 × 240 fr = 1,680 fr × $0.20/1k (30 fps: 6,300 fr) | 0.336 | 1.260 |
| SAM miss loop | 2 × 240 fr (30 fps: 2 × 900) | 0.096 | 0.360 |
| Voice Transcribe | 0.5 min × $0.003 | 0.002 | 0.002 |
| Scene pass (video) | 65k in × $1.25/M + 4k out × $4.25/M | 0.098 | 0.098 |
| Role pass vote 1 | 47k in × $1.25/M + 4k out | 0.076 | 0.076 |
| Role pass votes 2–3 | 2 × (45k cached × $0.15/M + 2k fresh × $1.25/M + 4k out) | 0.053 | 0.053 |
| Escalation (≈10 disputed keyframes, `high`) | 17k in + 8k out | 0.055 | 0.055 |
| Red-team (`redteam.md` sampling) | pass 1: 40 frames (30 at 1 fps + 3 per track × ~3 tracks + ~1 EgoBlur flag) = 61k in + 3k out; pass 2: 10 patched frames = 16k in + 2k out | 0.118 | 0.118 |
| **Total per 30 s clip** | | **≈ $0.83** | **≈ $2.02** |
| *With no prompt-cache hits* | +2 × 45k × ($1.25 − $0.15)/M | +0.10 | +0.10 |
| *With Wonder for scene + escalation* | scene 65k × $4 + 4k × $20; escalation 17k × $4 + 8k × $20 (replaces the Spark lines) | +0.41 | +0.41 |

**Reading:** at 30 fps SAM is 80% of the cost, and a clip costs ≈ $2.02, **over** `SAFECUT_JOB_USD_CAP = 2.00`. So **upload a ≤10 fps proxy to SAM** (or find what `input_video.fps` does) and densify back onto the prepared clip's frames; the miss-loop spec gives the frame-axis conversion. Muse Spark is about $0.40 per clip either way. Per minute of footage: **≈ $1.67 at 8 fps**. Totals were computed with a scratch script; its output is pasted in the PR.

### 9.2 The whole eval plan (EVAL.md §5) against $150

| Item | Calc | USD |
|---|---|---|
| WP0 probes | WP0 budget | 6.00 |
| Test split: full Safe Cut | 18 clips × $0.83 × 3 runs | 44.82 |
| Baseline 1 (blur every face) and 2 (detector-only) | reuse the full run's SAM `face`/`plate`/`screen` sweeps (replay) | 0.00 |
| Baseline 1b (EgoBlur Gen 2) | local compute | 0.00 |
| Baseline 3 (Muse without tracking) | 18 × 30 keyframes × 1 call ≈ 18 × $0.08 × 3 runs | 4.32 |
| Ablation (no audit) | replay of the full run | 0.00 |
| Dev split, first run | 12 × $0.83 | 9.96 |
| Dev iterations (prompt tuning; SAM replayed) | 9 iterations × 12 clips × $0.40 (Muse only) | 43.20 |
| Hero clips (3 clips × 2 takes; ~3 renders each incl. demo) | 6 × $0.83 × 3 | 14.94 |
| Pilots (5 creators × ~2 clips) + public "Try it" | 10 × $0.83 + daily-cap headroom | 8.30 + cap |
| **Subtotal** | | **≈ $131.54** |
| **Headroom vs $150** | | **≈ $18** |

**Risks to this budget:**
- **30 fps SAM** multiplies the SAM lines by 3.75 (test runs alone → ≈ $109). Stay at ≤10 fps.
- **Dev iterations over the full dev split** are the biggest discretionary line. Iterate on a 4-clip subset (→ $14.40, saving ≈ $29) and use the full split only for checkpoint runs. **With only ≈ $18 of headroom, treat this as the plan, not an option.**
- Adopting **Wonder** adds $0.41 per clip run. Across every clip run above (202) that's +$83.73, which doesn't fit. Restricted to test, hero and pilot runs (82) it's +$33.99, which fits only if dev iterations shrink to the 4-clip subset.
- The public demo's `SAFECUT_DAILY_USD_CAP = 10.00` would eat the ≈ $18 headroom in under 2 days. Lower it to $3 after judging starts, or require the access code.

Every figure above is a model to be replaced by measured `cost.jsonl` from WP0's probes. None of it may appear in the README (AGENTS rule 9).
