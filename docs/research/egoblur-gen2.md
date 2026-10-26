# EgoBlur Gen 2 (audit detector)

Read 2026-10-24. **Source:** Meta's official repo [`facebookresearch/EgoBlur`](https://github.com/facebookresearch/EgoBlur) at commit `75144e1` (2026-05-05): README, CHANGELOG, `pyproject.toml`, `gen2/script/constants.py`, `gen2/script/utils.py`. The project page [projectaria.com/tools/egoblur](https://www.projectaria.com/tools/egoblur/) **couldn't be opened** (network policy, see `docs/BLOCKED-PRE-A.md`), so gating, file sizes and speed are unconfirmed.

## Where and licence
- Code: GitHub `facebookresearch/EgoBlur`, package **`egoblur` 2.0.1** (`pyproject.toml`), with the CLIs `egoblur-gen1`, `egoblur-gen2` and `egoblur-vrs-blur`.
- **Licence: Apache 2.0** (the `LICENSE` file, for the repo). The README doesn't state a separate licence for the weights. Confirm on the project page before redistributing anything; we don't redistribute weights in any case.
- Weights: **four zips** linked from the README to the project page: `ego_blur_face_gen1`, `ego_blur_lp_gen1`, `ego_blur_face_gen2`, `ego_blur_lp_gen2`. Extracted, they're TorchScript files, e.g. `ego_blur_face_gen2.jit`.
- Release history (CHANGELOG): **2.0.0 on 2025-12-11 (the Gen 2 release)**; 2.0.1 on 2026-04-13 (a VRS end-to-end blur tool).
- Model details: the README points to the Gen 1 paper, [EgoBlur: Responsible Innovation in Aria (arXiv 2308.13093)](https://arxiv.org/abs/2308.13093). There's no Gen 2 paper link. Gen 2 bundles a `detectron2` copy under `gen2/script/detectron2`, so it's a detectron2-style detector.

## Gating
**Gated by an email request form** on the EgoBlur page, <https://www.projectaria.com/tools/egoblur/> [OWNER-2026-10-24: read from an open network during the PR #1 audit]. Every weight link in the README points there. The README itself mentions no form, account or Hugging Face mirror.

**Decided:** WP4 builds the audit behind a detector interface with a **replay stub** (saved EgoBlur detections as fixtures) used **only in tests and replay mode**, so the pipeline and tests run before the weights arrive. Live jobs need the real model: without it `/start` is refused (`503 auditor_unavailable`), and from Oct 28 the YuNet face fallback applies (WP4 builds it in its first PR, behind `SAFECUT_EGOBLUR_MODEL`) (API-NOTES §12, WP4 deviation).

**Owner steps (O8), also in `docs/BLOCKED-PRE-A.md`:**
1. Open <https://www.projectaria.com/tools/egoblur/> and submit the request form with the owner's own name and email, never an agent's.
2. When the download arrives, get **all four** zips (`ego_blur_face_gen1`, `ego_blur_lp_gen1`, `ego_blur_face_gen2`, `ego_blur_lp_gen2`; the Gen 1 vs Gen 2 comparison below needs both), and record the licence text shown and the date.
3. Upload them to the **private** consented-clips bucket under `models/egoblur/gen1/` and `models/egoblur/gen2/`. They must never be committed to this public repo. WP4 fetches them at runtime with the bucket token, or Modal mounts them from a Volume.
4. If the links are time-limited signed URLs, don't paste them anywhere public.

## Files and sizes
- File names as above. The project page (read 2026-10-25): "Both the Gen 2 face and license plate models are approximately **400 MB** each and have **~104 million parameters**".
- Runtime deps (pinned in `pyproject.toml`): `torch==2.9.1`, `torchvision==0.24.1`; Python **3.10–3.12**. That fits our 3.12, but the pins may clash with other deps, so WP4 keeps it in the `audit` group.

## Preprocessing and thresholds (`gen2/script/constants.py`)
- Resize: `RESIZE_MIN_GEN2 = 1200`, `RESIZE_MAX_GEN2 = 1200`, applied as detectron2-style `ResizeShortestEdge(1200, max_size=1200)` (`gen2/script/predictor.py`, which also has a GPU batched version). The short edge goes to 1200, then the whole image is scaled down so the long edge is ≤1200. **In effect the long edge = 1200**: a 1280×720 prepared frame runs at ≈1200×675.
- Colour: the detector takes **BGR**. `EgoblurDetector` defaults to `image_format="BGR"`, and the Gen 2 video demo converts moviepy's RGB frames with `cv2.COLOR_RGB2BGR` before detection (`demo_ego_blur_gen2.py` line 298). WP4 feeds OpenCV-decoded (BGR) frames unchanged.
- Score thresholds (per camera, via `--camera_name`; the default when it's unset is `camera-rgb`):

| Camera | Face | Licence plate |
|---|---|---|
| `camera-rgb` (**use this for phone footage**) | **0.67416** | **0.74475** |
| `slam-front-left/right` | 0.69862 | 0.95245 |
| `slam-side-left/right` | 0.68160 | 0.95242 |

- NMS IoU default: **0.5 for Gen 2** (`demo_ego_blur_gen2.py`, `--nms_iou_threshold` default=0.5; the README's "0.3" is out of date, and the code wins) and **0.3 for Gen 1** (`demo_ego_blur_gen1.py`). `--scale_factor_detections` (e.g. 1.15 = +15%) scales boxes.
- Its own blur is `cv2.blur` inside an **ellipse** mask. We don't use EgoBlur's blur (it's reversible, DESIGN §2.7); we only use its **detections** as the audit signal.
- **Audit threshold advice:** use a *lower* face threshold than 0.674 for the audit (e.g. 0.5), because a false alarm only costs an extra patch, while a miss is a leak. WP4 measures the false-alarm rate on hero clips.

## Speed (CPU vs GPU)
- The README reports **no numbers**. It says macOS runs CPU-only ("very slow") and recommends Linux + CUDA 12.8 (optional).
- The project page (read 2026-10-25): a "2MP RGB image" runs "in approximately **21ms on a GPU and 1.5 seconds on a CPU**", and a "0.3MP grayscale image" in "approximately 25ms on a GPU and 1.6 seconds on a CPU" (re-read 2026-10-26). Licence: "Both the Gen 2 face and license plate models are licensed under **Apache 2.0**". Our frames (≤ 1280×720 ≈ 0.9 MP, colour) sit between the two, so expect ≈ 1.5 s per frame per detector on CPU; WP4 measures it. **Access:** "If you are a researcher in AI or ML research", plus a licence agreement; "Use the model generation that matches your capture device" (Gen 2 is tuned on Aria Gen 2 data, so phone footage is unverified: the held-out choice below decides); "The models are not used to track or identify individual faces or license plates": Safe Cut uses detections only, never identity.
- Estimate for the budget: a 30 s × 30 fps clip = 900 frames × 21 ms ≈ **19 s of GPU**. On CPU, ≈ 1.5 s per frame per detector → ≈ 45 min per clip for face and plate, which is too slow. So **GPU for the audit** (Modal T4/L4; see `modal.md`), or, without a GPU, every frame on CPU with one test run instead of three (BLOCKED-PRE-A). EgoBlur never samples frames: the service, the eval audit and baseline 1b all scan every frame.

## Install and API for WP4 (read from the package and source, 2026-10-24)
- **PyPI:** `egoblur` **2.0.1** (a pure-Python wheel; `requires_python >=3.10,<3.13`). Its dependencies are **hard-pinned**: `torch==2.9.1`, `torchvision==0.24.1`, `vrs==1.2.2` (Apache-2.0), plus `moviepy>=1.0.3,<2`, `av>=12,<14`, `opencv-python-headless>=4.7,<5`, `numpy>=1.24,<3`, `tqdm`. WP0's `audit` dependency group must use exactly these torch and torchvision versions, or uv can't resolve. **Decided: install them from default PyPI.** The Linux x86-64 `torch` 2.9.1 wheel on PyPI is the CUDA build (its metadata requires 15 `nvidia-*-cu12` packages, CUDA 12.8, on Linux x86-64: a multi-GB install), and it also runs on CPU, so one lock file serves the Modal GPU image, the owner's Linux box and CI. *Rejected:* the PyTorch CPU index for the group, because its build can't use the Modal GPU (`Torch not compiled with CUDA enabled`). CI may skip the `audit` group, since its tests use the replay stub.
- **Platforms (checked against PyPI file lists):** `torch` 2.9.1 ships wheels for Linux x86-64/aarch64, Windows and **macOS arm64 only**, so there's **no Intel-Mac wheel**. `vrs` 1.2.2 likewise has `manylinux` x86-64 and macOS arm64 wheels only. **Consequence:** EgoBlur, and therefore the audit and the EgoBlur baseline (EVAL.md row 1b), **can't run on the owner's Intel dev Mac.** It runs on Linux x86-64 (Modal, the sandbox, or the owner's Linux build box). **Decided:** test-split runs (real-public clips, which never enter the sandbox) execute on the owner's **Linux build box**, the same machine PR #2 picks for CVAT, which already holds the private set. They don't run on the Intel Mac. This is a request to WP7 and an owner step in `docs/BLOCKED-PRE-A.md`.
- **Import path:** the wheel installs top-level packages named `gen1` and `gen2` (setuptools `find`), so **WP4 must not name any of its own modules `gen1` or `gen2`.** The detector is `gen2.script.predictor.EgoblurDetector`, and the constants are in `gen2.script.constants`.
- **`EgoblurDetector(...)` arguments** (`predictor.py`):
  - `model_path`: the `.jit` file;
  - `device`: `"cpu"` or `"cuda:0"`;
  - `detection_class`: `ClassID.FACE` (0) or `ClassID.LICENSE_PLATE` (1). **One detector per class**, so face and plate are two models and two passes;
  - `score_threshold`, applied after NMS;
  - `nms_iou_threshold` (the Gen 2 CLI default is **0.5**; use it);
  - `image_format`: `"BGR"` (the default);
  - `resize_aug={"min_size_test": 1200, "max_size_test": 1200}`;
  - `use_gpu_resize`: default `True`.
- **Input:** a `uint8` tensor `C×H×W` or `B×C×H×W` in **BGR** order, as OpenCV decodes it (`gen2.script.utils.get_image_tensor` transposes an `H×W×3` BGR array).
- **Output:** two options:
  - `run(tensor)` returns, per image, a list of `[x1, y1, x2, y2]` float boxes in **original image pixels** (XYXY), **without scores**;
  - for scores, call `pre_process` → `inference` → `get_detections(...)`, which returns a `FrameDetections` per image (`face_bboxes`, `face_scores` or `lp_bboxes`, `lp_scores`), or `None` when there are no detections.
- **Decided for the audit:**
  - construct the detectors with `score_threshold = 0.5` (lower than the `camera-rgb` default 0.674, because a miss is a leak);
  - use the `get_detections` path so scores are logged, which lets WP4 report recall at 0.5 and at each model's calibrated default (face 0.674, plate 0.745 for Gen 2) from one pass;
  - batch 8 frames;
  - boxes are floats, so convert to half-open integer boxes with `floor(x1), floor(y1), ceil(x2), ceil(y2)` (API-NOTES §5).
- **Its blur is never used.** Safe Cut uses EgoBlur only as a detector (DESIGN §2.7).

## Gen 1 vs Gen 2
| | Gen 1 | Gen 2 |
|---|---|---|
| Intended data | Aria Gen 1 | Aria Gen 2 |
| CLI | `egoblur-gen1` | `egoblur-gen2` |
| Camera-specific thresholds | no | `--camera_name` (table above) |
| Output FPS | `--output_video_fps` (default 30) | preserves the input FPS; **raises `ValueError` if FPS metadata is missing or invalid** |
| VRS | C++ tool (CUDA 12.1, libtorch 2.1) | `egoblur-vrs-blur` (2.0.1+) |
| Paper | arXiv 2308.13093 | none linked |

Default for Safe Cut: **Gen 2 with `camera-rgb`**. Our prepared clips have a constant frame rate (API-NOTES §5b), and we use the detector API rather than the CLI anyway. But the README ties each generation to Aria data, and our footage is phone video, so **decided:** WP4 compares Gen 1 and Gen 2 as the auditor on consented labelled footage, as follows.
  - **Weights:** both generations' face and plate zips (O8, `docs/BLOCKED-PRE-A.md`).
  - **Thresholds:** each model at its **own calibrated default** (Gen 1: 0.9; Gen 2 `camera-rgb`: face 0.674, plate 0.745) and at **0.5**. Face and plate are reported separately, as recall plus false detections per minute.
  - **Selection is held out:** choose on **hero clip 1** (both takes), then report the chosen model's recall on hero clips 2–3 and the dev split. The reported "auditor recall" is never measured on the clips used to pick it.
  - **Rule:** the service always runs at **0.5** (face and plate); the comparison picks only the **generation**: the one with the higher recall at 0.5 whose false detections stay ≤ 2 per minute (each costs an auto-patch, i.e. over-blur). If neither meets that, Gen 2 at 0.5. The calibrated defaults are reported, never shipped.
  - The results report the auditor's own recall (`research/winning-patterns.md` R2).

Gen 1's API is simpler (`gen1/script/demo_ego_blur_gen1.py`, read 2026-10-24): `torch.jit.load` the `.jit` file, call it on a **C×H×W BGR uint8** tensor with no resize, and it returns `(boxes, labels, scores, dims)`. Then apply `torchvision.ops.nms(boxes, scores, 0.3)` and keep the boxes whose score is above the threshold.

## Verification tasks for WP4 (on Oct 26)
1. The licence text shown with the download, and the zip sizes.
2. ~~Short or long edge~~: resolved from `predictor.py`, the long edge ends at 1200.
3. Measured ms/frame on Modal T4 vs L4 vs CPU at 1280×720.
4. Detection recall on our hero clips at 0.674 vs 0.5.
