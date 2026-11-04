> Imported unchanged from `sigmora-platform/docs/meta-hackathon/DESIGN.md` on 2026-10-20 (pre-event design). Where file paths or the Oct 14 model choices differ, [ARCHITECTURE.md](ARCHITECTURE.md) and [MAXXING.md](MAXXING.md) take precedence: this repo is standalone, and it adds Muse Voice Transcribe and an optional Muse Wonder escalation.

# Safe Cut: design

Status: **pre-event design (2026-10-14)**. Nothing here is built; code starts Oct 26 (README, rules of engagement). Every API fact cites Meta's docs as read on 2026-10-14. Re-verify on D1.

## 1. Principle: deny by default, reason to allow

Every face, person, plate, screen and document SAM 3.1 finds is **hidden**. Muse Spark can only *propose keeping something clear*, with a reason, and the creator approves. Children are never auto-cleared. Anything the tracker loses and picks up again is a new, hidden track. This flips the industry default (blur-all-faces or nothing) into one that is safe when the model is wrong, and turns SAM's documented weaknesses (no scores; IDs unreliable across exit and occlusion) into a guarantee instead of a hole.

## 2. Pipeline

```
upload ─► prepare ─► SAM 3.1 sweep (per concept) ─► tracks (IDs, boxes, masks)
                                   │
                    keyframes @1 fps with Set-of-Mark IDs + frame numbers burned in
                                   │
           Muse Spark: scene pass (whole clip) ─► role pass (SoM keyframes, ≤50/call)
                                   │                      │
                                   │            misses → new SAM noun phrases (loop ≤2)
                                   ▼
                    policy (deny-by-default, children locked, unsure = hidden)
                                   │
              leak guard (spatial pad, temporal extend/backfill, gap hold, crowd fallback)
                                   │
           review panel: Hidden / Kept clear / Needs you ─► creator approves
                                   │
                  render (solid / locked-grid pixelate) ─► AUDIT (EgoBlur Gen 2 + Muse Spark red-team)
                                   │                                   │ leak → auto-patch + log
                                   ▼
                     privacy receipt (what, why, who approved, exposure-rate) ─► publish
```

### 2.1 Prepare (reuse: `object-track/prepare.ts`)
H.264 MP4 with `-movflags +faststart` (SAM rejects VP9/WebM), ≤1280 px long edge (the SAM cookbook defaults to 960 px; tune on D1), with source-second timestamps per frame (`PreparedClip.times`, already built).

