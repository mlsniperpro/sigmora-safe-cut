# Meta Model API notes (PRE-A, pre-event)

**Read on 2026-10-24 (UTC) by the PRE-A cloud agent. Every item is per docs, unverified; WP0 verifies live.**

> ⚠️ **The primary source was unreachable.** The cloud environment's network policy denies `dev.meta.ai` (and `developer.meta.com`, `projectaria.com`, `modal.com`, `huggingface.co`), so none of the `dev.meta.ai/docs` pages could be opened from this session. See `docs/BLOCKED-PRE-A.md`. These notes are built from the best sources that *were* reachable, and each fact is tagged with where it came from:
>
> | Tag | Source | Trust |
> |---|---|---|
> | **[GH-cookbook]** | Meta's official [`meta-models/meta-model-cookbook`](https://github.com/meta-models/meta-model-cookbook) at commit `0a99b98` (2026-10-07), read in full | High: Meta's own code and READMEs, written against the live API |
> | **[GH-sam]** | Meta's official [`meta-models/meta-sam`](https://github.com/meta-models/meta-sam) at commit `4031897` (2026-10-06), esp. [`protocol/sam3.md`](https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md) | High: the normative wire grammar the official parsers implement |
> | **[PyPI]** | `pypi.org/pypi/meta-sam-parser/json`, `registry.npmjs.org/@meta-sam/parser` | High (package metadata) |
> | **[SNIP]** | A `dev.meta.ai` page seen only through a web-search summary, not opened | Medium: paraphrased by a search tool |
> | **[3P]** | Third-party issue trackers, blogs, resellers | Low |
> | **[DESIGN]** | Carried over from `DESIGN.md` (the owner's read of dev.meta.ai on 2026-10-14) and not re-checked | Medium |
> | **[OWNER-2026-10-24]** | The owner's read of the live `dev.meta.ai` page on 2026-10-24 from an open network (PR #1 audit), matching a search summary of the same page | High: the primary source, read today |
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
- **File IDs:** Meta's own examples use **both** `file-…` (the cookbook's SAM recipe, whose check rejects anything else) and `file_…` (ARCHITECTURE §3.2's example, from the docs). **Decided:** WP0's client and `contracts.py` accept both spellings (`file-` or `file_` followed by the server's ID) and treat the ID as opaque otherwise. Don't copy the cookbook's `startswith("file-")` check.
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
  - Results (`final_result()` of a parsed stream, or `.result` of the direct parser's `ParserFinish`): `.records` (box/mask records with `object_id`, `frame.frame_index`, `left/top/right/bottom`, `mask.encoding/width/height`), `.outcome.status`, `.diagnostics` (severity `error` = data dropped).
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
- `expires_after` (DESIGN uses `{"anchor":"created_at","seconds":3600}`, OpenAI-style; as multipart form fields: `expires_after[anchor]=created_at`, `expires_after[seconds]=3600`). The cookbook doesn't set it. **WP0 confirms it's accepted.** Safe Cut sends **21,600 s (6 h)**, above the 2 h job limit (DESIGN's 3600 could expire mid-job). It's only a backstop: Safe Cut deletes explicitly (§10.4).
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
Docs: [reasoning](https://dev.meta.ai/docs/reasoning) (the cookbook links an older path, `features/reasoning`).

| Model | Levels | Source |
|---|---|---|
| `muse-spark-1.3`, `muse-wonder-1.0` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. **`max` is supported by `muse-wonder-1.0` and `muse-spark-1.3`** (not by `muse-spark-1.3-contributor`). **`xhigh` reasons deeper than `high`.** `none` → HTTP 400 on both (reasoning can't be disabled) | **[OWNER-2026-10-24]** live reasoning page; the same page via a search summary |
| *(superseded)* `muse-spark-1.3` | the cookbook says "`xhigh` maps to the same strength as `high`"; a third-party report says `max` → 400 | [GH-cookbook] `06_reasoning_tokens` (written before the change); [3P] inspect_ai #5222. Third-party coverage says `max` reached the public API on 2026-09-04, two days after launch, which explains the 400 report |

**Decided:** the effort levels in the specs follow the live page, so escalation keeps DESIGN's **`max`** on Spark (`docs/prompts/escalation.md`). WP0's probe f confirms `max` on both models, and `config.py` validates effort per model. A 400 on an effort value is never silently downgraded. Two checks, both explicit:
- **At service start**, the API makes one minimal call for each configured `(model, effort)` pair (the **startup probe** of §10.7, which is separate from `/healthz`) and **refuses to start** on a 400. Static validation in `config.py` alone can't catch a server-side change.
- **Mid-job** (the setting changed after boot), the escalation call counts as failed: every disputed track stays `unsure` + `needs_you` (escalation.md, rule 3), the error is logged as `config_error`, and `/healthz` reports degraded.

ARCHITECTURE §4 stays as written.

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
- **Mapping to `transcript.json` (decided):** speaker letters map to `S1`, `S2`, … in order of first appearance (`"A"` → `"S1"` if A speaks first). That keeps the ARCHITECTURE §3.3 contract and the spark-1.2 fallback on one label scheme. `startMs/1000` → `start`, `endMs/1000` → `end`, and `transcript` → `text`. The WAV is extracted from `prepared.mp4`, so turn times are on the **prepared clock** (§5b).

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
     **box:** Safe Cut pixel boxes are **half-open** `[x1, y1, x2, y2)`, the same convention as the parser's normalised `left/top/right/bottom` (§1.4). First **normalise reversed corners** (swap so that x1 ≤ x2 and y1 ≤ y2). A box lying **entirely inside the bar** (`y2_img < bar_h`) describes our frame label, not the video: drop it and log `in_bar`, for every kind. Then map the top-left corner with steps 2–3. For the bottom-right corner, map the same way and then add 1 (`x2 = x2_img + 1`, `y2 = y2_img + 1 − bar_h`). Clamp to `[0, W] × [0, H]`. If the clamped box is under 2 px in either dimension (e.g. a hairline, or a sliver clipped at the frame edge), a **red-team** box becomes a 32×32 px box centred on `((x1+x2) div 2, (y1+y2) div 2)` and clamped to the frame (fail closed: it still gets patched); a **miss-loop** box is discarded and its point kept. When a half-open box goes into a SAM object prompt, it's sent as inclusive `x2 − 1`, `y2 − 1`; `meta_sam_parser.build_object_prompt(PromptBox(left, top, right, bottom))` does this conversion. Test vectors: §11.2.
  `floor` matches the SAM protocol's "round down to whole pixels" **[GH-sam]**. Whether the model's grid means `/1000·W` or `/1000·(W−1)` is undocumented (under 1.3 px apart at 1280); WP0 probe g checks it on a synthetic image with a known dot. WP2 implements this rule once and property-tests it: outputs are in-bounds, monotone in the input, and the round trip from frame pixels is within 1 px.
- Exact point JSON (`{"x","y"}` vs `[x,y]` vs `<point>` text) is only defined by **our** schema, because we ask for points via `text.format`. The grid convention is the model's trained prior, so the prompt must state it explicitly (see `docs/prompts/role-pass.md`).
- Note: SAM object prompts (§1.3) need **pixel** coordinates with `w`/`h`, so convert the 0–1000 points before sending.

---

## 5b. Time and frame axes, the definition every WP uses
PRE-A owns this definition, and PR #2 applies it (`docs/labeling/LABEL-FORMAT.md` §2 and §9.1, `docs/UI-SPEC.md` §3.6, at `f6815a5`). It also matches DESIGN §2.1's existing `PreparedClip.times` ("source-second timestamps per frame"). Every ffmpeg behaviour below was **verified with ffmpeg 6.1.1** on 2026-10-24 by matching per-frame checksums before and after the filter (vectors T1–T6, T9, T10). No contract field changes.

**Decided (2026-10-24, final):** the prepared clip has a **constant frame rate**, and `times` holds **source-clock seconds**.
- *Rejected:* a variable-frame-rate prepared clip that keeps source timestamps. It was tried twice in this branch's history, and two problems were found by running ffmpeg. A drop-only `select` rule drops real frames from jittery 30 fps phone clips (36% of a ±1.5 ms-jitter clip). And `-fps_mode passthrough` re-quantises timestamps to the stream's frame rate unless `-enc_time_base demux` is set.
- The constant-rate clip keeps the player, the SAM proxy and the render on one fixed slot rule. It tolerates timestamp jitter (slots round to the nearest tick), and the existing Sigmora prepare already works this way.

**Two clocks:**

| Clock | Origin | Unit | Used by |
|---|---|---|---|
| **Prepared clock** | prepared frame 0 = 0.0 s | `t_p = i / job.fps` | player, overlay, SAM proxy, render, **transcript turn times**, every UI time display |
| **Source clock** | the first decoded **video** frame (its PTS, after the container's edit list, is subtracted) | `job.times[i]`, seconds | mapping CVAT labels (source frames) onto prepared frames; the receipt's "source time" |

**`prepare` (WP1), exactly:**
1. `job.fps = min(30, round(source average fps))`, an integer from 1 to 30. The output is constant frame rate at `job.fps`, H.264, `+faststart`, ≤1280 px long edge (DESIGN §2.1).
2. **Normalise the start first:** video filter chain `setpts=PTS-STARTPTS, fps=<job.fps>, scale=…`. Without `setpts`, a video stream that starts after its audio (or with a non-zero first PTS) makes the `fps` filter slot frames by absolute time, and the mapping shifts (verified: a 0.1 s video delay moved proxy frame 0 from prepared frame 1 to 2; T9). **Audio stays in sync on the same origin:** if the audio starts earlier than the video by `d` seconds, `atrim=start=d, asetpts=PTS-STARTPTS`; if it starts later, `adelay=d×1000:all=1`. Then the prepared audio and video both start at 0.
3. **Frame selection is ffmpeg's `fps` filter** (default `round=near`). Give source frame `k` the slot `s_k = round_half_up(t_k × job.fps)`, where `t_k` is its source-clock time. **Output frame `n` shows the last source frame with `s_k ≤ n`.** Earlier frames in the same slot are dropped, and an empty slot repeats the previous frame. **`times[n] = t_k` of that frame.** WP1 computes `times` from the ffprobe per-frame PTS list with this rule, and its test checks the rule against ffmpeg's own output on a synthetic VFR clip (the bundled imageio-ffmpeg binary, with its version recorded).
4. **Exact arithmetic:** compute `t_k` from the **integer** `pts` and the stream `time_base` as a rational (`Fraction(pts − pts_0) × time_base`), not from ffprobe's 6-decimal `pts_time` string. `times` is stored as the **full-precision double** `float(Fraction(...))`, never rounded (the same rule PR #2 LABEL-FORMAT §2 states). Then every consumer that recomputes `t_k` with the same function gets bit-identical values, which PR #2's `|t_k − times[i]| ≤ 1e-6` match relies on.
5. Consequences a builder must not "fix":
   - `times` is **non-decreasing, not strictly increasing** (a gap repeats a frame);
   - `times[0]` is the time of the last source frame in slot 0, which **may be > 0** (T6c: 0.04);
   - **`job.frames` is the number of frames ffmpeg actually wrote, read back with ffprobe**, never computed from duration × fps (the last source frame can fall in a slot ffmpeg doesn't emit at end of stream);
   - a jittery 30 fps source keeps every frame, because each frame's slot rounds to its own tick.
6. Audio is muxed in sync on the prepared clock. The ASR WAV is extracted **from `prepared.mp4`**, so `transcript.json` turn times are prepared-clock seconds. Turn time → prepared frame: `clamp(floor(t × job.fps), 0, job.frames − 1)`.
7. No trim in Safe Cut v1 (creators trim before upload; PR #2 UI-SPEC §2). If trimming is ever added, `job.json` gains `source_offset_s` (a contract change in ARCHITECTURE §3.1 and `contracts.py`).

**Mappings (one module in WP1):**
- **player → prepared frame** (PR #2 UI-SPEC §3.6): `i = clamp(floor(mediaTime × job.fps + 0.25), 0, job.frames − 1)`.
- **prepared frame → display time:** `i / job.fps` (m:ss).
- **ground truth: prepared → label** (PR #2 LABEL-FORMAT §2 and §9.1): prepared frame `i` takes the label state of the source frame `k(i)` with `|t_k − times[i]| ≤ 1e-6` (exact by step 4). Repeated prepared frames repeat that state; labels on dropped source frames are never sampled.
- **SAM proxy** (`sam_proxy.mp4`, §9): encoded from `prepared.mp4` with the `fps` filter at **`sam_fps_eff = min(SAFECUT_SAM_FPS, job.fps)`** (`SAFECUT_SAM_FPS` defaults to 8, a request to WP0; never upsample). `sam_frames` is read back with ffprobe. The same slot rule applies, now on prepared times `i / job.fps`:
  - `from_proxy(j) = max{ i < job.frames : round_half_up(i × sam_fps_eff / job.fps) ≤ j }`: SAM detections on proxy frame `j` belong to prepared frame `from_proxy(j)`. Prepared frames in between are filled by WP1's densify, which interpolates box corners linearly between anchors;
  - `to_proxy(f) = argmin_j |from_proxy(j) − f|`, ties → the smaller `j`, for object prompts on prepared frame `f`. Precompute `from_proxy` as an array of length `sam_frames`.
- **Parameters defined in SAM's own frames must be scaled to prepared frames.** SAM 3/3.1 confirms a new object only after `hotstart_delay = 15` frames of **its** input video (`facebookresearch/sam3` @ `f1647e8`, `model_builder.py`: the video builder and the 3.1 multiplex builder both set `hotstart_delay=15`; the hosted API is assumed to behave the same, *(probe)*). On the proxy that's `15 / sam_fps_eff` seconds. So:
  - **the leak guard's back-fill** (DESIGN §2.6: "back-fill 15 frames before first detection") becomes `ceil(15 × job.fps / sam_fps_eff)` prepared frames, which is 57 at 30 → 8 fps. `plan.json` `temporal.backfill` stores that prepared-frame value (request to WP3);
  - **gap and merge thresholds** that count SAM frames (e.g. WP1's `gap_merge_frames = 2`) are measured in **proxy** frames, before densify (request to WP1). Measured on prepared frames, every pair of 8 fps anchors (3–4 prepared frames apart) would look like a gap;
  - `temporal.extend` (8) and `gap_hold_s` (2.0 s) are already defined on the prepared clip and stay as they are.
- **Property tests (WP1):** every output is in bounds and every map is monotone; `to_proxy(from_proxy(j)) == j` for every `j`; and `|from_proxy(to_proxy(f)) − f| ≤ ceil(job.fps / sam_fps_eff)`. That bound was brute-forced for `job.fps` ∈ {6, 10, 15, 24, 25, 30}, `sam_fps` ∈ {6, 8, 10} and every clip length from 5 to 1,800 frames; the maximum observed was one below the bound. Tests use the read-back `sam_frames`. Vectors are in §11.3.

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
4. **Effort levels changed after launch.** `max` is supported on Spark 1.3 and Wonder 1.0, and `xhigh` is deeper than `high` (live page). The cookbook's "`xhigh` = `high`" is out of date. §3.4.
5. **`input_audio` can be silently dropped** (HTTP 200, no error), so the speech fallback must use the video soundtrack and check `usage`. §3.1.
6. File IDs appear as both `file-…` and `file_…`, so accept both. ASR modes are case-sensitive and unknown modes are silently ignored. Speaker labels are letters.
7. Live SAM streams have no `response.output_text.done`.

---

## 9. Cost model
All numbers come from a scratch script (`cost2.py`, not committed; its output is pasted in PR #1). Prices are §6's. Every assumption is flagged; WP0 replaces them with measured `usage` and `cost.jsonl`.

### 9.1 One 30 s clip through the full pipeline (ARCHITECTURE §4 defaults: Spark 1.3 everywhere, Voice Transcribe)
Assumptions:
- **A1** SAM runs on the ≤10 fps proxy (§5b; 8 fps shown) and, for comparison, on the 30 fps prepared clip.
- **A2** Miss loop: 2 loops, each with **one batched object-prompt request** (all of that loop's points as object ids in one request, which `protocol/sam3.md` allows) **plus one phrase sweep**. Every SAM request sweeps the whole proxy, so each costs the full frame count. That's 4 sweeps per clip.
- **A3** ≈1,500 input tokens per 1280×720 keyframe (unknown; the cookbook only says tokens scale with resolution).
- **A4** The scene pass sees ≈ 65k input tokens (60 sampled frames, from Muse Spark Open's 2 fps sampling).
- **A5** 30 Set-of-Mark keyframes in one role-pass call; votes 2–3 hit the prompt cache for the image prefix.
- **A6** Output including reasoning: `medium` ≈ 4k tokens per call, `max` ≈ 16k (`high` ≈ 8k, `xhigh` ≈ 12k; no per-level figures are published).
- **A7** 8 tracks per typical clip (hero clip 1 has about 16).
- **A8** Red-team pass 1 = 30 frames at 1 fps + 4 frames per track (`redteam.md` sampling) + 2 EgoBlur flags = 64 frames in 2 calls. Pass 2 = 10 patched frames; pass 3 = 5 (WP4 allows 3 passes).
- **A9** Loop 2's role re-pass: about 10 new keyframes, with 3 votes.

| Stage | Calc | USD (8 fps) | USD (30 fps) |
|---|---|---|---|
| SAM base sweep | 7 concepts × 240 frames × $0.20/1k (30 fps: × 900) | 0.336 | 1.260 |
| SAM miss loop | 4 sweeps × 240 frames (A2) | 0.192 | 0.720 |
| Voice Transcribe | 0.5 min × $0.003 | 0.002 | 0.002 |
| Scene pass | 65k in + 4k out | 0.098 | 0.098 |
| Role pass vote 1 | 47k in + 4k out | 0.076 | 0.076 |
| Role pass votes 2–3 | 2 × (45k cached + 2k fresh + 4k out) | 0.053 | 0.053 |
| Loop-2 role re-pass | 17k in + 4k out, then 2 × (15k cached + 2k + 4k out) | 0.082 | 0.082 |
| Escalation (`max`) | 17k in + 16k out | 0.089 | 0.089 |
| Red-team pass 1 | 64 frames, 2 calls: 98k in + 6k out | 0.148 | 0.148 |
| Red-team passes 2–3 | 16k in + 2k out; 8.5k in + 1k out | 0.043 | 0.043 |
| **Total per 30 s clip** | | **$1.12** | **$2.57** |
| *With no prompt-cache hits* | +2 × 45k × ($1.25 − $0.15)/M | +0.10 | +0.10 |

**Reading:**
- At 30 fps, SAM is 77% of the cost and a clip costs $2.57, over the cap. So SAM always gets the proxy (§5b, §10.6). Per minute of footage: **$2.24 at 8 fps**.
- **A 60 s clip** (the upload limit, ARCHITECTURE §5) models at **$1.91 with 8 tracks, $1.99 with 16**. That's under `SAFECUT_JOB_USD_CAP = 2.00`, but with almost no margin once pre-call reservations are in flight (§10.5). **Decided:** request WP0 to raise the default `SAFECUT_JOB_USD_CAP` to **$3.00**. The daily cap (public), per-code caps (pilots) and per-WP budgets (owner runs) still bound total spend (§9.2). *Rejected:* keeping $2.00, under which a busy 60 s clip ends "audit over budget" and can never be published.
- **Pilot codes** (PR #2: $4 per code, 2 clips, a $20 total) cover two 30 s clips ($2.24) with margin, but not two busy 60 s clips ($3.82–3.98 against $4, with reservations in flight). Request to PRE-B: raise the per-code cap to **$6** (2 × the $3.00 job cap), keeping the **$20 total** that WP5 enforces separately.

### 9.2 The whole $150: every line, and the WP that spends it
Split sizes are PRE-B's final assignment (PR #2 `docs/labeling/SCHEDULE.md` §3): **12 test, 3 dev, 3 hero** (2 takes each). PRE-B owns labels and pilots; these are this doc's API cost estimates for them. Each WP's own budget (its WP file, AGENTS rule 10) is a **cap**, counted here at its full value.

| Line | Spent by (budget cap) | Calc | USD |
|---|---|---|---|
| Probes | WP0 (≤ $6) | WP0 budget | 6.00 |
| Build and integration tests | WP1 (≤ $8), WP4 (≤ $6), WP5 (≤ $6, includes deployed smoke runs) | their caps | 20.00 |
| Prompt tuning on the dev split (SAM replayed) | WP2 (≤ $15) | **8** iterations × 3 clips × $0.59 (Muse only) | 14.16 |
| Dev first run + SA-Co/VEval SmartGlasses runs | WP7 sandbox (≤ $12) | 3 × $1.12, plus a **$5 cap** on SA-Co SAM sweeps (≈ 6,250 frames: 4 phrases at 6 fps, about 4 min of SmartGlasses video; WP7 sizes the subset to fit) | 8.36 |
| Test split: full Safe Cut + baseline 3 | WP7, run by the owner on the Linux GPU box (BLOCKED) | 12 × $1.12 × 3 runs; 12 × $0.08 × 3 | 43.20 |
| Baselines 1, 1b, 2 and the no-audit ablation | WP7 | reuse the full run's SAM sweeps; EgoBlur runs locally | 0.00 |
| Hero renders (demo and video) | owner / WP8, outside the WP caps | 6 takes × $1.12 × **2** renders (one after review, one final) | 13.44 |
| Creator pilots | PRE-B's hard cap (PR #2 PILOTS §5) | our estimate is 10 clips × $1.12 = $11.20 | 20.00 |
| Public "Try it" (judges, Nov 4–9) | the deployed service's daily cap | 6 days × $3 | 18.00 |
| **Planned total** | | | **$143.16** |
| **Headroom vs $150** | | | **$6.84** |

**Decisions in this table:**
- **Fit every cap inside $150.** Dev tuning is **8** rounds (it fits WP2's $15); there are **2** hero renders per take (not 3); SA-Co gets a **$5** cap. *Rejected:* the earlier plan, which left the WP1/WP4/WP5 build budgets ($20) out of the total and quietly over-committed the credits.
- **Spending caps by who is calling** (also §10.2):
  - **`SAFECUT_DAILY_USD_CAP` ($3/day) covers only public "Try it" traffic** (judge access codes) and `/healthz`;
  - **pilot codes** sit outside it, with their own per-code cap and PRE-B's $20 total (as PR #2 PILOTS §5 asks);
  - **owner, eval and WP runs** are bounded by the per-job cap and their WP caps.

  The cap is $3/day over the whole deployed window. *Rejected:* ARCHITECTURE §4's $10/day default, under which 12 days could spend $120. Request to WP5: deploy with `SAFECUT_DAILY_USD_CAP=3.00`, apply it to access-code traffic only, and add a per-code cap for pilot codes.
- **Wonder isn't pre-approved.** The $6.84 headroom fits none of the options: Wonder for the scene pass on test and hero runs is +$11.60, and the larger options are more (§9.1 deltas: scene +$0.24, escalation +$0.30 per run). WP0 adopts Wonder only if probe f shows a gain (H1/H2) **and** the measured spend in `cost.jsonl` by then (WP caps are maxima, and replay-heavy WPs usually come in under) leaves room for the extra. If Wonder escalation is ever used, its `max_output_tokens` is 24,000 (§10.5).

**Risks to this budget:**
- **30 fps SAM** would make the test runs alone $92.53. Never send `prepared.mp4` to SAM (§10.6).
- **Busy clips:** with 16 tracks, red-team pass 1 needs 96 frames instead of 64. That's +$0.06 per run, or +$2.16 over the 36 test runs, a third of the headroom.
- **Dev iteration** beyond 8 rounds costs $1.77 per round (3 clips × $0.59) and would breach WP2's $15 cap.

---

## 10. Client implementation spec (WP0 builds `safecut/meta/` from this)

Everything here is either sourced (tagged) or a **decision** for the build. WP0's probes may change values marked *(probe)*; nothing else should need guessing.

### 10.1 Transport and limits
| Setting | Value | Why / source |
|---|---|---|
| Base URL | `https://api.meta.ai/v1` (env `SAFECUT_META_BASE_URL`, default this) | [GH-cookbook] |
| Auth | header `Authorization: Bearer $MODEL_API_KEY`; the key is never logged, and logs redact the header | [GH-cookbook]; AGENTS rule 6 |
| HTTP client | one shared `httpx.AsyncClient` per process, HTTP/1.1, `limits=Limits(max_connections=16)` | decision: bounded resources |
| Concurrency | per job ≤ 4 SAM streams + ≤ 3 Responses calls in flight; per process ≤ 8 Meta requests in flight (an `asyncio.Semaphore` each) | decision: 3,000 RPM / 4M TPM ([SNIP] §3.7) is far above this; the bound is memory and the per-job cap |
| Connect timeout | 10 s | decision |
| SAM stream | read idle 90 s (no SSE event); total ≤ 600 s per request | decision *(probe: measured latency)*; [3P] Reka ≈0.4 s/frame → ~96 s for 240 frames |
| Responses (stream) | read idle 300 s (`medium`), 600 s (`max`, which reasons silently before output); total ≤ 900 s | decision *(probe)*; [3P] reasoning precedes output (§3.5) |
| ASR one-shot | total 180 s for ≤60 s of audio (upload + transcription) | decision; [GH-cookbook] uses 300 s for up to 10 min |
| Files upload | total `30 s + size_MB × 2 s` | decision |
| Processing-segment wall clock (WP5) | 2 h for each processing segment: (a) upload → review-ready, (b) creator approval → render + audit done. The creator's review time doesn't count. A segment running longer is cancelled and its files deleted | decision; matches the Modal worker `timeout=7200` (one worker call per segment) and stays below the 6 h file expiry (§10.4) |
| Files delete | total 15 s | decision |

### 10.2 Retries (one policy, `safecut/meta/retry.py`)
- **Retry on:** HTTP 429, 500, 502, 503, 504, connect or read timeouts, connection resets, and a stream that ends with no terminal event (SAM `IncompleteOutcome(reason="eof")`). **Never retry:** 400, 401, 403, 413, 422, refusals (the red-team's one rephrased re-ask, `redteam.md`, is its stage's single re-ask, §10.6, not a transport retry), a server-declared `status: "incomplete"`, or a schema-invalid but complete response (that gets one *re-ask*, §10.6, not a transport retry). A 404 is retried only as `MetaFileGone` (re-upload, §10.4). [GH-cookbook] `09_error_handling`.
- **Attempts** (the only retry counts in the repo; prompt specs refer here): Responses at `none`…`high`, ASR and Files: **4** in total. Responses at `xhigh`/`max`: **2** in total (each attempt can cost ≈ $0.23, C4). **SAM: 2** in total, because every attempt re-bills the frames. A schema re-ask is one extra call on top of these, and only after a complete response.
- **Backoff:** `min(30, 1.0 × 2^(attempt−1)) + uniform(0, 1)` seconds (attempt 1 → 1–2 s, 2 → 2–3 s, 3 → 4–5 s). If the response has a `Retry-After` header (seconds or HTTP-date), wait `max(that, backoff)`. Whether Meta sends it is unknown *(probe)*.
- **Throttle before a 429:** read `x-ratelimit-remaining-requests` and `x-ratelimit-remaining-tokens` [GH-cookbook]. When either is below 5% of its `x-ratelimit-limit-*`, delay new requests by 1 s and log `throttled`.
- **Circuit breaker:** counts **calls** that failed after exhausting their attempts, not individual attempts. Five such failures within 60 s open the breaker for 60 s. Then it's half-open: one trial call is allowed; success closes it, failure re-opens it for 60 s. While it's open, calls fail fast with `MetaUnavailable`. A hide-critical stage that fails transiently sends the job to **`retry_later`** (rules below the typed-error table). `/healthz` reports degraded while the breaker is open.
- **Cost accounting (honest numbers, AGENTS rule 9):**
  - Before each attempt, **reserve** its pre-call estimate (§10.5) against the **job cap**, and against the cap of **who started the job**: a public access code → `SAFECUT_DAILY_USD_CAP`; a pilot code → its per-code cap and the $20 pilot total (PR #2 PILOTS §5); the owner, eval and WP runs → the job cap only. `/healthz` counts against the daily cap (§9.2).
  - On success, replace the reservation with the actual cost from `usage`, logged `estimated: false`.
  - On a failure where the request was **rejected before processing** (any non-200 HTTP status received **before the first stream event**, which covers 429, other 4xx and an immediate 5xx, or a connect error), release the reservation and log `usd: 0`. Assumption: Meta doesn't bill requests that error before producing output. WP0 checks this against the console's billing after the probes.
  - On a failure **after** the request was accepted (read timeout or stream drop **after** the first event), billing is unknown. Keep the reservation as a charge against the **caps**, and log it with `estimated: true`.
  - Reported figures (receipt `cost_usd`, README cost per minute, eval cost) sum **only `estimated: false` lines**. The receipt shows the estimated total as a separate line, "possibly billed: $x". So the caps are conservative and the reported numbers are measured.

### 10.3 Typed errors (`safecut/meta/errors.py`)
| Exception | Raised on | Pipeline effect |
|---|---|---|
| `MetaAuthError` | 401, 403 | stop the job; `/healthz` red; never retried |
| `MetaConfigError` | 404 on the model or path (not on a file), or a 400 naming `model`, `reasoning`, `text.format` or an unsupported param | stop the service at the startup probe (§3.4); mid-job → the stage fails closed and `config_error` is logged |
| `MetaFileGone` | 404 whose error `param` or `message` names the request's `file_id` | re-upload the file from the job directory once (§10.4), update `files.json`, repeat the call; a second 404 → `MetaBadRequest` |
| `MetaBadRequest` | any other 400 / 413 / 422 | the stage fails closed; the request shape is logged (without media or the key) |
| `MetaRateLimited` | 429 after the last attempt | the stage fails closed; a hide-critical stage → job `retry_later` |
| `MetaUnavailable` | 5xx or timeout after the last attempt, or the breaker is open | the stage fails closed; a hide-critical stage → job `retry_later` |
| `MetaRefusal` | a refusal part or event (§3.6, [GH-sam]) | the stage fails closed; logged |
| *(parser exceptions, `meta-sam-parser` 0.1.0)* | `ResponsesStreamSourceError` wraps the transport's exception (read it from `__cause__`, or the error's wrapped exception): map that inner exception as above (an `httpx` timeout or reset → retryable). `ResponsesStreamFailedError` (a `response.failed` event) and `ResponsesStreamEventError` (an `error` event) → retryable as `MetaUnavailable` within the SAM attempt count. `ResponsesStreamLaneError` (no or interleaved output lane) and `ResponsesStreamParserError` → non-eof `MetaIncomplete`. `ResponsesStreamRefusalError` → `MetaRefusal` | as for the mapped type |
| `MetaIncomplete` | the server declares `status: "incomplete"` (e.g. `incomplete_details.reason: "max_output_tokens"`), or a SAM stream still ends without a terminal event after its last attempt (S7), or the parser reports an `error` diagnostic (S5) | the stage fails closed; not retried |
| `BudgetExceeded` | the pre-call estimate exceeds the remaining job cap or the caller's cap (§10.2: daily cap for public codes, the per-code cap for pilots) | the call isn't made; the stage fails closed with reason `over_budget` (the same word as `audit.json` `redteam_status`). For the audit, the frames count in `unresolved` (§12) |

"Fails closed" means: for a stage that could only *add* keep evidence (role pass, escalation, scene pass, speech), the job continues with everything hidden and `needs_you` (docs/prompts/README.md rule 3). For a stage that's needed to *hide* (SAM base sweep, render), the job can't be published. It goes to **`retry_later`** when the cause is transient (`MetaUnavailable`, `MetaRateLimited`, or an eof `MetaIncomplete`); WP5 re-queues it once after 5 min. Otherwise it goes to **`failed`**: `MetaAuthError`, `MetaConfigError`, `MetaBadRequest`, `MetaRefusal`, `BudgetExceeded`, and a **non-eof** `MetaIncomplete` (a server-declared incomplete, or a parser `error` diagnostic, S5), which is deterministic, so re-running wouldn't help.

**The audit is the exception, because a rendered output already exists.** Any audit pass that can't run or finish (transient failure after its attempts, `BudgetExceeded`, or a refusal after the red-team's one rephrased re-ask) adds **every frame it should have audited** to `unresolved`, with `audit.redteam_status` set to `failed` or `over_budget` (PR #2's field, §12). The job goes to **`needs_you`**, never `failed` or `retry_later`, and the result page offers PR #2's **[Check again]** (UI-SPEC §5.3: `POST /v1/jobs/{id}/render` with `audit_only: true`) for `failed` only, which re-runs only the audit. `over_budget` gets no retry, since it would fail the same way. Publishing stays off through the one gate, `unresolved == 0`.

### 10.4 Files: idempotency and cleanup
- No idempotency key is documented for any endpoint, so idempotency is done **client-side through the job directory**:
  - before uploading, compute `sha256(file)`; if `jobs/<id>/files.json` already maps that hash to a live `file_id`, reuse it;
  - write `{name, sha256, file_id, purpose, created_at, deleted_at: null}` to `files.json` (the §12 fields) **before** the first use;
  - at the **end of each processing segment** (§10.1: review-ready, or render + audit done), and on cancel or failure, `DELETE /v1/files/{id}` for every entry. A 404 on delete counts as deleted. Then set `deleted_at`. Segment (b) re-uploads `sam_proxy.mp4` only if an audit patch needs a SAM point prompt. So no Meta file waits through a creator's review, and none outlives its segment;
  - an hourly sweeper (the WP5 cron) deletes anything in any `files.json` older than **6 h** that has no `deleted_at`. Upload with **`expires_after` 21,600 s (6 h)** as the backstop. That's well above the 2 h segment limit (§10.1), so a running segment never loses its file. If one does anyway, `MetaFileGone` re-uploads it.
- A retried Responses call is a new response. Stage outputs are checkpointed in the job directory, so a re-run stage replays its saved response (`SAFECUT_REPLAY=1`) instead of calling again.

### 10.5 Pre-call cost estimate and `cost.jsonl`
Prices live in `safecut/config.py` as a dated table (the §6 values, `price_table_date = "2026-10-24"`, re-read on Oct 26).

| Call | Pre-call estimate (worst case, checked against the remaining caps) | `units` logged after the call | `usd` |
|---|---|---|---|
| Responses | `POST /v1/responses/input_tokens` count [GH-cookbook] × `P_in` + `max_output_tokens` × `P_out` | `{"input": in, "cached": c, "output": out, "reasoning": r}` from `usage` (`input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`) | `(in − c) × P_in + c × P_cached + out × P_out` (reasoning is already inside `out`) |
| SAM video | `frames_billed × $0.0002` | `{"frames": frames_billed}` (worst case: every uploaded frame billed; replace it with `usage` if SAM reports any) *(probe)* | `frames × 0.20 / 1000` |
| ASR | `ceil(duration_s) × $0.00005` | `{"audio_s": floor(audioDurationMs / 1000)}` | `audio_s × 0.18 / 3600` (billing rounds down to whole seconds, [SNIP]) |
| Files | 0 | `{"bytes": n}` | 0 (no file price documented) |

- `max_output_tokens`: `medium` and lower 16,000; Spark `max` 48,000 (worst-case escalation `17k × $1.25/M + 48k × $4.25/M` ≈ $0.23, C4); **Wonder `max` 24,000** (≈ $0.55; at 48k it would be $1.03, enough to breach the job cap on its own, §9.2). A response cut off by this limit is `MetaIncomplete`.
- `cost.jsonl` line: `{"ts", "job_id", "stage", "model", "attempt", "units", "usd", "estimated": bool, "request_id"}`. `request_id` is the response's `id` (or `x-request-id` if present). This extends ARCHITECTURE §3.10 with `job_id`, `attempt` and `estimated`; WP0 adds them to the contract.

### 10.6 Request and response shapes
**SAM video** (one request per concept or per object-prompt batch):
```json
{"model": "sam-3.1", "stream": true, "store": false,
 "metadata": {"include_confidence": "true"},
 "input": [{"type": "message", "role": "user", "content": [
   {"type": "input_text", "text": "face"},
   {"type": "input_video", "file_id": "file-abc123"}]}]}
```
- `store: false` follows AGENTS rule 6. Whether `sam-3.1` accepts it is unverified *(probe)*. If it's rejected, the receipt's `data_handling` reports `store` per model truthfully. Never claim `store:false` for a call that didn't send it.
- **Don't send `metadata.mask_encoding`.** It isn't in the protocol file. The parser decodes both encodings, and the lossless default needs no request key.
- Object prompts replace the noun phrase text with `build_object_prompt(...)` output, plus `metadata.propagation_direction: "both"`.
- Parse the stream with `parse_responses_stream(events, video_segmentation_format())`. The result's `.records` give box and mask records (from the direct parser, use `finish(...).result.records`); `.outcome.status` is `completed` or `incomplete`; `.diagnostics` with severity `error` means data was dropped, so treat the request as `MetaIncomplete` (fail closed) and log the lines.

**Muse Spark / Wonder** (role pass shown; the other passes differ only in content, schema name and effort):
```json
{"model": "muse-spark-1.3", "stream": true, "store": false,
 "reasoning": {"effort": "medium"}, "max_output_tokens": 16000,
 "input": [
   {"role": "system", "content": [{"type": "input_text", "text": "<system prompt>"}]},
   {"role": "user", "content": [
     {"type": "input_text", "text": "<role definitions + scene + transcript>"},
     {"type": "input_image", "image_url": "data:image/jpeg;base64,<F90>"},
     {"type": "input_text", "text": "<vote phrasing k + labels per frame>"}]}],
 "text": {"format": {"type": "json_schema", "name": "role_pass", "strict": true, "schema": {"…": "…"}}}}
```
- Images go **only** in the user message (a system message with an image → 400) [GH-cookbook]. They're JPEG at quality 90, sent at the prepared resolution plus a `bar_h = 40 px` frame-number bar (§5), ≤50 images per request.
- Don't send `temperature`, `stop`, `n`, `logprobs`, `logit_bias`, `response_format` or `truncation` (all 400 or unverified, §3.6). `temperature` is unverified *(probe)*.
- The output is in `response.completed` → `response.output[]`: take the `type: "message"` item's `content[]` part with `type: "output_text"`. A `type: "refusal"` part → `MetaRefusal`. Parse the text as JSON, then validate with the pydantic model. If invalid, **re-ask once** with the same request, then fail closed.

**Files upload / delete:** **two uploads per job**: `sam_proxy.mp4` (≤10 fps, §5b; used by every SAM request) and `prepared.mp4` (the scene pass, and the speech fallback's soundtrack). Each is a multipart `POST /v1/files` with `purpose=user_data`, `file=@<name>`, `expires_after[anchor]=created_at`, `expires_after[seconds]=21600` → `{"id": "file-…" | "file_…", …}`. `DELETE /v1/files/{id}` → 200 `{"id", "deleted": true}`, or 404 (treated as deleted). The response bodies are OpenAI-compatible and unverified *(probe)*. Sending `prepared.mp4` to SAM by mistake multiplies the SAM cost by `job.fps / sam_fps` and breaks the frame indexing, so WP1's request builder takes the proxy's `file_id` from `files.json` by name.

**ASR:** see §4.1. Use `mode: "DIARIZATION"` and validate the mode client-side (an unknown mode is silently ignored [GH-cookbook]). The WAV is extracted from `prepared.mp4` (mono, 16-bit, 24 kHz).

### 10.7 Startup probe and `/healthz`
**At startup only** (once per deploy): for each configured `(model, effort)` pair, send a minimal request (text "ok", `max_output_tokens: 16`, `store: false`); for SAM, a 64×64 PNG with the text `"square"` (≈ $0.0025). Any HTTP 200 counts as healthy, even `status: "incomplete"`, because reasoning may use up the 16 tokens. A 400 or 404 → `MetaConfigError` → refuse to start; 401/403 → `MetaAuthError`.

**`/healthz`** (ARCHITECTURE §5: at most once a minute) sends **one** text request to `SAFECUT_ROLE_MODEL` at `reasoning.effort: "minimal"`, `max_output_tokens: 16`. At most ≈ 20 input + 16 output tokens = (20 × $1.25 + 16 × $4.25) / 1M = **$0.000093** per check, so at most **$0.134 a day** (1,440 checks) even if it's polled every minute. It never calls SAM. Probe costs are logged with stage `healthz` and count against `SAFECUT_DAILY_USD_CAP`, which leaves $2.866 of the planned $3/day for jobs.

---

## 11. Test vectors (expected outputs; WP0/WP1/WP2/WP4 copy these into tests)

Vectors in 11.1 came from Meta's `meta-sam-parser` 0.1.0, run in a scratch venv on 2026-10-24. Vectors in 11.2–11.5 came from a scratch reference implementation of §5, §5b and §10.5, run the same day. The scripts aren't committed (AGENTS rule 1); the outputs are pasted in PR #1.

### 11.1 SAM wire → records (`video_segmentation_format()`, then `finish(CompletedOutcome())`)
| # | Input line(s) | Expected records | Outcome / diagnostics |
|---|---|---|---|
| S1 | `<7f>0<\|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80\|><\|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?\|>` | box `id "0"`, frame 7, left 10, top 20, **right 15, bottom 25** (half-open); mask `one_bit`, 5×5, 10 foreground pixels | completed, none |
| S2 | the two-object line from `meta-sam/python/README.md` (ids 0 and 1, `w=320;h=334`) | id 0: box 211,228 → 271,255; mask `lossless` **60×27** (= box size), 1,539 px. id 1: box 155,228 → 203,255; mask 48×27, 1,236 px | completed, none |
| S3 | S1 with `;c=0.75` on the box token | box `confidence 0.75`; mask confidence `None` (each token carries its own) | completed |
| S4 | a `<9f>12…` line, then S1's `<7f>0…` line | records in **arrival order**: id `"12"` frame 9 first, then id `"0"` frame 7 | completed |
| S5 | `<0f>` (bare header) | no records | completed, **1 error `malformed_record` line 1** → treat as `MetaIncomplete` |
| S6 | empty lane | no records | completed (a valid zero-match result, **not** an error) |
| S7 | S1, then the stream ends with no terminal event (`IncompleteOutcome(reason="eof")`) | S1's records | **incomplete** → retry policy (§10.2) |

Object prompts (`build_object_prompt(size=(1280, 720), objects=[…])`):
| # | Objects | Expected text |
|---|---|---|
| O1 | id 1, frame 30, point (639, 339) | `<30f>1<\|point;x=639;y=339;w=1280;h=720\|>` |
| O2 | id 1, frame 30, `PromptBox(100, 50, 200, 150)` + point (150, 100) + negative point (10, 10) | `<30f>1<\|box;x1=100;y1=50;x2=199;y2=149;w=1280;h=720\|><\|point;x=150;y=100;w=1280;h=720\|>-<\|point;x=10;y=10;w=1280;h=720\|>` (half-open in, inclusive out) |
| O3 | point (1280, 10) or (−1, 10) | raises `ObjectPromptError`, code `invalid_point` |

### 11.2 Grid → pixels (§5; frame 1280×720, `bar_h` 40, sent image 1280×760)
| # | Input (0–1000) | Kind | Expected |
|---|---|---|---|
| G1 | point (500, 500) | point | (639, 339) |
| G2 | point (0, 0) | point | **dropped** (in the bar) |
| G3 | point (1001, 1000) | point | (1279, 719) (clamped) |
| G4 | point (0, 53) | point | (0, 0) |
| G5 | point (0, 52) | point | **dropped** |
| G6 | point (250, 750) | point | (319, 529) |
| G7 | box [100, 100, 300, 400] | red-team | [127, 35, 384, 264] (half-open) |
| G8 | box [100, 0, 300, 40] | red-team | **dropped** (`in_bar`: y_img 0–30 < 40; the model read our frame label) |
| G9 | box [100, 0, 300, 40] | miss-loop | **dropped** (`in_bar`; keep the point if it's valid) |
| G10 | box [500, 500, 501, 501] | red-team | [639, 339, 641, 341] |
| G11 | box [−5, 60, 1001, 1001] | red-team | [0, 5, 1280, 720] |
| G12 | box [300, 100, 100, 400] (reversed x) | red-team | [127, 35, 384, 264] (normalised, = G7) |
| G13 | box [100, 40, 300, 60] (straddles the bar's edge) | red-team | [127, 0, 384, 6] |
| G14 | box [0, 52, 10, 53] (1 px tall after mapping) | red-team | [0, 0, 22, 16] (degenerate → 32 px box centred at (6, 0), clamped) |

### 11.3 Time axes (§5b). The ground truth is ffmpeg 6.1.1's own output, matched by frame checksums
Constant-rate case: `job.fps` 30, `job.frames` 900, `sam_fps_eff` 8, `sam_frames` read back = **240**.

| # | Function | Input | Expected |
|---|---|---|---|
| T1 | `from_proxy` | j = 0, 1, 2, 3, 4, 8, 120, 239 | 1, 5, 9, 13, 16, 31, 451, 898 (prepared frame 899 never reaches the proxy) |
| T2 | `to_proxy` | f = 0, 1, 2, 3, 4, 5, 6, 7, 450, 898, 899 | 0, 0, 0, 0, 1, 1, 1, 1, 120, 239, 239 |
| T3 | `max_f abs(from_proxy(to_proxy(f)) − f)` | all f | **2** at this length (bound `ceil(30/8)` = 4; other lengths reach 3) |
| T4 | `to_proxy(from_proxy(j)) == j` | all j | true |
| T5 | player (PR #2 formula) | `mediaTime` 0.0, 0.0249, 0.025, 1/30, 0.05, 29.99, 31.0 | 0, 0, **1**, 1, 1, 899, 899 (clamped). The quarter-frame tolerance switches to the next frame 0.75 of the way through a frame |
| T6a | `times`, `job.fps` 10 | source frames at t = 0.00, 0.10, 0.26, 0.40 | ffmpeg wrote 4 frames: `times` = [0.00, 0.10, **0.10**, 0.26]. 0.26 → slot 3, so slot 2 repeats 0.10, and the 0.40 frame isn't emitted at end of stream |
| T6b | `times`, `job.fps` 10 | 0.00, 0.10, 0.31, 0.40 | 4 frames: [0.00, 0.10, 0.10, 0.31] (the nearest-frame rule happens to agree here; T6a is the case where it doesn't) |
| T6c | `times`, `job.fps` 10 | 0.00, 0.03, 0.04, 0.09, 0.10, 0.40 | 4 frames: [**0.04**, 0.10, 0.10, 0.10]. Slot 0 keeps its last frame (0.04), so `times[0] > 0` |
| T9 | start normalisation | a 30 fps video stream starting at 0.1 s, audio at 0; proxy at 8 fps | **without** `setpts=PTS-STARTPTS`: proxy frames show prepared frames 2, 6, 10, 13, 17 (shifted). **With** it: 1, 5, 9, 13, 16, which equals T1's rule. The audio is trimmed by 0.1 s so both streams start at 0 |
| T10 | back-fill scaling | `job.fps` 30, `sam_fps_eff` 8; `job.fps` 25, `sam_fps_eff` 8; `job.fps` 6, `sam_fps_eff` 6 | 57, 47, 15 prepared frames |

### 11.4 Cost (§10.5; Spark $1.25 / $0.15 / $4.25 per M)
| # | Call | Units | Expected `usd` |
|---|---|---|---|
| C1 | Responses | in 47,000, cached 0, out 4,000 | 0.07575 |
| C2 | Responses | in 47,000, cached 45,000, out 4,000 | 0.02625 |
| C3 | Responses (`max`) | in 17,000, cached 0, out 16,000 | 0.08925 |
| C4 | Responses pre-call worst case (`max`) | count 17,000, `max_output_tokens` 48,000 | 0.22525 |
| C5 | SAM | 240 frames | 0.048 |
| C6 | SAM | 7 concepts × 900 frames | 1.26 |
| C7 | ASR | `audioDurationMs` 30,500 | 0.0015 (30 s) |
| C8 | ASR | `audioDurationMs` 59,999 | 0.00295 (59 s) |

### 11.5 Retry, failure and cost-accounting schedule (§10.2–10.4), with `uniform` stubbed to 0
| # | Sequence of outcomes | Expected |
|---|---|---|
| R1 | Responses (`medium`): 429, 429, 200 (no `Retry-After`) | waits 1 s, 2 s; returns the 200. `cost.jsonl`: two lines with `usd: 0` (rejected before processing) and one actual line (`estimated: false`) |
| R2 | 429 with `Retry-After: 7`, then 200 | waits 7 s |
| R3 | 400 | no retry; `MetaBadRequest` (or `MetaConfigError` if `param` names the model, effort or format) |
| R4 | SAM base sweep: read timeout, read timeout | 2 attempts, then `MetaUnavailable`. Both attempts were accepted, so both reservations stay as **estimated** charges against the caps. Job → **`retry_later`** |
| R5 | Responses (`medium`): 503 × 4 | waits 1, 2, 4 s, then `MetaUnavailable`; role pass fails closed (all `unsure`) |
| R6 | 5 **calls** fail (each after its own attempts) within 60 s | breaker opens; the next call raises `MetaUnavailable` without a request; after 60 s one trial call is allowed; success closes it |
| R7 | Responses (`max`): timeout, timeout | **2** attempts only, then `MetaUnavailable`; escalation fails closed (E3) |
| R8 | SAM stream ends with no terminal event (eof), then a complete stream | eof counts as retryable: the second attempt's records are used |
| R9 | SAM stream eof, eof | `MetaIncomplete` after 2 attempts; base sweep → job `retry_later` |
| R10 | SAM request → 404 naming the `file_id` | `MetaFileGone`: re-upload `sam_proxy.mp4`, update `files.json`, repeat once. A second 404 → `MetaBadRequest` |
| R11 | Responses complete, but the JSON fails pydantic validation | one re-ask (same request); invalid again → the stage fails closed. Both calls are logged with their actual cost |
| R12 | the pre-call estimate exceeds the remaining job cap | no request; `BudgetExceeded`; the stage fails closed with reason `over_budget`. If the stage was a red-team pass over 40 frames: `unresolved` += 40, `redteam_status: "over_budget"` |

---

## 12. Contract changes PRE-A proposes (one list; WP0 implements them in `contracts.py` and ARCHITECTURE §3 together, per AGENTS rule 3)
Nothing is implemented yet (there's no code before kickoff), so these are **changes to the contract and its examples**, not backward-compatibility shims. Fields marked **required** have no default, and WP0 updates the ARCHITECTURE examples to include them. Optional fields have the default shown. The prompt specs emit model output; the pipeline maps it into these files.

| File | Field | Type, default | Written by → read by | Why |
|---|---|---|---|---|
| `scene.json` | `participants[].is_creator` | bool, optional, `false` | WP2 → role pass | the creator's own face must be found even if only seen in a mirror (`scene-pass.md` case 1) |
| `scene.json` | `children[]` | `[{description: str}]`, optional, `[]` | WP2 → role pass | early child flag; children are locked hidden |
| `scene.json` | `others_present` | str, optional, `""` | WP2 → role pass | context: kinds of non-participants |
| `scene.json` | `candidate_objects[].approx_time` | **required** enum `beginning\|middle\|end\|throughout\|unknown` | WP2 → miss loop | replaces free text; WP0 changes ARCHITECTURE §3.4's example `"mid-clip"` to `"middle"` |
| `roles.json` | `tracks[].matches_participant` | int \| null, optional, `null` | WP2 → UI | index into `scene.participants`. The UI's speech link is `scene.participants[matches_participant].speaker` |
| `roles.json` | `tracks[].suggested_role` | enum role \| null, optional, `null` | WP2 (escalation) → Needs-you card | advisory only, never a keep (`escalation.md`) |
| `roles.json` | `tracks[].escalation_evidence`, `tracks[].escalation_frames` | str \| null and `[int]` \| null, optional, `null` | WP2 → Why drawer | escalation's own evidence and cited frames, kept apart from the role pass's `evidence` (field names as PR #2 UI-SPEC §4.6 adopted them). The ruling's `why_others_wrong` goes to the job log only |
| `roles.json` | `missed[].box` | `[x1,y1,x2,y2]` half-open px \| null, optional, `null` | WP2 → WP1 object prompt | better SAM prompt |
| `roles.json` | `missed[].recurs` | bool, optional, `false` | WP2 → WP1 | gates paid phrase sweeps |
| `transcript.json` | `degraded` | bool, optional, `false` | WP2 → role pass, receipt | a dropped soundtrack is visible, never silent |
| `tracks.json` | `sam_fps`, `sam_frames` | number, int, **required** | WP1 → frame maps (§5b) | read back from `sam_proxy.mp4` |
| `tracks.json` | `requests[].fps`; `requests[].frames_billed` (ARCHITECTURE §3's name) | number **required**; int as in ARCHITECTURE | WP1 → cost, receipt | `fps` is new. `frames_billed` = the uploaded frame count (worst case) until SAM reports `usage` (§10.5) |
| `tracks.json` | `requests[].kind`, `requests[].matches` | `"phrase"\|"object_prompt"`, int, **required** | WP1 → miss-loop logs, eval | which request type ran, and how many objects it found (`miss-loop.md` zero-match logging) |
| **`files.json`** (new, per job) | `[{name, sha256, file_id, purpose, created_at, deleted_at}]` | **required** fields; `deleted_at` null until deleted | WP0 client → WP1 (proxy id by `name`), WP5 sweeper, receipt `files_deleted` | idempotent uploads and guaranteed deletion (§10.4) |
| `audit.json` | `leaks[].flag` | `"redaction_too_weak"` \| null, optional, `null` | WP4 → re-render, UI | read-through → `solid` (`redteam.md` L7) |
| `audit.json` | `redteam_status` (PR #2 UI-SPEC request 11's name, adopted) | `"ok"\|"failed"\|"over_budget"`, **required**, default `"ok"` | WP4 → UI result panel | why the audit didn't finish. **Invariant: `redteam_status != "ok"` ⇒ `unresolved > 0`.** Every frame an audit pass didn't run on counts in `unresolved`, so `unresolved == 0` stays the one publish gate; `ok` with `unresolved > 0` means real leaks left after 3 passes |
| `cost.jsonl` | `job_id`, `attempt`, `estimated` | str, int, bool, **required** | WP0 client → caps, receipt, eval | reservation accounting (§10.2) |
| `receipt.json` | `cost_usd_estimated` | number, optional, `0` | WP4 → receipt page | "possibly billed" kept apart from measured `cost_usd` (AGENTS rule 9) |
| `receipt.json` | `data_handling.store_by_model` | `{model: bool}`, **required** | WP4 → receipt page | what each model was actually sent. **`data_handling.store` is redefined as `any(store_by_model.values())`**, so it's `false` only when every call sent `store:false` (§10.6) |

Not contract changes: a job's `retry_later` state lives in WP5's job record (API), not in a stage file. `job.json` keeps ARCHITECTURE §3.1's fields, with the meanings in §5b.

Requests to PRE-B (UI, PR #2):
- show `suggested_role`, `escalation_evidence` and `escalation_frames` in the Why drawer next to the votes ("A second look suggests: Part of the story"). Adopted in PR #2 @ `e86a051`;
- show the `redteam_status` panels (PR #2 UI-SPEC §5.3) when it isn't `ok`;
- take a track's speech link from `roles.tracks[].matches_participant` → `scene.participants[i].speaker`, which replaces UI-SPEC §8 request 3 (a track ID in `scene.json`), so the link lives in one place.
