#!/usr/bin/env bash
# Record a full live job's raw Meta responses into fixtures/jobs/<id>/raw/ under a USD cap (E8).
#
#   bash scripts/go-live.sh <clip> [--id <id>] [--usd-cap <usd>] [--consented] [--analyse-only]
#
# Needs MODEL_API_KEY (the Meta Model API key; never printed). Only synthetic clips (fixtures/clips/) or consented
# clips (--consented: a hero/dev clip with releases, AGENTS rules 4-5) may be recorded into fixtures/.
set -euo pipefail
if [ -z "${MODEL_API_KEY:-}" ]; then
  echo "go-live: MODEL_API_KEY is not set; add the Meta Model API key to the environment's secrets (see .agent/win/SAFECUT-SENSE/BLOCKED.md)" >&2
  exit 2
fi
GO_LIVE_CWD="$PWD"
export GO_LIVE_CWD
cd "$(dirname "$0")/.."
exec uv run python -m scripts.go_live "$@"
