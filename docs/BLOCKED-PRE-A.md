# BLOCKED (PRE-A): inputs only the owner can supply

**Updated:** 2026-10-24 · **Branch:** `pre-a-research` · **WP:** `docs/work-packages/PRE-A.md`. This file lives in `docs/` because PRE-B's PR #2 has the root `BLOCKED.md`, which covers footage, labels, pilots, the API key and making the repo public. Those items aren't repeated here.

PRE-A's documents are all written. Each item below needs the owner, either through an account action or by changing this cloud environment's settings. Nothing waits on them: the affected facts are tagged in the docs for WP0 to verify, and the code WPs build behind stubs or replay fixtures (noted per item).

## Checklist (most urgent first)

- [ ] **Request SA-Co/VEval access on Hugging Face now.** The dataset is gated and approval is manual, so the wait is open-ended. Use the owner's own HF account on the `facebook/SACo-VEval` dataset page, then add a read-scoped token as the environment secret `HF_TOKEN`. *Meanwhile:* WP7 builds the loader against the documented format with a synthetic fixture. Details: `docs/research/sa-co-veval.md`.
- [ ] **Request the EgoBlur Gen 2 weights** (O8) using the email request form at <https://www.projectaria.com/tools/egoblur/>, with the owner's own name and email. When the download arrives, put `ego_blur_face_gen2` and `ego_blur_lp_gen2` in the private bucket under `models/egoblur/gen2/`, never in this repo. *Meanwhile:* WP4's audit runs on a replay stub of saved detections. Details: `docs/research/egoblur-gen2.md`.
- [ ] **Network allowlist for this cloud environment** (O3). Under claude.ai/code → environment → Edit → Network access → Allowed domains, leave "Allow package managers" ticked and add:
  - [ ] `dev.meta.ai`: Meta's docs. From this session it fails (`curl: (56) CONNECT tunnel failed, response 403`)
  - [ ] `developer.meta.com`
  - [ ] `api.meta.ai`: the API itself (WP0 probes)
  - [ ] `www.projectaria.com`
  - [ ] `modal.com`
  - [ ] `huggingface.co`
  - Steps: <https://code.claude.com/docs/en/cloud-environments#network-access>. Once it's done, WP0 re-reads the `dev.meta.ai` URLs listed in `docs/API-NOTES.md` and re-tags the `[SNIP]`/`[3P]` facts.

## Already decided (no owner input needed)
Where sources were silent, the docs record a decision instead of a question: see the "Decisions" section of PR #1.
