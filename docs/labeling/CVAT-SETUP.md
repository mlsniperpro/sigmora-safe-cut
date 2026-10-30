# CVAT setup for Safe Cut labelling

Status: **v1, 2026-10-24 (PRE-B).** CVAT facts below were read from CVAT's own docs in its repo (`cvat-ai/cvat`, `develop` at commit `a415be6`, 2026-10-23): `site/content/en/docs/administration/community/basics/installation.md`, `.../dataset_management/formats/format-mot.md`, `.../annotation/manual-annotation/modes/track-mode-basics.md`, `.../annotation/annotation-editor/navbar.md`, `.../workspace/tasks-page.md`. Latest release tag on 2026-10-24: **v2.80.0**. How the MOT export behaves (§7) was read from the **v2.80.0 source code** (tag commit `bb0a873`, 2026-10-21) and the Datumaro commit that release pins, with file and line numbers.

Why CVAT: free, open source, video track annotation with interpolation, MOT export ([EVAL.md](../EVAL.md) §1). How to label: [LABELING-GUIDE.md](LABELING-GUIDE.md). What to export: [LABEL-FORMAT.md](LABEL-FORMAT.md).

## 1. Privacy rules (read first)

1. **Self-hosted only.** Run CVAT on our own build box. **Never upload real-public clips to app.cvat.ai or any hosted labelling service**, and never to this repo or the cloud sandbox ([AGENTS.md](../../AGENTS.md) rules 4–5).
2. **Localhost only.** Don't set `CVAT_HOST` to a public IP and don't open port 8080 on a firewall. If the build box is remote, the owner may reach it through an SSH tunnel (forward local port 8080 to the box's `localhost:8080`) for **hero and dev clips only**. `test` (real-public) clips are labelled **in person at the box**, by everyone, on the first-choice machine and the fallback alike (§2): a tunnel or screen share streams their frames to another machine.
3. **Disk.** CVAT keeps uploaded videos and exports in Docker volumes on the build box. Treat the box as holding the private set: full-disk encryption on, no shared accounts, delete the volumes after judging (target 2026-12-01, [SHOTLIST.md](../SHOTLIST.md)).
4. **Exports** go to the owner's private storage (`~/SafeCutEval/labels/` on the CVAT box (the owner's; for `test`, also the eval box, PRE-A `docs/BLOCKED-PRE-A.md`), plus the private bucket for `dev`/`hero` only). Test-split labels never go to the bucket the cloud agents read.

## 2. The build box (decision)

**Decision: run CVAT on a machine the owner physically controls, never a cloud VM.** Real-public clips may live only on the owner's machines, never in the private bucket ([LABELING-GUIDE.md](LABELING-GUIDE.md) §6, [AGENTS.md](../../AGENTS.md) rule 5). [SHOTLIST.md](../SHOTLIST.md) line 15 still says real-public clips "live in `~/SafeCutEval/` plus a private bucket"; that is superseded here, and changing it is a request to SHOTLIST's owner (in the PRE-B PR): "they live only in `~/SafeCutEval/` on the owner's machines, never in a bucket". A rented VM would put them on a third-party host too, and that's the step that's hard to undo.
- **First choice:** any Linux x86_64 or Windows (WSL2) machine with Docker. CVAT's install guide covers Ubuntu 22.04/20.04 first, plus Windows (WSL2) and macOS.
- **Fallback if there's no such machine:** another local machine held by a trusted labeller (e.g. labeller B's), for **consented clips only** (hero and dev), moved on an encrypted drive and deleted from it after export. Real-public (`test`) clips never leave the owner's custody: if the owner has no machine of their own that runs CVAT, the borrowed machine comes into the owner's physical custody for the test clips (at the owner's place, used only by the labellers there, and wiped after export), so it counts as the owner's machine for that time. On any machine, labeller B labels test clips **in person** at the box; never over an SSH tunnel or screen share, which would stream real-public frames to B's own browser ([LABELING-GUIDE.md](LABELING-GUIDE.md) §6). **Not the Intel dev Mac:** [EVAL.md](../EVAL.md) §1 and the PRE-B brief both exclude it.

CVAT supports only Google Chrome. Setting up the machine is the owner's hands-on step, listed in [`BLOCKED-PRE-B.md`](../BLOCKED-PRE-B.md).

## 3. Install (from CVAT's guide)

Follow CVAT's installation page (`site/content/en/docs/administration/community/basics/installation.md` in `cvat-ai/cvat`, the section for your OS). In summary, for the owner to carry out on the build box (nothing here belongs in this repo):

1. Install Docker Engine and the Docker Compose plugin (CVAT's page links Docker's official instructions).
2. Clone `https://github.com/cvat-ai/cvat` and check out the release tag **v2.80.0** (the latest on 2026-10-24), so both labellers and any re-export use the same version. Record the tag in the clip list ([SCHEDULE.md](SCHEDULE.md)).
3. Start the containers with Docker Compose from the `cvat` folder, as the guide shows (the first run downloads the images and takes a while).
4. Create the admin account with Django's `createsuperuser` inside the `cvat_server` container, as the guide shows.
5. Open Chrome at `http://localhost:8080` and log in.
6. Create one non-admin user per labeller (A and B) from the admin account. Labeller B doesn't need to draw boxes, but may use CVAT to scrub frames.

To stop CVAT, bring the Compose stack down from the `cvat` folder; the data volumes stay. **Don't remove the volumes** (Compose's `-v` option) until every label is exported and backed up.

