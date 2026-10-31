#!/usr/bin/env bash
# Every check for lane SAFECUT-MODAL: lint, format, types (deploy/ included), the full Python suite (unit, property,
# integration, the SIGKILL-and-restart test, the GPU fallbacks, the deploy files' shape and cost tables), the
# deploy-check script, the web app (lint, types, unit tests, production build) and the whole entry's gate.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --locked --all-groups --quiet
uv run --no-sync ruff check --output-format concise .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest -q -p no:cacheprovider
bash -n scripts/deploy-check.sh
uv run --no-sync python -c "import deploy.modal_app, deploy.verify_deploy"
(cd web && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test && pnpm build)
bash scripts/entry-check.sh
