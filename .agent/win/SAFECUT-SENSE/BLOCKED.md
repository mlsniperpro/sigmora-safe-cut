# SAFECUT-SENSE: owner inputs (checklist; nothing here blocks the code, which runs on the synthetic demo job)

- [ ] **`MODEL_API_KEY`** in the cloud environment's secrets, with `api.meta.ai` allowed by its network policy. Then:
      `bash scripts/go-live.sh fixtures/clips/counter_30fps_audio.mp4` records a full SENSE job's raw responses into
      `fixtures/jobs/<id>/raw/` under its USD cap, and `uv run pytest -m live` runs every SENSE live test.
- [ ] **Consented hero clip 1** (`docs/SHOTLIST.md`, with releases) in the private bucket (`SAFECUT_CLIPS_URL`,
      `SAFECUT_CLIPS_TOKEN`), so `go-live.sh` can record it and its `tracks.json` lands in `fixtures/jobs/hero1/`.
