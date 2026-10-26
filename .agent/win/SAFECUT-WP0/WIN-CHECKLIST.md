# SAFECUT-WP0 win checklist

Legend: `- [x]` done with evidence · `- [P]` parked on an owner input (BLOCKED.md) · `- [-]` not applicable · `- [ ]` open.

## WP0 brief
- [x] pyproject (Python 3.12, uv) with main/dev/audit/deploy groups, plus the PRE-A §12 additions (meta-sam-parser, pycocotools, scipy, boto3, pytest-cov). Evidence: `uv lock` resolved 99 packages; `uv sync --locked` passes in checks.sh
- [x] config.py holds every env var in ARCHITECTURE §4 and the PRE-A §12 table, typed, with defaults; refuses -contributor IDs. Evidence: commit 895500e
- [x] contracts.py: a model for every §3 file plus PRE-A §12 fields, load/dump helpers. Evidence: tests/test_contracts.py, 56 passed
- [x] Round-trip tests for every contract using a coherent example job directory. Evidence: test_example_round_trips × 10 files
- [x] CI workflow: uv sync, ruff, pyright, pytest -m "not live", web job when web/ exists. Evidence: .github/workflows/ci.yml
- [x] Draft PR opened early. Evidence: PR #3
- [x] Meta client: client.py (httpx, retries/backoff on 429/5xx, request IDs), files.py, responses.py, asr.py, cost.py, sam.py, status.py; refuses -contributor (config + build_body). Evidence: tests/test_meta_client.py, tests/test_meta_endpoints.py
- [x] Typed errors, retry policy, circuit breaker and cost reservation per PRE-A §10.2–10.5, tested against vectors C1–C8, R1–R3, R5–R9, R11–R14. Evidence: tests/test_meta_client.py
- [x] Probe scripts a–h under scripts/probes/ (h = open weights), each saving raw responses and summary.json under fixtures/probes/<name>/, $6 cap enforced. Evidence: tests/test_probes_replay.py runs all eight against mocked APIs
- [P] Probes a–g run live (needs MODEL_API_KEY, BLOCKED.md)
- [P] docs/API-NOTES-WP0.md has provisional recommendations with price-based numbers (Spark 1.3 scene ≈ $0.10 vs Wonder ≈ $0.34 per 30 s; escalation $0.23 vs $0.55; ASR $0.0015 vs ≈ $0.10) and config defaults match; the probe-measured confirmation waits on MODEL_API_KEY
- [x] Fixtures: fixtures/sam (S1, S3–S7 vectors, a stream), fixtures/muse (role pass, incomplete, refusal), fixtures/asr (diarization), all labelled documented-shape; 2 deterministic synthetic clips ≤ 3 s with a burned-in counter and truth.json. Evidence: tests/test_fixtures_api.py, tests/test_fixtures_clips.py
- [x] ARCHITECTURE §3/§4 updated to match the contracts and config (AGENTS rule 3). Evidence: commit b7fe6c9
- [x] PR lists total probe spend from cost.jsonl: $0.00 (no live probe ran; no key). Evidence: PR #3 body
- [x] Failure paths covered: connect/read timeouts, every 4xx/5xx class, 429 with Retry-After (seconds, date, over the cap), non-JSON and empty bodies, eof streams, server incomplete, refusals, total timeout, budget stops. Evidence: tests/test_meta_client.py, tests/test_fuzz.py

## Official guide reconciliation (docs/OFFICIAL-GUIDE.md, captured 2026-10-26 16:25Z)
- [x] Theme fit: "Build for Your World" (creator privacy on footage the creator films). Not on the anti-project list: Safe Cut is a multi-model video pipeline with a closed SAM ↔ Muse loop and an audit, not a simple image analyzer. Evidence: docs/OFFICIAL-GUIDE.md, MAXXING §0
- [x] Deadline reconciled: Wed Nov 4 9:00 PM ET = 2026-11-05 02:00 UTC (ET is UTC-5 after Nov 1); the internal deadline stays 2026-11-04T18:00Z
- [x] Rubric weights match MAXXING §1: Impact 30, Meta tooling 25, Technical depth 20, Demo 25
- [x] New work only: every WP0 file is created on branch wp0-foundation after 2026-10-26 16:00 UTC (first commit 895500e at 16:1x UTC); the README's "built during the event" boundary is WP8's
- [P] Stage 1 pass/fail needs real Meta Model API use: the client is built and tested, live calls wait on MODEL_API_KEY (BLOCKED.md)
- [P] Public repo at submission (BLOCKED.md; owner approves)
- [x] Open-weight bonus path per PRE-A §3.8: safecut/open_weight.py (streamed Baseten chat, provider: "baseten", its own baseten_job cap, refused without a price, consent and code-kind gating), and probe h (4 synthetic frames, the AMINA K. grid check, medium vs omit). Evidence: tests/test_open_weight.py, tests/test_probes_replay.py; the live run waits on BASETEN_API_KEY (BLOCKED.md)
- [-] 3-minute video and live product: WP8 and WP5/WP6 own them (DEMO.md plans 2:50, under the limit)
- [-] Best Agentic Use-Case: the closed loop (SAM IDs → Muse rulings → new SAM prompts) is WP2's; WP0 supplies the client it runs on

## Judging criteria (WP0's share)
- [x] Technical depth 20%: strict-typed client (pyright strict on safecut/ and scripts/), reservation ledger, measured vs estimated spend. Evidence: checks.sh green
- [x] Meta tooling 25%: Standard mode only, store:false on Responses and SAM, uploads deleted with files.json proof, every model ID from env, SAM parsed by Meta's own meta-sam-parser. Evidence: tests/test_meta_endpoints.py::test_sam_stream_feeds_the_official_parser
- [x] Production 'holds up': timeouts, bounded retries, breaker, caps, no secrets in logs or errors. Evidence: test_key_is_sent_and_never_logged, test_errors_never_echo_values

- [x] PRE-A §12 contract rows (job.consented, audit.open_weight, audit.redteam_open, leak detector redteam_open, cost.jsonl provider, cap baseten_job, the SAFECUT_OPEN_WEIGHT_* env vars). Evidence: safecut/contracts.py, safecut/config.py, tests/test_open_weight.py

## Quality bar
- [x] Live smoke tests ready for the key: `uv run pytest -m live` (status, the model list, one metered Spark call ≤ $0.003). Evidence: tests/test_live.py, deselected from the default run
- [x] Probe f role calls (Spark vs Wonder at max on consented SoM keyframes) built; the footage is listed in BLOCKED.md. Evidence: tests/test_hardening.py::test_role_call_probe
- [x] State-of-the-art note in the PR (httpx, pydantic v2, meta-sam-parser, backoff, RFC 9110) with links. Evidence: PR #3 "State of the art"
- [x] Self-review section in the PR; code-review skill (medium) run on origin/main...HEAD: 10 findings, all verified and fixed. Evidence: PR #3 "Self-review", reaudit.md, tests/test_hardening.py
- [x] Fresh-clone run recorded in break-it.md: a clone of da8c047, uv sync --locked, ruff, pyright, pytest pinned to 2 CPUs → 265 passed, 66 s from clone to green
