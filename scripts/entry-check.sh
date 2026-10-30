#!/usr/bin/env bash
# scripts/entry-check.sh: is the whole Safe Cut entry done? One line per E-line of .agent/ENTRY-DONE.md.
#
#   bash scripts/entry-check.sh               every check; the last line is ENTRY: PASS or ENTRY: FAIL (<n>)
#   bash scripts/entry-check.sh --only E3,E5  a subset while working; never prints PASS
#
# Run it from a fresh clone of origin/main. Every check is bounded in time (ENTRY_TIMEOUT, seconds per check,
# default 2400); E3 runs with the network blocked. Logs go to $ENTRY_LOG_DIR (default: a temp directory).
# The owner reviews every diff to this file: checks may be added or made stricter, never removed or weakened.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# shellcheck source=scripts/entry_check_lib.sh
. "$ROOT/scripts/entry_check_lib.sh"

ONLY=""
if [ "${1:-}" = "--only" ]; then ONLY="${2:-}"; fi
if [ -n "${1:-}" ] && [ -z "$ONLY" ]; then echo "usage: bash scripts/entry-check.sh [--only E1,E2,…]" >&2; exit 2; fi

TIMEOUT="${ENTRY_TIMEOUT:-2400}"
LOGS="${ENTRY_LOG_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/entry-check.XXXXXX")}"
mkdir -p "$LOGS"
echo "== entry-check $(date -u +%Y-%m-%dT%H:%M:%SZ) at $(git rev-parse --short HEAD 2>/dev/null || echo '?') (logs: $LOGS)"

wanted() { [ -z "$ONLY" ] || [[ ",$ONLY," == *",$1,"* ]]; }

# step <log> <command…>: run one bounded step, appending to the log; returns the command's status.
step() {
  local log="$1"; shift
  echo "\$ $*" >>"$log"
  timeout "$TIMEOUT" "$@" >>"$log" 2>&1
}

# python_check <E-line>: the check lives in scripts/entry_check.py; its last line is OK or FAIL <reason>.
python_check() {
  local line="$1" log="$LOGS/$1.log" last
  if [ ! -x "$ROOT/.venv/bin/python" ]; then entry_record "$line" FAIL "no .venv (E1's uv sync failed)"; return; fi
  timeout "$TIMEOUT" "$ROOT/.venv/bin/python" -m scripts.entry_check "$line" >"$log" 2>&1
  local rc=$?
  last="$(grep -v '^[[:space:]]*$' "$log" | tail -n 1)"
  if [ "$rc" -eq 0 ] && [ "$last" = "OK" ]; then entry_record "$line" OK
  elif [ "$rc" -eq 124 ]; then entry_record "$line" FAIL "timed out after ${TIMEOUT}s (log: $log)"
  elif [[ "$last" == FAIL* ]]; then entry_record "$line" FAIL "${last#FAIL }"
  else entry_record "$line" FAIL "exit $rc: ${last:0:200} (log: $log)"; fi
}

# ------------------------------------------------------------------ E1: the full suite on this clone
if wanted E1; then
  log="$LOGS/E1.log"; : >"$log"; reason=""
  step "$log" uv sync --all-groups --locked || reason="uv sync --all-groups --locked failed"
  if [ -z "$reason" ]; then
    step "$log" uv run --no-sync pytest -q -p no:cacheprovider || reason="pytest failed"
    if [ -z "$reason" ] && grep -qE '[0-9]+ skipped' "$log"; then reason="pytest skipped tests: $(grep -oE '[0-9]+ skipped' "$log" | tail -1)"; fi
    step "$log" uv run --no-sync ruff check || reason="${reason:-ruff check failed}"
    step "$log" uv run --no-sync ruff format --check || reason="${reason:-ruff format --check failed}"
    step "$log" uv run --no-sync pyright || reason="${reason:-pyright failed}"
  fi
  if [ -z "$reason" ]; then
    ( cd web && step "$log" pnpm install --frozen-lockfile ) || reason="pnpm install --frozen-lockfile failed"
    for script in lint typecheck test; do
      [ -n "$reason" ] && break
      ( cd web && step "$log" pnpm "$script" ) || reason="web: pnpm $script failed"
    done
  fi
  if [ -z "$reason" ]; then entry_record E1 OK; else entry_record E1 FAIL "$reason (log: $log)"; fi
fi

# ------------------------------------------------------------------ E2–E12
for line in E2 E3 E4 E5 E6 E7 E8 E9 E10 E11 E12; do
  if wanted "$line"; then python_check "$line"; fi
done

echo "=="
if [ -n "$ONLY" ]; then entry_verdict "--only $ONLY"; else entry_verdict; fi
