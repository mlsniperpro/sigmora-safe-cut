# SAFECUT-SENSE win checklist

Every judging criterion, brief requirement and audit finding for the perception lane, with its evidence.
`- [x]` done (evidence named), `- [P]` waits on an owner input listed in `BLOCKED.md`, `- [-]` not applicable.

## Brief: lane SAFECUT-SENSE (`.agent/briefs/SAFECUT-SENSE.md`)

- [x] **1. prepare**: probe with the bundled ffmpeg, CFR H.264 ≤ 1280 px with `+faststart`, exact per-frame `times` from integer PTS, 1 fps keyframes, `source_sha256`, `too_large`/`too_long` limits first, `intake.json` read. Evidence: `tests/test_prepare.py` (frame-by-frame against ffmpeg 7.0.2 on jittery, 60→30, gappy-VFR and late-start clips; T6a–T6c, T9), `tests/test_axes.py` (T1–T5, T10, T11, property bounds).
- [x] **1. SAM stream parser** wrapping Meta's `meta-sam-parser`, failing closed; hypothesis over random valid streams split anywhere and over corrupted chunks. Evidence: `tests/test_sam_properties.py`, `tests/test_track.py` (S5, missing mask, out-of-frame box, EOF, refusal, zero matches, out-of-order frames).
- [x] **2. track**: one sweep per concept in parallel; never merges across a gap longer than `gap_merge_frames` (proxy frames); re-entry is a new ID with `reentry_of`; densified boxes rounded outward; crowded spans (T11); replay from `raw/sam/`. Evidence: `tests/test_track.py`, `tests/test_sam_properties.py`.
- [x] **2. proof on the synthetic counter clip**: every densified box has IoU ≥ 0.8 with `truth.json`; the square that vanishes for 5 proxy frames returns as `face:3` with `reentry_of: face:2`. Evidence: `tests/test_track.py::test_tracks_validate_and_match_truth`, `::test_reentry_is_a_new_id`.
- [x] **3. synthetic demo job**: every SENSE call recorded from ground truth, `synthetic: true`, validated by the same parsers and schemas as live; rebuilds byte for byte; merged into main (`011a881`). Evidence: `scripts/make_demo_job.py`, `fixtures/jobs/demo/raw/manifest.json`, `tests/test_demo_job.py`.
- [x] **4. transcribe**: Voice Transcribe (DIARIZATION, WAV from `prepared.mp4`), automatic Spark 1.2 fallback and `SAFECUT_SPEECH_SOURCE=spark-1.2`; `failed`/`skipped` always written. Evidence: `tests/test_sense_failures.py` (ASR down → fallback, both down → failed, budget → skipped), `tests/test_sense_live_paths.py`.
- [x] **5. scene**: one video call with structured output and `store: false`; speaker and introduction post-processing (P7, P11b, P11c); `failed`/`skipped` written. Evidence: `tests/test_demo_job.py::test_replay_writes_valid_contracts`, `tests/test_sense_failures.py::test_a_failed_scene_pass_is_written_down`, the fake API asserting `store is False` on every Responses call.
- [x] **6. Set-of-Mark keyframes**: bar added above, labels above the box (never over the face), inside the frame, apart, legible at 320 px, deterministic. Evidence: `tests/test_som.py`.
- [x] **7. roles**: three votes per ≤ 50-keyframe window sharing one prefix; participant only on 3/3 valid votes over ≥ 2 keyframes in every window; any child vote → child; disagreement → unsure → escalation at `max` once per window; objects sensitive unless 3/3 false. Evidence: `tests/test_scout_logic.py` (A1–A16, B1–B3, E2–E9 and hypothesis properties), `tests/test_demo_job.py::test_roles_match_the_scene`.
- [x] **8. miss loop**: ≤ 2 loops, ≤ 3 phrase sweeps and one batched object prompt per loop, the audit reserve kept, static boxes for anything SAM didn't return, `SAFECUT_MISS_SAM=stub`, already-tracked misses dropped. Evidence: `tests/test_scout_logic.py` (M1–M13), `tests/test_demo_job.py` (envelope found only by the miss loop), `tests/test_sense_failures.py::test_a_failed_miss_loop_request_leaves_a_static_box`.
- [x] **8. binding**: results bind by SAM object id (PRE-A §12 supersedes WP2's nearest-box helper), so no nearest-box fallback is needed. Evidence: `safecut/scout/missloop.py` (`sam_object.object_id == str(m_index)`).
- [x] **9. live path (E8)**: a `pytest -m live` test per Meta call (files, SAM, Voice Transcribe, scene, role, escalation, red-team, open-weight); `scripts/go-live.sh` records a whole job under a USD cap and exits 2 naming `MODEL_API_KEY` without it. Evidence: `tests/test_live_sense.py`, `tests/test_live_audit_calls.py`, `tests/test_go_live.py` (a whole job recorded against the fake API), entry-check `E8: OK`.
- [P] **9. live recordings**: run `go-live.sh` on the synthetic clips and hero clip 1, commit the responses and their cost, replace synthetic replays where real ones exist. Waits on `MODEL_API_KEY` and the consented hero clip (`BLOCKED.md`).
- [x] **Done for this lane**: every SENSE stage runs in replay with valid contracts on main; E2's SENSE stages and E8 are OK. Evidence: entry-check on main `569066a`: `E2: OK`, `E3: OK`, `E8: OK`.
- [x] **Then E3 (perception side)**: every should-hide entity of the demo job is tracked on every visible frame or inside the guard's back-fill/extension. Evidence: `tests/test_demo_job.py::test_every_hidden_entity_is_covered_on_every_visible_frame`; entry-check `E3: OK`.
- [x] **Then E9 (detector_only, muse_no_track)**: perception for both baselines, with offline replays on the demo job. Evidence: `safecut/scout/boxes.py`, `fixtures/jobs/demo/variants/muse_no_track/raw/`, `tests/test_demo_job.py` (both baselines). The runner `eval/run.py` is SHIP's.
- [x] **SHIP's E9 hook**: `safecut.scout.baselines.muse_keyframe_boxes(job_dir, *, replay)` → keyframe → Muse's sensitive boxes, replayed from `raw/baseline_muse/` (recorded into the demo job). Evidence: `tests/test_demo_job.py::test_muse_keyframe_boxes_replays_the_main_recordings`, `::test_muse_keyframe_boxes_fails_loudly_without_recordings`.
- [x] **SHIP's E6 case**: a participant re-entry in the demo job (the guest steps out 2.3 s and returns): a new ID, disputed, escalated, never auto-kept. Evidence: `tests/test_demo_job.py::test_roles_match_the_scene`.
- [x] **SHIP's interface requests**: prepare rejection reasons `too_long`/`too_large`/`bad_media`/`no_source` with `duration_s`/`size_bytes`; per-code service caps on SENSE calls. Evidence: `tests/test_prepare.py`, `safecut/meta/session.py`.
- [x] **Re-audits**: three full independent audits logged and every finding fixed with a test. Evidence: `.agent/win/SAFECUT-SENSE/reaudit.md`.

## Judging criteria

- [x] **Impact (30)**: the perception lane decides who can be kept; nothing is kept without 3/3 evidence, a child vote always locks, and every miss is covered. Evidence: the invariants above and their hypothesis properties.
- [x] **Use of Meta AI tooling (25)**: SAM 3.1 (per-concept sweeps, object prompts, Meta's own parser), Muse Spark 1.3 (scene, role ×3, escalation at max, miss loop), Muse Voice Transcribe with Spark 1.2 fallback; each has a job nothing else does. Evidence: `safecut/track/`, `safecut/scout/`, `safecut/speech/`.
- [x] **Technical depth (20)**: exact time axes checked against ffmpeg frame by frame; the SAM parser parallelised across processes (32 s → 8.6 s); the demo job recorded through the real stages with a responder seam. Evidence: PR decisions, `tests/test_prepare.py`, `safecut/meta/sam.py`.
- [x] **Demo (25)**: a labelled synthetic demo job that exercises every SENSE behaviour (participants kept, bystander, re-entry, child, screen, plate, a miss found by the loop) and runs offline end to end. Evidence: `fixtures/jobs/demo/`, entry-check `E3: OK`.

## Quality bar (`.agent/briefs/COMMON.md`)

- [x] Unit tests for pure functions; hypothesis where inputs vary; integration at stage boundaries; replay end to end; failure paths (timeouts and rate limits go through WP0's client, tested there; HTTP errors, empty and malformed input, partial results here). Evidence: the test files above.
- [x] Robustness: every external answer schema-validated (pydantic and strict `text.format`), typed errors, no silent fallback (the only fallback, a process pool that can't start, logs and computes the same result).
- [x] Scale: concurrency bounded by WP0's lanes and the process pool; per-job and daily caps through WP0's ledger; masks decoded within a pixel budget. Where it breaks first: Meta's pure-Python mask validation, ≈ 3 µs a pixel (≈ 4–5 min of 4-core CPU for a busy 60 s clip).
- [x] Code quality: pyright strict on `safecut/` and `scripts/`, ruff clean, no TODOs, small modules.
- [x] Honest evidence: synthetic data labelled synthetic everywhere; live cost $0 so far (no key).
