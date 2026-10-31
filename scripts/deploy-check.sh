#!/usr/bin/env bash
# scripts/deploy-check.sh <api-url> <web-url|-> [hero-id]: smoke-test a deployed Safe Cut.
#
# Checks the API (health, a cold wake, the GPU audit, CORS for the web origin, the demo job, refusals) and the web
# app (pages, security headers). Pass "-" as the web URL to check the API alone. The API must run live with
# MODEL_API_KEY set, unless DEPLOY_REPLAY_OK=1, and audit on the GPU (SAFECUT_AUDIT_GPU), unless DEPLOY_YUNET_OK=1.
# The API scales to zero: the first request may wait for a container (up to DEPLOY_WAKE_TIMEOUT_S, 150 s, Modal's
# own limit); DEPLOY_EXPECT_COLD=1 (right after a deploy) fails unless that request woke a fresh container. Every
# other request is bounded (curl -m 20). Prints one "ok"/"FAIL" line per check and ends with DEPLOY: PASS or
# DEPLOY: FAIL (<n>); exits 0 only on PASS.
set -uo pipefail

API="${1:-}"
WEB="${2:-}"
HERO="${3:-demo}"
if [ -z "$API" ] || [ -z "$WEB" ]; then
  echo "usage: bash scripts/deploy-check.sh <api-url> <web-url|-> [hero-id]" >&2
  exit 2
fi
API="${API%/}"
WEB="${WEB%/}"
FAILS=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok() { echo "ok    $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }

# fetch <name> <curl args…>: body in $TMP/<name>.body, headers in $TMP/<name>.head; prints the status code.
fetch() {
  local name="$1"; shift
  curl -sS -m 20 -o "$TMP/$name.body" -D "$TMP/$name.head" -w '%{http_code}' "$@" 2>"$TMP/$name.err" || echo "000"
}
header() { grep -i "^$2:" "$TMP/$1.head" | tail -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'; }
json() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))$2)" "$TMP/$1.body" 2>/dev/null; }

# ---------------------------------------------------------------- API
# The first request may wake the API from zero: it waits as long as Modal holds a request, and says how long.
wake="$(curl -sS -m "${DEPLOY_WAKE_TIMEOUT_S:-150}" -o "$TMP/health.body" -D "$TMP/health.head" \
  -w '%{http_code} %{time_total}' "$API/healthz" 2>"$TMP/health.err" || echo "000 0")"
code="${wake%% *}"
waited="${wake##* }"
if [ "$code" = "200" ] && [ "$(json health "['status']")" = "ok" ]; then
  ok "API /healthz: ok in ${waited} s (mode $(json health "['mode']"), meta $(json health "['meta']"))"
else
  fail "API /healthz answered $code: $(head -c 200 "$TMP/health.body" 2>/dev/null)"
fi
# A container whose uptime fits inside the first request's wait started for that request: a cold wake.
uptime="$(json health "['uptime_s']")"
cold="$(python3 -c "import sys; print(float(sys.argv[1]) <= float(sys.argv[2]) + 5)" "${uptime:-x}" "$waited" 2>/dev/null)"
if [ -z "$uptime" ]; then
  fail "API /healthz has no uptime_s: this isn't the scale-to-zero API"
elif [ "$cold" = "True" ]; then
  ok "API woke from a cold start: answered in ${waited} s by a container up ${uptime} s"
elif [ "${DEPLOY_EXPECT_COLD:-}" = "1" ]; then
  fail "API was already up ${uptime} s: no cold start right after the deploy (is min_containers still above 0?)"
else
  ok "API already awake (up ${uptime} s); no cold start this time"
fi
if [ "$(json health "['audit_gpu']")" = "True" ]; then
  ok "API audits with EgoBlur on the GPU function (SAFECUT_AUDIT_GPU on; YuNet only when it can't answer)"
elif [ "${DEPLOY_YUNET_OK:-}" = "1" ]; then
  ok "API audits with YuNet on CPU (audit_gpu $(json health "['audit_gpu']")), accepted by DEPLOY_YUNET_OK=1"
