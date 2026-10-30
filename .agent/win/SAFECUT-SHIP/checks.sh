#!/usr/bin/env bash
# Every check for lane SAFECUT-SHIP: lint, format, types, the full Python suite (unit, property, integration,
# the API flow), the web app (lint, types, unit tests, production build), and the whole entry's gate.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --locked --all-groups --quiet
uv run --no-sync ruff check --output-format concise .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest -q -p no:cacheprovider
(cd web && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test && pnpm build)
bash scripts/entry-check.sh
