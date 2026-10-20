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
 "prepared": "prepared.mp4", "fps": 30.0, "width": 1280, "height": 720, "frames": 900,
 "times": [0.0, 0.0333], "audio": true, "created_at": "2026-10-27T10:00:00Z"}
```

### 3.2 `tracks.json` (track)
```json
{"concepts": ["face", "person", "license plate", "screen", "phone", "document", "name badge"],
 "tracks": [
   {"track_id": "face:7", "concept": "face", "first": 120, "last": 410,
    "boxes": {"120": [x1, y1, x2, y2], "121": [x1, y1, x2, y2]},
    "masks": {"120": "rle:…"},
    "reentry_of": null,
    "source": "sam-3.1", "prompt": "face"}
 ],
 "crowded_frames": [312, 313],
 "requests": [{"concept": "face", "file_id": "file_…", "frames_billed": 900, "usd": 0.18}]}
```
`reentry_of` is informational only: a re-acquired object is ALWAYS a new `track_id` and starts hidden (DESIGN §2.5).

### 3.3 `transcript.json` (speech)
```json
{"source": "muse-voice-transcribe-1.0",
 "turns": [{"speaker": "S1", "start": 0.4, "end": 3.1, "text": "Hi, I'm Amina, and today…"}]}
```

### 3.4 `scene.json` (scout, scene pass)
```json
{"model": "muse-wonder-1.0", "summary": "street interview…",
 "participants": [{"description": "woman in yellow jacket", "evidence": "introduced as Amina by S1 at 0.4s", "speaker": "S2"}],
 "candidate_objects": [{"what": "phone screen showing a chat", "approx_time": "mid-clip"}]}
```

### 3.5 `roles.json` (scout, role pass)
This is the same shape as DESIGN §2.3, plus vote detail:
```json
{"tracks": [{"track_id": "face:7", "role": "participant|bystander|child|unsure",
             "votes": ["participant", "participant", "participant"], "escalated": false,
             "evidence": "introduced at frame 90, speaks to camera 120–600", "frames": [90, 120, 150]}],
 "objects": [{"track_id": "screen:2", "sensitive": true, "content": "email inbox with names", "frames": [300]}],
 "missed": [{"what": "addressed envelope", "sam_phrase": "envelope", "frame": 420, "point": {"x": 512, "y": 640}}],
 "keyframes": ["som/000090.jpg"]}
```

### 3.6 `decisions.json` (decide)
```json
{"items": [{"item_id": "i_3", "track_ids": ["face:7", "person:2"], "kind": "person|child|plate|screen|document|other",
            "decision": "hide|keep|needs_you", "reason": "bystander: walks behind guest, never addresses camera",
            "evidence_frames": [150, 300], "style": "solid|pixelate|person_solid",
            "decided_by": "policy|model|creator", "locked": false}]}
```
Children are `locked: true` and `hide`; the creator can't un-hide them (DESIGN §2.5). `needs_you` renders hidden until the creator decides.

### 3.7 `plan.json` (guard)
```json
{"padding": {"face": 0.15, "default": 0.08, "px": 8}, "temporal": {"extend": 8, "backfill": 15, "gap_hold_s": 2.0},
 "frames": {"150": [{"item_id": "i_3", "shape": "box|mask", "box": [x1, y1, x2, y2], "mask": null, "style": "solid", "grid": [gx, gy, cell]}]},
 "crowd_fills": [{"frames": [312, 313], "box": [0, 0, 1280, 400]}]}
```
`grid` locks the pixelation grid to the item's track box so it doesn't shift between frames (DESIGN §2.7).

### 3.8 `audit.json` (audit)
```json
{"frames_scanned": 900, "egoblur": {"model": "egoblur-gen2", "faces": 0, "plates": 0},
 "leaks": [{"frame": 401, "box": [x1, y1, x2, y2], "kind": "face", "detector": "egoblur|redteam", "patched_item": "i_9"}],
 "redteam": [{"frame": 450, "finding": "none"}], "unresolved": 0, "passes": 2}
