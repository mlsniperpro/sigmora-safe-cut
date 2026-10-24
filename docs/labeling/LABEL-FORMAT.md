# Label format: the label JSON and the MOT box files

Status: **v2, 2026-10-24 (PRE-B).** The schema is [EVAL.md](../EVAL.md) §1, unchanged; this file pins down what each field means, the file layout, the MOT conventions and the conversion from CVAT, plus the exact JSON Schemas (§6), the validator's error codes (§7), valid and invalid test cases (§8) and test vectors with expected outputs (§9). WP7 implements the loader and validator from it (`eval/`). What to put in the fields: [LABELING-GUIDE.md](LABELING-GUIDE.md). How to produce the boxes: [CVAT-SETUP.md](CVAT-SETUP.md).

## 1. Files per clip

```
labels/<split>/                       private: ~/SafeCutEval/labels/ (+ the private bucket for dev and hero only)
  SC-A-01.json                        the resolved label (what the metrics use)
  SC-A-01.labeller-A.json             A's independent label, before resolution
  SC-A-01.labeller-B.json             B's independent label (no boxes)
  SC-A-01.adjudication.md             every disagreement and how it was settled (§4)
  tracks/SC-A-01/e1.mot.txt           one MOT file per entity (§3)
  cvat/SC-A-01.mot.zip                CVAT's MOT 1.1 export, as downloaded
  cvat/SC-A-01.cvat-video.zip         CVAT for video 1.1 backup
  cvat/SC-A-01.track-map.json         CVAT track_id → entity ID (§3.1)
clips.md                              the clip list: clip, split, category, status, labellers, CVAT version
```

The **clip ID** is the first three parts of the file name in [SHOTLIST.md](../SHOTLIST.md): `SC-A-01-cbd-20261018.mp4` → `SC-A-01`. Test-split labels stay on the owner's Mac and its private backup; only the split hash (`eval/splits/test.sha256`, WP7) is committed.

## 2. The label JSON

