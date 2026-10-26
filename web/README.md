# Safe Cut web app (WP6)

The screens judges and creators see: the landing page with the hero result, `/try` (access code → upload → progress), the review panel at `/jobs/[id]` with the "Why?" drawer, and the result and privacy receipt at `/jobs/[id]/result`. Built from `docs/work-packages/WP6.md` and PRE-B's `docs/UI-SPEC.md`.

Next.js 16 (App Router, Cache Components), React 19, TypeScript strict, Tailwind 4, zod 4. Tests: vitest + Testing Library + fast-check, and a Playwright end-to-end run with axe.

## Run it

```bash
cd web
pnpm install
pnpm dev            # http://localhost:3000, mock mode (no API needed)
```

With `NEXT_PUBLIC_SAFECUT_API` unset, every request goes to an **in-browser mock backend** (`src/lib/mock-backend.ts`) built on the fixtures in `mocks/`. Nothing leaves the browser, and a note under the header says so. Things to try:

| URL | What it shows |
|---|---|
| `/` | Landing: the sample hero with the Raw / Safe Cut toggle |
| `/try` | The whole flow: any access code, then pick any MP4/MOV (`public/sample/prepared.mp4` works) |
| `/jobs/job-review-sample` | Review panel on the synthetic sample scene (playable video, keyframes) |
| `/jobs/<fixture>` | Any job fixture in `mocks/`, e.g. `job-review-reentry`, `job-review-cafe`, `result-audit-failed`, `job-replay` (demo-mode banner), `job-failed-roles`, `error-404-expired` |
| `/jobs/result-fixed/result` | Result page states: also `result-clean`, `result-unresolved`, `result-clean-yunet` |

Access codes with scripted answers in mock mode (`MOCK_CODES`):

| Code | Answer |
|---|---|
| `wrong` | 401 on Continue |
| `not-yet` | 401 `code_not_active` on Continue |
| `rate-limited` | 429 on Continue |
| `expired` | 401 `code_not_active` on `POST /v1/jobs` |
| `no-budget` | 429 `code_cap` on `POST /v1/jobs` |
| `revoked` | 401 on `POST /start` (the job is deleted once) |
| `too-big` | 422 `job_cap` on `POST /start` |
| `pilot-done` | 429 `pilot_pool_cap` on `POST /start` |
| `no-auditor`, `no-credits` | 503 on `POST /start` (Start stays enabled) |
| `upload-lost` | 409 `upload_incomplete` on `POST /start` |
| anything else | accepted |

The sample scene is drawn shapes, not people, so it needs no release (AGENTS.md rules 4–5). Its motion data (`scripts/sample-scene.mjs`) drives both the rendered media and the job JSON, so boxes, plan and pixels agree.

## Checks

```bash
pnpm lint        # ESLint, zero warnings allowed
pnpm typecheck   # tsc --noEmit
pnpm test        # vitest: unit, property, component and integration tests
pnpm build       # production build
pnpm e2e         # Playwright on the production build in mock mode, with axe (run after build)
```

`.agent/win/SAFECUT-WP6/checks.sh` runs all of them.

## Environment variables

The `NEXT_PUBLIC_*` values are public and fixed at build time; no secret ever reaches the browser. `SAFECUT_BLOCKED_TERRITORIES` is read on the server only.

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SAFECUT_API` | unset (mock mode) | WP5's API base URL, e.g. `https://api.safecut.sigmora.org` |
| `NEXT_PUBLIC_SAFECUT_HERO_ID` | `hero1` | The pinned hero job served by `GET /v1/demo/{hero_id}` |
| `NEXT_PUBLIC_SITE_URL` | `https://safecut.sigmora.org` | Canonical URL for Open Graph / X cards |
| `NEXT_PUBLIC_SIGMORA_URL` | `https://sigmora.org` | "Back to Sigmora", the publish target, and `frame-ancestors` |
| `NEXT_PUBLIC_REPO_URL` | this repo on GitHub | "Source on GitHub" |
| `NEXT_PUBLIC_EVAL_URL` | `docs/EVAL.md` on GitHub | "How we measured" under the results table |
| `NEXT_PUBLIC_PRIVACY_CONTACT` | unset (falls back to "Open an issue on GitHub") | The email address shown on `/privacy` (UI-SPEC §7.1). The owner sets it at deploy time; it is never committed |
| `NEXT_PUBLIC_HERO_HAS_CHILD` | `true` | Set `false` if the filmed hero clip has no child, so the landing copy doesn't promise one (UI-SPEC §1.3) |
| `SAFECUT_BLOCKED_TERRITORIES` | PRE-A §7's list | JSON `{"countries":[…],"regions":{"UA":[…]}}` replacing the territories that `/try` and the job pages refuse (`src/proxy.ts`, which reads Vercel's `x-vercel-ip-country` headers). A malformed value makes the proxy throw when it loads, rather than silently opening uploads |

## Deploy

Vercel builds `web/` on push (root directory `web`, framework Next.js, install `pnpm install --frozen-lockfile`). Don't deploy from a sandbox. The owner sets the custom domain and the variables above. Security headers (CSP, HSTS, nosniff, Permissions-Policy, `noindex` on job pages) are in `next.config.ts`.

## Regenerating fixtures and sample media

```bash
node scripts/gen-mocks.mjs     # mocks/*.json and mocks/index.ts (a test fails if they drift)
node scripts/gen-sample.mjs    # public/sample/* (needs ffmpeg on PATH)
```

The fixtures follow UI-SPEC §10.1; `mocks/mocks.test.ts` checks every §10.1 invariant on every job fixture. When WP5's API lands, its field names win and the mocks follow.

## Layout

```
src/app/                 routes: /, /try, /jobs/[id], /jobs/[id]/result, not-found, error
src/components/          landing/, try/, job/, review/ (Chip, VideoPane, WhyDrawer, ReviewPanel), shared ui
src/lib/contracts.ts     zod schemas for every API response
src/lib/api.ts           typed client: timeouts, GET retries, typed errors
src/lib/mock-backend.ts  the in-browser API used in mock mode and in tests
src/lib/review/          the review reducer (UI-SPEC §10.5), bottom bar, chip view model
src/lib/why/             Why-drawer copy and Muse Spark frame-reference rewriting
src/lib/overlay.ts       what the review canvas draws on each frame
mocks/                   UI-SPEC §10.1 fixtures (generated)
e2e/replay-e2e.mjs       real-browser end-to-end run with axe
```
