# Label format: the label JSON and the MOT box files

Status: **v1, 2026-10-24 (PRE-B).** The schema is [EVAL.md](../EVAL.md) §1, unchanged; this file pins down what each field means, the file layout, the MOT conventions and the conversion from CVAT. WP7 implements the loader and validator from it (`eval/`). What to put in the fields: [LABELING-GUIDE.md](LABELING-GUIDE.md). How to produce the boxes: [CVAT-SETUP.md](CVAT-SETUP.md).

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

**Coordinates and frames are in the source clip** (e.g. 1920×1080 at 30 fps). The pipeline works on the prepared clip (≤1280 px, its own frame list, [ARCHITECTURE.md](../ARCHITECTURE.md) §3.1). WP7 maps labels onto it: boxes scale by `prepared.width / source.width`, and frames map through `job.json`'s `times`. **One meaning, used by every PRE-B doc:** `times[i]` is the time in seconds of prepared frame `i`, measured from the first decoded source frame (the source's start timestamp subtracted, so `times[0] = 0`). The prepared clip is encoded with those same timestamps, so the same list maps both ways: label frame → source time → prepared frame for WP7, and the player's `mediaTime` → prepared frame for the review overlay ([UI-SPEC.md](../UI-SPEC.md) §3.6). Label frame `k` is at source time `k / fps` from that same first frame. (Request to WP1.) Labellers never resample anything.

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

1. Map each CVAT `track_id` to an entity ID (check the first row of each track against the CVAT UI; see the first-clip checks in [CVAT-SETUP.md](CVAT-SETUP.md) §7).
2. For each track: keep `frame_id`, `x`, `y`, `w`, `h`; set `id` to the entity number; set the last four columns to `1,-1,-1,-1`.
3. Confirm the frames are 1-based (the first-clip check). If the export turns out to be 0-based, add 1.

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
