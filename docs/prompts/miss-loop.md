# Miss loop (v0): proposing SAM noun phrases and points

**Model:** `SAFECUT_ROLE_MODEL` (default `muse-spark-1.3`) · **effort** `medium` · **loop 1 rides in the role-pass call** (the `missed` array); **loop 2** runs as its own call on the frames around loop 1's new tracks · **max 2 loops** (DESIGN §2.3) · **output** `roles.json.missed` → new SAM requests (WP1)

## Purpose
Close the loop between Meta's two models. Muse Spark looks at the numbered keyframes and names anything sensitive that **has no box**. Each miss becomes a SAM request, either as:
- **(a) a noun phrase** for a new concept sweep over the whole clip (e.g. `envelope`), or
- **(b) an object prompt**: a point (and optionally a box) on the exact frame, propagated `both` ways. SAM 3.1 accepts these per `meta-sam/protocol/sam3.md` (API-NOTES §1.3). This contradicts DESIGN's "text prompts only".

(b) is preferred when the thing is a one-off (one envelope), and (a) when it's a class that likely recurs (`tattoo`, `house number`). The model proposes both. The rule for which runs is fixed in step 3 below: the point prompt always runs, and a phrase sweep runs only for recurring kinds.

## Inputs
- The same Set-of-Mark keyframes as the role pass (shared prefix), plus the list of concepts already swept: `face, person, license plate, screen, phone, document, name badge` and any earlier loop phrases.
- On loop iteration 2: only the keyframes ±2 s around the previous loop's new tracks, plus "these were added last round: …".

## Prompt text (v0, the user-message section appended to the role pass)
> **Missed items.** Look for anything in these frames that could identify a person or reveal private information and **has no labelled box on it**: e.g. a letter or envelope, a parcel label, a house or flat number, a whiteboard with names, a photo of a person, a tattoo, a name written on clothing, an ID card, a face in a poster or on a screen, a reflection of a face in a window or mirror, or a licence plate that's partly hidden.
> For each one give:
> - `what`: a short description;
> - `sam_phrase`: a **1–3 word lowercase noun phrase** a segmentation model could search for (`envelope`, `house number`, `tattoo`, `face`). No adjectives about privacy and no verbs. It's fine to use a phrase that's already in the swept list if the thing simply has no box (e.g. an unboxed face on a TV);
> - `frame`: the burned-in frame number of an image where it's clearest;
> - `point`: one point **on the object** in that image, as `{"x", "y"}` on a 0–1000 grid where (0,0) is the top-left and (1000,1000) the bottom-right of **that image**;
> - `box`: its box on the same grid as `[x1, y1, x2, y2]`, or null if you can't bound it;
> - `recurs`: true if more of this kind probably appear elsewhere in the video.
> Report at most 8. If nothing is missed, return an empty list. Don't report things that already have a label.

## Output schema (the `missed` item, strict)
```json
{
  "type": "array", "items": {
    "type": "object", "additionalProperties": false,
    "required": ["what", "sam_phrase", "frame", "point", "box", "recurs"],
    "properties": {
      "what": {"type": "string"},
      "sam_phrase": {"type": "string"},
      "frame": {"type": "integer"},
      "point": {"type": "object", "additionalProperties": false, "required": ["x", "y"],
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}},
      "box": {"type": ["array", "null"], "items": {"type": "integer"}},
      "recurs": {"type": "boolean"}
    }}
}
```
**Decided:** the strict schema leaves out `maxItems`/`minItems`, because their support under `strict` is unverified and a 400 would cost a whole call. Pydantic enforces them instead: at most 8 items get SAM prompts (items after the 8th in output order get no SAM call; they take the static-box fallback below and are logged `item_cap`), and a `box` must have exactly 4 integers or it becomes null. `roles.json.missed` in ARCHITECTURE §3.5 stores `point` in **prepared-clip pixels**, so convert before writing (below). **Decided:** add `box` (a better SAM object prompt) and `recurs` (it gates the paid phrase sweeps) to the `missed` contract as optional fields. WP0 implements them in `contracts.py`.

