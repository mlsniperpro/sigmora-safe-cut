#!/usr/bin/env bash
# Every check for SAFECUT-WP6 (web/). Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../../../web"
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm e2e
