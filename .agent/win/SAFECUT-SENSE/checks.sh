#!/usr/bin/env bash
# Every check for lane SAFECUT-SENSE: lint, format, types, the whole Python suite (unit, property, integration,
# the replay end to end of the synthetic demo job), the SENSE stages through the CLI in replay, and the entry gate.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --locked --quiet
uv run ruff check --output-format concise .
uv run ruff format --check .
uv run pyright
uv run pytest -m "not live" -q -p no:cacheprovider
# The SENSE stages through the real CLI on a fresh copy of the demo job, network-free (replay).
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
uv run safecut prepare fixtures/clips/SC-A-91-synthetic-20261030.mp4 --job "$work/demo" --replay
cp -r fixtures/jobs/demo/raw "$work/demo/raw"
for stage in track transcribe scene roles; do uv run safecut "$stage" --job "$work/demo" --replay; done
uv run python -c "import sys; from safecut.contracts import validate_job_dir; validate_job_dir(sys.argv[1])" "$work/demo"
# The live path without a key: go-live.sh must refuse with exit 2, naming the missing input.
if env -u MODEL_API_KEY bash scripts/go-live.sh fixtures/clips/counter_30fps_audio.mp4; then exit 1; else test $? -eq 2; fi
bash scripts/entry-check.sh
