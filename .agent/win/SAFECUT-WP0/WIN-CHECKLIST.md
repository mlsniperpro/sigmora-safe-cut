# SAFECUT-WP0 win checklist

Legend: `- [x]` done with evidence · `- [P]` parked on an owner input (BLOCKED.md) · `- [-]` not applicable · `- [ ]` open.

## WP0 brief
- [x] pyproject (Python 3.12, uv) with main/dev/audit/deploy groups, plus the PRE-A §12 additions (meta-sam-parser, pycocotools, scipy, boto3, pytest-cov). Evidence: `uv lock` resolved 99 packages; `uv sync --locked` passes in checks.sh
- [x] config.py holds every env var in ARCHITECTURE §4 and the PRE-A §12 table, typed, with defaults; refuses -contributor IDs. Evidence: commit 895500e
- [x] contracts.py: a model for every §3 file plus PRE-A §12 fields, load/dump helpers. Evidence: tests/test_contracts.py, 56 passed
- [x] Round-trip tests for every contract using a coherent example job directory. Evidence: test_example_round_trips × 10 files
- [x] CI workflow: uv sync, ruff, pyright, pytest -m "not live", web job when web/ exists. Evidence: .github/workflows/ci.yml
- [x] Draft PR opened early. Evidence: PR #3
- [ ] Meta client: client.py (httpx, retries/backoff on 429/5xx, request IDs), files.py, responses.py, asr.py, cost.py, refuses -contributor
- [ ] Typed errors, retry policy, circuit breaker and cost reservation per PRE-A §10.2–10.5, tested against the §11.4/§11.5 vectors
- [ ] Probe scripts a–g under scripts/probes/, each saving raw responses under fixtures/probes/<name>/
- [P] Probes a–g run live (needs MODEL_API_KEY, BLOCKED.md)
- [ ] docs/API-NOTES.md: recommendations with numbers for SAFECUT_SCENE_MODEL, SAFECUT_ESCALATE_MODEL and SAFECUT_SPEECH_SOURCE; config defaults match
- [ ] Fixtures: fixtures/sam, fixtures/muse, fixtures/asr, plus 2 synthetic clips ≤ 3 s with a burned-in frame counter
- [ ] ARCHITECTURE §3/§4 updated to match the contracts and config (AGENTS rule 3)
- [ ] PR lists total probe spend from cost.jsonl
- [ ] tests/test_meta_client.py covers failure paths: timeouts, 4xx/5xx, 429 with Retry-After, malformed and empty bodies, partial streams

## Official guide reconciliation (docs/OFFICIAL-GUIDE.md, captured 2026-10-26 16:25Z)
- [x] Theme fit: "Build for Your World" (creator privacy on footage the creator films). Not on the anti-project list: Safe Cut is a multi-model video pipeline with a closed SAM ↔ Muse loop and an audit, not a simple image analyzer. Evidence: docs/OFFICIAL-GUIDE.md, MAXXING §0
- [x] Deadline reconciled: Wed Nov 4 9:00 PM ET = 2026-11-05 02:00 UTC (ET is UTC-5 after Nov 1); the internal deadline stays 2026-11-04T18:00Z
- [x] Rubric weights match MAXXING §1: Impact 30, Meta tooling 25, Technical depth 20, Demo 25
- [x] New work only: every WP0 file is created on branch wp0-foundation after 2026-10-26 16:00 UTC (first commit 895500e at 16:1x UTC); the README's "built during the event" boundary is WP8's
- [P] Stage 1 pass/fail needs real Meta Model API use: the client is built and tested, live calls wait on MODEL_API_KEY (BLOCKED.md)
- [P] Public repo at submission (BLOCKED.md; owner approves)
- [ ] Open-weight bonus path: config for Baseten `meta-models/muse-spark-open-1026` and an open-weight probe behind BASETEN_API_KEY
- [-] 3-minute video and live product: WP8 and WP5/WP6 own them (DEMO.md plans 2:50, under the limit)
- [-] Best Agentic Use-Case: the closed loop (SAM IDs → Muse rulings → new SAM prompts) is WP2's; WP0 supplies the client it runs on

## Judging criteria (WP0's share)
- [ ] Technical depth 20%: typed, tested Meta client with honest cost accounting
- [ ] Meta tooling 25%: Standard mode only, store:false, uploads deleted, every model ID from env
- [ ] Production 'holds up': timeouts, bounded retries, breaker, caps, no secrets in logs

## Quality bar
- [ ] State-of-the-art note in the PR (httpx, pydantic v2, meta-sam-parser) with links
- [ ] Self-review section in the PR; code-review skill run on the diff
- [ ] Fresh-clone README run recorded in break-it.md
