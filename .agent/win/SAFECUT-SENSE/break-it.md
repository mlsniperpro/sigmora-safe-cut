TESTED_COMMIT: ae004d8

# SAFECUT-SENSE: what was done to break it

All runs at `86be73c` (the code re-audit 10 covered) and again at `ae004d8` (the same code plus a behaviour-neutral lint
change, verified in `reaudit.md` audit 11), offline: no `MODEL_API_KEY`, no network, no live Meta call.

## Soak: the replay end to end, five times
`safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --replay --auto-approve-policy` (every stage: prepare →
track → transcribe → scene → roles → decide → guard → render → audit → receipt), five fresh jobs in a row. All exited 0;
the SHA-256 over `tracks.json`, `transcript.json`, `scene.json`, `roles.json`, `decisions.json` and `plan.json` was
`bfcfcf69b9f28fd4` every time, at both commits: the pipeline is deterministic, run to run.

## Fuzz
- Five seeded rounds (`--hypothesis-seed` 11, 22, 33, 44, 55, at both commits) of the property suites `tests/test_sam_properties.py`,
  `tests/test_scout_logic.py`, `tests/test_axes.py` and `tests/test_som.py`: 116 passed each round. They cover: any
  valid SAM stream split anywhere parses to exactly its boxes; junk spliced anywhere never parses silently wrong;
  linked tracks are dense, in frame and numbered once; interpolation rounds outward; the keep rule over random votes;
  windows never promote; escalation never keeps; any schema-valid votes and rulings assemble into a `roles.json` the
  contracts accept (with the keep rule asserted on every participant).
- The re-audits fuzzed the stages themselves (logged in `reaudit.md`): ~400 full speech → scene → roles → decide →
  guard jobs on hostile schema-valid answers through the live client path (FakeMeta with fault injection), 3,000
  multi-window cases against an independent oracle, ~11k mutated SAM streams, 200k vote/ruling cases, 30k hostile
  speech answers, 50k raw misses, and 20+ legitimate and 34+ hostile upload shapes through `prepare`. Every output
  valid; every finding at Medium or above fixed with a failing-first test.

## Failure injection
`tests/test_sense_failures.py` (FakeMeta with injected errors), `tests/test_sense_live_paths.py` and
`tests/test_go_live.py`: Voice Transcribe down → Spark 1.2 fallback; both down → `failed`; a budget stop → `skipped`;
a failed scene pass; one failed vote; every vote failed; a failed escalation; a failed, unusable or unaffordable
miss-loop SAM request, a proxy that can't be rebuilt and a ledger that can't answer → static boxes; a corrupt
checkpoint, scene or transcript file; a recorded answer that never parsed; a recording for another clip or model;
a resumed `roles` (re-bills nothing, byte-identical files); go-live killed mid-swap, failed, stopped or empty.
Uploads: edit-list trims, playlists, tiny-frame floods, resolution bombs, forged headers (U+2028 and raw newlines in
metadata keys), non-UTF-8 metadata, one-frame and too-short clips, memory limits (`tests/test_prepare.py`).

## The replay end-to-end path
Besides the soak: `entry-check --only E2,E3,E8` on this lane's merges gave E2, E3 and E8 OK; on a fresh clone of
`origin/main` at `efd8b9d` the full entry check gave every SENSE line OK (E2, E3, E8, and E9 with this lane's
`muse_keyframe_boxes` hook).

## A fresh clone
`git clone -b claude/kind-pasteur-y6blvc` → `uv sync --locked --all-groups` → the SENSE test files (250 passed) →
`safecut run … --replay --auto-approve-policy` to `receipt.json` → `validate_job_dir`: VALID. Done at `86be73c` and again
at `9a2fc80` (the code of `ae004d8`): 250 passed, VALID.

## The full suite
`uv run pytest` at `86be73c`: 1413 passed (12 deselected: the `live` marker).
