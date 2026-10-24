# EgoBlur Gen 2 (audit detector)

Read 2026-10-24. **Source:** Meta's official repo [`facebookresearch/EgoBlur`](https://github.com/facebookresearch/EgoBlur) at commit `75144e1` (2026-05-05): README, CHANGELOG, `pyproject.toml`, `gen2/script/constants.py`, `gen2/script/utils.py`. The project page [projectaria.com/tools/egoblur](https://www.projectaria.com/tools/egoblur/) **couldn't be opened** (network policy, see `BLOCKED.md`), so gating, file sizes and speed are unconfirmed.

## Where and licence
- Code: GitHub `facebookresearch/EgoBlur`, package **`egoblur` 2.0.1** (`pyproject.toml`), with the CLIs `egoblur-gen1`, `egoblur-gen2` and `egoblur-vrs-blur`.
- **Licence: Apache 2.0** (the `LICENSE` file, for the repo). The README doesn't state a separate licence for the weights. Confirm on the project page before redistributing anything; we don't redistribute weights in any case.
- Weights: **four zips** linked from the README to the project page: `ego_blur_face_gen1`, `ego_blur_lp_gen1`, `ego_blur_face_gen2`, `ego_blur_lp_gen2`. Extracted, they're TorchScript files, e.g. `ego_blur_face_gen2.jit`.
- Release history (CHANGELOG): **2.0.0 on 2025-12-11 (the Gen 2 release)**; 2.0.1 on 2026-04-13 (a VRS end-to-end blur tool).
- Model details: the README points to the Gen 1 paper, [EgoBlur: Responsible Innovation in Aria (arXiv 2308.13093)](https://arxiv.org/abs/2308.13093). There's no Gen 2 paper link. Gen 2 bundles a `detectron2` copy under `gen2/script/detectron2`, so it's a detectron2-style detector.

## Gated?
**Unknown.** Every weight link goes to `projectaria.com/tools/egoblur`. The README says only "download the zipped models from the links provided", with no mention of a form, an account or Hugging Face. Historically (Gen 1, 2023) the Aria page asked for a name and email and agreement to the licence before showing download links; **that's from memory and wasn't verified this session**.

**Owner steps (O8) if it's gated:**
1. On the Mac, open <https://www.projectaria.com/tools/egoblur/> and find the Gen 2 download section.
2. Fill in whatever form it shows (name, email, licence acceptance). Use the owner's own identity, never an agent's.
3. Download `ego_blur_face_gen2` and `ego_blur_lp_gen2` (zips), and record the page's licence text and the date.
4. Upload both zips to the **private** consented-clips bucket under `models/egoblur/gen2/` (they must never be committed to this public repo). Tell Claude the paths, and WP4 fetches them at runtime via `SAFECUT_CLIPS_URL` / token, or Modal mounts them from a Volume.
5. If the links are time-limited signed URLs, don't paste them anywhere public.

**If it's not gated:** add `www.projectaria.com` (and whatever CDN host the zips come from) to the environment's network allowlist; MAXXING §6 already lists projectaria.com. WP4 downloads at build time.

## Files and sizes
- File names as above. **Sizes aren't listed** in the README. WP4 records them. (The Gen 1 face model was a Faster R-CNN-class detector of a few hundred MB; unverified for Gen 2.)
- Runtime deps (pinned in `pyproject.toml`): `torch==2.9.1`, `torchvision==0.24.1`; Python **3.10–3.12**. That fits our 3.12, but the pins may clash with other deps, so WP4 keeps it in the `audit` group.

## Preprocessing and thresholds (`gen2/script/constants.py`)
- Resize: `RESIZE_MIN_GEN2 = 1200`, `RESIZE_MAX_GEN2 = 1200`, applied as detectron2-style `ResizeShortestEdge(1200, max_size=1200)` (`gen2/script/predictor.py`, which also has a GPU batched version). The short edge goes to 1200, then the whole image is scaled down so the long edge is ≤1200. **In effect the long edge = 1200**: a 1280×720 prepared frame runs at ≈1200×675.
- Colour: the demo reads frames with OpenCV and converts to RGB for the model (`cv2.cvtColor` in `demo_ego_blur_gen2.py`). WP4 matches this exactly.
- Score thresholds (per camera, via `--camera_name`; the default when it's unset is `camera-rgb`):

| Camera | Face | Licence plate |
|---|---|---|
| `camera-rgb` (**use this for phone footage**) | **0.67416** | **0.74475** |
| `slam-front-left/right` | 0.69862 | 0.95245 |
| `slam-side-left/right` | 0.68160 | 0.95242 |

- NMS IoU default **0.3**. `--scale_factor_detections` (e.g. 1.15 = +15%) scales boxes.
- Its own blur is `cv2.blur` inside an **ellipse** mask. We don't use EgoBlur's blur (it's reversible, DESIGN §2.7); we only use its **detections** as the audit signal.
- **Audit threshold advice:** use a *lower* face threshold than 0.674 for the audit (e.g. 0.5), because a false alarm only costs an extra patch, while a miss is a leak. WP4 measures the false-alarm rate on hero clips.

## Speed (CPU vs GPU)
- The README reports **no numbers**. It says macOS runs CPU-only ("very slow") and recommends Linux + CUDA 12.8 (optional).
- DESIGN §2.8 quotes **≈21 ms/frame on GPU** from the project page (read 2026-10-14). Not re-verified.
- Estimate for the budget: a 30 s × 30 fps clip = 900 frames × 21 ms ≈ **19 s of GPU**. On CPU at 1200 px with a detectron2 R-CNN, expect roughly 1–3 s/frame → 15–45 min per clip, which is too slow. So **GPU for the audit** (Modal T4/L4; see `modal.md`), or audit at a lower frame rate on CPU (1 in 3 frames, plus every frame at track edges).

## Gen 1 vs Gen 2
| | Gen 1 | Gen 2 |
|---|---|---|
| Intended data | Aria Gen 1 | Aria Gen 2 |
| CLI | `egoblur-gen1` | `egoblur-gen2` |
| Camera-specific thresholds | no | `--camera_name` (table above) |
| Output FPS | `--output_video_fps` (default 30) | preserves the input FPS; **raises `ValueError` if FPS metadata is missing or invalid** |
| VRS | C++ tool (CUDA 12.1, libtorch 2.1) | `egoblur-vrs-blur` (2.0.1+) |
| Paper | arXiv 2308.13093 | none linked |

For Safe Cut: **Gen 2 with `camera-rgb`**. Our prepared clips must carry a valid constant FPS (`prepare.py` already sets it).

## Open questions for WP4 (on Oct 26)
1. Gating, the licence text on the page, and the zip sizes.
2. ~~Short or long edge~~: resolved from `predictor.py`, the long edge ends at 1200.
3. Measured ms/frame on Modal T4 vs L4 vs CPU at 1280×720.
4. Detection recall on our hero clips at 0.674 vs 0.5.
