# BLOCKED (PRE-A): Meta's docs site isn't reachable from the cloud environment

**Date:** 2026-10-24 09:40 UTC · **Branch:** `pre-a-research` · **WP:** `docs/work-packages/PRE-A.md`

## What's blocked
PRE-A step 1 says to build `docs/API-NOTES.md` **from Meta's public docs at `dev.meta.ai/docs`**. The cloud environment's network policy denies that host:

```
curl https://dev.meta.ai/docs  →  CONNECT tunnel failed, response 403   (agent proxy)
WebFetch dev.meta.ai           →  getaddrinfo ENOTFOUND
```

These hosts are denied the same way: `developer.meta.com`, `www.projectaria.com` (EgoBlur weights page), `modal.com` (pricing and docs), `huggingface.co` (SA-Co/VEval dataset page), and most third-party sites. Only `github.com` (fetch and `git clone`), `pypi.org`, `registry.npmjs.org` and the web-search tool work.

## What was done instead (nothing faked)
- Every file PRE-A asks for exists. API facts come from **Meta's own GitHub repos**: `meta-models/meta-model-cookbook` (commit `0a99b98`, 2026-10-07) and `meta-models/meta-sam` (commit `4031897`, 2026-10-06, including the normative `protocol/sam3.md`). The remaining facts come from search-engine summaries and third-party sources. **Every fact is tagged with its source tier** (`[GH-…]`, `[SNIP]`, `[3P]`, `[DESIGN]`) and marked "per docs, unverified; WP0 verifies live".
- Facts no reachable source gave are listed as unknown, not guessed: the SAM price on Meta's own page, Muse Spark 1.2 pricing, the `input_video.fps` field, Standard-mode retention periods, Meta's Muse prompting-guide URL, EgoBlur gating and file sizes, and the SA-Co/VEval size.

## What's needed to finish (owner, ≈2 min)
1. In claude.ai/code → this environment → **Edit → Network access**, add under *Allowed domains* (leave "Allow package managers" ticked):
   `dev.meta.ai`, `developer.meta.com`, `api.meta.ai`, `www.projectaria.com`, `modal.com`, `huggingface.co`. All but `developer.meta.com` are already in MAXXING §6's allowlist; this environment doesn't have it applied yet (owner step O3). Steps: <https://code.claude.com/docs/en/cloud-environments#network-access>
2. Re-run PRE-A (or let WP0 do it on Oct 26). The agent re-reads each `dev.meta.ai` URL listed in `docs/API-NOTES.md`, replaces `[SNIP]`/`[3P]` tags with `[dev.meta.ai, read <date>]`, and fills in the unknowns above.

## Not blocked
Prompt specs (`docs/prompts/`) and the research files are complete as drafts. The EgoBlur and SA-Co/VEval facts come mostly from Meta's GitHub repos.
