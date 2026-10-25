# BLOCKED (PRE-A): inputs only the owner can supply

**Updated:** 2026-10-24 · **Branch:** `pre-a-research` · **WP:** `docs/work-packages/PRE-A.md`. This file lives in `docs/`. PRE-B's owner checklist is **`docs/BLOCKED-PRE-B.md`** on PR #2 (footage, labels, pilots, the API key, making the repo public). Those items aren't repeated here, so read both.

PRE-A's documents are all written. Each item below needs the owner, either through an account action or by changing this cloud environment's settings. Most don't block building: the affected facts are tagged in the docs for WP0 to verify, and the code WPs build behind stubs or replay fixtures (noted per item). **The EgoBlur weights are the exception:** every live job (WP5's deploy from about Oct 29, pilots, the Nov 3 recordings, judge "Try it") needs a real face auditor, so they're needed by **Oct 31**, after which WP4 switches to the decided YuNet fallback (API-NOTES §12).

## Checklist (most urgent first)

- [ ] **Request SA-Co/VEval access on Hugging Face now.** The dataset is gated and approval is manual, so the wait is open-ended. Use the owner's own HF account on the `facebook/SACo-VEval` dataset page, then add a read-scoped token as the environment secret `HF_TOKEN`. *Meanwhile:* WP7 builds the loader against the documented format with a synthetic fixture. Details: `docs/research/sa-co-veval.md`.
- [ ] **Request the EgoBlur weights** (O8) using the email request form at <https://www.projectaria.com/tools/egoblur/>, with your own name and email. When the download arrives, put all four zips (`ego_blur_{face,lp}_gen{1,2}`) in the private bucket under `models/egoblur/gen1/` and `models/egoblur/gen2/`, never in this repo. *Meanwhile:* WP4's tests and replay mode use a stub of saved detections; **live** jobs are refused (`503 auditor_unavailable`) until the weights arrive, or until the Oct 31 YuNet fallback is switched on. Details: `docs/research/egoblur-gen2.md`.
- [ ] **Provide a Linux x86-64 machine with an NVIDIA GPU, owned by you, for the test-split eval runs.** Nothing on it can run before you set it up.
  - **Why not the Intel Mac:** EgoBlur Gen 2 hard-pins `torch==2.9.1`, which has no Intel-macOS wheel (PyPI file list, 2026-10-24). So the audit and the EgoBlur baseline can't run on the Intel dev Mac, which MAXXING §4 and WP7.md currently name for `eval/run.py --split test`.
  - **Why not the cloud:** real-public test clips must never enter the cloud sandbox (AGENTS rule 5).
  - **Why a GPU:** on CPU, EgoBlur needs about 1–3 s per frame for each detector (`docs/research/egoblur-gen2.md` "Speed"). That's 30–90 min per 30 s clip-run for face and plate, or about 18–54 h for 12 test clips × 3 runs (plus baseline 1b), so a CPU-only machine can't do the full three runs (see the fallback below). With a GPU it's about 20 s per detector per clip.
  - **Which machine:** PR #2's CVAT decision prefers a Linux or WSL2 machine the owner controls. If that machine has an NVIDIA GPU, use it, since it already holds the private set. Never a third party's machine (e.g. labeller B's), because these runs use `MODEL_API_KEY`.
  - **Setup:** Python 3.12, `uv`, and ffmpeg from `imageio-ffmpeg`.
  - **If no GPU machine exists:** EgoBlur still runs on **every frame** on CPU (there is no sampled mode anywhere, so the audit, review load and baseline 1b stay comparable), but the test split does **one** run (k = 1) instead of three: the `full` audit (12 clips × 30–90 min ≈ 6–18 h) plus baseline 1b on every source frame (another ≈ 6–18 h), about 12–36 h in total, run unattended. The README states the run count next to every number. *Rejected:* auditing 1 frame in 3, which would either block every test job or weaken the audit and baseline 1b (audits #19–#21).
  - *Meanwhile:* dev and hero runs (consented clips) use the sandbox or Modal. WP7's runner refuses `--split test` inside the sandbox.

- [ ] **Network allowlist for this cloud environment** (O3). Under claude.ai/code → environment → Edit → Network access → Allowed domains, leave "Allow package managers" ticked and add:
  - [ ] `dev.meta.ai`: Meta's docs. From this session it fails (`curl: (56) CONNECT tunnel failed, response 403`)
  - [ ] `developer.meta.com`
  - [ ] `api.meta.ai`: the API itself (WP0 probes)
  - [ ] `www.projectaria.com`
  - [ ] `modal.com`
  - [ ] `huggingface.co`
  - Steps: <https://code.claude.com/docs/en/cloud-environments#network-access>. Once it's done, WP0 re-reads the `dev.meta.ai` URLs listed in `docs/API-NOTES.md` and re-tags the `[SNIP]`/`[3P]` facts.
- [ ] **Keep the test split's mean clip length at most 30 s** when you film and pick the eval clips (SHOTLIST allows 15–45 s; MAXXING O1). The $43.20 test line in `docs/API-NOTES.md` §9.2 is priced at a 30 s mean; a longer mean makes `eval/run.py` cut repetitions of run 3 (never a clip), and the README states the run count per clip.
- [ ] **Cloud setup script:** in this environment's setup script (MAXXING §6, owner item O3), replace `uv sync --all-groups` with `uv sync --all-groups --no-group audit`. The `audit` group is EgoBlur's CUDA `torch==2.9.1` (multi-GB, `docs/research/egoblur-gen2.md`); sandbox tests use the replay stub; WP4 and WP7 run `uv sync --group audit` on demand once the weights exist (API-NOTES §12, "Deliberate differences").
- [ ] **Owner code for WP5:** add one `{"code": "…", "kind": "owner", "cap_usd": 6}` entry to the `SAFECUT_ACCESS_CODES` deploy secret before WP5's first live deploy (about Oct 29), for its smoke runs and the live hero-1 end-to-end run (API-NOTES §12 env table). Never commit it.
- [ ] **Optional, for the Swahili check:** one consented short clip with Swahili or Sheng speech (a staged take of a hero scene is fine), uploaded to the private bucket, so WP0 probe d can test Voice Transcribe on it. Without it, the language bias stays English and the README says Swahili is untested.

## Already decided (no owner input needed)
Where sources were silent, the docs record a decision instead of a question: see the "Decisions" section of PR #1.