else
  fail "API doesn't audit on the GPU (audit_gpu $(json health "['audit_gpu']")): set SAFECUT_AUDIT_GPU=1"
fi
# A deployment the judges can use runs live with its Meta key; a demo-mode deployment passes only when asked to
# (DEPLOY_REPLAY_OK=1, e.g. after the judging window, or this script's own tests).
if [ "$(json health "['mode']")" = "live" ] && [ "$(json health "['key']")" = "True" ]; then
  ok "API runs live, with MODEL_API_KEY set"
elif [ "${DEPLOY_REPLAY_OK:-}" = "1" ]; then
  ok "API in mode $(json health "['mode']") (key $(json health "['key']")), accepted by DEPLOY_REPLAY_OK=1"
else
  fail "API isn't live with a Meta key (mode $(json health "['mode']"), key $(json health "['key']")): every judge upload would fail"
fi

code="$(fetch missing "$API/v1/jobs/j_0000000000000000000000")"
if [ "$code" = "404" ] && [ "$(json missing "['error']['code']")" = "not_found" ]; then ok "API: an unknown job is a 404 not_found"
else fail "API: an unknown job answered $code"; fi

code="$(fetch badcode -X POST -H 'Content-Type: application/json' --data '{"code":"deploy-check-not-a-code"}' "$API/v1/codes/check")"
if [ "$code" = "401" ]; then ok "API: a wrong access code is refused (401)"; else fail "API: a wrong access code answered $code"; fi

