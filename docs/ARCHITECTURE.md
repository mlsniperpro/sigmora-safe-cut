# Safe Cut: standalone architecture

This supersedes the file paths in `DESIGN.md` §3, which assumed the code would live inside Sigmora. The pipeline, the principles (deny by default, Set-of-Mark role calls, the leak guard, solid or locked-grid redaction, the audit) and the metrics are unchanged.

## 1. Why standalone

- **Scored work must be visibly new and dated.** It lives in this public MIT repo from Oct 26.
- **Each cloud agent sees one repo.** Everything a work package needs is here.
- **Production on the Startup track:** a deployable service with an API, a review web app, and a CLI, which Sigmora (and anyone else) calls over HTTP.

## 2. Layout

```
safecut/                 Python 3.12 package (uv); the pipeline
  config.py              env-driven settings: model IDs, padding, budgets (WP0)
  contracts.py           pydantic models for every JSON in §3 (WP0)
  meta/                  Meta Model API client: files, responses, SAM stream parser, cost log (WP0 base, WP1/WP2 extend)
  open_weight.py         open-weight second opinion: Muse Spark Open on Baseten, PRE-A §3.8 (WP0; WP4 calls it)
  prepare.py             probe, transcode to H.264 ≤1280 px, per-frame times, keyframes (WP1)
  track/                 SAM 3.1 sweeps per concept → tracks.json; link, densify, re-entry = new ID (WP1)
  speech/                Muse Voice Transcribe → transcript.json (diarized turns); spark-1.2 audio fallback (WP2)
  scout/                 scene pass, Set-of-Mark keyframes, role pass ×3, escalation, miss loop (WP2)
  decide/                policy (pure) + point/track binding (WP3)
  guard/                 leak guard: spatial/temporal padding, gap hold, crowd fallback → plan.json (WP3)
  render/                solid / locked-grid pixelate / whole-person mask, audio mux (WP4)
  audit/                 EgoBlur Gen 2 + Muse Spark red-team → audit.json, auto-patch loop (WP4)
  receipt/               privacy receipt JSON + HTML, hash chain (WP4)
  pipeline.py            stage orchestration over a job directory; replay mode (WP5)
  api/                   FastAPI service: jobs, review decisions, render, receipt (WP5)
  cli.py                 `safecut run|prepare|track|…` (WP5; each WP adds its own subcommand)
deploy/modal_app.py      the API + worker on Modal (WP5)
web/                     Next.js review app + landing/demo page (WP6)
eval/                    harness, metrics, baselines, results/<run-id>/ (WP7)
fixtures/                consented-clip API responses + tiny synthetic clips for tests (WP0, all WPs add)
tests/                   pytest; `-m live` marks real API calls
```

## 3. Data contracts (one job directory per clip)

Every stage reads and writes plain JSON in `jobs/<job_id>/`. That lets each WP develop and test against fixtures without the others, and replay mode re-runs any stage from saved inputs. All coordinates are in **pixels of the prepared clip**. Frames are 0-based indices into the prepared clip.

### 3.1 `job.json` (prepare)
```json
{"job_id": "j_01", "source": "SC-A-01.mp4", "source_sha256": "…",
 "prepared": "prepared.mp4", "fps": 30, "width": 1280, "height": 720, "frames": 900,
 "times": [0.0, 0.0333, /* … one per frame: 900 in all */], "audio": true, "created_at": "2026-10-27T10:00:00Z", "consented": false,
 "open_weight_attempted": false}
```

### 3.2 `tracks.json` (track)
```json
{"concepts": ["face", "person", "license plate", "screen", "phone", "document", "name badge"],
 "tracks": [
   {"track_id": "face:7", "concept": "face", "first": 121, "last": 410,
    "boxes": {"121": [x1, y1, x2, y2], "122": [x1, y1, x2, y2], /* … one per frame to 410 (densified) */},
    "masks": {"121": {"size": [720, 1280], "counts": "…"}},
    "reentry_of": null,
    "source": "sam-3.1", "prompt": "face", "origin": "sam",
    "sam_object": {"request": 0, "object_id": "3"}, "child_phrase": false, "conf": {"121": 0.91}}
 ],
 "sam_fps": 8, "sam_frames": 240,
 "crowded_frames": [310, 311, 312, 313, 314, 315],
 "requests": [{"kind": "phrase", "concept": "face", "file_id": "file_…", "fps": 8, "frames_billed": 240, "matches": 4, "usd": 0.048}]}
```
`reentry_of` is informational only: a re-acquired object is ALWAYS a new `track_id` and starts hidden (DESIGN §2.5).