### 2.2 SAM 3.1 sweep (new provider: `object-track/meta-sam31.ts`)
- `POST https://api.meta.ai/v1/responses`, `model: "sam-3.1"`, `stream: true`, `metadata.mask_encoding: "one_bit"`. Input is an `input_text` noun phrase plus an `input_video` (`file_id` from `POST /v1/files`, `purpose=user_data`, `expires_after: 3600`). [segmenting](https://dev.meta.ai/docs/sam/segmenting), [reading](https://dev.meta.ai/docs/sam/reading-segmentation)
- **One request per concept:** `face`, `person`, `license plate`, `screen`, `phone`, `document`, `name badge` (+ Muse-proposed phrases). Requests run in parallel (3,000 RPM).
- Output is a special-token stream, one delta per frame: `<0f>…<|box;x1;y1;x2;y2;w;h|><|mask;…|>`. Parse with `@meta-sam/parser` (`parseVideoStream`, `decodeMaskToRLE`). Masks are smaller than the frame, so upscale them. Frame indices skip empty frames, and **there are no scores**. [client-libraries](https://dev.meta.ai/docs/sam/client-libraries)
- **Interface change:** today's `ObjectTrackProvider.segment()` returns a *video* (`outputPath`) that `mask-video.ts` reads boxes out of (built for fal). Meta returns detections directly, so add an optional `detect(): AsyncIterable<FrameDetections>` path and skip `mask-video.ts` for this provider. Widen `TrackObjectsUsage['provider']` (`types.ts:27`, which also feeds billing) to `'fal/sam-3' | 'meta/sam-3.1'`.
- Limits: ≤15,000 frames per request (about 8 min at 30 fps), **≤16 objects per frame**, text prompts only.
- Cost: $0.20 per 1k frames. A 30 s clip at 30 fps × 7 concepts = 6,300 frames ≈ **$1.26**. At the 8 fps smart rate, ≈ $0.34.

### 2.3 Muse Spark: scene pass + role pass
- Model `muse-spark-1.3` **Standard** (never `-contributor`: Meta's policy says not to send personal information to Contributor mode). Responses API with `store: false`; delete files afterwards. [contributor-tier](https://dev.meta.ai/help/policies-and-privacy/contributor-tier), [responses](https://dev.meta.ai/docs/protocols/responses)
- **Scene pass (whole clip, video input):** "Who is the creator/host? Who is introduced or interviewed? What's happening?" This produces the context (participants by description, e.g. "the woman in the yellow jacket introduced as Amina at the start") plus candidate sensitive objects. Video timestamps are **undocumented**, so never trust free-text times; this pass only sets context.
- **Role pass (Set-of-Mark keyframes):** at 1 fps, draw each SAM track's box with its **ID number** and **burn in the frame number** (Set-of-Mark, [arXiv 2310.11441](https://arxiv.org/abs/2310.11441); NumPro, [arXiv 2411.10332](https://arxiv.org/abs/2411.10332)). Send ≤50 images per call plus the scene-pass context. Structured output via `text.format: {type:"json_schema", strict:true}`:

```json
{
  "tracks": [
    {"track_id": "face:7", "role": "participant|bystander|child|unsure",
     "evidence": "introduced at frame 90, speaks to camera at 120–600",
     "frames": [90, 120, 150]}
  ],
  "objects": [
    {"track_id": "screen:2", "sensitive": true, "content": "email inbox with names", "frames": [300]}
  ],
  "missed": [
    {"what": "addressed envelope on table", "sam_phrase": "envelope", "frame": 420, "point": {"x": 512, "y": 640}}
  ]
}
```

  - `missed` items become new SAM sweeps (loop ≤2). This is the closed loop Meta's docs describe, where Muse Spark interprets a scene and decides what to segment ([media-segmentation](https://dev.meta.ai/docs/media-segmentation)).
  - **Self-consistency:** run the role pass 3× at medium effort. `participant` requires 3 out of 3; any disagreement → `unsure` → hidden + "Needs you". Escalate disputed tracks to `reasoning.effort: "max"` once.
  - Points use a 0–1000 grid, clamped (values of 1001 have been seen) and mapped to the exact image sent. [image-understanding](https://dev.meta.ai/docs/image-understanding)

### 2.4 Matching (only where SoM didn't settle it)
A point → pixels → inside the dilated (10%) track mask on that frame? Otherwise the nearest box within 0.1 × the frame diagonal. Vote across keyframes, Hungarian assignment; ties → `unsure`.

### 2.5 Policy (new: `safe-cut/policy.ts`, pure functions, exhaustively unit-tested)
- Default `hide` for every track of every sensitive concept.
- `keep` only if: role = participant (3/3 votes) **and** the track isn't a child **and** it's consistent across ≥2 keyframes.
- New ID appearing mid-clip = new person = hidden until the creator merges it into a participant (no biometric re-ID; the EU AI Act treats behavioural matching as biometric, [Recital 17](https://ai-act-service-desk.ec.europa.eu/en/ai-act/recital-17)).
- Screens and documents: `hide` unless Muse Spark says the content is non-personal (menu, map, slide) **and** the creator confirms.

### 2.6 Leak guard
SAM 3 confirms new tracks only after about 15 frames and **zeroes masks for low-score masklets while the object is still there**, which causes leaked frames ([arXiv 2511.16719 App. B/C.3](https://arxiv.org/html/2511.16719)). So:
- **Spatial padding:** faces 15% + 8 px (Sigmora's default padding today is 8%; raise it for faces).
- **Temporal padding:** extend 8 frames after the last detection, **back-fill half a second (`ceil(0.5 × fps)` frames) before the first**, hold the last box through gaps ≤2 s while growing it 2% per frame.
- **Held boxes never move (owner, 2026-11-04).** A held box is the edge box held still: no sweep along the track's motion. It grows 2 % a frame on each side, at most **10 % before the first detection** and **25 % after the last and through gaps** (a gap holds the interpolated box, never a cover stretched from where the object was lost to where it came back). So a held cover stays under 4× its edge box's padded area. Why: the live street-interview review showed a 45-frame motion sweep grown 100 % each side turning a plate or a far bystander (0.1 % of the frame) into a cover over 80–95 % of the frame, "masks randomly placed everywhere", and pre-emptive covers sitting where nothing was yet, sometimes over the presenter. The half-second back-fill still catches SAM's late confirmation of an object already in view; the audit (§2.8) catches anything earlier.
- **A kept participant is never covered by someone else's cover.** Each plan entry of another item lists the kept participants' padded face boxes it overlaps on that frame (`keep_clear`); the renderer, the coverage metric and the web preview leave those pixels untouched. A child's cover and an audit patch are never clipped (a child always wins; a leak the audit found stays covered). Nor is a hidden face ever uncovered for it: where an item's own face box meets a kept face, that kept face isn't cut from the item's entries (its padding, a body or an object gives way elsewhere), since the audit would only patch the uncovered face back over both.
- **Crowd fallback:** if a frame hits the 16-object cap, fill the whole crowded region, and split into tiles or windows for a second pass.

### 2.7 Redaction style (change Sigmora's defaults)
Research says Gaussian blur and fine pixelation are **reversible**:
- Revelio re-identifies Gaussian-blurred faces at 95.9% ([arXiv 2506.12344](https://arxiv.org/abs/2506.12344)).
- Mosaic faces are re-identified at over 95% ([McPherson et al.](https://arxiv.org/abs/1609.00408)).
- Pixelated text is fully recoverable ([Unredacter](https://bishopfox.com/blog/unredacter-tool-never-pixelation)).

Safe Cut therefore uses:
- **Text, screens, plates, documents → `solid`** (always), on the object's own mask or box. Mosaics are reversible for text.
- **People and children → identity only: the face/head, never the body** (owner, 2026-11-04). A hidden, held or "Needs you" person, and every child, gets the **coarse locked-grid mosaic (`pixelate`): 4 blocks across the face (≤ 6 allowed), every block the face region's mean colour plus fixed per-block noise (±24), grid locked to the track** (a shifting grid leaks detail across frames), over the **face region only**, padded like a face (15 % + 8 px). On frames where the item's face isn't planned (missed, turned away, between detections) its body track draws only a **head estimate**: the top of the body box, its full width × `min(0.22·h, 0.9·w)` tall, padded like a face, in the item's mosaic grid (or `solid` when the item has no face track to size a grid). Children stay locked hidden; only the style changed.
- Why: production videos cover only enough to hide identity. The whole-body slate silhouettes we drew before (a "blanket" over half the frame for a held interviewer) made the result look broken, not edited. The mosaic stays unreadable: the cells are coarse and noisy, and a test checks the live audit detector (YuNet) doesn't see a face under it (if it ever did, cells get coarser, never finer). The audit (§2.8) still runs on every rendered frame and patches any leak.
- **`person_solid` (the whole person)** is only the creator's explicit **Remove person** (§2.7b).
- Blur is offered only as an explicitly labelled "cosmetic (reversible)" style, never in Safe Cut.

⚠️ This also matters for Sigmora today: `COMPOSITION_REDACT_DEFAULT_STYLE = 'blur'` in `packages/shared/src/composition-redact.ts`. That is ordinary product work (not hackathon code), and the owner decides whether to change it now.

### 2.7b Identifiability is more than a face (Reddit pass)
A creator had a privacy complaint upheld *despite blurring faces 100%* (r/PartneredYoutube). Blur is reversible (§2.7); our face cover is the coarse noisy mosaic, not blur, and an identifiable person who asks not to appear gets the **remove person** action: a **whole-person** solid mask from SAM `person` (with an estimated body under the face where no body is tracked), recorded in the receipt. That is the only path to `person_solid`. (Until 2026-11-04 the policy also gave prominent bystanders, over 25 % of the frame height, and close-up faces a whole-person mask by default; the owner replaced that with identity-only covers, §2.7.)

### 2.8 Audit (the second look; this is what makes it production-grade)
After rendering, before publishing:
1. **EgoBlur Gen 2** (Meta, Apache-2.0, face and plate detectors, about 21 ms/frame on GPU; [projectaria](https://www.projectaria.com/tools/egoblur/)) on **every output frame**. Any face or plate not under an approved-participant track is a **leak** → auto-patch (new hidden track) + log.
2. **Muse Spark red-team**: show sampled output frames and ask it to read or identify anything (a number, a name, a face). Every hit is a leak.
3. Publish only when there are zero unresolved leaks; the result goes into the receipt.

### 2.9 Privacy receipt
A JSON + human-readable page per render: every hidden or kept item (thumbnail of the redacted frame, reason, frames, who approved, when), the audit result (frames scanned, leaks found and fixed), the models and versions used, and data handling (Standard mode, `store:false`, files deleted). Hash-chained per project. This is the creator's evidence if a privacy complaint arrives.

## 3. What exists in Sigmora vs what we build

| Piece | Status | Where |
|---|---|---|
| Clip prepare (trim, resample, ≤1280 px, per-frame times) | **Exists** | `services/content-autopilot/src/tools/footage/object-track/prepare.ts` |
| Provider interface, track linking, densify, keyframes, low-confidence ranges | **Exists** (fal SAM 3 never run live) | `object-track/index.ts`, `tracks.ts`, `types.ts` |
| Redact layer (blur/pixelate/solid, padding, source-anchored tracks surviving trims) | **Exists** | `packages/shared/src/composition-redact.ts`, render `services/footage-edit/authored-planes.ts:780-822` |
| Sigma agent action + priced approval card | **Exists** (`blur_objects`) | `apps/web/src/lib/sigma/actions/blur-objects.ts` |
| Editor tracking UI + "Check" chips for low-confidence stretches | **Exists** | `apps/web/src/components/composition/object-tracking.tsx` |
| Publishing queue → backend publish | **Exists** | `apps/web/src/lib/publishing-dispatch.ts` |
| Spoken-PII bleep (Scribe entities) | **Exists** | Sigma `redact-sensitive.ts`, `packages/shared/src/sensitive-entities.ts` |
| Meta SAM 3.1 provider (detections path) | **Build** (M) | new `object-track/meta-sam31.ts` |
| Muse Spark client (Files, Responses, video, `text.format`, `store:false`) | **Build** (S–M; may bypass `@ai-sdk/openai` for video parts) | new `providers/llm/meta.ts` |
| Scene pass, SoM keyframe renderer, role pass, miss loop | **Build** (M) | new `tools/footage/safe-cut/{scene,som,roles}.ts` |
| Policy + leak guard | **Build** (M) | new `safe-cut/{policy,leak-guard}.ts` |
| Audit (EgoBlur Gen 2 + red-team) | **Build** (M; EgoBlur runs on the render box) | new `safe-cut/audit.ts` |
| Review panel (Hidden / Kept clear / Needs you; toggle without re-tracking) | **Build** (M) | `apps/web/src/components/composition/safe-cut-review.tsx` + Sigma action `safe_cut` |
| Privacy receipt | **Build** (S) | `safe-cut/receipt.ts` + a page |
| Eval harness | **Build** (M) | public repo `eval/` |

**Repo layout for judging:** the public repo `sigmora-safe-cut` holds the hackathon core as a library + CLI (`safe-cut run clip.mp4`) + eval harness + a static demo page. Sigmora imports it as the host app. The README's "What existed before Oct 26" lists the "Exists" rows above.

## 4. Use of Meta AI tooling (25% of the score): beyond a basic integration

1. **A closed-loop agent:** SAM draws IDs → Muse Spark judges them by number → Muse Spark writes new SAM prompts for what SAM missed.
2. **Turning a limitation into a guarantee:** SAM's no-scores / ID-loss behaviour becomes deny-by-default; Muse Spark's self-consistency becomes the only path to "keep".
3. **Meta-on-Meta audit:** EgoBlur Gen 2 (Meta's own glasses-privacy model) checks the rendered output; Muse Spark red-teams it; the exposure rate is certified per clip.
4. **Local mode (stretch):** Muse Glimmer (Apache-2.0, text + image, about 24 GB VRAM) runs the role pass on a creator's GPU or Apple-silicon Mac with the open SAM 3.1 checkpoint, so raw footage never leaves the machine. [glimmer](https://dev.meta.ai/docs/muse-glimmer)
5. **Measured on Meta's own benchmark (stretch):** run the tracking side on SA-Co/VEval SmartGlasses (CC BY 4.0) to show the leak guard's effect on public egocentric data.

## 5. Open questions to settle on D1 (probe scripts)

- What Muse Spark does with video: max duration, frame sampling, whether timestamps can be trusted. (Undocumented, so measure: a clip with a burned-in frame counter, asking "what frame number is visible when X happens".)
- What SAM's `input_video.fps` field does (undocumented). Whether mask resolution is configurable.
- Real latency for a 30 s clip at 30 fps × 7 concepts, streamed in parallel.
- Whether `@ai-sdk/openai` passes `input_file` video parts; otherwise use direct `fetch`.
- That the key works from Kenya, and Standard-mode availability.
