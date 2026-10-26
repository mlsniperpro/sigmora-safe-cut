# WIN-CHECKLIST: SAFECUT-WP6 (web app)

Legend: `- [x]` done with evidence · `- [P]` waits on an owner input (BLOCKED.md) · `- [-]` not applicable, why · `- [ ]` open.

## Official guide reconciliation (docs/OFFICIAL-GUIDE.md, captured 2026-10-26 16:25Z)

- [x] Rubric weights match: Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25 (guide Stage 2 = AGENTS.md); deadline Wed Nov 4 21:00 ET = 2026-11-05 02:00 UTC matches MAXXING §1 (05:00 EAT); internal deadline stays 2026-11-04T18:00Z
- [x] Theme fit: "Build for Your World" (creators publishing street footage without exposing bystanders); not on the anti-project list (no medical advice; not a simple image analyzer: a multi-model video pipeline with tracking, role rulings, review and audit)
- [ ] Stage 1 pass/fail made visible: every screen that shows a decision names the Meta model behind it (How it works, Why drawer, receipt models, footer)
- [ ] "New work only": the site carries a made-during-the-event boundary ("Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026"; Sigmora is the existing product, Safe Cut is new) on the landing page and footer, so judges can tell what was built during the event
- [ ] Copy never frames Safe Cut as an "image analyzer" or "face recognition" (UI-SPEC §0 voice rule + anti-project list); a test scans the copy
- [ ] Best Agentic Use-Case bonus: the landing "How it works" shows the closed agent loop (SAM 3.1 numbers objects → Muse Spark rules → Muse Spark writes new SAM prompts for misses → audit → auto-patch), and the Why drawer shows the loop's evidence per item
- [ ] Most Viral bonus: share-ready Open Graph / X card metadata on the landing page (title, description, image) so a posted link renders well
- [P] Best Build on Meta Open-Weight Models bonus (Muse Spark Open via Baseten `meta-models/muse-spark-open-1026`): pipeline-side (WP2) and needs Baseten credits; the web shows whichever models `receipt.models` reports, so no web change is needed. Requested in the PR's "Requests for other WPs"
- [P] Live product + public repo at submission: needs the owner's Vercel project/domain and the repo made public (BLOCKED.md)
- [P] 3-minute demo video: owner records; the web side is the demo-mode screens (STORYBOARD)

## Judging criteria (Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25; Startup track: holds up in production)

- [ ] Demo 25%: every WP6 screen works end to end against the mocks and reads as a product (UI-SPEC §1–§7)
- [ ] Meta tooling 25%: the Why drawer shows the SAM 3.1 Set-of-Mark keyframe with the ring, Muse Spark's three votes and escalation, and Muse Voice Transcribe evidence (UI-SPEC §4)
- [ ] Impact 30%: landing shows the results table component (WP8 fills numbers), "blur every face vs Safe Cut", and the 3-step story (UI-SPEC §1)
- [ ] Technical depth 20%: frame-accurate overlay on requestVideoFrameCallback with the §3.6 checks; optimistic review reducer with undo and idempotent edits (§10.5)
- [ ] Production: schema-validated API client with timeouts, bounded retries with backoff, idempotency keys; typed errors mapped to the copy deck (§10.3)
- [ ] Production: security headers (CSP, frame-ancestors, referrer policy), no secrets in the client bundle

## WP6 brief

- [ ] Step 1: scaffolded with the official create-next-app CLI; vitest + Testing Library; `lint`, `typecheck`, `test` scripts
- [ ] Step 2: typed API client `web/src/lib/api.ts` uses `web/mocks/` when `NEXT_PUBLIC_SAFECUT_API` is unset
- [ ] Screen 1 Landing `/`: hero raw ↔ Safe Cut toggle, how it works, results table, side-by-side, Try it + links
- [ ] Screen 2 Upload `/try`: access code → drag-and-drop with §10.2 validation → presigned upload → stage progress
- [ ] Screen 3 Review `/jobs/[id]`: overlay canvas, three chip columns, Why drawer, toggle/lock/merge/remove, Approve & render
- [ ] Screen 4 Result `/jobs/[id]/result`: video, download, audit summary, embedded receipt, Publish only from Sigmora
- [ ] Screen 5 Demo-mode banner whenever `mode: "replay"`
- [ ] Step 3 Accessibility: keyboard chips, visible focus, icon + text, captions (UI-SPEC §9)
- [ ] Step 4 Overlay synced to requestVideoFrameCallback with the §3.6 frame mapping (supersedes "via job.times", UI-SPEC §8 request 12)
- [ ] Step 5 `web/README.md` documents env vars and deployment
- [ ] Tests: chips (toggle, lock, merge), the review reducer (R1–R33), the API client against mocks, frame ↔ time mapping
- [ ] Done-when: screenshots of every screen (mock data) and a GIF of the review flow in the PR
- [P] Done-when: switch to the live API after WP5 merges (client is contract-driven; needs WP5's deployed URL)

## Owner quality bar

- [ ] State of the art: library/API choices recorded in the PR with sources
- [ ] Property-based tests where inputs vary (fast-check)
- [ ] Integration tests across the API client ↔ mock backend ↔ pages boundary
- [ ] One end-to-end test in replay/mock mode (real browser)
- [ ] Failure paths covered: timeouts, bad JSON, schema violations, 4xx/5xx, rate limits, partial data
- [ ] Strict TS (strict + noUncheckedIndexedAccess), ESLint zero warnings
- [ ] Self-review section in the PR; expected load and first breaking point stated

## Audit findings

(none yet)