### 3.3 `transcript.json` (speech)
```json
{"status": "ok", "source": "muse-voice-transcribe-1.0", "source_kind": "primary", "degraded": false,
 "turns": [{"speaker": "S1", "start": 0.4, "end": 3.1, "text": "Hi, I'm Amina, and today…"}]}
```

### 3.4 `scene.json` (scout, scene pass)
```json
{"status": "ok", "model": "muse-spark-1.3", "summary": "street interview…",
 "participants": [{"description": "woman in yellow jacket", "evidence": "introduced herself as Amina (S1) at 0.4s", "speaker": "S1",
                   "is_creator": false, "introduced_in_turn": 0, "introduction_quote": "I'm Amina"}],
 "candidate_objects": [{"what": "phone screen showing a chat", "approx_time": "middle"}],
 "children": [], "others_present": ""}
```

### 3.5 `roles.json` (scout, role pass)
This is the same shape as DESIGN §2.3, plus vote detail:
```json
{"status": "ok", "model": "muse-spark-1.3",
 "tracks": [{"track_id": "face:7", "role": "participant|bystander|child|unsure",
             "votes": ["bystander", "bystander", "bystander"], "escalated": false,
             "evidence": "walks behind the guest at frames 150–300, never addresses camera", "frames": [150, 300],
             "failed_votes": 0, "matches_participant": null, "suggested_role": null,
             "escalation_evidence": null, "escalation_frames": null}],
 "objects": [{"track_id": "screen:2", "sensitive": true, "content": "email inbox with names", "frames": [300]}],
 "missed": [{"what": "addressed envelope", "sam_phrase": "envelope", "frame": 420, "point": {"x": 512, "y": 640},
             "box": null, "recurs": false, "track_ids": []}],
 "keyframes": ["som/000150.jpg", "som/000300.jpg"]}
```

### 3.6 `decisions.json` (decide)
```json
{"items": [{"item_id": "i_3", "track_ids": ["face:7", "person:2"], "kind": "person|child|plate|screen|document|other",
            "decision": "hide|keep|needs_you", "reason": "bystander: walks behind guest, never addresses camera",
            "evidence_frames": [150, 300], "style": "solid|pixelate|person_solid",
            "decided_by": "policy|model|creator", "locked": false,
            "hold": null, "origin": "sam", "audit_label": null}]}
```
Children are `locked: true` and `hide`; the creator can't un-hide them (DESIGN §2.5). `needs_you` renders hidden until the creator decides.

