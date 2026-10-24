# Win checklist (PRE-A)

**Purpose:** every judging criterion, every PRE-A deliverable and every audit finding, mapped to the evidence in this branch, so the build waves (from Oct 26 16:00 UTC) can implement without guessing. Named `-PRE-A` so it can't collide with PR #2. **Updated:** 2026-10-24 ~18:00 UTC (loop iteration 1, after two review rounds). Status: ✅ done · 🟡 done, needs a live check (WP0) · 🔴 open.

## 1. Judging criteria → what PRE-A gives the builders
| Criterion (weight) | What wins it (MAXXING §3) | PRE-A evidence | Status |
|---|---|---|---|
| **Impact (30%)** | measured gains vs baselines; pilots | Eval cost plan on PRE-B's 12/3 split, with baselines reusing SAM sweeps (API-NOTES §9.2); prior-art gap table and draft README line (`research/prior-art.md`); SA-Co/VEval mapped to exposure and leak bursts (`research/sa-co-veval.md`) | ✅ (numbers come only from WP7 runs, AGENTS rule 9) |
| **Meta tooling (25%)** | the closed loop; deny-by-default from SAM's limits; 3× self-consistency; EgoBlur audit; Voice Transcribe | SAM grammar, object prompts and confidences (API-NOTES §1); miss loop with **point prompts** (`prompts/miss-loop.md`); rephrased 3× votes (`prompts/role-pass.md`); escalation at `max` (`prompts/escalation.md`); EgoBlur Gen 2 thresholds and resize (`research/egoblur-gen2.md`); ASR request/response (API-NOTES §4) | ✅ / 🟡 (`include_confidence`, object prompts, `max`: WP0 probes) |
| **Technical depth (20%)** | SoM binding, leak guard, locked grid, receipt, replay, eval | One coordinate rule + box convention (API-NOTES §5); time axes (§5b); client spec: timeouts, retries, typed errors, idempotency, cost (§10); test vectors with expected outputs (§11, `prompts/TEST-VECTORS.md`) | ✅ |
| **Demo (25%)** | the hero clips, review panel with reasons, audit catching a leak | Escalation gives the Needs-you card a `suggested_role` plus evidence; red-team tricky cases (mosaic read-through, reflection) are demo-able; demo budget reserve (§9.2) | ✅ (footage: owner, PR #2) |
| **Startup: holds up in production** | caps, deletion, observability, CI | Pre-call worst-case estimates against job and daily caps (§10.5); the $3/day demo cap decision (§9.2); startup probe and `/healthz` (§10.7); circuit breaker (§10.2); Files cleanup and sweeper (§10.4); `store:false` honesty in the receipt (§10.6) | ✅ |

## 2. PRE-A deliverables (`docs/work-packages/PRE-A.md`)
| Deliverable | File | Status |
|---|---|---|
| API notes: SAM 3.1 (video/image, token grammar, mask encodings, Python parser, limits, `input_video.fps`, price) | `API-NOTES.md` §1 | 🟡 (`input_video.fps` and the SAM price on Meta's page: WP0) |
| Files API (purpose, `expires_after`, retrieve, delete, limits) | §2, §10.4, §10.6 | 🟡 (`expires_after` acceptance) |
| Responses (video/image/audio/PDF parts, strict json_schema, `store:false`, effort per model, streaming, errors, rate limits) | §3, §10 | ✅ (effort per the live page) |
| Muse Voice Transcribe (request/response, diarization, timestamps, languages, limits, price) | §4 | ✅ |
| Image understanding (0–1000 grid, edge cases) | §5, §11.2 | 🟡 (`/1000·W` vs `/1000·(W−1)`: probe g) |
| Pricing and rate limits for 5 models | §6 | 🟡 (Spark 1.2 price not found; SAM price is third-party) |
| Data policies (Standard vs Contributor, retention, `store`) | §7 | 🟡 (retention periods: WP0 reads the policy page) |
| Cost model: one 30 s clip; the whole eval plan vs $150 | §9 | ✅ |
| 6 prompt specs (purpose, inputs, v0 text, JSON schema, failure handling, 3 tricky cases) and a link to Meta's prompting guidance | `prompts/*.md` | ✅ |
| `egoblur-gen2.md` (where, licence, gating, files, preprocessing, thresholds, speed, Gen 1 vs 2, owner steps) | `research/` | 🟡 (zip sizes; measured speed: WP4) |
| `sa-co-veval.md` (where, CC BY 4.0, size, format, mapping to EVAL) | `research/` | 🟡 (size: WP7 on download) |
| `modal.md` (plans, credits, pricing, Volumes, cron, secrets, endpoints, cold starts, estimate) | `research/` | 🟡 (Volume limits and cold starts not found) |
| `muse-wonder-vs-spark.md` (capabilities, effort, latency, price, hypotheses) | `research/` | ✅ |
| `prior-art.md` (YouTube, CapCut, Descript, PrivacyVideo, Blurize, EgoBlur, brighter AI) | `research/` | ✅ (two products unidentifiable, which is recorded) |
| PR summary: the 5 facts most likely to change WP0's plan | PR #1 body | ✅ |

## 3. Audit findings → fix → evidence
| Source | Finding | Fix (where) | Status |
|---|---|---|---|
| Owner audit 1 | effort levels wrong | §3.4 per the live reasoning page; escalation `max`; Wonder table | ✅ |
| Owner audit 2 | the `file_` → `file-` request | accept both (§1.1, §10.6) | ✅ |
| Owner audit 3 | reconcile with PR #2 | under 18; §5b time axes **aligned to PR #2's CFR model** (iteration 1); 12/3 split costing; pilot estimate within the $20 cap | ✅ |
| Owner audit 4 | gating facts | EgoBlur email form; SA-Co manual HF approval; `BLOCKED-PRE-A.md` | ✅ |
| Owner audit 5 | prompting-guide placeholder | real links (`prompts/README.md`) | ✅ |
| Owner audit 6 | BLOCKED conflict | `docs/BLOCKED-PRE-A.md` | ✅ |
| Self-review rounds 1–3 | 30 findings (listed in the PR body) | all fixed except one, overridden by the owner's direction | ✅ |
| Iteration 1 (hostile audit) | §5b contradicted PR #2 (VFR prepared clip; times relative to the prepared start; player via `times`; proxy via `times`) | rewritten to PR #2's model: CFR prepared clip, `times` = source seconds, player and proxy by ratio; prepared → label mapping direction; non-decreasing `times` | ✅ |
| Iteration 1 | no client spec (timeouts, retries, idempotency, cost formulas, typed errors) | API-NOTES §10 | ✅ |
| Iteration 1 | no test vectors | §11 (parser-verified SAM vectors; reference-generated grid, time, cost and retry vectors); `prompts/TEST-VECTORS.md` | ✅ |
| Iteration 1 | box convention (inclusive vs half-open) undefined; the parser's `PromptBox` is half-open but the wire format is inclusive | half-open everywhere, converted at the SAM boundary (§5, O2) | ✅ |
| Iteration 1 | round-trip bound wrong | bound `ceil(job.fps / sam_fps_eff)`, brute-forced over 6–30 fps × 6/8/10 proxies × 5–1,800 frames; `sam_fps_eff = min(SAFECUT_SAM_FPS, job.fps)` (§5b) | ✅ |
| Iteration 1 | spec ambiguities: >3-word phrases, the 9th miss item, a point in the bar, read-through remedy | decided in `miss-loop.md` and `redteam.md`; vectors M4, M8, M9, L7 | ✅ |
| Iteration 1, review (ffmpeg-verified) | the proxy mapping and the `times` rule didn't match ffmpeg's `fps` filter (it keeps the **last** frame per slot and repeats on gaps) | §5b rewritten from ffmpeg 6.1.1 output, matched by checksums; T1–T6 regenerated (e.g. proxy 0 → prepared 1, 120 → 451; `times[0]` can be > 0); `job.frames` read back with ffprobe | ✅ |
| Iteration 1, review | `/healthz` reused a paid SAM probe once a minute ($3.60/day, over the $3/day cap) | `/healthz` = one `minimal` text call (≤ $0.13/day); the SAM probe runs only at startup (§10.7) | ✅ |
| Iteration 1, review | retry counts contradicted between §10.2 and the prompt specs; SAM eof was both retried and fail-closed | one policy in §10.2 (the specs refer to it); `max` effort gets 2 attempts; eof → retry, then `MetaIncomplete` (R7–R9) | ✅ |
| Iteration 1, review | failed attempts logged at estimated cost would inflate reported numbers | reservation model: caps are conservative, reports use only measured lines; the receipt shows "possibly billed" separately (§10.2) | ✅ |
| Iteration 1, review | the breaker counted attempts, so one blip failed whole jobs | it counts calls; half-open state; transient failures → `retry_later`, not `failed` | ✅ |
| Iteration 1, review | the 1 h file expiry could hit a live job; a 404 was treated as a config error | 6 h expiry > 2 h job limit; `MetaFileGone` re-uploads once (R10) | ✅ |
| Iteration 1, review | no spec said SAM must get the proxy, not `prepared.mp4` | two named uploads; the request builder takes the proxy's id by name (§10.6) | ✅ |
| Iteration 1, review | §5b contradicted PR #2 on strictly increasing `times` and on the label-mapping direction | decided (non-decreasing; prepared → label); requests to PRE-B in PR #1 | 🟡 (PRE-B to update its two lines) |
| Iteration 1, review | stale `job.times` use in `role-pass.md`; the parser `.result` path; the checklist's file location | fixed; this file is owner-mandated, named like `BLOCKED-PRE-A.md` | ✅ |
| Iteration 1, review 3 | the half-proxy bound failed at other clip lengths; no guard for `job.fps < sam_fps`; speech-fallback's retry count; non-eof `MetaIncomplete` routing; `MetaRateLimited` row; an unclamped turn → frame conversion; immediate 5xx accounting; §3.4 conflated startup and `/healthz`; a rounded-down `/healthz` cost; no count for `high` | all fixed in API-NOTES §3.4, §5b, §10.2–10.7, `speech-fallback.md`, `role-pass.md` | ✅ |

## 4. Open (needs a live check or an owner input, not a guess)
| Item | Covered meanwhile by | Owner |
|---|---|---|
| `dev.meta.ai` unreachable from this sandbox | Meta GitHub sources + the owner's live reads; every fact tagged | owner (allowlist), `BLOCKED-PRE-A.md` |
| SA-Co/VEval access (manual approval) | synthetic loader fixture | owner, now |
| EgoBlur weights (email form) | replay stub of detections | owner, now |
| `MODEL_API_KEY` | replay fixtures; the §9 cost model | owner, at kickoff (PR #2 BLOCKED) |
| Probe-dependent values marked *(probe)* in §10 | conservative defaults given | WP0 |
