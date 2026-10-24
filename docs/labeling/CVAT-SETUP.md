# CVAT setup for Safe Cut labelling

Status: **v1, 2026-10-24 (PRE-B).** CVAT facts below were read from CVAT's own docs in its repo (`cvat-ai/cvat`, `develop` at commit `a415be6`, 2026-10-23): `site/content/en/docs/administration/community/basics/installation.md`, `.../dataset_management/formats/format-mot.md`, `.../annotation/manual-annotation/modes/track-mode-basics.md`, `.../annotation/annotation-editor/navbar.md`, `.../workspace/tasks-page.md`. Latest release tag on 2026-10-24: **v2.80.0**. Anything marked *(verify)* is our inference, to check on the first clip.

Why CVAT: free, open source, video track annotation with interpolation, MOT export ([EVAL.md](../EVAL.md) §1). How to label: [LABELING-GUIDE.md](LABELING-GUIDE.md). What to export: [LABEL-FORMAT.md](LABEL-FORMAT.md).

## 1. Privacy rules (read first)

1. **Self-hosted only.** Run CVAT on our own build box. **Never upload real-public clips to app.cvat.ai or any hosted labelling service**, and never to this repo or the cloud sandbox ([AGENTS.md](../../AGENTS.md) rules 4–5).
2. **Localhost only.** Don't set `CVAT_HOST` to a public IP and don't open port 8080 on a firewall. If the build box is remote, reach it through an SSH tunnel (forward local port 8080 to the box's `localhost:8080`).
3. **Disk.** CVAT keeps uploaded videos and exports in Docker volumes on the build box. Treat the box as holding the private set: full-disk encryption on, no shared accounts, delete the volumes after judging (target 2026-12-01, [SHOTLIST.md](../SHOTLIST.md)).
4. **Exports** go to the owner's private storage (`~/SafeCutEval/labels/` on the Mac, plus the private bucket for `dev`/`hero` only). Test-split labels never go to the bucket the cloud agents read.

## 2. The build box

Not the Intel dev Mac ([EVAL.md](../EVAL.md) §1). Any Linux x86_64 machine with Docker works; CVAT's install guide covers Ubuntu 22.04/20.04 first, plus Windows (WSL2) and macOS. Google Chrome is the only browser CVAT supports. **Open question for the owner:** which machine this is (see the PR).

## 3. Install (from CVAT's guide)

These are the steps from CVAT's installation page, in order. Type them on the build box; nothing here belongs in this repo.

1. Install Docker Engine and the Docker Compose plugin (CVAT's page links Docker's official Ubuntu instructions).
2. Clone CVAT and pin the release you use, so both labellers and any re-export see the same tool:
   ```
   git clone https://github.com/cvat-ai/cvat
   cd cvat
   git checkout v2.80.0
   ```
   Record the tag you actually used in the clip list ([SCHEDULE.md](SCHEDULE.md)).
3. Start it (the first run downloads the images and takes a while):
   ```
   docker compose up -d
   ```
4. Create the admin account:
   ```
   docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
   ```
5. Open Chrome at `http://localhost:8080` and log in.
6. Create one non-admin user per labeller (A and B) from the admin account. Labeller B doesn't need to draw boxes, but may use CVAT to scrub frames.

To stop: `docker compose down` in the `cvat` folder (the data volumes stay). Don't use `down -v` until the labels are exported and backed up.

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

## 7. Export

For each finished task, export twice (Task → Actions → Export task dataset), with "Save images" **off**:

1. **MOT 1.1**: a zip with `gt/gt.txt` and `gt/labels.txt`. CVAT documents the `gt.txt` columns as `frame_id, track_id, x, y, w, h, "not ignored", class_id, visibility`. This is converted to our per-entity MOT files ([LABEL-FORMAT.md](LABEL-FORMAT.md) §3).
2. **CVAT for video 1.1**: an XML backup that keeps the attributes and keyframes, so the task can be re-imported.

Also use **Backup task** before deleting anything from CVAT.

**First-clip checks (verify, then record the answers here):**
- Frame numbering. CVAT's UI counts frames from 0; MOT files conventionally count from 1. Draw a box that starts on UI frame 0 and check that its first row in `gt.txt` says frame `1`.
- Track IDs. Check that each `track_id` in `gt.txt` maps to the entity you think it does (compare the first row's frame and box with the UI).
- Outside frames. Check that frames marked Outside are absent from `gt.txt` (they must be, or "visible frames" are wrong).
- Coordinates. Check that boxes are in source pixels (1920×1080 for our footage) and note whether they're integers or decimals.
