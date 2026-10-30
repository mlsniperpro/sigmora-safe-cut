# Safe Cut web app (WP6)

The screens judges and creators see: the landing page with the hero result, `/try` (access code → upload → progress), the review panel at `/jobs/[id]` with the "Why?" drawer, and the result and privacy receipt at `/jobs/[id]/result`. Built from `docs/work-packages/WP6.md` and PRE-B's `docs/UI-SPEC.md`, which lands on `main` with PRE-B's PR; until then read it with `git show origin/pre-b-product:docs/UI-SPEC.md`. Code comments cite its sections as §n.

Next.js 16 (App Router; Cache Components is deliberately off, see `next.config.ts`), React 19, TypeScript strict, Tailwind 4, zod 4. Tests: vitest + Testing Library + fast-check, and a Playwright end-to-end run with axe.

## Run it

Needs Node 22–24 (`engines`: `>=22 <25`) and pnpm 10.28 (`corepack enable` picks it up from `packageManager`). The app always talks to the Safe Cut API (`safecut/api/`); run one locally in replay mode, which serves the synthetic demo job and never calls Meta:

```bash
# terminal 1, repo root: the API on http://127.0.0.1:8000, replaying recorded (synthetic) responses
SAFECUT_REPLAY=1 SAFECUT_JOBS_DIR=/tmp/safecut-jobs SAFECUT_CORS_ORIGINS='["http://localhost:3000"]' \
  SAFECUT_ACCESS_CODES='[{"code": "local-judge-code", "kind": "judge"}]' \
  SAFECUT_CODE_WINDOWS='{"judge": [null, null]}' \
  uv run uvicorn --factory safecut.api.app:create_app --port 8000 --no-proxy-headers
```

```bash
# terminal 2: the web app on http://localhost:3000
cd web
pnpm install
NEXT_PUBLIC_SAFECUT_API=http://127.0.0.1:8000 NEXT_PUBLIC_SAFECUT_HERO_ID=demo pnpm dev
```

Then `/` plays the demo job (labelled synthetic), and `/try` takes the code `local-judge-code` and the demo clip `fixtures/clips/SC-A-91-synthetic-20261030.mp4` (in replay the API can only replay clips it has recordings for). Without `NEXT_PUBLIC_SAFECUT_API` every request fails as a network error, so the pages show their "service isn't responding" state; the app never makes data up.

The unit tests run on an in-memory mock backend instead (`src/test/mock-backend.ts`, built on the fixtures in `mocks/`); it exists only for tests. Its scripted access codes (`MOCK_CODES`) drive the refusal paths: `wrong` (401), `not-yet` (401 `code_not_active`), `rate-limited` (429), `expired`, `no-budget` (429 `code_cap`), `revoked`, `too-big` (422 `job_cap`), `pilot-done` (429 `pilot_pool_cap`), `no-auditor`, `no-credits` (503) and `upload-lost` (409 `upload_incomplete`). The sample scene in `public/sample/` is drawn shapes, not people (AGENTS.md rules 4–5).

## Checks

```bash
pnpm lint        # ESLint, zero warnings allowed
pnpm typecheck   # tsc --noEmit
pnpm test        # vitest: unit, property, component and integration tests
pnpm build       # production build
pnpm e2e:api     # Playwright + axe on the production build against a local API in replay (starts both)
```

`pnpm e2e:api` builds the app against `http://127.0.0.1:<port>`, starts the API with `uv run`, and drives the judge's path in Chromium; it needs the repo's Python environment (`uv sync`) and a Chromium for Playwright (`pnpm exec playwright install chromium` if you don't have one).

## Environment variables

The `NEXT_PUBLIC_*` values are public and fixed at build time; no secret ever reaches the browser. `SAFECUT_BLOCKED_TERRITORIES` is read on the server only.

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SAFECUT_API` | unset (every call fails) | The API's base URL: the Modal URL `https://<workspace>--safecut-api.modal.run`, or a custom domain pointed at it. Plain http is accepted only for a loopback API (local runs and the e2e check) |
| `NEXT_PUBLIC_SAFECUT_HERO_ID` | `hero1` | The pinned hero job served by `GET /v1/demo/{hero_id}`: `demo` (the synthetic demo job) until hero clip 1 is recorded |
| `NEXT_PUBLIC_SITE_URL` | `https://safecut.sigmora.org` | Canonical URL for Open Graph / X cards |
| `NEXT_PUBLIC_SIGMORA_URL` | `https://sigmora.org` | "Back to Sigmora", the publish target, and `frame-ancestors` |
| `NEXT_PUBLIC_REPO_URL` | this repo on GitHub | "Source on GitHub" |
| `NEXT_PUBLIC_EVAL_URL` | `docs/EVAL.md` on GitHub | "How we measured" under the results table |
| `NEXT_PUBLIC_PRIVACY_CONTACT` | unset (falls back to "Open an issue on GitHub") | The email address shown on `/privacy` (UI-SPEC §7.1). The owner sets it at deploy time; it is never committed |
| `NEXT_PUBLIC_HERO_HAS_CHILD` | `true` | Set `false` if the filmed hero clip has no child, so the landing copy doesn't promise one (UI-SPEC §1.3) |
| `SAFECUT_BLOCKED_TERRITORIES` | PRE-A §7's list | JSON `{"countries":[…],"regions":{"UA":[…]}}` replacing the territories that `/try` and the job pages refuse (`src/proxy.ts`, which reads Vercel's `x-vercel-ip-country` headers). A malformed value makes the proxy throw when it loads, rather than silently opening uploads |

## Deploy (Vercel)

Vercel builds `web/` on every push to `main`; nothing deploys from a sandbox. Project settings:

| Setting | Value |
|---|---|
| Root directory | `web` |
| Framework preset | Next.js |
| Install command | `pnpm install --frozen-lockfile` |
| Build command | `pnpm build` |
| Node.js version | 24.x |
| Domain | `safecut.sigmora.org` (CNAME to `cname.vercel-dns.com`); the owner's Vercel team blocks public `*.vercel.app` aliases |
| Environment (Production) | `NEXT_PUBLIC_SAFECUT_API`, `NEXT_PUBLIC_SAFECUT_HERO_ID`, `NEXT_PUBLIC_SIGMORA_URL`, `NEXT_PUBLIC_REPO_URL`, `NEXT_PUBLIC_PRIVACY_CONTACT` (table above) |

The API must list the site's origin in `SAFECUT_CORS_ORIGINS` (it does by default: `https://safecut.sigmora.org`). Security headers (CSP, HSTS, nosniff, Permissions-Policy, `noindex` on job pages) are in `next.config.ts`; the CSP allows media and API calls to any https origin, plus the exact loopback origin a local build was made for. After a deploy, `bash scripts/deploy-check.sh <api-url> https://safecut.sigmora.org` checks both (from the repo root).

Captions on the hero and result videos come from the API's signed `captions.vtt` URL and are attached as blob URLs (`src/hooks/useRemoteCaptions.ts`); the API's CORS covers them.
