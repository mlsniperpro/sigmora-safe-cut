# SA-Co/VEval: SmartGlasses split

Read 2026-10-24. **Sources:** Meta's [`facebookresearch/sam3`](https://github.com/facebookresearch/sam3) README and [`scripts/eval/veval/README.md`](https://github.com/facebookresearch/sam3/blob/main/scripts/eval/veval/README.md) (via GitHub fetch), plus web-search summaries of the [Mintlify sam3 docs](https://mintlify.wiki/facebookresearch/sam3/evaluation/saco-veval) and [Roboflow Universe sa-co-veval](https://universe.roboflow.com/sa-co-veval). The HF dataset page [`facebook/SACo-VEval`](https://huggingface.co/datasets/facebook/SACo-VEval) **couldn't be opened** (network policy, see `docs/BLOCKED-PRE-A.md`).

## Where to get it
- **Annotations:** six JSON files on Hugging Face, `facebook/SACo-VEval` (test + val per domain).
- **SmartGlasses media:** `media/saco_sg.tar.gz` in the same HF repo; extract it under `data/media` → `saco_sg/JPEGImages_6fps/`.
- **Shortcut:** Roboflow Universe hosts preprocessed SmartGlasses frames + GT for both val and test.
- Tooling: `uv pip install -e ".[veval]"` in a uv venv in the sam3 repo (the repo's README says `pip install`; AGENTS rule 11 means we use uv), then the offline evaluator `saco_veval_eval.py` (modes `one` and `all`).
- **The HF dataset is gated, with manual approval** [OWNER-2026-10-24: read on Hugging Face during the PR #1 audit]. Access is requested on the dataset page with a Hugging Face account, and a person at Meta approves it, so the wait is open-ended. **Request it now** (owner step in `docs/BLOCKED-PRE-A.md`), then store a read-scoped token as the environment secret `HF_TOKEN`. *Meanwhile:* WP7 builds the loader against the documented format below, using a tiny synthetic fixture. If access hasn't arrived by WP7's run, the Roboflow mirror is the fallback; first check that its licence for the SmartGlasses split reads CC BY 4.0 (Roboflow mislabels SA-V, see below).
- Layout:
```
data/annotation/saco_veval_smartglasses_{test,val}.json
data/media/saco_sg/JPEGImages_6fps/<video>/<frame>.jpg
```

## Licence
| Domain | Licence | Source |
|---|---|---|
| **SmartGlasses** | **CC-BY-4.0** | sam3 `veval/README.md` (GitHub, read directly) and the Mintlify docs |
| SA-V | CC-BY-NC 4.0 | sam3 `veval/README.md`. ⚠️ Roboflow's SA-V test page shows "CC BY 4.0", which conflicts |
| YT-Temporal-1B | CC-BY-NC 4.0 | sam3 `veval/README.md` |

**Confirmed: SmartGlasses = CC BY 4.0** per Meta's own repo. Use only that split (EVAL.md §2: no NC splits in anything published). Attribution goes in the README and in `fixtures/README.md` for any frames used as fixtures (WP0 probe fallback).

## Size
**Not stated** in either README. WP7 records the video count, the frame count and the archive size on download. Frames are at **6 fps** (the YT1B and SG folders are `JPEGImages_6fps`; SA-V is 24 fps).

## Annotation format (YTVIS-like)
Top-level keys: `info`, `videos`, `annotations`, `categories`, `video_np_pairs`.
- `videos[]`: `id`, `video_name`, `file_names` (frame JPEG paths), `height`, `width`, `length`.
- `annotations[]` (positive masklets): `id`, `video_id`, `category_id`, `noun_phrase`, `segmentations` (**per-frame RLE**, null where absent), `bboxes`, `areas`, `iscrowd`, `height`, `width`.
- `categories[]`: `id`, `name`. The noun-phrase vocabulary is shared across domains.
- `video_np_pairs[]`: `id`, `video_id`, `category_id`, `noun_phrase`, `num_masklets`. **0 = a negative pair** (the phrase is absent), which is useful for false-positive checks.
- Every instance matching the phrase is annotated exhaustively.

## Loader spec for WP7 (read from Meta's evaluator code, `facebookresearch/sam3` @ `f1647e8`, 2026-10-23)
Files read: `sam3/eval/saco_veval_evaluators.py`, `sam3/eval/conversion_util.py`, `sam3/eval/ytvis_coco_wrapper.py`.
- **`annotations[].bboxes`** is a list with **one entry per frame**, aligned with `videos[].file_names`. Each entry is COCO-style **`[x, y, w, h]`** in pixels, or **`null` when the object isn't visible** on that frame (`conversion_util.py` copies it straight into a COCO `bbox` field; `ytvis_coco_wrapper.py` replaces `null` with `[0,0,0,0]` for its own use). Convert to Safe Cut's half-open boxes as `[x, y, x + w, y + h]` in **source** pixels, then **scale into prepared-clip pixels**, which is the frame space every Safe Cut file uses (ARCHITECTURE §3): multiply x by `job.width / videos[].width` and y by `job.height / videos[].height`. Prepare caps the long edge at 1280 px, so e.g. 1408 × 1408 frames become 1280 × 1280, a factor of 1280/1408. If the H.264 encode pads odd sizes, use the prepared `job.width`/`job.height` (from `job.json`, read with the bundled ffmpeg, API-NOTES §5b). Keep floats until the metric, and don't round.
- **`annotations[].segmentations`** is per frame too: **uncompressed RLE** (`counts` is a list of integers), or `null`. Meta's evaluator compresses it with `pycocotools.mask.frPyObjects(rle, h, w)` before use (`_compress_rle`), and WP7 does the same if it needs masks. Boxes are enough for EVAL.md's coverage metric.
- **`areas`** is per frame; `0`/`null` when absent.
- **Frames:** `videos[].file_names` are the JPEGs in `saco_sg/JPEGImages_6fps/`, so the frame rate is **6 fps**. Build each test video by concatenating `file_names` **in list order** (ffmpeg concat demuxer, `duration 1/6` per entry), encoded H.264 constant 6 fps. Then `job.fps = 6` and `sam_fps_eff = min(8, 6) = 6` (API-NOTES §5b): the proxy is the clip itself, and frame `k` of the video = `file_names[k]`. Check `len(file_names) == videos[].length` and the frame count read back with the bundled ffmpeg (`framemd5`, API-NOTES §5b; imageio-ffmpeg has no ffprobe); a mismatch fails the loader.
- **Which phrases:** pick categories whose `name` is a privacy concept (`face`, `person`, `license plate`, `screen`, …) from `categories`. The list isn't visible until access is granted, so WP7 prints the matching names on first download and commits that list (names only, no data) with the run.
- **Negative pairs** (`video_np_pairs[].num_masklets == 0`): the phrase isn't present. Use them to count SAM false positives (redactions with no ground truth) as a secondary number; over-blur by role doesn't apply.
- **Attribution** (CC BY 4.0): "SA-Co/VEval SmartGlasses, Meta AI, CC BY 4.0", plus the dataset URL, in the README and in each `eval/results/<run-id>/` that uses it.

## How it maps to EVAL.md (tracking and leak guard only)
There are **no participant/bystander labels** and no `should_hide`, so it can't measure recall-by-role, over-blur, or anything Muse Spark decides. It can measure the **SAM + leak-guard** half:

| EVAL.md metric | SA-Co/VEval adaptation |
|---|---|
| **Exposure rate** | Treat every GT masklet for a privacy phrase (`face`, `person`, `license plate`, `screen`, if present in `categories`; WP7 lists which are) as `should_hide`. Exposure = share of GT instance-frames where < 90% of the GT **box** area is covered by our plan's redaction (from `plan.json`, rendered at 6 fps) |
| **Leak bursts** | Runs of ≥3 consecutive exposed frames. ⚠️ At 6 fps, 3 frames = 0.5 s, not 0.1 s, so report it as "≥0.5 s bursts @6 fps" and never mix it with the 30 fps numbers |
| **Entity recall** | Share of GT masklets covered ≥95% of their frames |
| Leak-guard ablation | the same numbers with the guard off vs on (padding, back-fill, gap hold), which is the headline use: "the leak guard cuts exposure from X to Y on Meta's own egocentric benchmark" |
| Not applicable | over-blur rate (no keep-clear labels), review load, creator time |

Practical notes for WP7:
- SAM needs **video**, but the dataset ships JPEG frames. Encode each video to H.264 at 6 fps with `imageio-ffmpeg`, so that frame N = JPEG N (verify `length` == decoded frames).
- Cost: SAM bills per frame. At 6 fps the SG split is cheap, but WP7 counts frames before running: `frames × concepts × $0.20/1k`.
- GT boxes come straight from `bboxes` (no MOT conversion needed). Convert to MOT only if reusing the EVAL.md loader.
- Use **val** for development and **test** once, mirroring EVAL.md's frozen-split rule.
- It's Meta's own benchmark, so it's credible to judges, but say plainly that it measures tracking coverage, not role decisions.