## Post-processing (WP1/WP2, deterministic)
1. Validate that `frame` was among the images sent, or drop the item.
2. Convert `point` and `box` from the 0–1000 grid to prepared-clip pixels with the single rule in API-NOTES §5 (sent-image size, minus the frame-number bar, floor, clamp). If the point lands in the bar (dropped by that rule) and the item has a valid `box`, the box's centre becomes the point; otherwise the item is dropped.
3. Normalise `sam_phrase`: lowercase, strip punctuation, collapse spaces. A phrase of **more than 3 words** isn't truncated (that would change its meaning); it gets no phrase sweep and is logged `phrase_too_long`. A **phrase sweep** is planned only if `recurs` is true **and** the phrase isn't already swept **and** it isn't on the blocklist (`thing`, `object`, `stuff`, `private`, `sensitive`, `item`). The **point prompt is always planned**, whatever the phrase.
4. Dedupe across votes: the role pass runs 3×, so take the union of misses, merging items whose phrases match and whose points are within 5% of the frame diagonal on the same frame.
5. **Plan:**
   - convert the frame axis. `frame` is a **prepared-clip** frame index (the burned-in number), but the SAM upload may be a lower-fps proxy encoded from the prepared clip (API-NOTES §9: ≤10 fps for cost). Use the single definition in **API-NOTES §5b**: `sam_frame = to_proxy(frame)`, the proxy frame whose shown prepared frame (`from_proxy`) is nearest to `frame`. It's derived from ffmpeg's `fps` filter slot rule, not a plain ratio (vectors T1–T4). A briefly visible object that the nearest proxy frame misses is caught by the static-box fallback below;
   - **one batched object-prompt request per loop**: every kept item of the loop becomes its own object id (1, 2, …) in a single request's `input_text`, built with `build_object_prompt(size=(W, H), objects=[…])`, each on its own `sam_frame`. Each object's segment is `<{sam_frame}f>{n}<|point;x={x_px};y={y_px};w={W};h={H}|>`, plus its box token if present. The request sets `metadata.propagation_direction: "both"` (`W×H` = the SAM upload's size; rescale the pixels if the proxy is also downscaled). Every SAM request sweeps the whole proxy and is billed for all of its frames (API-NOTES §9.1 A2), so batching keeps it to one charge per loop. If the API rejects the object count *(probe; "a model may limit how many objects one request can prompt")*, split into the fewest requests it accepts;
   - if `recurs`: also a phrase sweep with `sam_phrase`, **at most 3 phrase sweeps per loop** (WP2.md step 5). Pick the first 3 recurring items in output order; log the rest as `phrase_budget`;
   - the new tracks are **hidden by default** (`solid`), and enter the next role pass as normal labels. A new track's **concept is the normalised `sam_phrase`** (step 3), except that a phrase naming a person (`child`, `kid`, `baby`, `boy`, `girl`, `man`, `woman`, `person`, `people`, `reflection`, `face`) maps to concept `person` (or `face` for `face`), so it's judged as a person and can be locked as a `child` (DESIGN §2.5); the phrase sweep still uses the original phrase, so `track_id` = `"<sam_phrase>:<id>"` (ARCHITECTURE §3.2) and a face found by point prompt is `face:n`, never `other:n`. In the role pass, `face` and `person` labels are judged as people; **every other concept** is judged as an object (`sensitive`), whether or not it's in role-pass.md's example list (`envelope:3`, `tattoo:1`). In `decisions.json` a concept outside the base sweep list gets `kind: "other"`.
6. **Stop** after 2 loops (loop 1 sweeps the first role pass's misses; loop 2 sweeps the misses from the role re-pass over loop 1's new tracks, the "loop-2 role re-pass" priced in API-NOTES §9.1. **Loop 2's new tracks get no role pass**: they stay hidden, and the creator can keep one in review), or when a loop adds no new tracks, or when the next request's pre-call estimate exceeds the remaining job budget **minus the audit reserve**. The reserve is **1.2 ×** red-team passes 1–3 at the `redteam.md` sampling for the current track count (API-NOTES §9.1 A8), re-estimated before each loop. The 20% covers re-asks and missing-frame follow-ups. The miss loop never spends the money the audit needs (an un-runnable audit blocks publishing).

## Failure handling
- An empty or failed miss list means no new sweeps. Not an error.
- A phrase sweep that returns zero matches is logged (`requests[].matches = 0`); the point prompt is still tried.
- **Every validated miss item is covered, swept or not (fail closed).** An item that never gets a SAM result (past the 8-item cap, stopped by the budget check in step 6, or whose object-prompt request failed after the API-NOTES §10.2 retries) gets the static hidden box below and marks the job `needs_you` with the note "possible missed object at F{frame}". The miss loop may stop early; a reported miss is never silently dropped. Only items failing step 1 or 2 (frame not sent, no usable point) are dropped.
- A point that SAM can't segment (empty response) → add a **static hidden box** on that frame ±`max(temporal.extend, round(job.fps))` frames (at least ±1 s, so boxes from neighbouring 1 fps keyframes overlap and nothing between them is left open), from `box` if given, else a square around the point with a side of 6% of `min(W, H)` (43 px at 1280×720). Fail closed.

## Tricky cases it must get right
1. **An envelope on a table**, readable for 2 s. `sam_phrase: "envelope"`, a point on it, `recurs: false` → an object prompt on that frame, tracked both ways.
2. **A face on a TV screen** where SAM boxed the screen but the face inside is unboxed. The screen is already labelled, so this is *not* a miss if the screen is sensitive. If the role pass marked the screen non-sensitive (a "news programme"), the face on it is a miss: the model proposes `face` with a point. `face` is already swept, so no phrase sweep is planned, but **the point prompt runs** (step 3), and the face gets its own hidden track.
3. **The phrase that matches everything.** The model proposes `sign` for a street sign with a phone number. `sign` would segment every sign in a city clip, and the cost scales with frames, not matches. Normalisation keeps it, but `recurs: false` means only the point prompt runs. WP1 should log a phrase that returns >16 objects per frame as "too broad" and not re-run it.