| Field | Type | Meaning |
|---|---|---|
| `clip` | string | the source file name, exactly as filmed |
| `fps` | number | the source frame rate (ffprobe's average, e.g. `30` or `29.97`) |
| `frames` | integer | number of frames in the source clip |
| `width`, `height` | integer | source resolution in pixels |
| `split` | `"dev"` \| `"test"` \| `"hero"` | the split the clip belongs to ([EVAL.md](../EVAL.md) §1) |
| `entities[].id` | string | `e1`, `e2`, …, unique within the clip; the number is the MOT `id` |
| `entities[].category` | string | one of the nine in [LABELING-GUIDE.md](LABELING-GUIDE.md) §2.1 |
| `entities[].should_hide` | boolean | the ground truth |
| `entities[].reason` | string | one plain sentence about behaviour or content |
| `entities[].difficulty` | string[] | zero or more of `small`, `occluded`, `reentry`, `motion_blur`, `crowd` |
| `entities[].frames.first`, `.last` | integer | the first and last **visible** frame, **0-based** source frame indices, inclusive. Gaps in between are allowed (that's re-entry) |
| `entities[].boxes` | string \| null | path to the entity's MOT file, relative to `labels/<split>/`. `null` only in a labeller-B file |
| `notes` | string | anything a reader needs: things below threshold, harmless items that must stay clear, filming problems |

**Coordinates and frames are in the source clip** (e.g. 1920×1080 at 30 fps). The pipeline works on the prepared clip (≤1280 px, its own frame list, [ARCHITECTURE.md](../ARCHITECTURE.md) §3.1). WP7 maps labels onto it. **The time axes follow PRE-A `docs/API-NOTES.md` §5b, which owns the definition**; this doc doesn't redefine anything:
  - **No trim in Safe Cut.** The prepared clip covers the whole source, and `times[0] = 0.0`. `times[i]` is the presentation time of prepared frame `i` on the source timeline, where `t = 0` is the first decoded source frame (its PTS, after the edit list, is subtracted).
  - **label → prepared** (WP7): a label on source frame `k` sits at its **own** timestamp `t_k = PTS_k − PTS_0`, which WP7 reads per frame from the source file with ffprobe (it isn't stored in the label JSON). Its prepared frame is `argmin_i |times[i] − t_k|`, with a **tie going to the lower index**. `k / fps` is correct only for constant-frame-rate sources, so WP7 never uses it. Boxes scale per axis: `x, w` by `prepared.width / source.width` and `y, h` by `prepared.height / source.height` (equal ratios when prepare keeps the aspect ratio). Keep the results as floats; never round.
  - **player → prepared** (UI overlay): `i = max{ i : times[i] ≤ m + 0.001 }` for media time `m` ([UI-SPEC.md](../UI-SPEC.md) §3.6).
  - **prepared → SAM proxy:** PRE-A §5b's formula, not this doc's.
  - **If trimming is ever added,** `job.json` gains `source_offset_s` (PRE-A §5b, a contract change), and every mapping above adds it.

Labellers never resample anything; all of this is WP7's code.

## 3. The MOT files

One file per entity at `tracks/<clip-id>/<entity-id>.mot.txt`, one row per **visible** frame, ascending, no header:

```
frame,id,x,y,w,h,1,-1,-1,-1
```

| Column | Meaning |
|---|---|
| `frame` | **1-based** (MOT convention): source frame index + 1. Frame index 0 is row frame `1` |
| `id` | the entity number: `e3` → `3` |
| `x`, `y` | top-left corner of the box, source pixels |
| `w`, `h` | box width and height, source pixels (integers or decimals) |
| `1` | confidence: always 1 for ground truth |
| `-1,-1,-1` | unused (MOTChallenge's 3D coordinates) |

A frame with no row is a frame where the entity isn't visible (out of frame, fully hidden, marked Outside in CVAT). So the number of rows is the entity's **visible frames**, the denominator of recall and exposure.

### 3.1 From the CVAT export

CVAT's MOT 1.1 export is one `gt/gt.txt` for the whole task with columns `frame_id, track_id, x, y, w, h, "not ignored", class_id, visibility` (CVAT docs) and a `gt/labels.txt` listing the label names. To get our files:

1. Map each CVAT `track_id` to an entity ID. In CVAT v2.80.0's export, `track_id = n` is **the n-th track to appear in the clip**, not the ID shown in CVAT's UI ([CVAT-SETUP.md](CVAT-SETUP.md) §7.1, with source lines). So labeller A numbers the entities by first visible frame, breaking ties by box, and writes the map.
2. For each track: keep `frame_id`, `x`, `y`, `w`, `h`; set `id` to the entity number; set the last four columns to `1,-1,-1,-1`.
3. Frames are already 1-based and equal to UI frame + 1, provided no frame was deleted in the task and the frame step is 1 (CVAT-SETUP.md §7.1). Frames marked Outside have no rows. Coordinates are decimals in source pixels; keep them as written.

This is mechanical, so WP7's label loader should accept the CVAT zip directly, plus a small map file next to it (`cvat/SC-A-01.track-map.json`, e.g. `{"1": "e1", "2": "e3"}`, written by labeller A), and produce the per-entity files itself. That's listed as a request to WP7 in the PRE-B PR. Until it exists, nobody converts by hand: export, store the zip, and wait.

### 3.2 Checks the validator should run (spec for WP7)

- Every entity in the label JSON has a MOT file, and every MOT file belongs to an entity.
- Row frames are ascending, unique, and within `1 … frames`.
- `frames.first + 1` equals the first row's frame and `frames.last + 1` the last row's.
- Every box lies inside `0 … width` × `0 … height` and has `w, h > 0`.
- Person boxes are at least 24 px tall on at least one frame (the threshold in the guide).
- Categories and difficulty tags come from the allowed lists; `child` entities have `should_hide: true`.
- Labeller B's file contains every entity ID in labeller A's file (B labels A's whole list) and may add more. The resolved file contains every ID from both. Agreement statistics use only the IDs in A's file; B's extra IDs are counted separately as A's misses ([LABELING-GUIDE.md](LABELING-GUIDE.md) §5).

## 4. The adjudication log

`SC-A-01.adjudication.md` is a short table, one row per entity where A and B differed:

| Entity | A said | B said | Resolved | How | Guide case |
|---|---|---|---|---|---|
| e6 | screen, false | screen, true | false | case covers it | #24 (menu) |

"How" is one of: *case covers it*, *agreed after discussion (new case #n added)*, *disputed → hidden by default*. Agreement (percent, κ, and the 2×2 counts) is computed from the labeller-A and labeller-B files, never from the resolved one.

## 5. Worked example: a 10-second clip

**This example is invented to show the format**; it is not a real clip and its numbers are not results. `SC-A-90` is a 10 s street interview, 1920×1080, 30 fps, 300 frames (indices 0–299). In it: the host (right) and the guest (left) talk; a passer-by crosses behind them right to left, ducks behind a parked van and comes out the other side holding a phone that shows a chat; a parked car's plate is visible throughout; a food kiosk's menu screen is on the left until the camera pans at 0:03; a child walks past at the end.

### 5.1 `labels/dev/SC-A-90.json`

```json
{
  "clip": "SC-A-90-example-20261024.mp4",
  "fps": 30, "frames": 300, "width": 1920, "height": 1080,
  "split": "dev",
  "entities": [
    {"id": "e1", "category": "participant", "should_hide": false,
     "reason": "host, asks the questions and faces the camera",
     "difficulty": [], "frames": {"first": 0, "last": 299},
     "boxes": "tracks/SC-A-90/e1.mot.txt"},
    {"id": "e2", "category": "participant", "should_hide": false,
     "reason": "interview guest, introduced at 0:00 and answers",
     "difficulty": [], "frames": {"first": 0, "last": 299},
     "boxes": "tracks/SC-A-90/e2.mot.txt"},
    {"id": "e3", "category": "bystander", "should_hide": true,
     "reason": "passer-by, walks behind the guest, hidden behind a van then reappears",
     "difficulty": ["reentry", "occluded"], "frames": {"first": 60, "last": 209},
     "boxes": "tracks/SC-A-90/e3.mot.txt"},
    {"id": "e4", "category": "plate", "should_hide": true,
     "reason": "parked car plate, legible",
     "difficulty": ["small"], "frames": {"first": 0, "last": 299},
     "boxes": "tracks/SC-A-90/e4.mot.txt"},
    {"id": "e5", "category": "screen", "should_hide": true,
     "reason": "phone in the passer-by's hand shows a chat with a phone number",
     "difficulty": ["small", "motion_blur"], "frames": {"first": 165, "last": 194},
     "boxes": "tracks/SC-A-90/e5.mot.txt"},
    {"id": "e6", "category": "screen", "should_hide": false,
     "reason": "kiosk menu screen, no personal data",
     "difficulty": [], "frames": {"first": 0, "last": 89},
     "boxes": "tracks/SC-A-90/e6.mot.txt"},
    {"id": "e7", "category": "child", "should_hide": true,
     "reason": "child passing in the background",
     "difficulty": ["small"], "frames": {"first": 240, "last": 299},
     "boxes": "tracks/SC-A-90/e7.mot.txt"}
  ],
  "notes": "Menu screen e6 must stay CLEAR (context test). 2 far faces at 0:01 below the 24 px threshold; 1 distant plate at 0:08 illegible. Neither is labelled."
}
```

Row counts (= visible frames): e1 300, e2 300, e3 **120** (60–119 and 150–209; 120–149 behind the van), e4 300, e5 30, e6 90, e7 60.

### 5.2 `tracks/SC-A-90/e5.mot.txt` (complete)

The phone is visible on source frames 165–194, so rows run from frame `166` to `195`. It moves left with the passer-by at about 6 px per frame:

```
166,5,860,432,40,70,1,-1,-1,-1
167,5,854,432,40,70,1,-1,-1,-1
168,5,848,432,40,70,1,-1,-1,-1
169,5,842,432,40,70,1,-1,-1,-1
170,5,836,432,40,70,1,-1,-1,-1
171,5,830,432,40,70,1,-1,-1,-1
172,5,824,432,40,70,1,-1,-1,-1
173,5,818,432,40,70,1,-1,-1,-1
174,5,813,432,40,70,1,-1,-1,-1
175,5,807,432,40,70,1,-1,-1,-1
176,5,801,432,40,70,1,-1,-1,-1
177,5,795,432,40,70,1,-1,-1,-1
178,5,789,432,40,70,1,-1,-1,-1
179,5,783,432,40,70,1,-1,-1,-1
180,5,777,432,40,70,1,-1,-1,-1
181,5,771,432,40,70,1,-1,-1,-1
182,5,765,432,40,70,1,-1,-1,-1
183,5,759,432,40,70,1,-1,-1,-1
184,5,753,432,40,70,1,-1,-1,-1
185,5,747,432,40,70,1,-1,-1,-1
186,5,741,432,40,70,1,-1,-1,-1
187,5,735,432,40,70,1,-1,-1,-1
188,5,730,432,40,70,1,-1,-1,-1
189,5,724,432,40,70,1,-1,-1,-1
190,5,718,432,40,70,1,-1,-1,-1
191,5,712,432,40,70,1,-1,-1,-1
192,5,706,432,40,70,1,-1,-1,-1
193,5,700,432,40,70,1,-1,-1,-1
194,5,694,432,40,70,1,-1,-1,-1
195,5,688,432,40,70,1,-1,-1,-1
```

In CVAT this took three keyframes (frames 165, 180 and 194 in the UI); the rest is interpolation.

### 5.3 `tracks/SC-A-90/e3.mot.txt` (excerpt around the gap)

```
61,3,1500,300,70,90,1,-1,-1,-1      ← source frame 60, first visible
62,3,1493,300,70,90,1,-1,-1,-1
63,3,1487,300,70,90,1,-1,-1,-1
…                                    (rows 64–118)
119,3,1113,300,70,90,1,-1,-1,-1
120,3,1107,300,70,90,1,-1,-1,-1     ← source frame 119, last before the van
                                     (no rows 121–150: fully behind the van, Outside in CVAT)
151,3,950,300,70,90,1,-1,-1,-1      ← source frame 150, reappears
152,3,944,300,70,90,1,-1,-1,-1
…                                    (rows 153–208)
209,3,606,300,70,90,1,-1,-1,-1
210,3,600,300,70,90,1,-1,-1,-1      ← source frame 209, last visible
```

(The arrows and `…` lines are annotations for this doc only; real files contain only data rows.)

### 5.4 How the metrics read this clip

- **should_hide entities:** e3, e4, e5, e7 (4). Recall counts each one hidden if ≥95% of its visible frames are covered; for e3 that's ≥114 of its 120 frames. Frames 120–149 don't count either way.
- **should_keep entities:** e1, e2, e6 (3). Over-blur counts any of them hidden on >10% of their frames; e6 hidden on more than 9 of its 90 frames is an over-blur.
- **Leak bursts:** any run of ≥3 consecutive visible frames of e3, e4, e5 or e7 with less than 90% of the box covered. For e3, a run can't span the gap: frame 119 and frame 150 aren't consecutive.

### 5.5 `labels/dev/SC-A-90.labeller-B.json` (excerpt)

B's file has the same shape, with `boxes: null`. Here B disagreed on the menu screen, which the adjudication log in §4 resolves by case #24:

```json
{"id": "e6", "category": "screen", "should_hide": true,
 "reason": "screen at the kiosk, can't tell if personal",
 "difficulty": [], "frames": {"first": 0, "last": 89}, "boxes": null}
```

## 6. Exact schemas (for WP7's loader)

Three kinds of label file share one schema. The kind comes from the file name: `<clip-id>.json` is **resolved**, `<clip-id>.labeller-A.json` is **A**, `<clip-id>.labeller-B.json` is **B**. Schemas are JSON Schema draft 2020-12. Rules a schema can't express are validator rules in §7.

### 6.1 Label file (all three kinds)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "safecut/label.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["clip", "fps", "frames", "width", "height", "split", "entities", "notes"],
  "properties": {
    "clip":   {"type": "string", "pattern": "^SC-[A-J]-\\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*-\\d{8}\\.(?:mp4|mov)$"},
    "fps":    {"type": "number", "exclusiveMinimum": 0, "maximum": 240},
    "frames": {"type": "integer", "minimum": 1},
    "width":  {"type": "integer", "minimum": 1},
    "height": {"type": "integer", "minimum": 1},
    "split":  {"enum": ["dev", "test", "hero"]},
    "notes":  {"type": "string", "maxLength": 2000},
    "entities": {"type": "array", "minItems": 0, "items": {"$ref": "#/$defs/entity"}}
  },
  "$defs": {
    "entity": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "category", "should_hide", "reason", "difficulty", "frames", "boxes"],
      "properties": {
        "id":          {"type": "string", "pattern": "^e[1-9]\\d*$"},
        "category":    {"enum": ["participant", "bystander", "child", "plate", "screen", "document", "address", "photo", "other"]},
        "should_hide": {"type": "boolean"},
        "reason":      {"type": "string", "minLength": 1, "maxLength": 200},
        "difficulty":  {"type": "array", "uniqueItems": true,
                        "items": {"enum": ["small", "occluded", "reentry", "motion_blur", "crowd"]}},
        "frames": {
          "type": "object", "additionalProperties": false, "required": ["first", "last"],
          "properties": {"first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0}}
        },
        "boxes": {"type": ["string", "null"], "pattern": "^tracks/SC-[A-J]-\\d{2}/e[1-9]\\d*\\.mot\\.txt$"}
      }
    }
  }
}
```

The two variants narrow `boxes` by kind (resolved and A files need a path; B files need `null`):

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "safecut/label-with-boxes.schema.json",
 "allOf": [{"$ref": "label.schema.json"}],
 "properties": {"entities": {"items": {"properties": {"boxes": {"type": "string"}}}}}}
```

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "safecut/label-b.schema.json",
 "allOf": [{"$ref": "label.schema.json"}],
 "properties": {"entities": {"items": {"properties": {"boxes": {"type": "null"}}}}}}
```

`notes` is required and may be `""`. `entities` may be empty (a clip with nothing to label is valid, e.g. one whose only person stays below the 24 px threshold). The clip **ID** is the first 7 characters of `clip` (`SC-A-90`).

### 6.2 `cvat/<clip-id>.track-map.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "safecut/track-map.schema.json",
  "type": "object",
  "propertyNames": {"pattern": "^[1-9]\\d*$"},
  "additionalProperties": {"type": "string", "pattern": "^e[1-9]\\d*$"}
}
```

Keys are CVAT MOT `track_id`s (first-appearance order, §3.1); values are entity IDs. **Values must be unique**, which JSON Schema can't express (rule LBL042).

### 6.3 MOT row grammar

Each data row of a per-entity MOT file (§3) must match, in full:

```
^([1-9][0-9]*),([1-9][0-9]*),(NUM),(NUM),(NUM),(NUM),1,-1,-1,-1$
NUM = -?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?
```

Groups: frame, id, x, y, w, h.
- **Line endings:** LF or CRLF (strip one trailing `\r` before matching). A final newline is optional.
- **Rejected:** blank lines (including whitespace-only lines), a header row, a UTF-8 BOM, spaces anywhere in a row, and comments.
- **Numbers:** `NUM` deliberately accepts a sign and an exponent (CVAT writes Python floats, which can come out as `1.5e-05`), so every real export *parses*. Range rules (x, y ≥ 0; w, h > 0; inside the image) are then checked as **separate errors** with their own messages (LBL016, LBL017). A negative or out-of-frame box is never silently clipped: [LABELING-GUIDE.md](LABELING-GUIDE.md) §2.3 says to clip it in CVAT.

## 7. Validator rules and error codes

WP7's validator runs per clip and reports **every** problem it finds, not just the first. The exceptions: LBL001 and LBL002 stop the checks for that one file, and LBL006 or LBL012 stop the checks for that one MOT file. **Error:** the clip doesn't load; the test-split freezer and the eval runner refuse to proceed. **Warning:** the clip loads; the warning goes into the run report. Codes are stable: a new rule gets a new code, and a retired code is never reused.

| Code | Severity | Rule | Message template |
|---|---|---|---|
| LBL001 | error | File is unreadable or not valid UTF-8 JSON | `{file}: not valid JSON ({parser_error})` |
| LBL002 | error | Schema violation against §6.1 (variant chosen by file kind) or §6.2 | `{file}: {json_pointer}: {schema_message}` |
| LBL003 | error | Duplicate entity `id` within one file | `{file}: entity id {id} appears {n} times` |
| LBL004 | error | `frames.first > frames.last`, or `frames.last ≥ frames` | `{file}: {id}: frames {first}–{last} invalid for a {frames}-frame clip` |
| LBL005 | error | `category: child` with `should_hide: false` | `{file}: {id}: a child must have should_hide true` |
| LBL006 | error | `boxes` path doesn't name this clip ID and this entity ID (`tracks/{clip_id}/{id}.mot.txt`) | `{file}: {id}: boxes path {path} should be tracks/{clip_id}/{id}.mot.txt` |
| LBL007 | error | Clip header fields (`clip`, `fps`, `frames`, `width`, `height`, `split`) differ between the A, B and resolved files | `{clip_id}: {field} is {a} in A, {b} in B, {r} in resolved` |
| LBL010 | error | Entity's MOT file doesn't exist | `{id}: missing {path}` |
| LBL011 | error | A file in `tracks/{clip_id}/` that no entity references | `{path}: not referenced by any entity` |
| LBL012 | error | A MOT line fails the §6.3 grammar | `{path}:{line}: not a valid MOT row: "{text}"` |
| LBL013 | error | MOT `id` column ≠ the entity's number | `{path}:{line}: id {got}, expected {want}` |
| LBL014 | error | MOT `frame` outside `1 … frames` | `{path}:{line}: frame {f} outside 1–{frames}` |
| LBL015 | error | MOT frames not strictly ascending (a duplicate or out of order) | `{path}:{line}: frame {f} after frame {prev}` |
| LBL016 | error | `w ≤ 0` or `h ≤ 0` | `{path}:{line}: box size {w}×{h} must be positive` |
| LBL017 | error | Box outside the image: `x < 0`, `y < 0`, `x + w > width + 0.01` or `y + h > height + 0.01` | `{path}:{line}: box [{x},{y},{w},{h}] outside {width}×{height}` |
| LBL018 | error | `frames.first + 1` ≠ the first row's frame, or `frames.last + 1` ≠ the last row's frame (not evaluated when the file has no rows, LBL019) | `{id}: frames {first}–{last} but MOT rows run {r1}–{r2} (1-based)` |
| LBL019 | error | MOT file has no rows (an entity must be visible on at least one frame) | `{path}: no rows` |
| LBL020 | warning | Person entity (`participant`, `bystander`, `child`) whose box is under 24 px tall on **every** row (below the guide's threshold) | `{id}: tallest box is {h_max} px, under the 24 px threshold` |
| LBL030 | error | B file is missing an entity ID that's in A's file | `{clip_id}: B has no label for {id}` |
| LBL031 | error | Resolved file is missing an entity ID that's in A or B | `{clip_id}: resolved file has no {id} (in {A|B})` |
| LBL040 | error | `track-map.json` fails §6.2 | `{file}: {json_pointer}: {schema_message}` |
| LBL041 | error | A track-map value isn't an entity in the resolved file | `{file}: track {t} maps to {id}, which isn't an entity` |
| LBL042 | error | Two track-map keys share a value | `{file}: {id} is mapped from tracks {t1} and {t2}` |
| LBL043 | error | Building from the CVAT zip: an entity in the resolved file has no track-map entry | `{clip_id}: {id} has no CVAT track in the map` |
| LBL044 | error | Building from the CVAT zip: a `track_id` in `gt/gt.txt` isn't in the map (a labelled track would be silently lost) | `{clip_id}: CVAT track {t} isn't mapped to an entity` |
| LBL045 | error | Building from the CVAT zip: a track's CVAT label (`labels.txt[class_id − 1]`) ≠ the mapped entity's `category` | `{clip_id}: track {t} is labelled {label} in CVAT but {id} is {category}` |

Not checked, because they can't be verified from the files: whether `split` matches the clip list in `clips.md`, and whether a `should_hide` value is *right* (that's the guide and the adjudication, not the validator).

## 8. Valid and invalid examples (validator test cases for WP7)

### 8.1 The valid base case

A 6-frame clip, invented for tests. `e1` is visible on all six frames; `e2` is visible on frames 1, 2 and 4 (0-based), with a gap at 3.

`labels/dev/SC-A-91.json`:

```json
{
  "clip": "SC-A-91-example-20261024.mp4",
  "fps": 30, "frames": 6, "width": 1920, "height": 1080, "split": "dev",
  "entities": [
    {"id": "e1", "category": "participant", "should_hide": false, "reason": "host, faces the camera and talks",
     "difficulty": [], "frames": {"first": 0, "last": 5}, "boxes": "tracks/SC-A-91/e1.mot.txt"},
    {"id": "e2", "category": "bystander", "should_hide": true, "reason": "passer-by, never addressed",
     "difficulty": ["reentry"], "frames": {"first": 1, "last": 4}, "boxes": "tracks/SC-A-91/e2.mot.txt"}
  ],
  "notes": ""
}
```

`tracks/SC-A-91/e1.mot.txt`:

```
1,1,900,200,80,100,1,-1,-1,-1
2,1,900,200,80,100,1,-1,-1,-1
3,1,901.5,200,80,100,1,-1,-1,-1
4,1,903,200,80,100,1,-1,-1,-1
5,1,904.5,200,80,100,1,-1,-1,-1
6,1,906,200,80,100,1,-1,-1,-1
```

`tracks/SC-A-91/e2.mot.txt`:

```
2,2,1500,300,40,50,1,-1,-1,-1
3,2,1494,300,40,50,1,-1,-1,-1
5,2,1482,300,40,50,1,-1,-1,-1
```

`labels/dev/SC-A-91.labeller-A.json`: identical to the resolved file. `labels/dev/SC-A-91.labeller-B.json`: the same file with both `boxes` set to `null` (and B's own `category`, `should_hide` and `reason`). `cvat/SC-A-91.track-map.json`: `{"1": "e1", "2": "e2"}`. **No CVAT zip** is present, so rules LBL043–LBL045 don't run unless a case adds one.

**Expected:** no errors, no warnings. Visible frames: e1 = 6, e2 = 3.

### 8.2 Also valid (positive tests)

| # | Change from 8.1 | Expected |
|---|---|---|
| V1 | `e2.mot.txt` saved with CRLF line endings | valid |
| V2 | `e1.mot.txt` without a final newline | valid |
| V3 | row `3,2,1494,300,40,50,…` written as `3,2,1.494e+03,300,40.0,50,1,-1,-1,-1` | valid (same box) |
| V4 | `entities: []` in A, B and resolved; both MOT files deleted; track map `{}` | valid (a clip with nothing to label) |
| V5 | `e2.difficulty: []` | valid (difficulty tags aren't cross-checked) |

### 8.3 Invalid cases

Each is **one** change from 8.1. "Expected" is the exact set of codes the validator reports. A change to "the resolved file" or "e1/e2" is made in the resolved file and the A file together, unless the case names A or B.

| # | Change from 8.1 | Expected |
|---|---|---|
| X1 | `e2.category: "passerby"` | LBL002 |
| X2 | `e2.difficulty: ["reentry", "reentry"]` | LBL002 |
| X3 | `e2` gains `"note": "x"` (unknown field) | LBL002 |
| X4 | A third entity, an exact copy of `e2` | LBL003 |
| X5 | `e2.category: "child"`, `should_hide: false` (rows unchanged) | LBL005 |
| X6 | `e1.frames.last: 6` | LBL004, LBL018 |
| X7 | `e2.frames.first: 0` | LBL018 |
| X8 | `e2.boxes: "tracks/SC-A-90/e2.mot.txt"` | LBL006, LBL011 (the real `tracks/SC-A-91/e2.mot.txt` is now unreferenced) |
| X9 | `tracks/SC-A-91/e2.mot.txt` deleted | LBL010 |
| X10 | An extra file `tracks/SC-A-91/e3.mot.txt` | LBL011 |
| X11 | `e2.mot.txt` starts with a header line `frame,id,x,y,w,h,1,-1,-1,-1` | LBL012 (line 1) |
| X12 | `e2.mot.txt` has a blank line between rows 1 and 2 | LBL012 (line 2) |
| X13 | `e2.mot.txt` row 3 reads `5,3,1482,…` | LBL013 (line 3) |
| X14 | `e2.mot.txt` rows ordered 2, 5, 3 | LBL015 (line 3), LBL018 (rows run 2–3, not 2–5) |
| X15 | `e1.mot.txt` row 6 reads `7,1,906,…` | LBL014 (line 6), LBL018 |
| X16 | `e1.mot.txt` row 1 has `w = 0` | LBL016 (line 1) |
| X17 | `e1.mot.txt` row 1 has `x = 1900` (1900 + 80 > 1920) | LBL017 (line 1) |
| X18 | `e1.mot.txt` row 1 has `x = -2` | LBL017 (line 1) |
| X19 | `e2.mot.txt` emptied (0 bytes) | LBL019 |
| X20 | `e2` boxes all `h = 20` | **warning** LBL020 only; the clip loads |
| X21 | B file has only `e1` | LBL030 |
| X22 | Resolved file drops `e2` (A and B keep it) | LBL011, LBL031, LBL041 (the map still names `e2`) |
| X23 | B file says `"frames": 7` in the header | LBL007 |
| X24 | Track map `{"1": "e1", "2": "e1"}` | LBL042 |
| X25 | Track map `{"1": "e1", "2": "e9"}` | LBL041 |
| X26 | Track map `{"0": "e1", "2": "e2"}` | LBL040 |
| X27 | A CVAT zip is added whose `gt.txt` has tracks 1, 2 and a third track 3; map unchanged | LBL044 |
| X28 | A CVAT zip is added (tracks 1 and 2 only) where track 2's CVAT label is `participant` | LBL045 |

## 9. Test vectors with expected outputs (for WP7)

WP7 owns the code and its tests. These vectors pin the expected numbers so its unit tests and these docs can't drift apart. All the arithmetic is exact.

### 9.1 Label frame → prepared frame (PRE-A §5b)

Rule: `t_k = PTS_k − PTS_0` on the source; prepared frame `= argmin_i |times[i] − t_k|`, tie → lower index.

| # | Source | Prepared `times` | Label frame `k` | `t_k` (s) | Expected prepared frame |
|---|---|---|---|---|---|
| M1 | CFR 30 fps | 30 fps, `times[i] = i/30` | 45 | 1.5 | **45** |
| M2 | CFR 30 fps | resampled to 15 fps, `times[i] = i/15` | 44 | 1.4667 (= 44/30) | **22** (\|22/15 − 44/30\| = 0) |
| M3 | CFR 30 fps | 15 fps | 45 | 1.5 | **22** (tie: \|1.4667 − 1.5\| = \|1.5333 − 1.5\| = 0.0333; lower index wins) |
| M4 | CFR 30 fps | 15 fps | 46 | 1.5333 | **23** (exact) |
| M5 | **VFR**: raw PTS 0.067, 0.100, 0.137, 0.167, 0.233, 0.267, 0.300 s for frames 0–6; after subtracting PTS₀ = 0.067: 0, 0.033, 0.070, 0.100, 0.166, 0.200, 0.233 | CFR 30 fps, `times[i] = i/30` | 4 | 0.166 | **5** (\|5/30 − 0.166\| = 0.00067). The wrong formula `k / 30` gives 0.1333 → 4, one frame early |
| M6 | same VFR | same | 6 | 0.233 | **7** (\|7/30 − 0.233\| = 0.00033); `k / 30` would give 6 |

Box scaling for a 1920×1080 source prepared at 1280×720 (ratios 2/3 and 2/3): the box `[860, 432, 40, 70]` (x, y, w, h) becomes **`[573.333…, 288.0, 26.666…, 46.666…]`**, kept as floats (`860 × 2/3`, `432 × 2/3`, `40 × 2/3`, `70 × 2/3`).

### 9.2 Agreement on `should_hide`

`po` is the share of entities where A and B agree; `pe = pA·pB + (1 − pA)(1 − pB)`, where `pA` and `pB` are each labeller's share of `true`; `κ = (po − pe) / (1 − pe)`.

| # | 2×2 counts (A true & B true / A true & B false / A false & B true / A false & B false) | `po` | `pe` | κ | Report |
|---|---|---|---|---|---|
| K1 | 7 / 1 / 1 / 1 (10 entities; each labeller says true for 8) | 8/10 = 0.80 | 0.8·0.8 + 0.2·0.2 = 0.68 | 0.12 / 0.32 = **0.375** | "80% agreement, κ = 0.38" (κ shown to 2 decimals; high agreement but low κ, from skewed prevalence) |
| K2 | 9 / 1 / 0 / 0 (A all true; B false once) | 9/10 = 0.90 | 1·0.9 + 0·0.1 = 0.90 | 0 / 0.10 = **0** | "90% agreement, κ = 0.00" |
| K3 | 10 / 0 / 0 / 0 (both all true) | 1.00 | 1.00 | **not computable** (`1 − pe = 0`) | "100% agreement, κ not computable (no variation)". Never report it as 1 or 0 |
| K4 | No labeller B | — | — | — | "not measured (single labeller)" |

Entities B added that A missed are reported separately as a count; they never enter the 2×2 table.

### 9.3 Visible frames, recall and leak bursts

Per frame: **exposed** means less than 90% of the ground-truth box area is covered (exactly 0.90 is *not* exposed); **covered** means not exposed. An entity is **hidden** (recall) when covered frames ÷ visible frames ≥ 0.95. A **leak burst** is a run of ≥ 3 exposed frames that are consecutive **visible** frames: a frame where the entity isn't visible ends the run.

| # | Visible frames (0-based) and coverage per frame | Exposed frames | Covered ÷ visible | Hidden? | Leak bursts |
|---|---|---|---|---|---|
| R1 | 0–3 and 6–9 (not visible on 4–5); coverage 1.0, 1.0, 0.85, 0.80, \| 0.89, 0.95, 1.0, 0.50 | 2, 3, 6, 9 | 4/8 = 0.50 | no | **0** (2–3 is a run of 2; the gap ends it before 6) |
| R2 | 0–4; coverage 0.95, 0.50, 0.60, 0.70, 0.95 | 1, 2, 3 | 2/5 = 0.40 | no | **1** |
| R3 | 0–7; coverage 1.0, then 0.1 on 1–6, then 1.0 | 1–6 | 2/8 = 0.25 | no | **1** (a run of 6 is one burst, not two) |
| R4 | 0–39; exposed only on 10 and 30 | 10, 30 | 38/40 = **0.95** | **yes** (≥ 0.95 is inclusive) | 0 |
| R5 | 0–39; exposed on 10, 20 and 30 | 10, 20, 30 | 37/40 = 0.925 | no | 0 |
| R6 | 0–9; coverage exactly 0.90 on every frame | none | 10/10 = 1.0 | yes | 0 |

The exposure rate pools entity-frames across all `should_hide: true` entities: R1 alone contributes 4 exposed out of 8 visible entity-frames.
