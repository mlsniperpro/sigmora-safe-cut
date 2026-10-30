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
# This lane's E-lines of .agent/ENTRY-DONE.md (E2: the SENSE stages on main, E3: the demo job hidden offline,
# E8: the live path). --only never prints PASS and exits non-zero, so each line is required by name; the whole
# ENTRY: PASS (every lane's lines) is run on a fresh clone of origin/main, not here.
if bash scripts/entry-check.sh --only E2,E3,E8 >"$work/entry.log" 2>&1; then :; fi
cat "$work/entry.log"
for line in E2 E3 E8; do grep -qx "$line: OK" "$work/entry.log"; done
