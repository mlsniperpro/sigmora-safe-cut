# SA-Co/VEval: SmartGlasses split

Read 2026-10-24. **Sources:** Meta's [`facebookresearch/sam3`](https://github.com/facebookresearch/sam3) README and [`scripts/eval/veval/README.md`](https://github.com/facebookresearch/sam3/blob/main/scripts/eval/veval/README.md) (via GitHub fetch), plus web-search summaries of the [Mintlify sam3 docs](https://mintlify.wiki/facebookresearch/sam3/evaluation/saco-veval) and [Roboflow Universe sa-co-veval](https://universe.roboflow.com/sa-co-veval). The HF dataset page [`facebook/SACo-VEval`](https://huggingface.co/datasets/facebook/SACo-VEval) **couldn't be opened** (network policy, see `BLOCKED.md`).

## Where to get it
- **Annotations:** six JSON files on Hugging Face, `facebook/SACo-VEval` (test + val per domain).
- **SmartGlasses media:** `media/saco_sg.tar.gz` in the same HF repo; extract it under `data/media` → `saco_sg/JPEGImages_6fps/`.
- **Shortcut:** Roboflow Universe hosts preprocessed SmartGlasses frames + GT for both val and test.
- Tooling: `pip install -e ".[veval]"` in the sam3 repo, then the offline evaluator `saco_veval_eval.py` (modes `one` and `all`).
- Whether the HF dataset is **gated** (the sam3 *checkpoints* are gated: "request access… must be authenticated") is **unknown**. If it is, the owner requests access on HF with their own account (an owner step, like O8).
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