## 4. Project and labels

Create **one project per split**: `safecut-dev`, `safecut-test`, `safecut-hero`. Keeping splits in separate projects stops a test clip being exported with the dev set by accident.

Add these labels to each project (all **Rectangle** type). One CVAT label per `category` in [LABELING-GUIDE.md](LABELING-GUIDE.md) §2.1:

| CVAT label | Attribute | Type | Values |
|---|---|---|---|
| `participant`, `bystander`, `child`, `plate`, `screen`, `document`, `address`, `photo`, `other` | `should_hide` | checkbox | default: on (unchecked only for `should_hide: false`) |
| (same) | `small`, `occluded`, `reentry`, `motion_blur`, `crowd` | checkbox each | default: off |

Build these with the label constructor in the project's UI. The attributes don't survive the MOT export (CVAT's MOT export keeps only `visibility` and `ignored`), so they are there for the **CVAT for video 1.1** backup export and for the labeller's own bookkeeping; the label JSON is the source of truth ([LABEL-FORMAT.md](LABEL-FORMAT.md)).

## 5. A task per clip

Create a task inside the right project for each clip:

| Setting (Advanced configuration) | Value | Why |
|---|---|---|
| Name | the clip ID, e.g. `SC-A-01` | matches the label file name |
| Files | "My computer", the source MP4 | local upload only |
| Image quality | **95** or more | CVAT recommends raising it when objects are small; far faces are |
| Frame step | **1** | every frame must be labelled (interpolation fills them) |
| Start frame / stop frame | leave empty | labels index the whole source clip |
| Segment size | leave empty (one job per clip) | one track per entity across the clip |
| Use cache | on | faster task creation |
| Prefer zip chunks | off | CVAT recommends off for video |

## 6. The interpolation workflow

Per CVAT's track-mode docs:

1. **Settings → Player Step = 15** (default 10). Then `V` jumps forward 15 frames, `C` back 15; `F`/`D` step one frame. At 30 fps, 15 frames = 2 keyframes per second ([EVAL.md](../EVAL.md) §1).
2. Go to the entity's first visible frame. Pick **Rectangle**, the label, then **Track** (not Shape), and draw the box per the conventions in [LABELING-GUIDE.md](LABELING-GUIDE.md) §2.3. Set the attributes.
3. Press `V`, fix the box. Each edit creates a keyframe (`K` toggles one); frames in between are interpolated.
4. Add extra keyframes wherever the motion turns or speeds up.
5. When the entity leaves the frame or is fully hidden, press `O` (**Outside**) on that frame. When it comes back, go to its first visible frame, turn Outside off and redraw. If you drew it as two separate tracks, select both and **Merge** (`M`) so the entity is one track.
6. Play the track back at normal speed, then scrub fast-motion stretches frame by frame (`F`/`D`); fix any frame where the box slides off the head.
7. Save often (`Ctrl+S`).

Use one CVAT track per entity. If the same person is in a reflection, that reflection is its own entity and its own track (case 4/5 in the guide).

**Optional speed-up: OpenCV TrackerMIL** (built into CVAT, not a Meta model; CVAT docs `annotation/manual-annotation/utilities/opencv-tools.md`). Draw the first box, open the **OpenCV** menu, pick TrackerMIL, set the target frame, and run. CVAT's docs warn that it runs on **all rectangles that pass the current filter**, so filter to the one object first, or it moves other tracks you've already finished. Then check and fix it at the usual 15-frame keyframe spacing. **Never use the "Segment Anything 2 Tracker"** for ground truth ([LABELING-GUIDE.md](LABELING-GUIDE.md) §2.4).

## 7. Export

For each finished task, export twice (Task → Actions → Export task dataset), with "Save images" **off**:

1. **MOT 1.1**: a zip with `gt/gt.txt` and `gt/labels.txt`. CVAT documents the `gt.txt` columns as `frame_id, track_id, x, y, w, h, "not ignored", class_id, visibility`. This is converted to our per-entity MOT files ([LABEL-FORMAT.md](LABEL-FORMAT.md) §3).
2. **CVAT for video 1.1**: an XML backup that keeps the attributes and keyframes, so the task can be re-imported.

Also use **Backup task** before deleting anything from CVAT.

### 7.1 What the MOT 1.1 export writes (from the v2.80.0 source)

CVAT's MOT exporter (`https://github.com/cvat-ai/cvat/blob/v2.80.0/cvat/apps/dataset_manager/formats/mot.py`, lines 102–109) builds a dataset with `GetCVATDataExtractor` and hands it to Datumaro's `mot_seq_gt` writer. CVAT v2.80.0 pins Datumaro at commit `335fc3e` (`cvat/requirements/base.txt`, line 54); the writer is `MotSeqGtExporter` in [`datumaro/plugins/data_formats/mot.py`](https://github.com/cvat-ai/datumaro/blob/335fc3e55fe699b9401091f6af11f10c3b0e08cb/src/datumaro/plugins/data_formats/mot.py), lines 258–324.

| Question | Answer | Source |
|---|---|---|
| **Frame numbering** | **1-based, numbered by position in the export.** For video tasks CVAT names each item `frame_NNNNNN` (`bindings.py` line 420) and uses that as the item ID (lines 2051–2052). Datumaro writes `frame_id = cast(item.id, int, 1 + idx)` (Datumaro `mot.py` line 280); `"frame_000000"` isn't an integer, so `cast` returns the default `1 + idx` (`datumaro/util/__init__.py` lines 28–34), where `idx` is the item's position in the export. Every included frame becomes an item, in order, **including frames with no boxes**: the extractor iterates `group_by_frame(include_empty=True)` (`bindings.py` line 2101), so the skip for empty frames at lines 654–657 doesn't apply, and the loop at line 641 yields frames in sorted order. So **MOT frame = UI frame + 1** as long as no frame is deleted. Deleted and excluded frames are removed from the export (`get_included_frames`, `bindings.py` lines 666–674), which would shift every later frame number down. Hence the rules below | `https://github.com/cvat-ai/cvat/blob/v2.80.0/cvat/apps/dataset_manager/bindings.py`; Datumaro `mot.py` |
| **Track IDs** | **Renumbered: 1, 2, 3, … in order of first appearance.** CVAT gives each track its position in its own track list, not the ID shown in the UI (`annotation.py` lines 659 and 721). This holds because `use_server_track_ids` is `False`: `CommonData.__init__` defaults it to `False` (`bindings.py` lines 338, 345, 357) and passes it on at line 600, and neither the MOT exporter nor the task export code sets it. Datumaro then maps those to `1, 2, 3, …` in the order it first meets them while writing frames in order (Datumaro `mot.py` lines 276–289). So `track_id = n` is the n-th track to appear in the clip. Two tracks that start on the same frame are told apart by their box | `https://github.com/cvat-ai/cvat/blob/v2.80.0/cvat/apps/dataset_manager/annotation.py`; Datumaro `mot.py` |
| **Outside frames** | **Left out.** The export asks for shapes with `include_outside=False` (`bindings.py` lines 596–599, passed on in `annotation.py` line 676) and also skips any tracked shape whose `outside` flag is set (`bindings.py` lines 622–624). A frame with no row is a frame where the entity isn't visible, which is what our metrics need | `https://github.com/cvat-ai/cvat/blob/v2.80.0/cvat/apps/dataset_manager/bindings.py`, `annotation.py` |
| Coordinates | Written as Datumaro's `anno.x, anno.y, anno.w, anno.h` (Datumaro `mot.py` lines 295–298): **source pixels, as decimals**, since interpolated boxes aren't whole numbers. Column 7 is `1` unless the box's `ignored` attribute is set (line 299); column 9 is `1 − occluded` unless a `visibility` attribute is set (lines 301–305) | Datumaro `mot.py` |

**Rules that follow** (they keep "MOT frame = UI frame + 1" true):
- **Never delete a frame** in a CVAT task (Delete frame in the player), and keep **Frame step = 1**, with start/stop frame left empty (§5). Any of these renumbers the export.
- Write `track-map.json` from **first-appearance order**: sort the clip's entities by their first visible frame and number them 1, 2, 3, …; break ties on the same frame by comparing the first row's box with the UI ([LABEL-FORMAT.md](LABEL-FORMAT.md) §3.1).
- Don't set the `ignored` attribute on any box. Our MOT files rewrite columns 7–10 to `1,-1,-1,-1` anyway.
