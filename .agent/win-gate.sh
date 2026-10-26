#!/usr/bin/env bash
# .agent/win-gate.sh: deterministic "done" gate for one hackathon entry.
#
# Adapted from prod-kit's gate.sh for repos where several cloud sessions each
# own one branch. Every check is scoped to this branch's own diff against the
# base branch, and each session keeps its evidence in .agent/win/<TAG>/, so
# parallel sessions never judge (or block on) each other's work.
#
#   bash .agent/win-gate.sh <TAG>            run every check
#   bash .agent/win-gate.sh <TAG> --cached   reuse the last result if nothing changed
#
# Last line is always "GATE: PASS" or "GATE: FAIL (<n>): <first failure>".
# Exit code: 0 on PASS, 1 on FAIL. The formats it reads are in .agent/WIN-GATE.md.
#
# Tunables (env): WIN_CMD_TIMEOUT (seconds per command, default 1800),
#                 WIN_MIN_CHECKLIST (minimum resolved checklist lines, default 15).

set -uo pipefail

TAG="${1:-}"
MODE="${2:-}"
if [ -z "$TAG" ] || [[ "$TAG" == -* ]] || [[ ! "$TAG" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: bash .agent/win-gate.sh <TAG> [--cached]   (TAG: letters, digits, . _ -)" >&2
  echo "GATE: FAIL (1): no session TAG given"
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 1

S=".agent/win/$TAG"
LOGDIR="$S/gate-logs"
LAST_LOG="$S/gate-last.log"
LAST_META="$S/gate-last.meta"
TIMEOUT="${WIN_CMD_TIMEOUT:-1800}"
MIN_CHECKLIST="${WIN_MIN_CHECKLIST:-15}"
mkdir -p "$LOGDIR"

conf() { # <key> <default>: read KEY=value from $S/gate.conf
  local v=""
  [ -f "$S/gate.conf" ] && v="$(grep -m1 -E "^$1=" "$S/gate.conf" | cut -d= -f2- | sed -E 's/^[[:space:]]+|[[:space:]]+$//g; s/^"(.*)"$/\1/')"
  echo "${v:-$2}"
}
BASE="$(conf BASE origin/main)"
if [ -f "$S/WIN-CHECKLIST.md" ]; then CHECKLIST="$(conf CHECKLIST "$S/WIN-CHECKLIST.md")"; else CHECKLIST="$(conf CHECKLIST WIN-CHECKLIST.md)"; fi
if [ -f "$S/BLOCKED.md" ]; then BLOCKED="$(conf BLOCKED "$S/BLOCKED.md")"; else BLOCKED="$(conf BLOCKED BLOCKED.md)"; fi

# Runtime files this gate writes; never count them as uncommitted work.
RUNTIME_EXCLUDES=(':(exclude).agent/win/*/gate-logs' ':(exclude).agent/win/*/gate-last.log' ':(exclude).agent/win/*/gate-last.meta')

hash16() { if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | cut -c1-16; }
if command -v timeout >/dev/null 2>&1; then TMO=(timeout "$TIMEOUT"); elif command -v gtimeout >/dev/null 2>&1; then TMO=(gtimeout "$TIMEOUT"); else TMO=(); fi

# ---------------------------------------------------------------- fingerprint
fingerprint() {
  {
    git rev-parse HEAD 2>/dev/null || echo "no-head"
    git rev-parse "$BASE" 2>/dev/null || echo "no-base"
    git status --porcelain -- . "${RUNTIME_EXCLUDES[@]}" 2>/dev/null
    for f in "$S/checks.sh" "$S/gate-skip" "$S/gate.conf" "$S/pids" "$S/reaudit.md" "$S/break-it.md" \
             "$CHECKLIST" "$BLOCKED" "$0"; do
      [ -f "$f" ] && { echo "$f"; cat "$f"; }
    done
  } | hash16
}

if [ "$MODE" = "--cached" ] && [ -f "$LAST_META" ] && [ -f "$LAST_LOG" ]; then
  # shellcheck disable=SC1090
  . "$LAST_META"
  if [ "${FINGERPRINT:-}" = "$(fingerprint)" ]; then
    cat "$LAST_LOG"
    echo "(cached result from ${TIME:-unknown}; nothing changed since)"
    [ "${RESULT:-FAIL}" = "PASS" ] && exit 0 || exit 1
  fi
fi

exec > >(tee "$LAST_LOG") 2>&1

# ---------------------------------------------------------------- helpers
FAILS=()
fail() { FAILS+=("$1"); echo "FAIL  $1"; }
ok()   { echo "ok    $1"; }
note() { echo "skip  $1"; }

# $S/gate-skip lines:  <command substring> | <reason>
# Only for commands that physically cannot run here (a missing owner key, say);
# the same input must be listed in the BLOCKED file.
skip_reason() {
  [ -f "$S/gate-skip" ] || return 1
  local line pat reason
  while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "${line// }" || "$line" == \#* || "$line" != *"|"* ]] && continue
    pat="$(echo "${line%%|*}" | xargs)"
    reason="$(echo "${line#*|}" | xargs)"
    { [ -z "$pat" ] || [ -z "$reason" ]; } && continue
    if [[ "$1" == *"$pat"* ]]; then echo "$reason"; return 0; fi
  done < "$S/gate-skip"
  return 1
}

run_cmd() { # <label> <dir> <command>
  local label="$1" dir="$2" cmd="$3" reason log rc
  if reason="$(skip_reason "$cmd")"; then note "$label: $cmd  (gate-skip: $reason)"; return; fi
  log="$LOGDIR/$(echo "$label" | tr -c 'A-Za-z0-9._-' '_').log"
  ( cd "$dir" && CI=true FORCE_COLOR=0 "${TMO[@]}" bash -c "$cmd" ) >"$log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    ok "$label: $cmd"
  else
    [ "$rc" -eq 124 ] && rc="timeout after ${TIMEOUT}s"
    fail "$label: \`$cmd\` failed ($rc). Full log: $log"
    tail -n 12 "$log" | sed 's/^/        | /'
  fi
}

count() { grep -cE "$1" "$2" 2>/dev/null || true; }

# Code (not prose, not this kit) that differs between <sha> and the working tree.
changed_since() {
  git diff --name-only "$1" -- . ':(exclude).agent' ':(exclude).claude' ':(exclude)*.md' 2>/dev/null
}

check_report_commit() { # <file> <key>
  local file="$1" key="$2" sha changed
  sha="$(grep -m1 -E "^${key}:" "$file" | sed -E "s/^${key}:[[:space:]]*//; s/[[:space:]]+$//")"
  if [ -z "$sha" ]; then fail "$file has no '${key}: <sha>' line"; return; fi
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then fail "$file: ${key} '$sha' is not a commit in this repo"; return; fi
  changed="$(changed_since "$sha")"
  if [ -n "$changed" ]; then
    fail "$file is stale: code changed after ${key} $sha ($(echo "$changed" | wc -l | xargs) files, e.g. $(echo "$changed" | head -1)). Redo it against the current code."
  else
    ok "$file covers the current code ($key $sha)"
  fi
}

echo "== win-gate $TAG: $(date -u +%Y-%m-%dT%H:%M:%SZ)  repo: $ROOT  base: $BASE"

# ---------------------------------------------------------------- 0. base and gate integrity
echo "-- base"
git fetch -q origin "${BASE#origin/}" 2>/dev/null || note "could not fetch $BASE (offline?); using the local copy"
if ! git rev-parse -q --verify "$BASE^{commit}" >/dev/null; then
  fail "base $BASE not found (set BASE= in $S/gate.conf)"
  MB="$(git rev-list --max-parents=0 HEAD | tail -1)"
else
  MB="$(git merge-base "$BASE" HEAD 2>/dev/null || git rev-parse "$BASE")"
  ok "branch diff measured from merge-base ${MB:0:12} with $BASE"
  if git cat-file -e "$BASE:.agent/win-gate.sh" 2>/dev/null; then
    if git diff --quiet "$BASE" -- .agent/win-gate.sh; then ok "gate matches $BASE"
    else fail "this gate differs from $BASE:.agent/win-gate.sh; restore it with: git checkout $BASE -- .agent/win-gate.sh"; fi
  fi
fi

# ---------------------------------------------------------------- 1. checklist and blockers
echo "-- checklist"
if [ ! -s "$CHECKLIST" ]; then
  fail "missing $CHECKLIST (every judging criterion, brief requirement and audit finding as - [x] done / - [P] parked / - [-] n/a, each with evidence)"
else
  c_open="$(count '^[[:space:]]*[-*] \[ \]' "$CHECKLIST")"
  c_done="$(count '^[[:space:]]*[-*] \[[xXpP-]\]' "$CHECKLIST")"
  c_park="$(count '^[[:space:]]*[-*] \[[pP]\]' "$CHECKLIST")"
  # Status tables count as open while any row still shows a work-in-progress mark.
  t_open="$(grep -E '^\|' "$CHECKLIST" 2>/dev/null | grep -cE '❌|🔧|⏳|🟡|🚧|⚠️|\bWIP\b|\bTODO\b' || true)"
  if [ "${c_open:-0}" -gt 0 ]; then
    fail "$CHECKLIST has $c_open open item(s). Next: $(grep -m1 -E '^[[:space:]]*[-*] \[ \]' "$CHECKLIST" | sed -E 's/^[[:space:]]*[-*] \[ \][[:space:]]*//' | cut -c1-140)"
  elif [ "${t_open:-0}" -gt 0 ]; then
    fail "$CHECKLIST has $t_open table row(s) still marked in progress, e.g. $(grep -E '^\|' "$CHECKLIST" | grep -m1 -E '❌|🔧|⏳|🟡|🚧|⚠️|\bWIP\b|\bTODO\b' | cut -c1-140)"
  elif [ "${c_done:-0}" -lt "$MIN_CHECKLIST" ]; then
    fail "$CHECKLIST resolves only ${c_done:-0} checkbox item(s); map every criterion, requirement and finding (minimum $MIN_CHECKLIST)"
  else
    ok "checklist: $c_done items resolved ($c_park parked), none open"
  fi
  if [ "${c_park:-0}" -gt 0 ] && [ ! -s "$BLOCKED" ]; then
    fail "$c_park parked item(s) but $BLOCKED is missing or empty (list each owner input it waits for)"
  fi
fi

# ---------------------------------------------------------------- 2. audits and break-it
echo "-- reports"
R="$S/reaudit.md"
if [ ! -f "$R" ]; then
  fail "missing $R (hostile judge + senior-reviewer audit of the current code, with AUDITED_COMMIT / OPEN_CRITICAL / OPEN_HIGH / CLEAN_AUDITS_IN_A_ROW lines)"
else
  crit="$(grep -m1 -E '^OPEN_CRITICAL:' "$R" | grep -oE '[0-9]+' | head -1)"
  high="$(grep -m1 -E '^OPEN_HIGH:' "$R" | grep -oE '[0-9]+' | head -1)"
  clean="$(grep -m1 -E '^CLEAN_AUDITS_IN_A_ROW:' "$R" | grep -oE '[0-9]+' | head -1)"
  if [ -z "$crit" ] || [ -z "$high" ] || [ -z "$clean" ]; then
    fail "$R needs 'OPEN_CRITICAL: <n>', 'OPEN_HIGH: <n>' and 'CLEAN_AUDITS_IN_A_ROW: <n>' lines"
  elif [ "$crit" -gt 0 ] || [ "$high" -gt 0 ]; then
    fail "re-audit still has $crit critical and $high high open findings"
  elif [ "$clean" -lt 2 ]; then
    fail "only $clean clean full audit(s) in a row; two consecutive audits must find nothing new"
  else
    ok "re-audit: 0 critical, 0 high, $clean clean audits in a row"
  fi
  check_report_commit "$R" AUDITED_COMMIT
fi
B="$S/break-it.md"
if [ -f "$B" ]; then check_report_commit "$B" TESTED_COMMIT
else fail "missing $B (what you did to break it: fuzz, soak, failure injection, the replay e2e path, a fresh-clone README run; results; TESTED_COMMIT line)"; fi

# ---------------------------------------------------------------- 3. git state
echo "-- git"
dirty="$(git status --porcelain -- . "${RUNTIME_EXCLUDES[@]}")"
if [ -n "$dirty" ]; then fail "uncommitted changes in $(echo "$dirty" | wc -l | xargs) path(s), e.g. $(echo "$dirty" | head -1 | cut -c4-)"
else ok "working tree clean"; fi
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  ahead="$(git rev-list --count '@{u}..HEAD')"
  if [ "$ahead" = "0" ]; then ok "branch pushed"; else fail "$ahead commit(s) not pushed to $(git rev-parse --abbrev-ref '@{u}')"; fi
else
  fail "branch $(git rev-parse --abbrev-ref HEAD) has no upstream; push it (git push -u origin HEAD)"
fi

# ---------------------------------------------------------------- 4. background processes
echo "-- processes"
if [ -f "$S/pids" ]; then
  alive=()
  while IFS= read -r p || [ -n "$p" ]; do
    p="$(echo "$p" | grep -oE '^[0-9]+' || true)"
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null && alive+=("$p")
  done < "$S/pids"
  if [ "${#alive[@]}" -eq 0 ]; then ok "no recorded background process still running"
  else fail "background process(es) still running: ${alive[*]} (finish or stop them, record the results, then clear $S/pids)"; fi
else
  ok "no background processes recorded"
fi

# ---------------------------------------------------------------- 5. shortcuts this branch added
echo "-- shortcuts (lines added since ${MB:0:12})"
EXCL=(':(exclude).agent' ':(exclude).claude' ':(exclude)*.md' ':(exclude)*.mdx' ':(exclude)*.lock'
      ':(exclude)**/package-lock.json' ':(exclude)**/pnpm-lock.yaml' ':(exclude)**/yarn.lock'
      ':(exclude)**/vendor/**' ':(exclude)**/node_modules/**' ':(exclude)*.min.js' ':(exclude)*.snap'
      ':(exclude)*.svg' ':(exclude)*.csv' ':(exclude)*.jsonl')
ADDED="$(git diff -U0 --no-color "$MB" -- . "${EXCL[@]}" 2>/dev/null | awk '
  /^\+\+\+ /{f=substr($0,7); next} /^@@/{split($3,a,","); n=substr(a[1],2)+0; next}
  /^\+/{print f ":" n ": " substr($0,2); n++}')"
scan() { # <label> <regex> [filter regex that drops justified lines]
  local hits n
  hits="$(printf '%s\n' "$ADDED" | grep -E "$2" | grep -v 'gate-allow' || true)"
  [ -n "${3:-}" ] && hits="$(printf '%s\n' "$hits" | grep -viE "$3" || true)"
  n="$(printf '%s\n' "$hits" | grep -c . || true)"
  if [ "${n:-0}" -gt 0 ]; then
    fail "$1: $n line(s) added on this branch"
    printf '%s\n' "$hits" | head -5 | cut -c1-160 | sed 's/^/        | /'
  else
    ok "$1: none"
  fi
}
scan "unfinished markers (TODO/FIXME/HACK/XXX)" '\b(TODO|FIXME|HACK|XXX)\b'
scan "not-implemented stubs" 'NotImplementedError|[Nn]ot [Ii]mplemented( yet)?["'"'"'`]|unimplemented!\(|todo!\(|implement (this )?later'
scan "skipped or focused tests" '\b(it|test|describe|context)\.(skip|only|todo)\(|\bx(it|describe|test)\(|@pytest\.mark\.(skip|xfail)|pytest\.skip\(|\bt\.Skip(Now)?\(|#\[ignore\]|@Disabled\b|@Ignore\b'
scan "masked failures (|| true, continue-on-error)" '\|\|[[:space:]]*true\b|continue-on-error:[[:space:]]*true'
scan "unjustified suppressions" '@ts-ignore|@ts-nocheck|@ts-expect-error|eslint-disable|#[[:space:]]*type:[[:space:]]*ignore|#[[:space:]]*noqa|//[[:space:]]*nolint|#[[:space:]]*pylint:[[:space:]]*disable' \
  ' -- .{8,}|because|reason|justif'

# ---------------------------------------------------------------- 6. verification
echo "-- verification"
if [ ! -f "$S/checks.sh" ]; then
  fail "missing $S/checks.sh: every lint, typecheck, unit/property, integration, replay e2e and build command for this entry"
elif ! grep -qiE 'test|pytest|vitest|jest|playwright|cargo|go ' "$S/checks.sh"; then
  fail "$S/checks.sh contains no test command"
else
  run_cmd "checks.sh" "$ROOT" "bash $S/checks.sh"
fi

# Independent of checks.sh: run the scripts each touched package declares, so a
# thin checks.sh cannot hide a failing suite.
SCRIPT_NAMES=(lint typecheck type-check check-types tsc test build)
pm_for() { # <dir>
  local d="$1" probe
  for probe in "$d" "$ROOT"; do
    [ -f "$probe/pnpm-lock.yaml" ] && { echo pnpm; return; }
    [ -f "$probe/yarn.lock" ] && { echo yarn; return; }
    { [ -f "$probe/bun.lockb" ] || [ -f "$probe/bun.lock" ]; } && { echo bun; return; }
    [ -f "$probe/package-lock.json" ] && { echo npm; return; }
  done
  echo npm
}
has_script() { node -e 'const p=require(process.argv[1]);process.exit(p.scripts&&p.scripts[process.argv[2]]?0:1)' "$1" "$2" 2>/dev/null; }
nearest_pkg() { # <file> -> directory of the nearest tracked package.json, or nothing
  local d; d="$(dirname "$1")"
  while :; do
    if [ -f "$d/package.json" ] && git ls-files --error-unmatch "$d/package.json" >/dev/null 2>&1; then echo "$d"; return; fi
    [ "$d" = "." ] && return
    d="$(dirname "$d")"
  done
}
if command -v node >/dev/null 2>&1; then
  PKGS="$(git diff --name-only "$MB" -- . ':(exclude).agent' ':(exclude).claude' ':(exclude)*.md' 2>/dev/null \
          | while IFS= read -r f; do nearest_pkg "$f"; done | sort -u)"
  if [ -z "$PKGS" ]; then note "no JavaScript package touched on this branch"; fi
  for d in $PKGS; do
    for s in "${SCRIPT_NAMES[@]}"; do
      has_script "$ROOT/$d/package.json" "$s" && run_cmd "pkg:${d}:$s" "$ROOT/$d" "$(pm_for "$ROOT/$d") run $s"
    done
  done
fi
PY_CHANGED="$(git diff --name-only --diff-filter=d "$MB" -- '*.py' 2>/dev/null | tr '\n' ' ')"
if [ -n "${PY_CHANGED// }" ]; then
  if command -v ruff >/dev/null 2>&1; then run_cmd "py:ruff" "$ROOT" "ruff check $PY_CHANGED"
  else note "ruff not installed; Python lint must be in $S/checks.sh"; fi
fi

# ---------------------------------------------------------------- 7. secrets this branch added
echo "-- secrets"
if command -v gitleaks >/dev/null 2>&1; then
  if gitleaks help git >/dev/null 2>&1; then run_cmd "secrets:gitleaks" "$ROOT" "gitleaks git --no-banner --redact --log-opts='$MB..HEAD' ."
  else run_cmd "secrets:gitleaks" "$ROOT" "gitleaks detect --no-banner --redact --log-opts='$MB..HEAD' --source ."; fi
else
  note "gitleaks not installed; running the built-in pattern scan on added lines"
fi
SECRET_RE='sk-ant-[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9]{16,}|rk_live_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN ([A-Z]+ )?PRIVATE KEY-----|"private_key":[[:space:]]*"-----BEGIN'
leaks="$(printf '%s\n' "$ADDED" | grep -E "$SECRET_RE" | grep -v 'gate-allow' || true)"
if [ -n "$leaks" ]; then fail "possible secret(s) in lines added on this branch: $(printf '%s\n' "$leaks" | cut -d: -f1-2 | head -3 | tr '\n' ' ')"
else ok "no secret patterns in added lines"; fi

# ---------------------------------------------------------------- result
echo "=="
if [ "${#FAILS[@]}" -eq 0 ]; then RESULT=PASS; else RESULT=FAIL; fi
{
  echo "FINGERPRINT=$(fingerprint)"
  echo "RESULT=$RESULT"
  echo "TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$LAST_META"

if [ "$RESULT" = "PASS" ]; then echo "GATE: PASS"
else echo "GATE: FAIL (${#FAILS[@]}): ${FAILS[0]}"; fi
[ "$RESULT" = "PASS" ] && exit 0 || exit 1