### 3.7 `plan.json` (guard)
```json
{"padding": {"face": 0.15, "default": 0.08, "px": 8}, "temporal": {"extend": 8, "backfill": 57, "gap_hold_s": 2.0},
 "frames": {"150": [{"item_id": "i_3", "shape": "box|mask", "box": [x1, y1, x2, y2], "mask": null, "style": "solid", "grid": null, "source": "decision"}]},
 "crowd_fills": [{"frames": [310, 311, 312, 313, 314, 315], "box": [0, 0, 1280, 400]}]}
```
`grid` locks the pixelation grid to the item's track box so it doesn't shift between frames (DESIGN §2.7): it is `[x0, y0, cell_px]`, the grid origin (the track box's top-left, fixed for the item) and the cell size in pixels, set only when `style` is `pixelate`. Only faces and people are ever pixelated (text, screens, plates and documents are always solid, DESIGN §2.7), and the cell is large enough that a face spans ≤ 6 blocks across. `temporal.backfill` is in prepared frames, `ceil(15 × job.fps / sam_fps)` (PRE-A §5b, T10: 57 at 30 → 8 fps). Each entry renders its decision's `style`, except that a flagged leak's `through_item` renders solid once re-planned; audit-patch entries carry `source: "audit_patch"`.

### 3.8 `audit.json` (audit)
```json
{"frames_scanned": 900, "egoblur": {"model": "egoblur-gen2", "faces": 1, "plates": 0},
 "leaks": [{"frame": 401, "box": [x1, y1, x2, y2], "kind": "face", "detector": "egoblur|redteam|redteam_open", "patched_item": "p_1"}],
 "redteam": [{"frame": 0, "finding": "none"}, {"frame": 30, "finding": "none"}, /* … one entry per frame sent: pass 1's full 1 fps set (≥ frames // sample_step = 30 frames), kept across later passes */],
 "unresolved": 0, "passes": 2,
 "sample_step": 30, "spots": [], "blocked_reason": null, "audit_budget_cause": null,
 "open_weight": {"model": null, "status": "off", "frames": 0, "findings": 0}, "redteam_open": []}
```
Publishing is allowed only when `unresolved == 0`.

### 3.9 `receipt.json` + `receipt.html` (receipt)
```json
{"job_id": "j_01",
 "items": [{/* every decisions.items field, compared one by one */ "item_id": "i_1", …, "thumbnail": "thumbs/i_1.jpg"}],
 "audit": {"auditor": "egoblur-gen2", "frames_scanned": 900, "leaks_found": 1, "leaks_patched": 1, "unresolved": 0,
           "passes": 2, "blocked_reason": null},
 "models": {"scene": "muse-spark-1.3", "roles": "muse-spark-1.3", "sam": "sam-3.1", "asr": "muse-voice-transcribe-1.0",
            "redteam": "muse-spark-1.3", "auditor": "egoblur-gen2"},
 "data_handling": {"mode": "standard", "store": false,
                   "store_by_model": {"muse-spark-1.3": false, "sam-3.1": false},
                   "no_store_param": ["muse-voice-transcribe-1.0"], "files_deleted": true,
                   "responses_delete_requested": 0, "notes": []},
 "approved_by": "creator", "approved_at": "…", "cost_usd": 0.91, "cost_usd_estimated": 0,
 "cost_usd_baseten": 0, "prev_hash": "…", "hash": "sha256(prev_hash + canonical_json(body))"}
```

### 3.10 `cost.jsonl`
One line per API attempt: `{"ts", "provider", "job_id", "stage", "model", "attempt", "units", "usd", "estimated", "request_id", "cap", "code_kind", "code_id"}`. `estimated: true` marks an attempt whose billing is unknown (accepted, then lost); reported figures sum only `estimated: false` lines. A call whose worst-case estimate doesn't fit a cap is never sent and writes one `budget:<stage>` line naming the `cap`. `job_id` is null only on `system` lines (`/healthz`, the startup probe).

### 3.11 `files.json`
A JSON array, one entry per upload: `[{"name": "sam_proxy.mp4", "sha256": "…", "file_id": "file-…", "purpose": "user_data", "created_at": "…Z", "deleted_at": null, "orphan": false}]`. Written before the file is used; `deleted_at` is set when `DELETE /v1/files/{id}` succeeds (or answers `file_not_found`). An upload that may have left a copy without an ID (a cancel, a timeout, any failed attempt but a breaker refusal, even one followed by a successful retry) adds a `file_id: null, orphan: true` entry, because a copy can land after the immediate listing; the orphan is resolved (`deleted_at` set) once a `/files` listing found and deleted every unrecorded copy of its name (`FileStore.reconcile_orphans`, run by `delete_all`). `files_deleted: true` needs every entry, orphans included, to have `deleted_at` set.

### 3.12 `responses.json`
Only when SAM is called without `store: false` (`SAFECUT_SAM_SEND_STORE=false`): `[{"response_id": "resp_…", "requested_at": null}]`. The SAM client appends each response ID the moment the stream names it (`response.created`), on every attempt, before parsing (`sam.ResponseLog.note`; an ID that isn't a plain token is refused, and one that can't be written is kept in memory); after parsing, `ResponseLog.delete_pending` sends `DELETE /v1/responses/{id}` and sets `requested_at` (a 404 with an error body counts as done; an empty-body 404 means a wrong path and stays pending). A failed DELETE stays `null` for the cancel sweep and the hourly sweeper. The receipt's `data_handling.responses_delete_requested` counts the entries with `requested_at` set; Meta soft-deletes, so the receipt says "deletion requested", never "deleted".

**Types and rules** live in `safecut/contracts.py` (PRE-A §12 implemented): boxes are int, half-open and non-empty; a frame side (`job.width`/`height`, a mask's `size`) is at most 8192 px; an item id starts with `p_` exactly when it's an audit patch; an `egoblur` plate leak needs `egoblur.plates` non-null; a non-empty `responses.json` needs the SAM model in `no_store_param` (PRE-A §10.6) or `store_by_model` true, never false; `job.fps` is an int 1–30 and `times` is non-decreasing; masks are frame-sized COCO RLE objects; `status` fields are `ok|failed|skipped`; children are always locked hides, an item over a `child_phrase` track is a child (WP3 rule 0), and an item whose track `roles.json` rules a child is never kept; an `audit_patch` item carries `box`/`first`/`last` and an `A<n>` label; `blocked_reason` is set exactly when `unresolved > 0`. In `audit.json`: every leak is patched (`patched_item`) or `unresolved`, and a flag alone fixes nothing; `through_item` is set exactly on a flagged leak; an unflagged leak's `patched_item` is an audit patch (a flagged leak's may instead be its own `through_item`, re-rendered solid); a leak's patch and `through_item`, and a spot's `covered_by`, are hidden items that hide the leak's (or spot's) frames, where the item exists or the plan renders it (extend and backfill included), and its region (an unflagged leak's own audit patch contains its box, as does a spot's cover, judged on the boxes `plan.json` renders on that frame when a plan is present; otherwise, for a flag or a `through_item`, the item's planned region on that frame overlaps it, any positive area); `unresolved` counts at least the unresolved leaks plus every frame not in `frames_scanned`, summed (≤ `job.frames`), and a publishable audit ran at least one pass and has `sample_step == job.fps` (PRE-A §12) and a `redteam` entry in every whole second of the clip (1 per second, any phase); an audit patch is solid, decided by `policy`, with one evidence frame inside its span; a flagged leak that isn't unresolved has its `through_item` rendered solid on every `plan.json` frame; every `redteam` hit has its own `detector: "redteam"` leak overlapping its box on its frame unless it's `excluded_by` a kept item through one of its tracks on that frame whose concept matches the hit's kind (redteam.md: face→`face`, person→`person`, text/screen→any other concept, plate→`license plate`; `misaligned_redaction`/`other` never) and whose box there overlaps the hit (`redteam_open` stays advisory until `SAFECUT_OPEN_WEIGHT_GRID_OK`, and its entries, copied verbatim into a re-run's audit by redteam.md, aren't held to today's decisions beyond naming an existing item); `open_weight.frames`/`findings` match the `redteam_open` entries; a spot's boxes lie within its `first..last`. In `plan.json`: every `hide`/`needs_you` item is planned on each of its tracks' `first − backfill … last + extend` (clamped; an audit patch: its `first..last`), where a crowd fill containing the track's box also counts; the gap between a merged item's tracks needs nothing beyond that; each track box on a planned frame, grown by half its kind's `padding` ratio (`face` for face tracks, else `default`) of its size each side plus `padding.px` (the reading of DESIGN §2.6's "15 % + 8 px" that refuses no valid guard), lies inside one of its item's box entries (or the box inside a crowd fill; a mask entry's foreground spans ≥ 80 % of the box's width and height and fills ≥ 25 % of its area); a pixelated item has a face track; a pixelate cell keeps a `face` track inside its entry ≤ 6 blocks across, and each track keeps one grid that holds it on every frame (in a merged item another track's entry may hold it too); every `tracks.crowded_frames` frame has a crowd fill; `temporal.backfill` is `ceil(15 × job.fps / sam_fps)`, with `tracks.sam_fps` the effective proxy rate `min(SAFECUT_SAM_FPS, job.fps)`; `padding` is at least DESIGN §2.6's 15 %/8 % + 8 px and `temporal.extend` at least 8; back-fill, extend and audit-patch frames cover their held box; on a crowded frame where a concept reached SAM's 16-object cap, each of its hidden objects lies inside some crowd fill (tiles allowed); on a frame with no entry, crowd fills must contain every track box of the item. The receipt's `models` and `audit.auditor` match the job files that recorded them (scene, roles, transcript source, `audit.egoblur.model`), `models` names every Meta model `cost.jsonl` billed (a line with `usd > 0` or `estimated`; budget lines aside) — so a Voice Transcribe call billed (or charged its estimate) before the Spark fallback ran keeps its `asr` key and store claim beside `speech_fallback`, since the audio did reach it —, and `data_handling` states the store setting of each (Voice Transcribe in `no_store_param`, never `store_by_model`; besides it, `no_store_param` may hold only SAM, and only when `responses.json` shows SAM ran without `store`, PRE-A §10.6, and the open-weight model, a Baseten call with no `store` field, which may also be named in `models` with no claim at all but never `store_by_model`), and of every other non-auditor model in `models`; `roles.json` tracks carry exactly three votes. Across `tracks.json` and `decisions.json`: every track is in exactly one item (deny by default); an item is `static` exactly when all its tracks are; nothing but a creator keeps a non-face, non-person, re-entered (`reentry_of`) or static track; a `keep` not decided by the creator (with `roles.json` present) is a `person` item whose every track has a `roles.json` row with role `participant`, three `participant` votes, `failed_votes: 0` and ≥ 2 distinct cited frames, carries no `hold`, and respects PRE-A §12's holds (the scene pass ran; with audio, a usable transcript and each track's speech or introduction evidence; no unmatched scene child); a non-excluded red-team text, screen or plate hit (or a `redteam_open` one with its own leak) on a hidden decision item's planned region (not the audit patch drawn for it) has a flagged (`redaction_too_weak`) leak; an audit patch spans at least `f ± (ceil(sample_step / 2) + extend)` around its evidence frame, clamped; an open-weight opinion needs `job.consented` and `open_weight_attempted`, and so does any non-budget `provider: "baseten"` cost line (also an owner or recording code, with the opinion not `off`); an `egoblur` leak needs `egoblur.faces` non-null; `over_budget` is backed by a Meta `budget:` line in the job's `cost.jsonl` (a Baseten stop never blocks); `blocked_reason` follows over_budget > audit_failed > unresolved_leaks (unscanned frames are never `unresolved_leaks`); frames between a track's anchors have an entry near the interpolated box or either anchor (a mask entry's foreground filling a tenth of it); `matches_participant` is set only on a unanimous participant; a `reentry_of` names a track that ended before the re-entry starts; with `files.json`, every SAM request's `file_id` is `sam_proxy.mp4`'s. Path fields (`job.prepared`, `roles.keyframes[]`, `receipt.items[].thumbnail`) are job-relative: no absolute path, `..` segment, backslash or NUL (`job.source` is the upload's own name and only rejects `..` and NUL). `validate_job_dir` cross-checks the files: `job_id` equals the directory name (as given, so a symlinked job dir keeps its own); IDs, frames and boxes in roles, decisions (including audit patches), plan and audit spots exist in the files they point at; and the receipt agrees with the job (`job_id`, every item field except `thumbnail` compared item by item with `decisions.json`, audit counts, `files_deleted` vs `files.json`, and `cost_usd`/`cost_usd_estimated`/`cost_usd_baseten` vs the Meta and Baseten totals of `cost.jsonl` when present, which holds only this job's lines). `fixtures/contracts/j_example/` is a complete, cross-checked job directory.

## 4. Models and config (env, with defaults in `safecut/config.py`)

| Env | Default | Used for | Why |
|---|---|---|---|
| `SAFECUT_SAM_MODEL` | `sam-3.1` | tracking per concept | the only segmentation model; detections straight from the stream |
| `SAFECUT_ROLE_MODEL` | `muse-spark-1.3` | role pass ×3 on SoM keyframes, red-team | high volume; image input; structured output |
| `SAFECUT_SCENE_MODEL` | `muse-spark-1.3` | scene pass on the whole clip (video) | switch to `muse-wonder-1.0` if the D1 probe shows it's better (WP0 decides and records why) |
| `SAFECUT_ESCALATE_MODEL` | `muse-spark-1.3` (`reasoning.effort: max`) | disputed tracks, once | same as above: Wonder only if probes justify it |
| `SAFECUT_ASR_MODEL` | `muse-voice-transcribe-1.0` | diarized transcript with turn timestamps | Meta's docs say Muse Spark 1.3 audio is **degraded**, and speech ("Hi, I'm Amina") is key participant evidence. Fallback: `SAFECUT_SPEECH_SOURCE=spark-1.2` |
| `SAFECUT_JOB_USD_CAP` | `3.00` | per-clip spend guard | a busy 60 s clip models at $2.09 (PRE-A §9.1) |
| `SAFECUT_DAILY_USD_CAP` | `3.00` | public and judge codes, service keys, `/healthz` | PRE-A §9.2 |
| `SAFECUT_SAM_FPS` | `8` | SAM proxy frame rate (1–10) | PRE-A §5b |
| `SAFECUT_SPEECH_FALLBACK_MODEL` / `_EFFORT` | `muse-spark-1.2` / `omit` | speech fallback through the video soundtrack | PRE-A §3.4 |
| `SAFECUT_ROLE_EFFORT`, `SAFECUT_SCENE_EFFORT`, `SAFECUT_REDTEAM_MODEL`, `SAFECUT_REDTEAM_EFFORT` | `medium`, `medium`, `muse-spark-1.3`, `medium` | efforts per pass | every effort is validated; `none` is refused (Meta returns 400) |
| `SAFECUT_OPEN_WEIGHT_AUDIT`, `_MODEL`, `_BASE_URL`, `_EFFORT`, `_JOB_USD_CAP`, `_PRICE`, `_GRID_OK`, `_CODE_KINDS` | `off`, `meta-models/muse-spark-open-1026`, `https://inference.baseten.co/v1`, `medium`, `0.50`, none, `false`, `[]` | the open-weight second opinion in the audit (Muse Spark Open on Baseten, PRE-A §3.8) | Baseten credits, outside the $150; `provider: "baseten"` cost lines; key in `BASETEN_API_KEY` |
| `SAFECUT_SAM_SEND_STORE`, `SAFECUT_SAM_DELETE_RESPONSES` | `true`, unset (= on exactly when `SAM_SEND_STORE` is `false`) | whether SAM is sent `store: false`; if it can't be, delete each SAM response after parsing (§3.12). `SAM_SEND_STORE=false` with `SAM_DELETE_RESPONSES=false` is refused at load (stored responses must be deleted) | AGENTS rule 6; PRE-A §10.6 |
| `MODEL_API_KEY` | none | Meta Model API key | secret; never logged; stripped at load, and a key with inner whitespace or non-ASCII characters is refused (it would fail every call unsent) |

The full list (access codes, code windows, pilot and recording caps, R2 storage, EgoBlur, the test line) is in `safecut/config.py` and `.env.example`; PRE-A §12 explains each.

Endpoint: `https://api.meta.ai/v1` (OpenAI-compatible Responses, Files, ASR). The owner's design choice was depth with a few models, not a tour. Every model above does a job nothing else in the stack can do, and the README must say what each one is for.

## 5. Runtime and deployment

- **API + worker:** Modal (`deploy/modal_app.py`), CPU containers with ffmpeg, plus a small GPU function for EgoBlur if CPU is too slow (measure first). Job artifacts go in a Modal Volume and are **deleted 24 h after the job** (a cron). Uploads go through a presigned URL straight to storage, capped at ≤60 s and ≤150 MB.
- **Web:** Next.js on Vercel at a custom domain (the owner's Vercel team blocks public `*.vercel.app` aliases). The owner and Claude set the domain and env.
- **Public demo:** the landing page plays the precomputed hero results (labelled). "Try it" needs a judge access code (`SAFECUT_ACCESS_CODES`), is rate-limited per IP, and stops at `SAFECUT_DAILY_USD_CAP`.
- **Replay mode** (`SAFECUT_REPLAY=1`): stages read saved API responses from the job directory instead of calling Meta. It's used for tests, the live-finals fallback (labelled "demo mode"), and cost-free UI work.
- **Observability:** structured logs with job ID and stage timings, `cost.jsonl`, and a `/healthz` endpoint that checks the Meta API with a minimal call (`max_output_tokens: 16`, the documented minimum) at most once a minute (once every 5 minutes before Nov 5 00:00 UTC; PRE-A §10.7).
- **CI:** GitHub Actions (free for public repos) runs ruff + pytest + web lint/typecheck/test on every PR, and deploys Modal from `main` once WP5 lands.
