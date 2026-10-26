#!/usr/bin/env bash
# Every check for SAFECUT-WP6 (web/). Run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../../../web"
# Every source file must be tracked: an ignore rule once hid the /jobs routes and the sample clips.
hidden="$(git ls-files --others --ignored --exclude-standard -- src public mocks e2e scripts)"
if [ -n "$hidden" ]; then echo "ignored source files: $hidden"; exit 1; fi
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm e2e
