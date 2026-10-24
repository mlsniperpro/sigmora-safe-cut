# BLOCKED (PRE-A): inputs only the owner can supply

**Updated:** 2026-10-24 · **Branch:** `pre-a-research` · **WP:** `docs/work-packages/PRE-A.md`

PRE-A's documents are all written. Each item below needs the owner, either through an account action or by changing this cloud environment's settings. Nothing waits on them: every affected fact is already in the docs, tagged with the source it came from and marked for WP0 to verify, and the code WPs build behind stubs or replay fixtures (noted per item).

## Checklist

- [ ] **Network allowlist for this cloud environment** (owner step O3). Add these under claude.ai/code → environment → Edit → Network access → Allowed domains, leaving "Allow package managers" ticked:
  - [ ] `dev.meta.ai`: Meta's docs. **Today it returns a 403 from the agent proxy** (`curl: (56) CONNECT tunnel failed, response 403`), and WebFetch gets `getaddrinfo ENOTFOUND dev.meta.ai`
  - [ ] `developer.meta.com`: Meta model pages and blog
  - [ ] `api.meta.ai`: the API itself (WP0 probes)
  - [ ] `www.projectaria.com`: EgoBlur Gen 2 weights page
  - [ ] `modal.com`: pricing and docs
  - [ ] `huggingface.co`: SA-Co/VEval
  - Steps: <https://code.claude.com/docs/en/cloud-environments#network-access>
  - Effect once done: WP0 re-reads each `dev.meta.ai` URL listed in `docs/API-NOTES.md` and replaces the `[SNIP]`/`[3P]` tags with `[dev.meta.ai, read <date>]`.
- [ ] **EgoBlur Gen 2 weights** (O8). If the projectaria.com download sits behind a form, the owner fills it in with their own identity, downloads `ego_blur_face_gen2` and `ego_blur_lp_gen2`, and uploads them to the private bucket under `models/egoblur/gen2/`. Details: `docs/research/egoblur-gen2.md`. *Meanwhile:* WP4's audit runs on a replay stub of saved detections.
- [ ] **SA-Co/VEval access on Hugging Face** if the dataset is gated: the owner requests access with their own HF account, then stores a read token as the environment secret `HF_TOKEN`. *Meanwhile:* WP7 builds the loader against the documented YTVIS-like format (`docs/research/sa-co-veval.md`) with a tiny synthetic fixture.
- [ ] **`MODEL_API_KEY`** with the hackathon credits (O6, at kickoff), as an environment secret. *Meanwhile:* the cost model in API-NOTES §9 stands in, until WP0's probes replace it with measured `cost.jsonl`.

## Already decided (no owner input needed)
Where the sources were silent, the docs record a decision instead of a question: see the "Decisions" section of PR #1.
