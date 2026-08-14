#!/usr/bin/env bash
# Smoke test against a RUNNING dashboard — the deployed artifact, not a dev
# server. Walks the CLI's own sequence: sign in, upload, read the report.
#
# Usage: BASE=http://localhost:3000 TEAM_TOKEN=... ./scripts/smoke-e2e.sh
set -euo pipefail

BASE="${BASE:-http://localhost:3000}"
TEAM_TOKEN="${TEAM_TOKEN:-dev}"
CB="http://127.0.0.1:9/callback"   # never connected to; we only read the query

pass() { printf '  ✓ %s\n' "$1"; }

echo "1. cli-auth page renders"
curl -fsS "$BASE/cli-auth?redirect_uri=$CB&count=1" | grep -q "Authorize upload"
pass "sign-in form served"

echo "2. a wrong team token is refused"
code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$BASE/api/cli-auth" \
  --data-urlencode "team_token=definitely-not-it" \
  --data-urlencode "name=Smoke Tester" --data-urlencode "email=smoke@example.com" \
  --data-urlencode "redirect_uri=$CB" --data-urlencode "count=1")
[ "$code" = "303" ] || { echo "expected 303 back to the form, got $code" >&2; exit 1; }
pass "bounced back to the form"

echo "3. the real token issues upload credentials"
LOC=$(curl -fsS -o /dev/null -w '%{redirect_url}' -X POST "$BASE/api/cli-auth" \
  --data-urlencode "team_token=$TEAM_TOKEN" \
  --data-urlencode "name=Smoke Tester" --data-urlencode "email=smoke@example.com" \
  --data-urlencode "redirect_uri=$CB" --data-urlencode "count=1")
TOKEN=$(python3 -c "
import sys, json, urllib.parse
q = urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)
print(json.loads(q['tokens'][0])[0])" "$LOC")
[ -n "$TOKEN" ] || { echo "no token in callback: $LOC" >&2; exit 1; }
pass "token issued and redirected to the loopback callback"

echo "4. an upload is accepted and reports where to read it"
# Tz-aware ISO bounds, exactly what gnomon/sources/discovery.py produces.
REPORT=$(curl -fsS -X POST "$BASE/api/gnomon/ingest" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"score_contract_id":"smoke","coverage":{"flag":"complete","indexed":9,"transcripts":9},
       "context":{"date_range":["2026-01-01T00:00:00-03:00","2026-06-30T00:00:00-03:00"],
                  "total_sessions":9,"total_prompts":42,"window_months":6},
       "profile":{"aq":{"aq_0_100":64,"tier":"Proficient"}}}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['reportUrl'])")
pass "ingested, report at $REPORT"

echo "5. the report and the board render that upload"
curl -fsS "$BASE$REPORT" | grep -q "Smoke Tester"
curl -fsS "$BASE/" | grep -q "Smoke Tester"
pass "profile and team board both show the new person"

echo "6. an unauthenticated upload is rejected"
code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$BASE/api/gnomon/ingest" \
  -H "Content-Type: application/json" -d '{}')
[ "$code" = "401" ] || { echo "expected 401, got $code" >&2; exit 1; }
pass "401 without a token"

echo
echo "smoke OK against $BASE"
