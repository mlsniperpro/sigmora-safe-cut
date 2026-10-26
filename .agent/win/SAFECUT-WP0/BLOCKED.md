# SAFECUT-WP0 blockers (owner inputs only)

- [ ] `MODEL_API_KEY`: the Meta Model API key with the hackathon credits (MAXXING O6), added as a secret in this repo's cloud environment. Unblocks probes a–g (`scripts/probes/`, ≤ $6) and the `pytest -m live` tests. Everything else runs on replay fixtures.
- [ ] `SAFECUT_CLIPS_URL` + `SAFECUT_CLIPS_TOKEN`: read access to the private consented-clips bucket with the hero clips (MAXXING O1, O3). Without them the probes use the synthetic burned-in-counter clips in `fixtures/clips/`.
- [ ] Make `mlsniperpro/sigmora-safe-cut` public before submission (official guide: "Repositories must be public"; MAXXING O7). Repos stay private until the owner approves.
- [ ] GitHub Actions for this private repo: CI jobs on PR #3 get no runner (runner_id 0, finished in 3 s, no log), which usually means the account's Actions minutes or spending limit is used up. Either make the repo public (Actions is free for public repos) or raise the Actions limit. Every local check passes (`.agent/win/SAFECUT-WP0/checks.sh`).
- [ ] `BASETEN_API_KEY` (Baseten credits, by request): unlocks the open-weight probe of `meta-models/muse-spark-open-1026` for the "Best Build on Meta Open-Weight Models" bonus. The config and client path exist and are tested on replay fixtures.
- [ ] Consented hero keyframes for probe f's role calls: a folder with up to 5 Set-of-Mark JPEGs (hand-drawn boxes are fine) and `role_calls.json` (`[{"image", "label", "context", "expected"}]`), run as `uv run python -m scripts.probes.probes f --keyframes=<dir>`. Needs MODEL_API_KEY too.
