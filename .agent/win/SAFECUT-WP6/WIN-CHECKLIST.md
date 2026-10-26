# WIN-CHECKLIST: SAFECUT-WP6 (web app)

Legend: `- [x]` done with evidence · `- [P]` waits on an owner input (BLOCKED.md) · `- [-]` not applicable, why · `- [ ]` open.

## Judging criteria (AGENTS.md: Impact 30 · Meta tooling 25 · Technical depth 20 · Demo 25; Startup: holds up in production)

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
