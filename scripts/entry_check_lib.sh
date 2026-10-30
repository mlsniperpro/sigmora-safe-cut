# shellcheck shell=bash
# The verdict half of scripts/entry-check.sh, sourced by it and by tests/test_entry_check.py.
#
#   entry_record <E-line> OK|FAIL [reason]   print and remember one line
#   entry_verdict [partial-note]              print ENTRY: PASS or ENTRY: FAIL (<n>), return 0 only on PASS
#
# PASS needs every line in ENTRY_LINES recorded, each exactly once, all OK, and no partial run. A line that never
# reported (a crash, a timeout that killed the reporter) counts as a failure.

ENTRY_LINES=(E1 E2 E3 E4 E5 E6 E7 E8 E9 E10 E11 E12)
declare -A ENTRY_RESULT=()
ENTRY_DUPLICATES=0

entry_record() {
  local line="$1" status="$2" reason="${3:-}"
  if [ -n "${ENTRY_RESULT[$line]+set}" ]; then
    ENTRY_DUPLICATES=$((ENTRY_DUPLICATES + 1))
    status="FAIL"
    reason="reported twice"
  fi
  case "$status" in
    OK) ENTRY_RESULT[$line]=OK; echo "$line: OK" ;;
    *) ENTRY_RESULT[$line]=FAIL; echo "$line: FAIL ${reason:-no reason given}" ;;
  esac
}

entry_verdict() {
  local partial="${1:-}" failed=0 line
  for line in "${ENTRY_LINES[@]}"; do
    if [ "${ENTRY_RESULT[$line]:-}" != "OK" ]; then
      failed=$((failed + 1))
      if [ -z "${ENTRY_RESULT[$line]+set}" ] && [ -z "$partial" ]; then echo "$line: FAIL never reported"; fi
    fi
  done
  failed=$((failed + ENTRY_DUPLICATES))
  if [ -n "$partial" ]; then
    echo "ENTRY: FAIL ($failed): partial run ($partial); only a full run can pass"
    return 1
  fi
  if [ "$failed" -eq 0 ]; then
    echo "ENTRY: PASS"
    return 0
  fi
  echo "ENTRY: FAIL ($failed)"
  return 1
}
