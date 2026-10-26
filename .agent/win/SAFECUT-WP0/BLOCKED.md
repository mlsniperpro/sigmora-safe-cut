# SAFECUT-WP0 blockers (owner inputs only)

- [ ] `MODEL_API_KEY`: the Meta Model API key with the hackathon credits (MAXXING O6), added as a secret in this repo's cloud environment. Unblocks probes a–g (`scripts/probes/`, ≤ $6) and the `pytest -m live` tests. Everything else runs on replay fixtures.
- [ ] `SAFECUT_CLIPS_URL` + `SAFECUT_CLIPS_TOKEN`: read access to the private consented-clips bucket with the hero clips (MAXXING O1, O3). Without them the probes use the synthetic burned-in-counter clips in `fixtures/clips/`.
