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
- **Consequence for WP1:** no hand-written stream parser is needed. Depend on `meta-sam-parser` and use `decode_mask_to_rle` for `tracks.json` masks. **Stored form (decided, §12):** `masks[f]` is a **frame-sized** COCO RLE (`size` = the prepared clip's `[H, W]`): the box-sized mask is placed at its box origin (rescaled first only if the proxy was downscaled) and re-encoded, so every reader uses one shape. Masks exist only on anchor frames (`from_proxy(j)`). On a frame between two anchors, the renderer's mask is the **union** of the two neighbouring anchors' masks, each shifted by its box's move to the interpolated box, then dilated as usual (WP3/WP4). A frame with only one neighbouring anchor uses that one. That keeps mask-shaped styles from flickering to boxes between anchors, and the union fails toward hiding more.

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
- `keywords` (names, jargon) and `languageBias` are lists of strings. **v1 sends `keywords: []`** (no creator note), and `languageBias` from `SAFECUT_ASR_LANGUAGE_BIAS` (below). They nudge the model and don't guarantee a spelling.

### 4.2 Response
```json
{"sessionId": "…", "transcript": "…", "audioDurationMs": 30000,
 "turns": [{"speaker": "A", "startMs": 1520, "endMs": 3100, "transcript": "How is the weather?"}]}
```
- `turns` is present only in speech modes. `speaker` appears only in `DIARIZATION` and is a **bare letter** (`"A"`, not `speaker_a`).
- `endMs` is used by the cookbook's caption recipe (`07_sam/03…/build-demo-data.py`).
- "Diarization covers non-overlapping speech." Overlapping talk is a known gap.
- **Mapping to `transcript.json` (decided):** speaker letters map to `S1`, `S2`, … in order of first appearance (`"A"` → `"S1"` if A speaks first). That keeps the ARCHITECTURE §3.3 contract and the spark-1.2 fallback on one label scheme: `speaker` matches `^[SU][1-9][0-9]*$`, where `U` labels come only from the fallback (`speech-fallback.md`: an uncertain voice, never reused). A `U` turn's words count as speech evidence, but it's never treated as the same speaker as any other turn. `startMs/1000` → `start`, `endMs/1000` → `end`, and `transcript` → `text`. The WAV is extracted from `prepared.mp4`, so turn times are on the **prepared clock** (§5b).

### 4.3 Limits and errors
- One-shot: **≤10 min of audio or ≤32 MB**, whichever comes first. 413 = body too big; 400 = too long (after decode) or malformed.
- Errors: 401 bad key, 404 bad endpoint, 429 rate limited, 500 "the server exceeded its processing budget".
- **25 languages** (the count is [GH-cookbook]; the list isn't in a reachable source, so whether **Swahili** is supported is unverified: WP0 probe d records the list and tests one Swahili and one Sheng clip). Punctuation, endpointing and speaker attribution are done by the model. **Decided:** v1 has **no** creator note or language field (PR #2's `/try` has neither, and adding one is scope the UI doesn't carry), so `languageBias` comes from `SAFECUT_ASR_LANGUAGE_BIAS` (default `["english"]`; WP0 adds `"swahili"` if probe d shows it's supported), never a constant in code. Prompt slots for the note are filled with "none". If Swahili isn't supported, a Swahili clip's transcript still exists (`degraded: false`) but rarely links speech, so its participants tend to `no_speech_link` holds (`needs_you`), the safe direction.
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
     **box:** Safe Cut pixel boxes are **half-open** `[x1, y1, x2, y2)`, the same convention as the parser's normalised `left/top/right/bottom` (§1.4). First **normalise reversed corners** (swap so that x1 ≤ x2 and y1 ≤ y2). A box lying **entirely inside the bar** (`y2_img < bar_h`) describes our frame label, not the video: it describes our frame label only if it's a red-team `text` finding whose text matches the label (`F` plus digits, spaces ignored): **drop it** and log `in_bar`. **Any other in-bar box** (a face, person or plate finding, or text that isn't the label) is a misplaced real finding: the red-team keeps it as a leak with a **whole-frame box** (fail closed, like a malformed box), Role-pass and miss-loop boxes in the bar are dropped, and the item keeps its point if that's valid (G9, M9). Then map the top-left corner with steps 2–3. For the bottom-right corner, map the same way and then add 1 (`x2 = x2_img + 1`, `y2 = y2_img + 1 − bar_h`). Clamp to `[0, W] × [0, H]`. If the clamped box is under 2 px in either dimension (e.g. a hairline, or a sliver clipped at the frame edge), a **red-team** box becomes a 32×32 px box centred on `((x1+x2) div 2, (y1+y2) div 2)` and clamped to the frame (fail closed: it still gets patched); a **miss-loop** box is discarded and its point kept. When a half-open box goes into a SAM object prompt, it's sent as inclusive `x2 − 1`, `y2 − 1`; `meta_sam_parser.build_object_prompt(PromptBox(left, top, right, bottom))` does this conversion. Test vectors: §11.2.
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
  - **crowded frames:** the 16-object cap (§1.6) is only ever seen on proxy frames. A proxy frame `j` whose detections hit it marks the **whole prepared span around it** as crowded: prepared frames `from_proxy(j−1) + 1` … `from_proxy(j+1) − 1`, with `0` for `j = 0` and `job.frames − 1` for the last proxy frame. `tracks.json` `crowded_frames` lists those **prepared** indices (ARCHITECTURE §3: frames index the prepared clip), so `plan.json` `crowd_fills` covers the frames between anchors too (fail closed; request to WP1 and WP3; vector T11). Listing only `from_proxy(j)` would leave 3 of every 4 prepared frames unfilled at 30 → 8 fps;
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
- **A2** Miss loop: 2 loops (loop 1 on the first role pass's misses, loop 2 on the misses of the role pass that judges loop 1's new tracks), each with **one batched object-prompt request** (all of that loop's points as object ids in one request, which `protocol/sam3.md` allows) **plus one phrase sweep** (miss-loop.md allows up to 3 per loop; each extra sweep bills the whole 240-frame proxy, 240 × $0.0002 = $0.048 on a 30 s clip at 8 fps, so up to 4 extra sweeps add +$0.19 per clip, which the job cap and the hard line caps absorb). Every SAM request sweeps the whole proxy, so each costs the full frame count. That's 4 sweeps per clip.
- **A3** ≈1,500 input tokens per 1280×720 keyframe (unknown; the cookbook only says tokens scale with resolution).
- **A4** The scene pass sees ≈ 65k input tokens (60 sampled frames, from Muse Spark Open's 2 fps sampling).
- **A5** 30 Set-of-Mark keyframes in one role-pass call; votes 2–3 hit the prompt cache for the image prefix.
- **A6** Output including reasoning: `medium` ≈ 4k tokens per call, `max` ≈ 16k (`high` ≈ 8k, `xhigh` ≈ 12k; no per-level figures are published).
- **A7** 8 tracks per typical clip (hero clip 1 has about 16).
- **A8** Red-team pass 1 = 30 frames at 1 fps + 4 frames per track (`redteam.md` sampling) + 2 EgoBlur flags = 64 frames in 2 calls. Pass 2 = 10 patched frames; pass 3 = 5 (WP4 allows 3 passes).
- **A9** Loop 2's role re-pass: about 10 new keyframes, with 3 votes.
- **A10** A **60 s** clip: SAM 7 concepts × 480 proxy frames ($0.672) + 4 miss-loop sweeps × 480 ($0.384); Voice Transcribe 1 min ($0.003); the scene pass at 2 fps sees 120 frames (≈ 130k in + 4k out, $0.179); the role pass at 1 fps has 60 keyframes, so it runs in **2 windows** (`role-pass.md`: ≤50 per call, 5 s overlap): 50 + 15 keyframes, each with vote 1 fresh and votes 2–3 cached ($0.175 + $0.093); loop-2 re-pass as at 30 s ($0.082); escalation in up to **2 windows** (`escalation.md`, $0.178); red-team pass 1 = 60 + 4 per track + 2 frames (94 frames in 2 calls with 8 tracks, $0.205; 126 in 3 calls with 16, $0.279) and passes 2–3 as at 30 s ($0.043). That models **$2.02 with 8 tracks and $2.09 with 16**. With no prompt-cache hits, votes 2–3 of both windows and loop 2 pay fresh input: +$0.25, so **$2.26 / $2.34**.

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
| *With no prompt-cache hits* | +(2 × 45k + 2 × 15k) × ($1.25 − $0.15)/M (votes 2–3 and loop 2's votes 2–3) | +0.13 | +0.13 |

**Reading:**
- At 30 fps, SAM is 77% of the cost and a clip costs $2.57, over the cap. So SAM always gets the proxy (§5b, §10.6). Per minute of footage: **$2.24 at 8 fps**, defined as 2 × the 30 s clip. A single 60 s clip costs less ($2.02 with 8 tracks, below), because the SAM-free calls don't all double. The README quotes per-clip costs from `metrics.json`, never this per-minute figure.
- **A 60 s clip** (the upload limit, ARCHITECTURE §5) models at **$2.02 with 8 tracks, $2.09 with 16**, and **$2.26 / $2.34** with no cache hits (A10). These replace the earlier $1.91 / $1.99, which priced the role pass and escalation as one window each. That's over ARCHITECTURE's `SAFECUT_JOB_USD_CAP = 2.00`, before pre-call reservations in flight (§10.5). **Decided:** request WP0 to raise the default `SAFECUT_JOB_USD_CAP` to **$3.00**. The daily cap (public), per-code caps (pilots) and per-WP budgets (owner runs) still bound total spend (§9.2). *Rejected:* keeping $2.00, under which a busy 60 s clip ends "audit over budget" and can never be published.
- **Pilot codes** (PR #2 @ `32a349f`: $6 per code, one clip plus one retry, a $20 total that returns `pilot_pool_cap`) cover a busy 60 s clip and its retry ($4.04–4.18, or $4.52–4.68 with no cache hits) with margin. This was PRE-A's request (the earlier $4 couldn't), now adopted.

### 9.2 The whole $150: every line, and the WP that spends it
Split sizes are PRE-B's final assignment (PR #2 `docs/labeling/SCHEDULE.md` §3): **12 test, 3 dev, 3 hero** (2 takes each). PRE-B owns labels and pilots; these are this doc's API cost estimates for them. Each WP's own budget (its WP file, AGENTS rule 10) is a **cap**, counted here at its full value.

| Line | Spent by (budget cap) | Calc | USD |
|---|---|---|---|
| Probes | WP0 (≤ $6) | WP0 budget | 6.00 |
| Build and integration tests | WP1 (≤ $8), WP4 (≤ $6), WP5 (≤ $6, includes deployed smoke runs) | their caps | 20.00 |
| Prompt tuning on the dev split (SAM replayed) | WP2 (≤ $15) | its cap; the plan uses **8** iterations × 3 clips × $0.59 (Muse only) = $14.16 of it. During tuning the **miss loop's new SAM requests are stubbed** (`SAFECUT_MISS_SAM=stub`, a WP2-only tuning switch: each kept miss item takes the miss loop's static hidden box, `miss-loop.md` Failure handling), because a changed prompt yields new phrases and points with no saved response to replay; live, they'd add up to $0.19 per clip and push 8 rounds to about $18.7. Eval and service runs always call SAM | 15.00 |
| Dev first run + SA-Co/VEval SmartGlasses runs | WP7 sandbox (≤ $12) | its cap; the plan uses 3 × $1.12 plus a **$5 cap** on SA-Co SAM sweeps ($5 = 25,000 billed frames = 4 phrases × 6,250 video frames, about 17 min of SmartGlasses video at 6 fps; WP7 sizes the subset to fit) = $8.36 of it | 12.00 |
| Test split: full Safe Cut + baseline 3 | WP7, run by the owner on the Linux GPU box (BLOCKED); **hard cap $43.20** enforced by `eval/run.py` from `cost.jsonl` | 12 × $1.12 × 3 runs; 12 × $0.08 × 3 (priced at a 30 s mean clip; the owner's SHOTLIST allows 15–45 s) | 43.20 |
| Baselines 1, 1b, 2 and the no-audit ablation | WP7 | reuse the full run's SAM sweeps; EgoBlur runs locally | 0.00 |
| Hero runs (demo and video, Nov 3) | the owner, through PR #2's **recording code** (UI-SPEC request 20; WP8 itself spends $0, as WP8.md says); **hard cap $12.00 in total**, enforced by WP5; the owner may raise it to at most **$15.00** (the whole $3.00 headroom, as PR #2 STORYBOARD §3 and BLOCKED-PRE-B say), and nothing beyond that fits | PR #2 STORYBOARD §3's paid runs: H1A, H1B and H2 once each, the `SR-08` render and H1B's render (`R-03B`), plus one retake; every other recording re-opens a finished job ($0). 3 runs × ≤ $2.34 (the 60 s no-cache worst case, §9.1 A10) = $7.02, + 2 renders with their audits (≤ $0.32 each at 60 s with 16 tracks: red-team $0.279 + passes 2–3 $0.043) + a retake run ≤ $2.34 = **≤ $10.00** (exactly $9.99 at A10's unrounded figures), which fits $12 | 12.00 |
| Creator pilots | PRE-B's hard cap (PR #2 PILOTS §5) | our estimate: 5 pilots × (1 clip + 1 retry) × $1.12 = $11.20 | 20.00 |
| Public "Try it" (judges, Nov 5–10 UTC, including the owner's live demo run on an access code) | the deployed service's daily cap | 6 days × $3 | 18.00 |
| `/healthz` before the public window | WP5, under the daily cap; **budget line $0.80, bounded by the probe rate** (no enforced cap) | Oct 29 – Nov 4: 7 days; before Nov 5 the Meta probe runs at most once every **2 minutes** (§10.7), ≤ $0.067 a day, so the plan is 7 × $0.067 = $0.47 of it | 0.80 |
| **Planned total** | | | **$147.00** |
| **Headroom vs $150** | | | **$3.00** |

**Decisions in this table:**
- **Fit every cap inside $150.** Every WP line is counted at its full cap, even where the plan uses less (WP2 $14.16 of $15, WP7 $8.36 of $12), so no WP can overspend the ledger by spending to its cap. Dev tuning is **8** rounds (it fits WP2's $15); the hero runs are PR #2's $12 recording code (STORYBOARD §3's paid runs only); SA-Co gets a **$5** cap. *Rejected:* the earlier plan, which left the WP1/WP4/WP5 build budgets ($20) out of the total and quietly over-committed the credits.
- **Spending caps by who is calling** (also §10.2):
  - **`SAFECUT_DAILY_USD_CAP` ($3/day) covers public "Try it" traffic** (judge access codes), **Sigmora service-key traffic** (`SAFECUT_SERVICE_KEYS`, WP5.md) and `/healthz`, all sharing the one $3/day. Public access codes are valid, **and service keys make live calls, only** from **Nov 5 00:00 UTC to Nov 10 23:59 UTC** (submissions close Nov 4 21:00 ET = Nov 5 02:00 UTC; the event page gives judging as Nov 4–8 and the live finals as Nov 9, MAXXING §1; the window opens 2 h before submissions close and ends a full day after Nov 9 in every US time zone. **Decided:** keep the Nov 5 00:00 UTC opening. Between the owner's planned submit, Nov 4 20:00 UTC (BLOCKED-PRE-B), and the opening, a judge's code answers `code_not_active`, and the landing page's precomputed hero results and the video still work without one. *Rejected:* opening at the submit time, which adds a sixth $3 cap day, spends the whole headroom and breaks PR #2's $15 recording bound) (the cap resets at 00:00 UTC, PR #2 UI-SPEC §8), so the line is exactly 6 cap days × $3. After Nov 10 23:59 UTC, WP5 turns `/healthz` into a no-call check (or tears the deployment down), so nothing is spent after the window. Before Nov 5 the deployed service takes only the owner's smoke runs (WP5's cap), pilot codes, the owner's **recording code**, and Sigmora integration calls in **replay mode** (no Meta calls): outside its live window a service-key job is forced to replay **server-side** (`mode: "replay"` in every response, PR #2 UI-SPEC request 1): a replay-mode service job **whatever was uploaded** returns the precomputed results **and media** of the job named by `SAFECUT_REPLAY_JOB_ID` (WP5's hero-1 run until Nov 3, then H1A), labelled demo mode, with `replay_of: "<that job id>"`. The submitted clip is never processed or rendered (no stage runs on it, and it's deleted with the job), so another job's responses can never be applied to it, so the Sigmora integration can be built and tested end to end without spending, **except publishing**: PR #2 turns "Publish to Sigmora" off in demo mode (UI-SPEC §5.4), so the publish leg is tested on the live H1A job (`SR-09`) or after Nov 5, and it can never spend before Nov 5 or after Nov 10 (request to WP5; the window is the `service` kind in `SAFECUT_CODE_WINDOWS`, §12). `/healthz` before the window (WP5 deploys from Oct 29) has its own ledger line, $0.80 (bounded by rate, not an enforced cap): before Nov 5 its Meta probe runs at most once every 2 minutes (§10.7), so 7 days cost at most $0.47. *Rejected:* a once-a-minute probe before the window ($0.94), which would cut the headroom to $2.86 and break PR #2's $15 recording bound, and no probe at all before the window, which would hide an outage on the Nov 3 recording day;
  - **every access code has a validity window, set by its kind.** WP0's `config.py` holds one default window per `kind` (ISO 8601 UTC, env-overridable like every default): **judge and public** Nov 5 00:00 – Nov 10 23:59; **recording** from deploy until Nov 3 23:59; **pilot** from deploy until Nov 2 23:59 UTC (PR #2 PILOTS §5: pilots run Oct 30 – Nov 2, results collected by Nov 2 23:59 EAT, which is 20:59 UTC; the 3 h slack only lets a late pilot finish). A `SAFECUT_ACCESS_CODES` entry (PR #2 UI-SPEC request 20) may add `valid_from`/`valid_until` only to **narrow** its kind's window; a wider value fails config validation at startup. So the entry BLOCKED-PRE-B tells the owner to create (`{"code": "…", "kind": "recording", "cap_usd": 12}`) is valid as written. The window is checked on **every request that can start paid work** (`POST /v1/jobs`, `POST /start` including a restart, `POST /render`, `POST /audit`), because each can spend: a judge job restarted after Nov 10 would otherwise spend outside the ledger. Reading a job, review edits, download and delete always work, whatever the window. WP5's own `retry_later` re-queue checks the window again before it runs (outside it, the job fails with `failure.reason: "code_not_active"`, a new reason with no retry offered, PRE-B request), and the daily cap is **$0 after Nov 10 23:59 UTC**, so a job started at 23:58 can't spend on Nov 11. Outside its window WP5 refuses those calls, before any Meta call, with `401` and `error.code: "code_not_active"`, and every job response carries `code_valid_until` so the UI can hide a retry that would land after it (PRE-B requests, §12) (request to WP5 and WP0's `config.py`; the copy is a PRE-B request, §12). An unknown `kind` fails config validation, so no code is ever valid without a window;
  - **pilot codes** sit outside it, with their own per-code cap and PRE-B's $20 total (as PR #2 PILOTS §5 asks);
  - **the recording code** (PR #2 UI-SPEC request 20, adopted): one owner code with a **$12 total** cap (not per day), outside the daily cap, valid until **Nov 3 23:59 UTC** and revoked after the recordings. `SR-09` ("From Sigmora") re-opens H1A's finished job, so it starts no paid work;
  - **owner, eval and WP runs** are bounded by the per-job cap, their WP caps and the **aggregate line caps** above. **How a line cap is enforced** (the same rule for `eval/run.py`'s test line, $43.20 including baseline 3, and the recording code's $12 total): the line is a **caller cap**, like the daily and per-code caps: every call's pre-call reservation (§10.2) is checked against `line_cap − the line's measured spend − the line's open reservations`, across all jobs on the line, including jobs running at the same time. That stops the line at its cap, with no per-run estimate. `eval/run.py` also runs the test jobs **one at a time**, so a job is never cut off mid-run by a concurrent one. A job whose line is exhausted fails before any call, with `failure.reason` `job_cap` (test line) or `code_cap` (recording code, §10.3). **A line job never counts unless it finished within budget:** a test-line job with **any** `cost.jsonl` budget line with `cap: "test_line"` (whatever its final status, including a keep-only stop that set no `failure`) is left out of `metrics.json` and `per_clip.csv` and counts as not run for that k (request to WP7). A `BudgetExceeded` from the **job cap** is a real product outcome and is scored as what it produced (a `failed` job counts as a failure; a `needs_you` job with everything hidden is scored as hidden), as AGENTS rule 9 requires. The recording code refuses to start a job when it has less left than the job's **§9.1 estimate**, `max($1.12, clip_seconds × $2.24 / 60)`. The cap, checked on every reservation, still stops any overspend, and a job cut off anyway isn't used as a recording. **Test run k** (k = 1, 2, 3) is baseline 3 (`muse_no_track`, $0.08 per clip) and then `full` over every clip; `eval/run.py`'s 3-run counter (WP7.md) counts run indices k, not calls or variants. Runs go k = 1, 2, 3, so a shortfall cuts the last repetitions of `full`, never a clip or a baseline, and the README states the run count per clip (request to WP7). Request to the owner, who films the eval clips and owns SHOTLIST (MAXXING O1; PRE-B.md doesn't give PRE-B that file): keep the test split's mean clip length ≤ 30 s (SHOTLIST allows 15–45 s), since that's what the line is priced at (BLOCKED-PRE-A).

  The $3/day still applies whenever the service is deployed, as a backstop. *Rejected:* ARCHITECTURE §4's $10/day default, under which 12 days could spend $120. Request to WP5: deploy with `SAFECUT_DAILY_USD_CAP=3.00`, apply it to judge and public access codes, service keys and `/healthz` (not pilot, recording or `owner` codes), and add a per-code cap for pilot codes.
- **Wonder isn't pre-approved.** The $3.00 headroom fits none of the options: Wonder for the scene pass on the 36 test runs and 3 hero runs is 39 × $0.24175 = +$9.43, and the larger options are more (§9.1 deltas: scene +$0.24175, escalation +$0.30 per run). Adopting it needs this room, and raising the hard test-line cap by its test-run share (or accepting fewer runs, since `eval/run.py` would cut run 3): **scene** 39 × $0.24175 = $9.43 room, 36 × = $8.70 raise; **escalation** 39 × $0.29875 = $11.65 room, $10.76 raise; **both** $21.08 room, $19.46 raise. WP0 adopts Wonder for the scene pass only if H1 shows a gain, and for escalation only if H2 does (both with zero new false keeps, as `docs/research/muse-wonder-vs-spark.md` decides), **and** the measured spend in `cost.jsonl` by then (WP caps are maxima, and replay-heavy WPs usually come in under) leaves room for the extra. If Wonder escalation is ever used, its `max_output_tokens` is 24,000 (§10.5).

**Risks to this budget:**
- **30 fps SAM** would make the test runs alone $92.53. Never send `prepared.mp4` to SAM (§10.6).
- **Busy clips:** with 16 tracks, red-team pass 1 needs 96 frames instead of 64. That's +$0.06 per run, or +$2.16 over the 36 test runs, inside the $3.00 headroom, but the test line is a hard cap. **Decided:** the test line's cap absorbs it (the headroom isn't moved into it). The run order (k = 1, 2, 3, above) means a busy or long split loses part of run 3, never a clip, and the README states the run count per clip.
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
| Responses (stream) | read idle 300 s (`medium` and lower), 450 s (`high`, `xhigh`), 600 s (`max`, which reasons silently before output); total ≤ 900 s | decision *(probe)*; [3P] reasoning precedes output (§3.5) |
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
  - Before each attempt, **reserve** its pre-call estimate (§10.5) against the **job cap**, and against the cap of **who started the job**: a public access code or a Sigmora service key → `SAFECUT_DAILY_USD_CAP`; a pilot code → its $6 per-code cap and the $20 pilot total (PR #2 PILOTS §5, UI-SPEC request 20); the recording code → its $12 total; the `owner` code (WP5's runs on the deployed service) → its own `cap_usd` (≤ $6, WP5's budget); test-split eval runs → the $43.20 test line; other owner, eval and WP runs → the job cap and their WP caps (§9.2). `/healthz` counts against the daily cap (§9.2).
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
| `BudgetExceeded` | the pre-call estimate exceeds the remaining job cap or the caller's cap (§10.2: the daily cap for public codes and service keys, the per-code cap and $20 total for pilots, the recording code's $12 total and the test line) | the call isn't made; the stage fails closed. A job that fails on it sets PR #2's `failure.reason` (UI-SPEC request 1 and §5.3; adopted): `job_cap` for the job cap and the test line; `code_cap` for a pilot's, the recording code's or the `owner` code's own cap; `pilot_pool_cap` for the $20 pilot total; `daily_cap` for the daily cap (with `retry_at` = the next 00:00 UTC). `POST /start` refuses before any call once a cap can't cover the job's §9.1 estimate, with PR #2's codes (UI-SPEC §2.6, §10): **`422` `job_cap`** when the job cap can't (the same clip can never fit, so it isn't a retryable `429`), and **`429`** with `code_cap`, `pilot_pool_cap` or `daily_cap` for a caller cap. The exception carries **`cap`**, one of `job`, `test_line` (both → `job_cap`), `code` (→ `code_cap`), `pilot_pool` (→ `pilot_pool_cap`) and `daily` (→ `daily_cap`), and is logged to `cost.jsonl` as a budget line (§10.5), so `eval/run.py` can tell a test-line stop from a job-cap outcome. An audit pass sets `audit.blocked_reason: "over_budget"` and `audit_budget_cause` instead. For the audit, the frames count in `unresolved` (§12) |

"Fails closed" means: for a stage that could only *add* keep evidence (role pass, escalation, scene pass, speech), the job continues with everything hidden and those **items** `needs_you` (the job itself goes on to `review`; docs/prompts/README.md rule 3; a failed scene pass also holds every would-be auto-keep, `hold: "no_scene"`, §12). For a stage that's needed to *hide* (SAM base sweep, render), the job can't be published. It goes to **`retry_later`** when the cause is transient (`MetaUnavailable`, `MetaRateLimited`, or an eof `MetaIncomplete`); WP5 re-queues it once after 5 min; if the re-queued run fails transiently again, the job goes to `failed` with `failure.reason: "upstream"` (PR #2 UI-SPEC request 1). Otherwise it goes to **`failed`**: `MetaAuthError`, `MetaConfigError`, `MetaBadRequest`, `MetaRefusal`, `BudgetExceeded`, and a **non-eof** `MetaIncomplete` (a server-declared incomplete, or a parser `error` diagnostic, S5), which is deterministic, so re-running wouldn't help.

**The audit is the exception, because a rendered output already exists.** Any audit pass that can't run or finish (transient failure after its attempts, `BudgetExceeded`, or a refusal after the red-team's one rephrased re-ask) adds **every frame it should have audited** to `unresolved`, with `audit.blocked_reason` set to `audit_failed` or `over_budget` (§12), and for `over_budget` also `audit_budget_cause` (from the exception's `cap`, PR #2 UI-SPEC request 11). The job goes to **`needs_you`**, never `failed` or `retry_later`, and the review page offers PR #2's **[Run the audit again]** whenever `blocked_reason` is `audit_failed` or `over_budget` (the precedence in §12 puts either above `unresolved_leaks`, so a run with failed frames always offers it) (`POST /v1/jobs/{id}/audit`, PR #2 UI-SPEC request 11: it re-runs the audit pass on the existing render, with WP4's auto-patch loop exactly as after a first audit, so only a segment it patches is rendered again, and then **the receipt stage runs** as after a first audit; the creator's decisions aren't rendered again), except when the cause is `job_cap`, which would fail the same way (PR #2 UI-SPEC §4, §5.3). Publishing stays off through the one gate, `unresolved == 0`.

### 10.4 Files: idempotency and cleanup
- No idempotency key is documented for any endpoint, so idempotency is done **client-side through the job directory**:
  - before uploading, compute `sha256(file)`; if `jobs/<id>/files.json` already maps that hash to a live `file_id`, reuse it;
  - write `{name, sha256, file_id, purpose, created_at, deleted_at: null}` to `files.json` (the §12 fields) **before** the first use;
  - at the **end of each processing segment** (§10.1: review-ready, or render + audit done), and on cancel or failure, `DELETE /v1/files/{id}` for every entry. A 404 on delete counts as deleted. Then set `deleted_at`. Segment (b) never needs `sam_proxy.mp4`: audit patches are static boxes (`redteam.md`), so no SAM call runs after review. So no Meta file waits through a creator's review, and none outlives its segment;
  - **an upload that times out** (the server may have accepted it, but the id never arrived): before retrying, list files (`GET /v1/files`, OpenAI-compatible, *(probe)*) and delete any whose `filename` and `created_at` match this job's upload; write each one found to `files.json` first. If listing isn't available, the 6 h `expires_after` is the only backstop, so the receipt sets `files_deleted: false` with "one upload's id is unknown; Meta expires it within 6 h". `files_deleted: true` is written only when no upload is unaccounted for;
  - an hourly sweeper (the WP5 cron) deletes anything in any `files.json` older than **6 h** that has no `deleted_at`. Upload with **`expires_after` 21,600 s (6 h)** as the backstop. That's well above the 2 h segment limit (§10.1), so a running segment never loses its file. If one does anyway, `MetaFileGone` re-uploads it.
- A retried Responses call is a new response. Stage outputs are checkpointed in the job directory, so a re-run stage **reuses its saved response** only when its **checkpoint key** matches: the stage name plus the sha256 of its inputs (files, frame list, prompt version, model and effort). Audit checkpoints key on the render's sha256 too, so a re-render is never "audited" with an older render's results (a checkpoint, never `SAFECUT_REPLAY=1`: reuse inside a live job isn't demo mode, and the job's `mode` stays `live`) instead of calling again.

### 10.5 Pre-call cost estimate and `cost.jsonl`
Prices live in `safecut/config.py` as a dated table (the §6 values, `price_table_date = "2026-10-24"`, re-read on Oct 26).

| Call | Pre-call estimate (worst case, checked against the remaining caps) | `units` logged after the call | `usd` |
|---|---|---|---|
| Responses | `POST /v1/responses/input_tokens` count [GH-cookbook] × `P_in` + `max_output_tokens` × `P_out`. The count call is free *(probe)*, retried per §10.2 (4 attempts), and is replaced by a **fallback estimate** when it fails or returns less than it: 1,500 tokens per image (A3), ≈ 1,100 per sampled frame, i.e. **2,200 per second** of `input_video` at 2 fps (A4: 65k for 30 s), and 1.3 × the UTF-8 byte count of text / 4. The larger of the two is reserved, so an under-count can't overrun a cap | `{"input": in, "cached": c, "output": out, "reasoning": r}` from `usage` (`input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`) | `(in − c) × P_in + c × P_cached + out × P_out` (reasoning is already inside `out`) |
| SAM video | `frames_billed × $0.0002` | `{"frames": frames_billed}` (worst case: every uploaded frame billed; replace it with `usage` if SAM reports any) *(probe)* | `frames × 0.20 / 1000` |
| ASR | `ceil(duration_s) × $0.00005` | `{"audio_s": floor(audioDurationMs / 1000)}` | `audio_s × 0.18 / 3600` (billing rounds down to whole seconds, [SNIP]) |
| Files | 0 | `{"bytes": n}` | 0 (no file price documented) |

- `max_output_tokens`: `medium` and lower 16,000; `high` and `xhigh` (used only if `config.py` sets them, e.g. the `xhigh` fallback in `escalation.md`) 32,000 on Spark and 24,000 on Wonder; Spark `max` 48,000 (worst-case escalation `17k × $1.25/M + 48k × $4.25/M` ≈ $0.23, C4); **Wonder `max` 24,000** (≈ $0.55; at 48k it would be $1.03, a third of the $3.00 job cap per call, and windows multiply it, §9.2). A response cut off by this limit is `MetaIncomplete`.
- `cost.jsonl` line: `{"ts", "job_id", "stage", "model", "attempt", "units", "usd", "estimated": bool, "request_id", "cap", "code_kind", "code_id"}`. `code_kind` is who started the job (`pilot`, `recording`, `judge`, `public`, `service`, `owner`, `eval`, or `system` for `/healthz` and the startup probe, PR #2 UI-SPEC request 20) and `code_id` the code's id (`null` only for `system` lines and for local owner, eval and WP runs that use no code, which log `code_kind` `owner` or `eval`; an `owner`-kind access code logs its id, so its cap sums by it). `system` lines have `job_id: null` and go to the service-level `cost.jsonl` on the Volume, which the daily-cap sum includes; the caps sum spend by them (§10.2). `request_id` is the response's `id` (or `x-request-id` if present), `null` when no call was made. **Budget line:** a `BudgetExceeded` stop writes one line with the stopped stage's name in a `stage: "budget:<stage>"` form, the model it would have called, `attempt: 0`, `units: {}`, `usd: 0`, `estimated: false`, `request_id: null` and `cap` set (§10.3); every other line has `cap: null`. This extends ARCHITECTURE §3.10 (one line per API call) with `job_id`, `attempt`, `estimated`, `cap`, `code_kind` and `code_id`, and with budget lines for stops that made no call; WP0 adds them to the contract.

### 10.6 Request and response shapes
**SAM video** (one request per concept or per object-prompt batch):
```json
{"model": "sam-3.1", "stream": true, "store": false,
 "metadata": {"include_confidence": "true"},
 "input": [{"type": "message", "role": "user", "content": [
   {"type": "input_text", "text": "face"},
   {"type": "input_video", "file_id": "file-abc123"}]}]}
```
- `store: false` follows AGENTS rule 6. Whether `sam-3.1` accepts it is unverified *(probe)*. If it's rejected (probe b), WP0 sets `SAFECUT_SAM_SEND_STORE=false` (default `true`; §12 env table), the client stops sending the field to SAM, and `sam-3.1` goes in the receipt's `data_handling.no_store_param` instead of `store_by_model`, so the receipt stays truthful. Never claim `store:false` for a call that didn't send it.
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
**At startup only** (once per deploy): for each configured `(model, effort)` pair, send a minimal request (text "ok", `max_output_tokens: 16`, `store: false`); for SAM, a 64×64 PNG with the text `"square"` (≈ $0.0025). Any HTTP 200 counts as healthy, even `status: "incomplete"`, because reasoning may use up the 16 tokens. A 400 or 404 → `MetaConfigError` → refuse to start; 401/403 → `MetaAuthError` → refuse to start. 429, 5xx and timeouts retry per §10.2; after the last attempt the service **starts degraded** (`/healthz` red); only the **failed** `(model, effort)` pairs are re-probed, at most once every 30 minutes (≤ $0.0001 per text pair; SAM is never re-probed once it passed, and a failed SAM probe is retried at most once an hour, ≤ $0.06 a day), because the cause is transient and each stage's own retries and `retry_later` still fail closed. **Once per deploy, not per container:** on Modal a scaled-to-zero app cold-starts often, so the probe writes a marker with the deploy id to the Volume and skips if it's present. Its cost (≈ $0.003: the SAM image plus about five text pairs) is logged as a `system` line and counts in the pre-window `/healthz` line, whose $0.80 is a budget line bounded by rate, not an enforced cap (WP5 builds no cap for it): ≤ $0.47 of probes in 7 days leaves $0.33, over 100 deploys.

**`/healthz`** (ARCHITECTURE §5: at most once a minute; **before Nov 5 00:00 UTC at most once every 2 minutes**, §9.2, with the last result and its time cached **on the Volume**, so every container shares one rate) sends **one** text request to `SAFECUT_ROLE_MODEL` at `reasoning.effort: "minimal"`, `max_output_tokens: 16`. At most ≈ 20 input + 16 output tokens = (20 × $1.25 + 16 × $4.25) / 1M = **$0.000093** per check, so at most **$0.134 a day** (1,440 checks) even if it's polled every minute, and at most $0.067 a day (720 checks) before the window. It never calls SAM. Probe costs are logged with stage `healthz` and count against `SAFECUT_DAILY_USD_CAP`, which leaves $2.866 of the planned $3/day for jobs.

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
| G8 | box [100, 0, 300, 40], `kind: text`, text "F 000090" | red-team | **dropped** (`in_bar`: y_img 0–30 < 40; the model read our frame label) |
| G8b | box [100, 0, 300, 40], `kind: face` (or text "AMINA") | red-team | **leak with a whole-frame box** (an in-bar box that isn't the label is a misplaced real finding) |
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
| T11 | crowded span | `job.fps` 30, `sam_fps_eff` 8, 300 prepared frames (`from_proxy` = 1, 5, 9, 13, 16, 20, …); proxy frame 0 crowded; proxy frame 3 crowded; proxy frames 3 and 4 crowded | `crowded_frames` = 0–4; 10–15; 10–19 |

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
| R12 | the pre-call estimate exceeds the remaining job cap | no request; `BudgetExceeded`; the stage fails closed per §10.3: a **hide-critical** stage (SAM base sweep, render) → job `failed`, `failure.reason: "job_cap"`; a **keep-only** stage (scene, speech, role, escalation) → no `failure`, everything it would have judged stays hidden with its **items** `needs_you`, and the **job** continues to `review` (job status `needs_you` is only for an audit that couldn't run, §10.3, PR #2 UI-SPEC §10.5); a **red-team** pass over 40 frames → `unresolved` += 40, `blocked_reason: "over_budget"`, `audit_budget_cause` from the `cap` |
| R12b | a test-split `full` run: the role pass hits the **test line** cap (`cap: "test_line"`); its items stay hidden (`needs_you`), the job continues with no `failure` | `cost.jsonl` has `{stage: "budget:role", cap: "test_line", usd: 0, request_id: null}`; `eval/run.py` leaves the job out of `metrics.json` and `per_clip.csv` and counts run k as not run for that clip. The same stop from the **job** cap (`cap: "job"`) is scored |

---

## 12. Contract changes PRE-A proposes (one list; WP0 implements them in `contracts.py` and ARCHITECTURE §3 together, per AGENTS rule 3)
Nothing is implemented yet (there's no code before kickoff), so these are **changes to the contract and its examples**, not backward-compatibility shims. Fields marked **required** have no default, and WP0 updates the ARCHITECTURE examples to include them. Optional fields have the default shown. The prompt specs emit model output; the pipeline maps it into these files.

| File | Field | Type, default | Written by → read by | Why |
|---|---|---|---|---|
| `scene.json` | `participants[].is_creator` | bool, optional, `false` | WP2 → role pass | the creator's own face must be found even if only seen in a mirror (`scene-pass.md` case 1) |
| `scene.json` | `status` | `"ok"\|"failed"\|"skipped"`, **required** | WP2 → WP3 policy, receipt | WP2 **always** writes `scene.json`, also on a failure (`failed`) or a budget stop (`skipped`, R12); the children gate reads this field, never the `summary` text (vector P1) |
| `scene.json` | `children[]` | `[{description: str}]`, optional, `[]` | WP2 → role pass (context), WP3 policy | early child flag. A scene child can't be mapped to a track, so it can't lock one. Instead, **when `len(scene.children)` exceeds the number of distinct child _items_** (WP3's review items after it groups a person's `face:`/`person:` tracks, counting an item as a child if any of its tracks is voted `child` by the role pass or ruled `child` by escalation (a `child_phrase` lock alone **never** counts, rule 0), and not counting an item whose tracks all have `reentry_of` set; a child the role pass didn't find), WP3 doesn't auto-keep any `person:` or `face:` track: a track that would be kept by votes alone stays hidden, `needs_you`, with `decisions.items[].hold: "unmatched_child"` (below), and the creator decides. **A failed or skipped scene pass counts as an unmatched child** (`hold: "no_scene"`): WP3 sets it whenever `scene.json` `status != "ok"` or the file is missing, because an empty `children` must never turn the gate off, so a scene failure can't show more than a successful pass (prompts README rule 3; vector P1). When every scene child is matched (hero clip 1: its consented child is locked as `face:4`), auto-keep works as before, so PR #2's hero mocks and STORYBOARD 3.3/4.2 stand (fail closed only where a child is unaccounted for; request to WP3) |
| `roles.json` → WP3 | speech and introduction evidence (WP3.md step 3: "when a transcript exists, the participant has speech or an introduction as evidence") | definitions, no new field | WP3 policy | **a transcript exists** when `job.audio == true`, `status == "ok"` and `degraded == false`, **even with `turns: []`** (an unsupported language or music can hide real speech, so an empty but successful transcript still requires speech or introduction evidence, P9c). **Speech evidence:** `matches_participant = k` and `scene.participants[k].speaker` has ≥ 1 turn. **Introduction evidence:** `matches_participant = k` and `scene.participants[k].speaker == null` (introduced, silent; scene-pass case Kev). A participant with `matches_participant == null` has neither, so with a transcript it stays hidden (`needs_you`, `hold: "no_speech_link"`; vectors P6–P8). **No usable transcript while the clip has audio** (`job.audio == true` and the speech stage failed, was skipped for budget, or wrote `degraded: true`) counts like `no_scene`: no person is auto-kept (`hold: "no_speech"`, P9), so a speech failure can never show more than a working transcript. A clip with no audio track (`job.audio == false`) has no speech evidence to require |
| `decisions.json` | `items[].hold` | `null\|"no_scene"\|"no_speech"\|"no_roles"\|"unmatched_child"\|"no_speech_link"`, optional, `null`; when several apply, the first in that order is written. `no_roles`: `roles.json` `status != "ok"` or is missing, or the item's track has `failed_votes > 0`, or escalation failed or was skipped for it (`role == unsure` with `escalated == false` after a dispute) (vectors A8, E3 then carry it). The column says why an item that could have been kept is `needs_you` |
| `roles.json` | `status`; `tracks[].failed_votes` | `"ok"\|"failed"\|"skipped"`, **required**; int 0–3, optional, `0` | WP2 → WP3 policy | WP2 **always** writes `roles.json` (also on a failure or budget stop, with every track `unsure`); `failed_votes` counts the votes that were failure placeholders, not judgements (`role-pass.md` Failure handling) | WP3 → UI Why drawer | why a 3/3 `participant` track wasn't auto-kept (the rule above); a PRE-B copy request (below) |
| `scene.json` | `others_present` | str, optional, `""` | WP2 → role pass | context: kinds of non-participants |
| `scene.json` | `candidate_objects[].approx_time` | **required** enum `beginning\|middle\|end\|throughout\|unknown` | WP2 → miss loop | replaces free text; WP0 changes ARCHITECTURE §3.4's example `"mid-clip"` to `"middle"` |
| `roles.json` | `tracks[].matches_participant` | int \| null, optional, `null` | WP2 → UI | index into `scene.participants`. The UI's speech link is `scene.participants[matches_participant].speaker` |
| `roles.json` | `tracks[].suggested_role` | enum role \| null, optional, `null` | WP2 (escalation) → Needs-you card | advisory only, never a keep (`escalation.md`) |
| `roles.json` | `tracks[].escalation_evidence`, `tracks[].escalation_frames` | str \| null and `[int]` \| null, optional, `null` | WP2 → Why drawer | escalation's own evidence and cited frames, kept apart from the role pass's `evidence` (field names as PR #2 UI-SPEC §4.6 adopted them). The ruling's `why_others_wrong` goes to the job log only |
| `roles.json` | `missed[].box` | `[x1,y1,x2,y2]` half-open px \| null, optional, `null` | WP2 → WP1 object prompt | better SAM prompt |
| `roles.json` | `missed[].recurs` | bool, optional, `false` | WP2 → WP1 | gates paid phrase sweeps |
| `transcript.json` | `degraded` | bool, optional, `false` | WP2 → role pass, receipt | a dropped soundtrack is visible, never silent |
| `transcript.json` | `status` | `"ok"\|"failed"\|"skipped"`, **required** | WP2 → WP3 policy | WP2 **always** writes `transcript.json` when `job.audio == true`: `failed` after both paths fail, `skipped` on a budget stop (R12), each with `turns: []` and `degraded: true`. WP3 sets `hold: "no_speech"` when `job.audio == true` and `status != "ok"`, `degraded == true`, or the file is missing (P9, P9b) |
| `transcript.json` | `source_kind` (PR #2 UI-SPEC request 16, adopted) | `"primary"\|"fallback"`, **required** when `status` is `ok`, else `null` | WP2 → UI, receipt | which path produced the turns, so nothing compares `source` with a model ID (AGENTS rule 8) |
| `tracks.json` | `sam_fps`, `sam_frames` | number, int, **required** | WP1 → frame maps (§5b) | read back from `sam_proxy.mp4` |
| `tracks.json` | `requests[].fps`; `requests[].frames_billed` (ARCHITECTURE §3's name) | number **required**; int as in ARCHITECTURE | WP1 → cost, receipt | `fps` is new. `frames_billed` = the uploaded frame count (worst case) until SAM reports `usage` (§10.5) |
| `tracks.json` | `requests[].kind`, `requests[].matches` | `"phrase"\|"object_prompt"`, int, **required** | WP1 → miss-loop logs, eval | which request type ran, and how many objects it found (`miss-loop.md` zero-match logging) |
| **`files.json`** (new, per job) | `[{name, sha256, file_id, purpose, created_at, deleted_at}]` | **required** fields; `deleted_at` null until deleted | WP0 client → WP1 (proxy id by `name`), WP5 sweeper, receipt `files_deleted` | idempotent uploads and guaranteed deletion (§10.4) |
| `tracks.json` | `tracks[].masks` | `{frame: {"size": [H, W], "counts": str}}` (COCO compressed RLE, frame-sized, prepared-clip pixels), optional, `{}`; keys are **anchor** frames only | WP1 → WP3, WP4, WP7 | replaces ARCHITECTURE §3.2's `"rle:…"` string; the box-sized SAM mask placed at its box origin (§1.5) |
| `tracks.json` | `tracks[].track_id` numbering; `tracks[].sam_object` (new) | `"<concept>:<n>"` with `n` the **next free integer for that concept across the whole job** (every SAM request, static tracks and re-entry splits), never SAM's own object id; `sam_object`: `{request: int, object_id: str}` \| `null`, optional | WP1 (and WP2 for static tracks) → all | SAM ids are only stable within one response (§1.4), so a point-prompt `face` object and the base sweep's `face` object would otherwise both be `face:1` |
| `tracks.json` | `tracks[].child_phrase` | bool, optional, `false` | WP2 miss loop → WP3 policy | `true` when the track came from a miss-loop phrase in the **child set** (`miss-loop.md`). WP3's **rule 0**: such an item is `kind: child`, `locked: true`, never escalated, whatever any vote says, and it does **not** count toward the `scene.children` match (a poster tagged "kid" must not switch the gate off) |
| `tracks.json` | `tracks[].origin` (new; ARCHITECTURE §3.2's `source: "sam-3.1"` stays as the model ID that produced it, `null` for a static track) | `"sam"\|"static"`, optional, `"sam"` | WP2 miss loop → WP3, WP4, WP7 | a **static** track is a miss-loop fallback box (`miss-loop.md` Failure handling: item cap, budget stop, failed or empty object prompt, and every item under `SAFECUT_MISS_SAM=stub`). WP2 appends it to `tracks.json` with `track_id` `"<concept>:<n>"` (the numbering row above; the phrase goes in `prompt`), a box on every frame of its span and no masks. It's **never sent to a role pass** and **never auto-kept**: it stays hidden with `needs_you` until the creator keeps it in review, except a `child_phrase` track, which is locked (row above) |
| `decisions.json` | `items[].origin`; `items[].audit_label`; `items[].box`, `items[].first`, `items[].last` (audit patches only) | `origin`: `"sam"\|"static"\|"audit_patch"`, optional, `"sam"` (an item is `static` if all its tracks are static); `audit_label`: `"A<n>"` \| `null`; the span fields required when `origin` is `audit_patch` | WP3 (sam, static), **WP4** (audit_patch) → WP3 guard, UI, receipt, eval | an **audit patch** (a red-team or EgoBlur leak, `redteam.md`; and a covered spot, PR #2 `cover_spot`) is a hidden decision item, `item_id` `"p_<n>"`, `track_ids: []`, `kind` from the leak (`face`/`person` → `person`, `plate` → `plate`, anything else → `other`; a covered spot: `person` if any of its leak rows is `face`/`person`, else `plate` if any is `plate`, else `other`), `decision: "hide"`, `reason: "audit_patch"`, `evidence_frames: [<finding frame>]` (a covered spot or a merged EgoBlur run: its first leak frame; never the padded span start), `decided_by: "policy"`, `style: "solid"`, **`locked: true`** (a found leak isn't un-hidden in review; a false positive is reported, not toggled), with `box` = the **raw** finding box (for a covered spot: the **union of the spot's `boxes`**, so a face moving between audited frames up to `sample_step` apart is still inside it; never interpolated) and `first`/`last` = the final span: WP3's guard applies only the kind's spatial padding, never temporal padding or back-fill, numbered `A<n>` in order of first frame when an audit pass writes them; a spot covered later takes the **next free** `A` number (PR #2 UI-SPEC §0), and numbers never change once given. Because it's a decision item, **WP3's guard rebuilds every patch into `plan.json` on any re-plan** (a review edit after `done`, a re-render), so no patch is ever lost; it never enters `tracks.json` or a role pass. The UI gets chips, Why row "Added by the audit" and overlay regions from it (PR #2 UI-SPEC §0, §4.3). `origin` is also returned in the job response so the UI can tell static items apart |
| `plan.json` | `frames[f][].source` | `"decision"\|"audit_patch"`, optional, `"decision"` | WP3 → WP4 render, eval | marks entries built from an `audit_patch` item (above), for the receipt and eval counts |
| `plan.json` | `frames[f][].mask` | the same RLE object, or `null` when `shape` is `box` | WP3 → WP4 render, WP7 coverage | **WP3** writes each frame's mask: the anchor's own, or the union of the two neighbouring anchors' masks shifted to the interpolated box (§1.5), so WP4 and WP7's coverage metric read one value and never recompute it |
| `audit.json` | `leaks[].flag`; `leaks[].through_item` | `"redaction_too_weak"` \| null, optional, `null`; `through_item`: the `item_id` of the hidden item the finding's box overlaps most (IoU, on that frame), **required** when `flag` is set | WP4 → WP3 guard, re-render, UI | read-through → WP3 sets **that** item's style to `solid` on every re-plan (`redteam.md` L7) |
| `audit.json` | `leaks[].unresolved`, `sample_step`, `spots[]` and the review edit `cover_spot` (PR #2 UI-SPEC request 18 @ `74bb9d2`, adopted as written there) | `unresolved`: bool, optional, `false` (when `true`: `patched_item: null`, `frame`, `box`, `kind` set); `sample_step`: int, **required**; `spots[]`: `{spot_id, first, last, boxes, covered_by}`, WP4 groups them | WP4 → UI "Unfixed spot" chips; `cover_spot` (`spot_id`) → WP3/WP5 add one hidden item | a leak still present after pass 3; each unresolved row counts 1 in `unresolved` (`blocked_reason: "unresolved_leaks"`). **`sample_step`** = the red-team's step in output frames, `round(job.fps)` for its 1 fps sampling (`redteam.md`); EgoBlur scans every frame, so its leak rows fall inside that step and group the same way |
| `audit.json` | `blocked_reason`; `audit_budget_cause` (PR #2 UI-SPEC request 11) | `null\|"unresolved_leaks"\|"audit_failed"\|"over_budget"`, **required** (no default: a writer that omits it fails validation); when several causes apply in one audit, the **first** of `over_budget` > `audit_failed` > `unresolved_leaks` is written (the unresolved count still sums all of them); `audit_budget_cause`: `null\|"job_cap"\|"daily_cap"\|"code_cap"\|"pilot_pool_cap"`, optional, `null`, non-null exactly when `blocked_reason` is `over_budget` | WP4 writes both in `audit.json`; WP5's `GET /v1/jobs/{id}` returns `audit.blocked_reason` and mirrors the cause **at the job's top level** as `audit_budget_cause`, with `retry_at` when it's `daily_cap` (PR #2 UI-SPEC request 11 and fixtures `result-audit-over-budget*.json`) → UI audit panel (§4.4, §5.3) | why publishing is off. **Invariant: `blocked_reason != null` ⇔ `unresolved > 0`.** Every frame an audit pass didn't run on counts in `unresolved`, so `unresolved == 0` stays the one publish gate |
| `cost.jsonl` | `job_id`, `attempt`, `estimated` | str \| null (`null` only for `code_kind: "system"`), int, bool, **required** | WP0 client → caps, receipt, eval | reservation accounting (§10.2) |
| `cost.jsonl` | `cap`; `code_kind`, `code_id`; `request_id` nullable; `stage` may be `budget:<stage>` | `cap`: `null\|"job"\|"test_line"\|"code"\|"pilot_pool"\|"daily"`, optional, `null`; `code_kind`: enum (§10.5), **required**; `code_id`: str \| null | WP0 client → caps, eval | which cap stopped a stage; `eval/run.py` excludes a job with any `cap: "test_line"` line (§9.2, R12b) |
| `receipt.json` | `cost_usd_estimated` | number, optional, `0` | WP4 → receipt page | "possibly billed" kept apart from measured `cost_usd` (AGENTS rule 9) |
| `receipt.json` | `data_handling.store_by_model`; `data_handling.no_store_param` | `{model: bool}` over the models called through the **Responses API** only, **required**; `[model]`, **required** (may be empty) | WP4 → receipt page | what each Responses call was actually sent. **`data_handling.store` is redefined as `any(store_by_model.values())`**, so it's `false` only when every Responses call sent `store:false` (§10.6). Muse Voice Transcribe (`POST /v1/asr/transcribe`, §4.1) has no `store` parameter, so its model goes in `no_store_param` instead, and the receipt says "no store setting exists for this call; Meta's Standard-mode policy applies (§7)". It's never counted as `store:false` (AGENTS rule 9) |

**Config and env changes** (WP0's `safecut/config.py` holds every default; WP0 updates ARCHITECTURE §4's table to match, AGENTS rule 8):

| Variable | Type, default | Change | Read by | Why |
|---|---|---|---|---|
| `SAFECUT_JOB_USD_CAP` | float, `3.00` | was `2.00` | WP0 client | a busy 60 s clip models at $2.09, $2.34 with no cache hits (§9.1 A10) |
| `SAFECUT_DAILY_USD_CAP` | float, `3.00` | was `10.00`; scope: public and judge codes, service keys, `/healthz` | WP0 client, WP5 | the ledger's 6 × $3 line (§9.2) |
| `SAFECUT_SAM_FPS` | int, `8` | new | WP1 | the SAM proxy rate (§5b, §9.1) |
| `SAFECUT_META_BASE_URL` | str, `https://api.meta.ai/v1` | new | WP0 client | §10.1 |
| `SAFECUT_SPEECH_SOURCE` | `"asr"\|"spark-1.2"`, `"asr"` | was named in ARCHITECTURE §4 with no type | WP2 | `asr` = Muse Voice Transcribe, with the automatic fallback to the speech fallback when it fails after retries (≈ 30 s × 2,200 tokens/s of video + 4k out ≈ $0.10 at 30 s, $0.18 at 60 s; absorbed by the job cap, not in §9.1's row) |
| `SAFECUT_SPEECH_FALLBACK_MODEL` | str, `muse-spark-1.2` | new | WP2 | the speech fallback's model ID from env (`speech-fallback.md`) |
| `SAFECUT_MISS_SAM` | `live\|stub`, `live` | new; `stub` only in WP2 tuning runs | WP2 | §9.2 WP2 line |
| `SAFECUT_ACCESS_CODES` | JSON list of `{code, kind, cap_usd?, valid_from?, valid_until?}` | PR #2 UI-SPEC request 20's shape plus the optional window fields | WP5 | §9.2 code windows |
| `SAFECUT_CODE_WINDOWS` | JSON `{kind: [from, until]}`, ISO UTC; defaults judge/public `2026-11-05T00:00Z`–`2026-11-10T23:59Z`, recording `null`–`2026-11-03T23:59Z`, pilot `null`–`2026-11-02T23:59Z` (UTC, 3 h after PILOTS' Nov 2 23:59 EAT deadline), service `2026-11-05T00:00Z`–`2026-11-10T23:59Z` (live calls; replay outside it), owner `null`–`2026-11-10T23:59Z` (`null` = no start bound) | new | WP5 | §9.2 |
| `SAFECUT_PILOT_CODE_USD` | float, `6.00` | new (PR #2 PILOTS §5) | WP0 client | per-pilot-code cap when an entry has no `cap_usd` |
| `SAFECUT_PILOT_POOL_USD` | float, `20` | new (PR #2 UI-SPEC request 20) | WP0 client | the shared pilot total |
| `SAFECUT_RECORDING_CODE_USD` | float, `12.00` | new | WP0 client | the recording code's total when its entry has no `cap_usd`; the owner may raise it to at most `15.00` (§9.2) |
| `SAFECUT_ASR_LANGUAGE_BIAS` | JSON list, `["english"]` | new | WP2 | Voice Transcribe `languageBias` (§4.1); WP0 adds `"swahili"` if probe d supports it |
| `SAFECUT_EGOBLUR_MODEL` | `egoblur-gen2\|egoblur-gen1\|yunet-face`, `egoblur-gen2` (`yunet-face` only as the Oct 31 fallback, WP4 deviation) | new | WP4 | the auditor generation WP4 picks on hero clip 1 (`egoblur-gen2.md` held-out rule); written to `audit.json` `egoblur.model` and the receipt (AGENTS rule 8) |
| `SAFECUT_EGOBLUR_FACE_THRESHOLD`, `SAFECUT_EGOBLUR_PLATE_THRESHOLD` | float, `0.5`, `0.5` | new | WP4 | set from the same held-out choice (0.5, or the model's calibrated default) |
| `SAFECUT_REPLAY_JOB_ID` | str \| null, `null`; set to WP5's owner-code live run on hero clip 1 once it exists, then H1A's job after Nov 3. While `null`, a service-key job outside its live window is refused with `401 code_not_active` (no forced replay) | new | WP5 | the job a forced-replay service request returns (§9.2). WP5 **copies that job to a read-only `replay/` path that the 24 h purge skips** (consented hero footage only, AGENTS rule 5), so replay keeps working; the copy is deleted when the deployment is torn down |
| `SAFECUT_TEST_LINE_USD` | float, `43.20` | new | `eval/run.py` (WP7) | the test line's caller cap (§9.2) |
| `SAFECUT_SAM_SEND_STORE` | bool, `true` | new; WP0 sets `false` only if probe b shows SAM rejects `store` | WP0 client | §3.3, §10.6 |
| *(`owner` kind)* | an `owner` entry in `SAFECUT_ACCESS_CODES` with `cap_usd` ≤ 6.00 (WP5's budget); window `null`–`2026-11-10T23:59Z` | new kind | WP5 | WP5's deployed smoke runs and its live end-to-end run on hero clip 1 before Nov 5; outside the daily cap, counted in WP5's $6 line (`code_kind: "owner"`) |

**Deliberate differences from the WP files** (requests to the owning WP, with the reason; PR #1 lists them too):
- **WP0.md** "`audit`: `torch` (CPU wheels)" → default-PyPI `torch==2.9.1` (CUDA build, also runs on CPU), because EgoBlur 2.0.1 hard-pins it and the CPU-index build can't use the Modal GPU (`docs/research/egoblur-gen2.md`). The cloud setup script and CI skip the `audit` group (`uv sync --all-groups --no-group audit`), since CI's tests use the replay stub; **WP4** (EgoBlur CPU timing, the Gen 1/Gen 2 comparison) and **WP7** (baseline 1b on dev and hero clips) run `uv sync --group audit` on demand once the O8 weights exist;
- **WP0.md** "`expires_after: 3600`" → 21,600 s (6 h), the backstop above the 2 h segment limit (§10.4); explicit deletes and the hourly sweeper are unchanged;
- **WP1.md** "delete the file after the sweep" → delete at the end of the processing segment (§10.4), because the miss loop reuses `sam_proxy.mp4` within the segment and a re-upload would cost time and risk `MetaFileGone`;
- **WP2.md** step 5 "for each `missed` item, call WP1's `track.sweep` with `sam_phrase` … bind returned tracks to the point" → one **batched object-prompt request** per loop (every kept item's point as its own object id), plus a phrase sweep only when `recurs`, the phrase isn't already swept and isn't blocklisted (`miss-loop.md` steps 3–5); results bind by **object id**, not by nearest point;
- **WP1.md** "one request per concept … plus any extra phrases" → WP1 also needs an **object-prompt request builder** (`meta_sam_parser.build_object_prompt`, `metadata.propagation_direction: "both"`, §1.3) and writes `requests[].kind` (§12);
- **WP2.md** step 5 "re-run the role pass for them only" → loop 1's new tracks get the role re-pass; **loop 2's new tracks get none** and stay hidden (`miss-loop.md` step 6), so the loop ends in two rounds at a priced cost (§9.1);
- **WP4.md** "all frames near item boundaries" → 4 frames per track just outside its covered span plus gap midpoints and EgoBlur-flagged frames (`redteam.md` Inputs). Frames inside a covered span are already redacted, and sending every frame near every boundary multiplies the red-team's images per track beyond what §9.1's audit reserve prices; EgoBlur still scans every frame;
- **WP0.md** probe f "the same scene question on one clip, plus 5 hard role calls" (max effort) → H1 on **2** hero clips at `medium` (the scene pass's own effort, so the comparison is fair), H2 on **3** role sets at `max`, plus side-on guest and re-entry if probe f's $3.00 allows (`muse-wonder-vs-spark.md`; priced $2.44); probe f counts as run when H1–H4 ran;
- **WP4.md**/**WP7.md** "EgoBlur Gen 2" → the **service auditor** is `SAFECUT_EGOBLUR_MODEL` (Gen 2 unless WP4's held-out comparison picks Gen 1, `egoblur-gen2.md`); **baseline 1b stays Gen 2 at its calibrated defaults** (EVAL row 1b), so the baseline is fixed whatever the auditor choice;
- **WP0.md** probe d "on the same clip" → also one Swahili or Sheng clip **if a consented one exists** (BLOCKED-PRE-A owner step); without it, `SAFECUT_ASR_LANGUAGE_BIAS` stays `["english"]` and the README says Swahili speech evidence is untested;
- **WP1.md**/ARCHITECTURE §3.2 `requests[].concept` → `null` when `kind == "object_prompt"` (a batched object-prompt request mixes concepts; each object's concept lives on its track);
- **WP2.md** step 4 "disputed tracks get one escalation call" → one call **per ≤ 50-keyframe window** the track appears in, combined by `escalation.md`'s window rules (a 60 s clip can need two, §9.1 A10);
- **WP0.md** main dependencies → add `meta-sam-parser==0.1.0` (SAM License; a dependency, never vendored, §1.5);
- **WP1.md** step 2 "a streaming parser … property-test it" → wrap the official parser; property-test the wrapper and the record → track mapping (§1.5, §5b);
- **WP4.md** step 1 (EgoBlur, with a gated download) → the replay stub runs **only** under `SAFECUT_REPLAY=1` and in tests. A live service whose detector can't load (no weights) reports `egoblur: missing` on `/healthz` and refuses `POST /start` with `503` `error.code: "auditor_unavailable"` before any Meta call, so no job is processed without its audit (a PRE-B copy request); a detector that fails mid-job counts its frames unscanned (`audit_failed`, L10). WP4's own done-when ("`unresolved == 0` on hero clip 1 (live)") therefore needs the weights. **Decided fallback** if the O8 weights haven't arrived by **Oct 31**: `SAFECUT_EGOBLUR_MODEL=yunet-face` runs OpenCV's YuNet face detector (`cv2.FaceDetectorYN`, model from `opencv_zoo`, MIT licence) on every frame as the face auditor, plates are checked by the red-team only, and `audit.json` `egoblur.model`, the receipt and the README say so plainly (AGENTS rule 9). *Rejected:* running live jobs on the replay stub (fails open) and red-team only (no every-frame face check);
- **WP5.md** API and cron → adds `POST /v1/jobs/{id}/audit` (PR #2 request 11), the `cover_spot` review edit, `code_valid_until`, `replay_of`, `retry_at`, `401 code_not_active`, `422`/`429` on `/start`, `503 auditor_unavailable`; the 24 h purge skips only the consented replay copy and the **pinned hero jobs** that `GET /v1/demo/{hero_id}` serves (PR #2 UI-SPEC §1.6 and request 19, `pinned: true`; consented hero footage only, AGENTS rule 5); the daily cap is $0 after the judge/public window end in `SAFECUT_CODE_WINDOWS`;
- **WP2.md** step 3 "burn the frame number in a corner" → a `bar_h` = 40 px black bar **added above** the frame, carrying the number (§5; `role-pass.md`), so the grid mapping and vectors G1–G14 hold and nothing in the picture is covered;
- **WP4.md** step 2 "each leak becomes a new hidden item (a box from the detector, padded)" and DESIGN §2.8 "new hidden track" → every leak, EgoBlur's and the red-team's, becomes one hidden **decision item** with `origin: "audit_patch"` and a static box over `f ± (ceil(sample_step / 2) + temporal.extend)` (consecutive EgoBlur frames of one leak merge into one item, IoU ≥ 0.3, with `box` = the union of the merged boxes and the span `first_f − pad … last_f + pad`, `pad = ceil(sample_step / 2) + temporal.extend`); WP4's patch loop **calls WP3's guard (`safecut.guard`) between passes** to rebuild `plan.json` before each re-render, and WP3's `decide` and `apply_review` carry `origin: "audit_patch"` items through unchanged; a `redaction_too_weak` upgrade is recorded in `audit.json` `leaks[].flag`, and WP3's guard reads it to set that item's style to `solid` on every re-plan (§12 rows above, `redteam.md`);
- **WP7.md** "`--variant <v>`" and "caps itself at 3 test runs (counter file)" → run k = baseline 3 then `full`, the counter counts k, the test line is a caller cap, and any job with a `cap: "test_line"` budget line is excluded from `metrics.json` (§9.2);
- **WP1.md** "upscale masks to the frame size" → **place** the box-sized mask at its box origin as a frame-sized RLE (§1.4, §1.5; the `tracks.json` row above); "gap_merge_frames" counts **proxy** frames (§5b); `crowded_frames` lists the **whole prepared span** around each crowded proxy frame (§5b, T11);
- **WP2.md** "map turn times to frame ranges with `job.times`" → `clamp(floor(t × job.fps), 0, job.frames − 1)` (§5b step 6): turns are on the prepared clock, and `job.times` holds source seconds;
- **WP3.md** "back-fill 15 frames" (and its test) → `ceil(15 × job.fps / sam_fps_eff)` prepared frames, 57 at 30 → 8 fps (§5b, T10);
- **WP6.md** "frame-accurate mapping via `job.times`" → the review player plays `prepared.mp4` and maps with `clamp(floor(mediaTime × job.fps + 0.25), 0, job.frames − 1)` (§5b, T5; PR #2 UI-SPEC §3.6); `job.times` is used only to show source time;
- **WP7.md** "`--split test` works on the owner's Mac" → on the owner's **Linux NVIDIA box**: EgoBlur's `torch==2.9.1` has no Intel-Mac wheel (`egoblur-gen2.md`, BLOCKED-PRE-A).

Not contract changes: a job's `retry_later` state lives in WP5's job record (API), not in a stage file. `job.json` keeps ARCHITECTURE §3.1's fields, with the meanings in §5b.

Requests to PRE-B (PR #2):
- UI-SPEC §5.3 "Audit detail link" row: drop "otherwise on a sample plus every frame at an item's edges", and in §3.3 (request 11's re-run) drop "which is every frame when `frames_scanned` equals `frames`". EgoBlur always scans every output frame, so a clean result has `frames_scanned == frames`; fewer means unscanned frames in `unresolved` with `blocked_reason: "audit_failed"` (vector L10);
- STORYBOARD §3: drop "PRE-A's hero line (§9.2: 6 runs × 3 renders)", "$20.16" and "overruns can come out of PRE-A's planned headroom". Recording runs are paid only by the $12 recording code; PRE-A's §9.2 has no hero line. UI-SPEC request 20, STORYBOARD §3 and BLOCKED-PRE-B let the owner raise that cap in WP5's config: bound the raise at **+$3.00 in total, to $15.00** (the §9.2 headroom, shared with every other overrun). **Done in PR #2 @ `22283eb`** (STORYBOARD §3, BLOCKED-PRE-B: "at most $15"); UI-SPEC request 20 describes only the mechanism, which is consistent;
- adopted from PR #2 @ `32a349f`, no change needed: the $6 pilot code and $20 pool with `pilot_pool_cap`, the $12 recording code (but see the raise bound above), the `failure.reason` set (plus PRE-A's new `code_not_active`, requested below), `blocked_reason` + `audit_budget_cause`, and `code_kind`/`code_id` in `cost.jsonl` (UI-SPEC requests 1, 11, 20);
- show `suggested_role`, `escalation_evidence` and `escalation_frames` in the Why drawer next to the votes ("A second look suggests: Part of the story"). Adopted in PR #2 @ `e86a051`;
- show the `blocked_reason` panels and `audit_budget_cause` copy (adopted in PR #2 @ `32a349f`, UI-SPEC §4 and §5.3);
- add a §2.6 row for `401` `code_not_active` on `/try` (a code used outside its kind's window, §9.2), e.g. "This access code isn't active right now." (today UI-SPEC §2.6 maps every `401` to "That code didn't work"), **and a §10.3 job-page row** for the same code on `POST /start`/`/render`/`/audit` (e.g. "This access code has expired, so Safe Cut can't run more work on this clip. You can still download or delete it."); hide [Try again tomorrow] when `retry_at` is after the job's `code_valid_until`; add `owner` to request 20's `kind` list and to request 1's `code_cap` definition ("a pilot, recording or owner code"); and mention in request 20 that entries may carry `valid_from`/`valid_until` to narrow the kind's window (optional; BLOCKED-PRE-B's recording entry is valid as written);
- **`audit.sample_step`** (request 18, §3.3, mock `result-unresolved-review.json`): PRE-A owns the audit contract (UI-SPEC §3.3 says so) and defines it as `round(job.fps)`, the red-team's 1 fps step, for every pass, EgoBlur's leak rows included (§12 above). Drop "(1 when every frame was checked)" and "EgoBlur leaks found on every frame group with step 1", and use `round(job.fps)` (e.g. 30) in the mock; with 1, `cover_spot` would extend a spot by half a frame instead of half a second;
- request 1: `POST /start` answers `429 code_cap` / `429 pilot_pool_cap` when the code's or the pool's remaining budget **can't cover the job's §9.1 estimate** (§10.3), not only when it's used up, so a job never starts on a code that would cut it off mid-run (HANDOFF-PRE-B lists this wording as open);
- HANDOFF-PRE-B item 1: strike "`429 job_cap` on POST /start, replacing `422`" (both sides now use `422 job_cap`, UI-SPEC §10 and PRE-A §10.3) and "the recording cap limit of at most $15 in request 20" (not needed: STORYBOARD and BLOCKED-PRE-B carry the bound);
- audit patches are `decisions.items[]` with `origin: "audit_patch"` and `audit_label` `A<n>` (§12), which is what UI-SPEC §0/§4.3 already assume; please name `origin` and `audit_label` in request 18 and in the mocks, and draw their overlay regions like any hidden item;
- static items (`origin: "static"`, a miss-loop fallback that SAM couldn't track, no votes, no keyframe label): a Why row, e.g. "Muse Spark spotted something here that SAM 3.1 couldn't follow, so Safe Cut covered the area. Keep it clear if it's harmless.", and exempt them from the mock invariant that an evidence frame is a keyframe with a box;
- Why rows for `hold: "no_speech"` ("The speech check didn't work for this clip, so we didn't keep anyone clear automatically.") and `hold: "no_speech_link"`, a 3/3 `participant` track that nothing links to speech or an introduction while a transcript exists (§12 speech/introduction evidence, vectors P8, P9): e.g. "All three checks said part of the story, but Safe Cut couldn't link them to anyone speaking or introduced, so it's your call.", above "checks didn't all agree"; and the café mock's `i_1` (`face:1`, `matches_participant: null`, hero transcript) should then be `needs_you`, not `keep`;
- `failure.reason: "code_not_active"` (a re-queued job whose code window closed): copy like the job-page `401` row, with **no** [Try again]; `503 auditor_unavailable` on `/start`: "Safe Cut's final check isn't available right now, so it can't start new clips. Try again later.";
- request 14 kind mapping: `child` also when the item's track has `child_phrase: true` (§12), and the static-item Why row ranks **below** "Hidden, child" (a locked child static item never shows "keep it clear");
- a Why row for `hold: "no_roles"` ("Safe Cut's checks couldn't run on this, so it stays hidden until you decide."), above "checks didn't all agree";
- `cover_spot` box (request 18, §3.3): the covering item has **one static box, the union of the spot's `boxes`**, not boxes interpolated between audited frames (which can miss a face moving within `sample_step`); please drop "with boxes interpolated between them";
- `other` items (miss-loop concepts) **do** get object rulings: PRE-A's role pass judges every label that isn't `face:`/`person:` as an object (`role-pass.md`, `miss-loop.md`), so UI-SPEC §4.3's "no object ruling to quote" for `other` should read `roles.objects[]` like any object and use the harmless-object row;
- `cover_spot` span (request 18, §3.3): write "`first − half − temporal.extend` … `last + half + temporal.extend`, `half = ceil(sample_step / 2)`, no back-fill" instead of "the leak guard's temporal padding", which DESIGN §2.6 also uses for back-fill;
- a Why-drawer row for `decisions.items[].hold: "no_scene"` ("The scene check didn't run, so we didn't keep anyone clear automatically."), and one for `hold: "unmatched_child"` (§12 table, `scene.children`): e.g. "A child may be in this video and we couldn't tell who, so we didn't keep this person clear automatically. Keep them clear if they're part of the story.", above the "checks didn't all agree" row. It never shows on the hero clips, where every scene child is matched;
- transcript speakers can be `U1`, `U2`, … (the speech fallback's uncertain voices, §4.2), which collide with the `U{n}` unfixed-spot chips (UI-SPEC §1 "every label on screen is unique"): show transcript speakers with a prefix (e.g. "Voice S1", "Voice U1") or otherwise keep the two label sets apart;
- PILOTS §5 and STORYBOARD §3 quote PRE-A's 60 s figures as $1.91–1.99 (@ `948b678`/`4a682c2`). §9.1 A10 now models **$2.02–2.09** ($2.26–2.34 with no cache hits): two pilot clips $4.04–4.18 still fit the $6 code, and the recording runs ≤ $10.00 (exactly $9.99) still fit $12, so only the quoted figures change;
- done in PR #2, no change needed: the mid-job copy for `failure.reason: "daily_cap"` (UI-SPEC §2.6 and mock `job-failed-daily-cap.json`), and the speech link `roles.tracks[].matches_participant` → `scene.participants[i].speaker` (UI-SPEC §4.6 and request 3).
