#!/usr/bin/env bash
# SAFECUT-SAFETY lane checks (.agent/WIN-GATE.md): lint, types, the full suite, the E4 safety properties at their
# required volume, policy branch coverage, the replay end-to-end run, and the entry-check lines in this lane's area.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --all-groups --locked
uv run --no-sync ruff check
uv run --no-sync ruff format --check
uv run --no-sync pyright
uv run --no-sync pytest -q -p no:cacheprovider
HYPOTHESIS_PROFILE=entry uv run --no-sync pytest -q -p no:cacheprovider --entry-only=E4
uv run --no-sync pytest -q -p no:cacheprovider --cov=safecut.decide.policy --cov-branch --cov-fail-under=100 tests/test_policy.py
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
uv run --no-sync safecut run fixtures/clips/SC-A-91-synthetic-20261030.mp4 --out "$work/j_checks" --replay --auto-approve-policy
uv run --no-sync python -m safecut.receipt verify "$work/j_checks/receipt.json"
uv run --no-sync python -c "import sys; from safecut.contracts import validate_job_dir; validate_job_dir(sys.argv[1])" "$work/j_checks"
# A partial entry-check run always ends "ENTRY: FAIL … partial run" (only a full run can pass); this lane's lines must
# each be OK, and any other failure still fails the checks.
status=0
bash scripts/entry-check.sh --only E2,E3,E4 > "$work/entry.log" 2>&1 || status=$?
cat "$work/entry.log"
if [ "$status" -ne 0 ] && ! grep -q "^ENTRY: FAIL .*partial run" "$work/entry.log"; then exit "$status"; fi
for line in E2 E3 E4; do grep -q "^$line: OK" "$work/entry.log"; done
