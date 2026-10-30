#!/usr/bin/env bash
# Every check for SAFECUT-WP0: lint, format, typecheck, unit/property, integration and replay tests.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --locked --quiet
uv run ruff check --output-format concise .
uv run ruff format --check .
uv run pyright
uv run pytest -m "not live" -q