# The demo job is precomputed in the background after a cold start (about a minute): wait for it before judging.
deadline=$(( $(date +%s) + ${DEPLOY_DEMO_WAIT_S:-300} ))
# A redeploy's container keeps serving the previous demo while it builds its own: wait until /healthz says the build
# for this code is done, so the checks below judge this deploy's demo, never an earlier one.
# Anything but an explicit False (a poll that timed out, a partial body) means keep waiting.
while [ "$(json health "['demos_building']")" != "False" ] && [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 5
  fetch health "$API/healthz" >/dev/null
done
# Every start asks Modal to hold the container up while the demo builds: the same call that keeps a judge's job alive.
# It runs on a thread of its own, so the first answer after a cold wake may predate it: wait for its outcome too.
while [ "$(json health "['keepalive']")" = "None" ] && [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 2
  fetch health "$API/healthz" >/dev/null
done
keepalive="$(json health "['keepalive']")"
if [ "$keepalive" = "True" ]; then
  ok "API: its keepalive reached Modal (a started job holds the container up)"
elif [ "$keepalive" = "False" ]; then
  fail "API: its keepalive failed (SafeCutApi.hold.spawn): a job could be stranded when the container sleeps"
elif [ "${DEPLOY_EXPECT_COLD:-}" = "1" ]; then
  fail "API: no keepalive was tried after the cold start (is the API built with Service(keepalive=...)?)"
else
  ok "API: no keepalive tried (${keepalive:-not reported}): not on Modal, or not yet"
fi
if [ "$(json health "['demos_building']")" = "False" ] && json health "['demos_current']" | grep -q "'$HERO'"; then
  ok "API: the demo '$HERO' was built (or confirmed) by this deploy's code"
elif [ "$(json health "['demos_building']")" = "False" ]; then
  fail "API: this deploy's code didn't build the demo '$HERO' (the one served, if any, is an earlier deploy's)"
else
  fail "API: the demo build didn't finish within ${DEPLOY_DEMO_WAIT_S:-300} s"
fi
code="$(fetch demo "$API/v1/demo/$HERO")"
while [ "$code" = "404" ] && [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 5
  code="$(fetch demo "$API/v1/demo/$HERO")"
done
if [ "$code" = "200" ] && [ "$(json demo "['mode']")" = "replay" ]; then
  ok "API: the demo job '$HERO' replays (synthetic: $(json demo "['synthetic']"))"
  video="$(json demo "['video_url']")"
  case "$video" in http*) video_url="$video" ;; *) video_url="$API$video" ;; esac
  vcode="$(fetch video -r 0-1023 "$video_url")"
  if [ "$vcode" = "206" ] || [ "$vcode" = "200" ]; then ok "API: the demo's signed video URL serves bytes ($vcode)"
  else fail "API: the demo's signed video URL answered $vcode"; fi
  # The API container builds the demo job at startup through its own audit path (the handoff Volume, the GPU
  # function): its audit names what actually ran there.
  dmodel="$(json demo "['audit']['egoblur']['model']")"
  ddevice="$(json demo "['audit']['egoblur'].get('device') or ''")"
  if [ "$dmodel" = "egoblur-gen2" ] && [[ "$ddevice" == cuda:* ]]; then
    ok "API: the demo job, built in the API container, was audited by $dmodel on $ddevice"
  elif [ "${DEPLOY_YUNET_OK:-}" = "1" ]; then
    ok "API: the demo job was audited by $dmodel on ${ddevice:-an unnamed device}, accepted by DEPLOY_YUNET_OK=1"
  else
    fail "API: the demo job was audited by $dmodel on ${ddevice:-an unnamed device}, not EgoBlur on a GPU (its raw/audit/gpu.json says why)"
  fi
else
  fail "API: /v1/demo/$HERO answered $code (is the demo job built? see the api container's logs)"
fi

if [ "$WEB" != "-" ]; then
  origin="$(python3 -c "import sys; from urllib.parse import urlsplit; u=urlsplit(sys.argv[1]); print(f'{u.scheme}://{u.netloc}')" "$WEB")"
  code="$(fetch cors -X OPTIONS -H "Origin: $origin" -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' "$API/v1/jobs")"
  if [ "$(header cors access-control-allow-origin)" = "$origin" ]; then ok "API: CORS allows the web origin $origin"
  else fail "API: CORS preflight from $origin answered $code without allowing it (SAFECUT_CORS_ORIGINS)"; fi
  code="$(fetch evil -X OPTIONS -H 'Origin: https://deploy-check.invalid' -H 'Access-Control-Request-Method: POST' "$API/v1/jobs")"
  if [ -z "$(header evil access-control-allow-origin)" ]; then ok "API: CORS refuses other origins"
  else fail "API: CORS allowed https://deploy-check.invalid"; fi

  # ---------------------------------------------------------------- web
  for path in / /try /privacy; do
    name="web_$(printf '%s' "$path" | tr -c 'a-z' '_')"
    code="$(fetch "$name" "$WEB$path")"
    if [ "$code" = "200" ]; then ok "web $path: 200"; else fail "web $path answered $code"; fi
  done
  csp="$(header web__ content-security-policy)"
  if [[ "$csp" == *"frame-ancestors"* && "$csp" == *"object-src 'none'"* ]]; then ok "web: CSP with frame-ancestors and object-src 'none'"
  else fail "web: the landing page's CSP is missing or weak: ${csp:0:120}"; fi
  if [ -n "$(header web__ strict-transport-security)" ]; then ok "web: HSTS is set"; else fail "web: no Strict-Transport-Security header"; fi
  code="$(fetch web404 "$WEB/deploy-check-no-such-page")"
  if [ "$code" = "404" ]; then ok "web: unknown pages are 404"; else fail "web: an unknown page answered $code"; fi
fi

# Last, because it uses up this checker's own rate limit for a minute.
# The per-IP limit must hold even when the client sends its own X-Forwarded-For (a proxy that doesn't set it would
# let every request claim a new IP). SPOOF_N requests with a different forged address each must meet a 429.
SPOOF_N="${SPOOF_N:-70}"
limited=0
for i in $(seq 1 "$SPOOF_N"); do
  c="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' -H "X-Forwarded-For: 198.51.100.$((i % 250))" "$API/v1/jobs/j_0000000000000000000000" 2>/dev/null || echo 000)"
  if [ "$c" = "429" ]; then limited=1; break; fi
done
if [ "$limited" = "1" ]; then ok "API: the per-IP limit holds against forged X-Forwarded-For headers"
else fail "API: $SPOOF_N requests with forged X-Forwarded-For were never rate limited (check SAFECUT_TRUST_PROXY)"; fi


if [ "$FAILS" -eq 0 ]; then echo "DEPLOY: PASS"; exit 0; fi
echo "DEPLOY: FAIL ($FAILS)"
exit 1
