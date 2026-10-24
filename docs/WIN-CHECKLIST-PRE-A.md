# Win checklist (PRE-A)

Every PRE-A deliverable, judging criterion and audit finding, mapped to evidence on this branch. Legend:
- `- [x]` done, with the evidence named;
- `- [P]` done as far as documents can go, pending a **live check at kickoff** (WP0/WP4/WP7) or an **owner input** listed in `docs/BLOCKED-PRE-A.md`. The pending part and the fallback are named on the line;
- `- [-]` not applicable, or superseded (the reason is named).

Named `-PRE-A` so it can't collide with PR #2. **Updated:** 2026-10-24.

## 1. PRE-A deliverables (`docs/work-packages/PRE-A.md`)
- [x] API notes: SAM 3.1 video/image requests, token grammar, mask encodings, Python parser, limits: `API-NOTES.md` §1 (sources: `meta-sam/protocol/sam3.md` @ `4031897`, cookbook @ `0a99b98`; parser outputs verified by running `meta-sam-parser` 0.1.0, §11.1)
- [P] SAM `input_video.fps` field and the SAM price on Meta's own page: §1.6–1.7. Both are undocumented in the reachable sources. The budget uses the third-party $0.20/1k frames and assumes every uploaded frame is billed (§10.5). Pending: WP0 probe b and a re-read of the pricing page (allowlist, BLOCKED)
- [x] Files API (purpose, `expires_after`, retrieve, delete, limits, idempotency): §2, §10.4, §10.6
- [P] `expires_after` acceptance and the response bodies: §10.6 *(probe)*. Fallback: explicit delete plus the 6 h sweeper (§10.4)
- [x] Responses: input parts, strict `text.format`, `store:false`, effort per model (live reasoning page), streaming, errors, rate-limit headers, caching: §3, §10
- [x] Muse Voice Transcribe request/response, modes, diarization, limits, price: §4
- [x] Image understanding 0–1000 grid and its edge cases: §5, vectors G1–G11
- [P] Whether the grid means `/1000·W` or `/1000·(W−1)` (under 1.3 px apart): §5. Pending: WP0 probe g
- [x] Pricing and rate limits table: §6
- [P] `muse-spark-1.2` price: not found in any reachable source, so §6 assumes it equals 1.3. Pending: the pricing page (allowlist)
- [x] Data policies (Standard vs Contributor, `store`): §7, with the receipt's `store_by_model` (§12)
- [P] Standard-mode retention periods: not found. Pending: WP0 reads the policy page (allowlist)
- [x] Cost model for one 30 s clip and for the whole eval plan vs $150: §9 (v3: $1.12 per 30 s clip at 8 fps, $1.91–1.99 per 60 s clip; $126.65 planned on PRE-B's 12/3 split, with the pilot cap and a Nov 4–9 demo reserve; $23.35 headroom)
- [x] Six prompt specs (purpose, inputs, v0 prompt, strict JSON schema, failure handling, 3 tricky cases): `prompts/*.md`, plus `prompts/TEST-VECTORS.md`
- [x] Link to Meta's prompting guidance: `prompts/README.md`
- [x] `research/egoblur-gen2.md`: where, licence, gating (email form), files, preprocessing (BGR), thresholds, NMS defaults (0.5 Gen 2 / 0.3 Gen 1), speed, Gen 1 vs Gen 2, install pins, detector API, owner steps
- [P] EgoBlur zip sizes and measured speed: pending the owner's weights request (BLOCKED) and WP4's measurement. The replay stub covers it meanwhile
- [x] `research/sa-co-veval.md`: where, CC BY 4.0, gating (manual HF approval), format, loader spec (XYWH, per-frame nulls, uncompressed RLE, 6 fps, scaling to prepared pixels), mapping to EVAL
- [P] SA-Co/VEval size and the privacy-phrase category names: pending HF access (BLOCKED). The synthetic loader fixture covers it meanwhile
- [x] `research/modal.md`: plans, credits, prices, endpoints, cron, secrets, Volumes, the per-clip estimate, and **API names verified from `modal` 1.6.2**
- [P] Modal Volume limits and cold-start numbers: not found; WP5 measures them
- [x] `research/muse-wonder-vs-spark.md`: capabilities, effort (live page), price, hypotheses H1–H7, and the adoption bar
- [x] `research/prior-art.md`: YouTube, CapCut, Descript, PrivacyVideo/Blurize (unidentifiable, which is recorded), EgoBlur, brighter AI, the SAM 3 tutorial, choose-to-keep apps, enterprise audit trails
- [x] PR summary: the 5 facts most likely to change WP0's plan (PR #1 body)
- [x] Owner-input checklist: `docs/BLOCKED-PRE-A.md`, with only owner inputs, each with its stub or replay path

## 2. Build-readiness (owner win mandate)
- [x] Exact request and response shapes for SAM, Responses, Files and ASR: §1, §4, §10.6
- [x] Timeouts, retries (attempt counts by effort), `Retry-After`, the throttle, the circuit breaker: §10.1–10.2
- [x] Typed errors and stage routing (`retry_later` vs `failed`, fail closed): §10.3
- [x] Idempotency and file cleanup: §10.4 and the `files.json` contract (§12)
- [x] Cost formulas, pre-call reservation, honest reporting: §10.5, §10.2
- [x] Startup probe and `/healthz` (≤ $0.134/day): §10.7
- [x] Time and frame axes, ffmpeg-verified: constant-frame-rate prepared clip, the `fps`-filter slot rule, start normalisation, exact rational times, SAM-frame parameter scaling: §5b
- [x] Coordinate rule and the half-open box convention: §5
- [x] One contract-change table (fields, defaults, writer → reader): §12
- [x] Test vectors with expected outputs: §11 (S1–S7, O1–O3 from the parser; G1–G14; T1–T6, T9, T10 checked against ffmpeg; C1–C8; R1–R12) and `prompts/TEST-VECTORS.md` (A1–A13, B, E, M, L1–L9)

## 3. Judging criteria → evidence
- [x] **Impact (30%):** the eval plan cost on the final split (§9.2); baselines named the way judges expect, i.e. the public "SAM blur-everything" approach (`research/winning-patterns.md` R1); prior-art gap (`research/prior-art.md`); SA-Co/VEval mapping. The numbers themselves come only from WP7 runs (AGENTS rule 9)
- [x] **Use of Meta AI tooling (25%):** the SAM grammar with confidences and object prompts (§1); a closed miss loop with point prompts (`prompts/miss-loop.md`); 3× rephrased votes (`prompts/role-pass.md`); escalation at `max`; EgoBlur as the auditor with Gen 1 vs Gen 2 measured (`research/egoblur-gen2.md`); Voice Transcribe (§4)
- [x] **Technical depth (20%):** §5, §5b, §10, §11, §12, and the TEST-VECTORS
- [x] **Demo (25%):** `suggested_role`, `escalation_evidence` and `escalation_frames` for the Needs-you card; audit catches that can be demoed (`prompts/redteam.md` cases); a live-finals plan and a declared replay fallback (`research/winning-patterns.md` R4); the demo budget reserve (§9.2)
- [x] **Startup, "holds up in production":** caps and reservations (§10.5); the $3/day demo cap (§9.2); startup probe and `/healthz` (§10.7); breaker and `retry_later` (§10.2–10.3); the file sweeper (§10.4); `store` honesty (§12)

## 4. PRE-A ↔ PRE-B shared facts (checked against `origin/pre-b-product` @ `e86a051`)
- [x] Child = anyone who may be under 18: PRE-B `LABELING-GUIDE.md` §2; PRE-A `scene-pass`, `role-pass`, `escalation`
- [x] Two clocks, a constant-frame-rate prepared clip, `job.fps = min(30, round(source average fps))`: PRE-B `LABEL-FORMAT.md` §2 and UI-SPEC §3.6; PRE-A §5b
- [x] `times` is source-clock seconds, non-decreasing, and `times[0]` may be > 0: PRE-B `LABEL-FORMAT.md` §2 (citing T6c); PRE-A §5b step 5, T6a–T6c
- [x] Player → frame `clamp(floor(mediaTime × job.fps + 0.25), 0, job.frames − 1)`: PRE-B UI-SPEC §3.6 and LABEL-FORMAT §2 (citing T5); PRE-A §5b, T5
- [x] Ground truth maps prepared → label, by exact source-frame match within 1e-6: PRE-B `LABEL-FORMAT.md` §2 and §9.1 (M1–M6, built on PRE-A's T6a/T6c); PRE-A §5b (exactness guaranteed by the rational-time rule, step 4)
- [x] The SAM proxy mapping belongs to PRE-A: PRE-B `LABEL-FORMAT.md` §2 defers to PRE-A's `to_proxy`/`from_proxy`
- [x] Split of 12 test, 3 dev, 3 hero: PRE-B `SCHEDULE.md` §3; PRE-A §9.2
- [x] Pilot money cap: PRE-B owns the $20 cap and $4 per code; PRE-A §9.2 budgets the full $20
- [P] Pilot money: PR #2 `PILOTS.md` §5 @ `e86a051` still quotes PRE-A's old **$8.70** (from `498fa20`) and derives $4 per code from a $2 per-clip cap. PRE-A's current estimate is **$11.20** (§9.2), still inside PRE-B's $20 total cap, and PRE-A requests a **$6 per-code cap** so that two busy 60 s clips fit. The fact both sides share, a $20 total cap with the estimate under it, holds. Pending: PRE-B's next pass updates the number and the per-code cap
- [x] CVAT machine: PRE-B decides (Linux/WSL2, never the Intel Mac). PRE-A's test-split GPU machine prefers that same owner-controlled box but never a third party's (`BLOCKED-PRE-A.md`); pointer to `docs/BLOCKED-PRE-B.md` fixed
- [x] `retry_later` job state: PRE-B UI-SPEC (`f6815a5` adds it); PRE-A §10.3
- [x] UI fields PRE-A added: `suggested_role`, `escalation_evidence`/`escalation_frames` (PRE-B's names, adopted by PRE-A) and `matches_participant` as the speech link are in PR #2 UI-SPEC §4.6, §8 and §10.1. The audit-status field is PR #2's `audit.redteam_status` (ok|failed|over_budget, UI-SPEC request 11), adopted by PRE-A in place of its draft `blocked_reason`; the retry is PR #2's [Check again] (§5.3). `unresolved == 0` stays the one publish gate

## 5. Audit findings → fix (full trail)
- [x] Owner audit 1: effort levels → §3.4 per the live reasoning page; escalation `max`
- [x] Owner audit 2: the `file_` → `file-` request → accept both (§1.1, §10.6)
- [x] Owner audit 3: reconcile with PR #2 → under 18; the 12/3 split; the pilot estimate within the $20 cap; time axes (§4 above)
- [x] Owner audit 4: gating → EgoBlur email form; SA-Co manual approval; BLOCKED items
- [x] Owner audit 5: prompting-guide placeholder → real links
- [x] Owner audit 6: BLOCKED conflict → `docs/BLOCKED-PRE-A.md`
- [x] Self-review rounds 1–3 (30 findings: escalation keeping on 2/3 votes, the bar mapping, floor vs round, proxy axes, point prompts for swept phrases, the red-team placeholder, overlapping rule rows, under-costed red-team, loop count, `S?`, `degraded`, `job.times`, scaling, degenerate boxes, frame caps, override wording, "top-left", unequal vote phrasings, whole-batch failure, number drift) → fixed (PR #1 earlier bodies)
- [-] Self-review suggestion "keep `BLOCKED.md` at the root": superseded by the owner's direction to use `docs/BLOCKED-PRE-A.md`
- [x] Iteration 1: no client spec, no test vectors, no box convention → §10, §11, §5
- [x] Iteration 1 review, ffmpeg: the proxy map and `times` rule didn't match ffmpeg → slot rule verified by checksums (T1–T4)
- [x] Iteration 1 review: the `/healthz` SAM probe would cost $3.60/day → `/healthz` is one `minimal` text call; SAM only at startup
- [x] Iteration 1 review: contradictory retry counts; SAM eof handling → one policy (§10.2), R7–R9
- [x] Iteration 1 review: estimated costs inflating reports → reservation model (§10.2)
- [x] Iteration 1 review: the breaker counted attempts → it counts calls, has a half-open state, and routes to `retry_later`
- [x] Iteration 1 review: a 1 h expiry could hit a live job; 404 treated as config → 6 h expiry, `MetaFileGone`
- [x] Iteration 1 review: SAM must get the proxy → two named uploads (§10.6)
- [x] Iteration 1 review 3: wrong bound, the `job.fps < sam_fps` guard, speech retries, `MetaIncomplete` routing, the rate-limit row, the turn clamp, immediate 5xx, startup vs `/healthz`, the `/healthz` cost rounding, the `high` count → all fixed
- [x] Iteration 2: EgoBlur pins have no Intel-Mac wheels → test-split machine requirement (BLOCKED); install and API documented
- [x] Iteration 2: scattered contract changes → §12
- [x] Iteration 2 review: an over-budget audit could publish → invariant `redteam_status != "ok"` ⇒ `unresolved > 0` (was `blocked_reason`, renamed in audit #3); L9, R12
- [x] Iteration 2 review: CPU vs CUDA torch → default PyPI CUDA build (verified: 15 `nvidia-*-cu12` deps)
- [x] Iteration 2 review: RGB/BGR contradiction and the NMS default → BGR; NMS 0.5 for Gen 2, 0.3 for Gen 1 (read from the code)
- [x] Iteration 2 review: §12 defaults, `approx_time`, missing fields (escalation evidence, `requests[].kind`/`matches`, `files.json`) → §12 rewritten (required vs optional)
- [x] Iteration 2 review: `data_handling.store` could misstate → redefined as `any(store_by_model)`
- [x] Iteration 2 review: the test-machine wording and the CPU cost → BLOCKED rewritten (GPU, owner-owned, no third party, CPU fallback stated)
- [x] Iteration 2 review: the Gen 1 vs Gen 2 comparison wasn't runnable or fair → all four zips requested; calibrated thresholds; held-out selection (`research/egoblur-gen2.md`)
- [x] Iteration 2 review: SA-Co boxes not scaled to prepared pixels → loader spec scales per axis
- [x] Iteration 2 review: `matches_participant` vs UI-SPEC's speaker link → one link, requested of PRE-B (§12)
- [-] Iteration 2 reconciliation draft (switch to a variable-frame-rate prepared clip with drop-only thinning): withdrawn. Audit #1 showed it drops real frames from jittery 30 fps sources and re-quantises timestamps, and PR #2 had meanwhile adopted the pushed constant-rate model (`f6815a5`). Final: the constant-rate model, improved (§5b)
- [x] Iteration 2 research: winning patterns → `research/winning-patterns.md` (claims → code table, named baselines, auditor recall, live finals, positioning; new risks 11–14)

- [x] Audit #1: §5b vs PR #2 → converged on PR #2's adopted constant-rate model
- [x] Audit #1: back-fill and gap thresholds counted in SAM frames → scaling rule in §5b (back-fill 57 prepared frames at 30→8; T10), with `hotstart_delay=15` sourced from `sam3` @ `f1647e8`
- [x] Audit #1: video starting after audio shifts the proxy mapping → `setpts=PTS-STARTPTS` plus audio alignment (§5b step 2, T9, verified)
- [x] Audit #1: 6-decimal `pts_time` breaks the 1e-6 match → exact rational times (§5b step 4)
- [-] Audit #1: drop-only `select` drops jittery frames; passthrough re-quantises; ambiguous tie tolerance → all moot under the constant-rate model (the `fps` filter rounds jitter to the right slot)
- [x] Audit #1: the miss loop could spend the audit's budget; no per-loop phrase limit → audit reserve, ≤3 phrase sweeps per loop, one batched object-prompt request (`miss-loop.md`)
- [x] Audit #1: bar findings never clearable; reversed boxes shrunk → `in_bar` drop and corner normalisation (§5, G8, G12–G14; redteam prompt)
- [x] Audit #1: red-team policy vs §10.3; refusal retries; scene-pass retries → audit exception paragraph (§10.3), one rephrased re-ask, scene-pass aligned
- [x] Audit #1: ≤2 passes vs WP4's ≤3 → ≤3 passes; pass 3 costed
- [x] Audit #1: parser exceptions unmapped → mapping row in §10.3
- [x] Audit #1: Wonder budget ignored dev runs and reservation size → §9.2 table (84 runs), 24k `max_output_tokens`
- [x] Audit #1: red-team edge sampling inside covered spans → 4 frames per track just outside the span, plus gap midpoints
- [x] Audit #1: vote fields not collapsed deterministically → `role-pass.md` rule 7, vectors A11–A13
- [x] Audit #1: cost model omitted miss-loop Muse calls and busy clips → v3 model (A2, A7–A9); job cap default $3.00 requested; demo cap staged
- [x] Audit #1: broken pointer to PRE-B's BLOCKED file → `docs/BLOCKED-PRE-B.md`

## 6. Full hostile audits of the whole package (for the done condition: two consecutive with nothing new)
- [x] Audit #1 (2026-10-24 ~18:10 UTC, `code-review` at max effort, whole package `main..HEAD` vs the brief, MAXXING, ARCHITECTURE, DESIGN, EVAL, WP0–WP8, PR #2 @ `f6815a5`): **15 findings, all fixed** (§5 above). Not clean
- [x] Audit #2 (2026-10-24 ~21:30 UTC, an independent fresh agent over the whole package at `eb4c62c` vs the brief, MAXXING, WP0–WP8 and PR #2 @ `e86a051`): **8 findings, all fixed.** They were: a false `[x]` on the PRE-B pilot figure (back to `[P]`); the $1/day pre-judging cap (now $3/day throughout, $18 reserve); the $4 pilot-code margin (a $6 request to PRE-B); `times` rounding vs PRE-B (now full-precision doubles); dangling T7/T8 references; the busy-clip delta (+$2.16); escalation's budget guard (one path, §10.5); a garbled miss-loop clause and the red-team re-ask budget. Not clean
- [x] Audit #3 (2026-10-24 ~21:40 UTC, an independent fresh agent over the whole package at `948b678` vs the brief, MAXXING, ARCHITECTURE, WP0–WP8 and PR #2): **11 findings, all fixed.** (1) the miss loop dropped unswept items → static hidden box + `needs_you` (miss-loop.md, M8, M11); (2) pilot spend sat inside the public daily cap → caps scoped by who started the job (§9.2, §10.2, §10.3); (3) `blocked_reason` → PR #2's `audit.redteam_status` and [Check again] (§10.3, §12, redteam.md, L6, L9); (4) WP2.md maps turn times with `job.times`, but turns are on the prepared clock → request to WP2: `floor(t × job.fps)` (role-pass.md input 3); (5) no full $150 ledger → §9.2 ledger, $143.16, $6.84 headroom, Wonder not pre-approved (muse-wonder-vs-spark.md H5); (6) Wonder `max` at 48k output could breach the job cap → 24k (§10.5); (7) PR #1 body figures stale → refreshed with evidence; (8) `frames_uploaded` vs ARCHITECTURE's `frames_billed` → `frames_billed` (§10.5, §12); (9) `files.json` lacked `name` (§10.4); (10) a 2 h job clock would cancel jobs waiting on the creator → 2 h per processing segment, files deleted at each segment's end (§10.1, §10.4); (11) README rule 7 omitted the effort exceptions, and escalation had no >50-keyframe rule → both added