```
Publishing is allowed only when `unresolved == 0`.

### 3.9 `receipt.json` + `receipt.html` (receipt)
```json
{"job_id": "j_01", "items": [/* decisions.items + thumbnail paths */], "audit": {/* audit summary */},
 "models": {"scene": "muse-wonder-1.0", "roles": "muse-spark-1.3", "sam": "sam-3.1", "asr": "muse-voice-transcribe-1.0"},
 "data_handling": {"mode": "standard", "store": false, "files_deleted": true},
 "approved_by": "creator", "approved_at": "…", "cost_usd": 0.91,
 "prev_hash": "…", "hash": "sha256(prev_hash + canonical_json(body))"}
```

### 3.10 `cost.jsonl`
One line per API call: `{"ts", "stage", "model", "units", "usd", "request_id"}`. The pipeline refuses to start a stage that would exceed `SAFECUT_JOB_USD_CAP`.

## 4. Models and config (env, with defaults in `safecut/config.py`)

| Env | Default | Used for | Why |
|---|---|---|---|
| `SAFECUT_SAM_MODEL` | `sam-3.1` | tracking per concept | the only segmentation model; detections straight from the stream |
| `SAFECUT_ROLE_MODEL` | `muse-spark-1.3` | role pass ×3 on SoM keyframes, red-team | high volume; image input; structured output |
| `SAFECUT_SCENE_MODEL` | `muse-spark-1.3` | scene pass on the whole clip (video) | switch to `muse-wonder-1.0` if the D1 probe shows it's better (WP0 decides and records why) |
| `SAFECUT_ESCALATE_MODEL` | `muse-spark-1.3` (`reasoning.effort: max`) | disputed tracks, once | same as above: Wonder only if probes justify it |
| `SAFECUT_ASR_MODEL` | `muse-voice-transcribe-1.0` | diarized transcript with turn timestamps | Meta's docs say Muse Spark 1.3 audio is **degraded**, and speech ("Hi, I'm Amina") is key participant evidence. Fallback: `SAFECUT_SPEECH_SOURCE=spark-1.2` |
| `SAFECUT_JOB_USD_CAP` | `2.00` | per-clip spend guard | |
| `SAFECUT_DAILY_USD_CAP` | `10.00` | service-wide guard for the public demo | |
| `MODEL_API_KEY` | none | Meta Model API key | secret; never logged |

Endpoint: `https://api.meta.ai/v1` (OpenAI-compatible Responses, Files, ASR). The owner's design choice was depth with a few models, not a tour. Every model above does a job nothing else in the stack can do, and the README must say what each one is for.

## 5. Runtime and deployment

- **API + worker:** Modal (`deploy/modal_app.py`), CPU containers with ffmpeg, plus a small GPU function for EgoBlur if CPU is too slow (measure first). Job artifacts go in a Modal Volume and are **deleted 24 h after the job** (a cron). Uploads go through a presigned URL straight to storage, capped at ≤60 s and ≤150 MB.
- **Web:** Next.js on Vercel at a custom domain (the owner's Vercel team blocks public `*.vercel.app` aliases). The owner and Claude set the domain and env.
- **Public demo:** the landing page plays the precomputed hero results (labelled). "Try it" needs a judge access code (`SAFECUT_ACCESS_CODES`), is rate-limited per IP, and stops at `SAFECUT_DAILY_USD_CAP`.
- **Replay mode** (`SAFECUT_REPLAY=1`): stages read saved API responses from the job directory instead of calling Meta. It's used for tests, the live-finals fallback (labelled "demo mode"), and cost-free UI work.
- **Observability:** structured logs with job ID and stage timings, `cost.jsonl`, and a `/healthz` endpoint that checks the Meta API with a 1-token call at most once a minute.
- **CI:** GitHub Actions (free for public repos) runs ruff + pytest + web lint/typecheck/test on every PR, and deploys Modal from `main` once WP5 lands.
