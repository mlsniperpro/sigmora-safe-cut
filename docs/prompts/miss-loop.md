# Miss loop (v0): proposing SAM noun phrases and points

**Model:** `SAFECUT_ROLE_MODEL` (default `muse-spark-1.3`) · **effort** `medium` · **rides in the role-pass call** (the `missed` array), and on loop iterations 2–3 runs as its own call on the frames around the new sweeps · **max 2 loops** (DESIGN §2.3) · **output** `roles.json.missed` → new SAM requests (WP1)

## Purpose
Close the loop between Meta's two models. Muse Spark looks at the numbered keyframes and names anything sensitive that **has no box**. Each miss becomes a SAM request, either as:
- **(a) a noun phrase** for a new concept sweep over the whole clip (e.g. `envelope`), or
- **(b) an object prompt**: a point (and optionally a box) on the exact frame, propagated `both` ways. SAM 3.1 accepts these per `meta-sam/protocol/sam3.md` (API-NOTES §1.3). This contradicts DESIGN's "text prompts only".

(b) is preferred when the thing is a one-off (one envelope), and (a) when it's a class that likely recurs (`tattoo`, `house number`). The model proposes both, and WP1 decides which to run.

## Inputs
- The same Set-of-Mark keyframes as the role pass (shared prefix), plus the list of concepts already swept: `face, person, license plate, screen, phone, document, name badge` and any earlier loop phrases.
- On loop iteration 2: only the keyframes ±2 s around the previous loop's new tracks, plus "these were added last round: …".

## Prompt text (v0, the user-message section appended to the role pass)
> **Missed items.** Look for anything in these frames that could identify a person or reveal private information and **has no labelled box on it**: e.g. a letter or envelope, a parcel label, a house or flat number, a whiteboard with names, a photo of a person, a tattoo, a name written on clothing, an ID card, a face in a poster or on a screen, a reflection of a face in a window or mirror, or a licence plate that's partly hidden.
> For each one give:
> - `what`: a short description;
> - `sam_phrase`: a **2–3 word lowercase noun phrase** a segmentation model could search for (`envelope`, `house number`, `tattoo`). No adjectives about privacy, no verbs, and not a phrase already in the swept list;
> - `frame`: the burned-in frame number of an image where it's clearest;
> - `point`: one point **on the object** in that image, as `{"x", "y"}` on a 0–1000 grid where (0,0) is the top-left and (1000,1000) the bottom-right of **that image**;
> - `box`: its box on the same grid as `[x1, y1, x2, y2]`, or null if you can't bound it;
> - `recurs`: true if more of this kind probably appear elsewhere in the video.
> Report at most 8. If nothing is missed, return an empty list. Don't report things that already have a label.

## Output schema (the `missed` item, strict)
```json
{
  "type": "array", "maxItems": 8, "items": {
    "type": "object", "additionalProperties": false,
    "required": ["what", "sam_phrase", "frame", "point", "box", "recurs"],
    "properties": {
      "what": {"type": "string"},
      "sam_phrase": {"type": "string"},
      "frame": {"type": "integer"},
      "point": {"type": "object", "additionalProperties": false, "required": ["x", "y"],
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}},
      "box": {"type": ["array", "null"], "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
      "recurs": {"type": "boolean"}
    }}
}
```
`maxItems`/`minItems` support under `strict` is unverified. If WP0 finds they're rejected, drop them and enforce in pydantic. `roles.json.missed` in ARCHITECTURE §3.5 stores `point` in **prepared-clip pixels**, so convert before writing (below). `box` and `recurs` are additions needing a contracts decision.

## Post-processing (WP1/WP2, deterministic)
1. Validate that `frame` was among the images sent, or drop the item.
2. Clamp `x, y` (and box) to [0,1000], then map to pixels: `x_px = floor(x/1000 × (W−1))`, `y_px = floor(y/1000 × (H−1))`, using the size of the prepared clip (keyframes are sent unscaled).
3. Normalise `sam_phrase`: lowercase, strip punctuation, ≤3 words, and reject it if it's already swept or on a blocklist (`person`, `face`, `thing`, `object`, `private`, `sensitive`).
4. Dedupe across votes: the role pass runs 3×, so take the union of misses, merging items whose phrases match and whose points are within 5% of the frame diagonal on the same frame.
5. **Plan:**
   - object prompt on `frame`: `<{frame}f>{n}<|point;x={x_px};y={y_px};w={W};h={H}|>` plus the box token if present, with `metadata.propagation_direction: "both"`;
   - if `recurs`: also a phrase sweep with `sam_phrase`;
   - the new tracks are **hidden by default** (concept `other` → `solid`), and enter the next role pass as normal labels.
6. **Stop** after 2 loops, or when a loop adds no new tracks, or when the job budget falls below the next sweep's cost.

## Failure handling
- An empty or failed miss list means no new sweeps. Not an error.
- A phrase sweep that returns zero matches is logged (`requests[].matches = 0`); the point prompt is still tried.
- A point that SAM can't segment (empty response) → add a **static hidden box** on that frame ±`temporal.extend`, from `box` if given, else a 6% square around the point. Fail closed.

## Tricky cases it must get right
1. **An envelope on a table**, readable for 2 s. `sam_phrase: "envelope"`, a point on it, `recurs: false` → an object prompt on that frame, tracked both ways.
2. **A face on a TV screen** where SAM boxed the screen but the face inside is unboxed. The screen is already labelled, so this is *not* a miss if the screen is sensitive. If the role pass marked the screen non-sensitive (a "news programme"), the face on it is a miss: `sam_phrase: "face on screen"` is too vague, so propose `face` with a point. That's already swept, so the point prompt path is the one that runs.
3. **The phrase that matches everything.** The model proposes `sign` for a street sign with a phone number. `sign` would segment every sign in a city clip, and the cost scales with frames, not matches. Normalisation keeps it, but `recurs: false` means only the point prompt runs. WP1 should log a phrase that returns >16 objects per frame as "too broad" and not re-run it.
