#!/usr/bin/env bash
# Smoke test all major TravelAI API endpoints.
set -euo pipefail

API="${1:-https://0f43uh5wuf.execute-api.ap-south-1.amazonaws.com/prod/api/v1}"
ORIGIN="${2:-https://duao2n2qg02hl.cloudfront.net}"

pass=0
fail=0

check() {
  local name="$1"
  local method="$2"
  local path="$3"
  local data="${4:-}"
  local expect="${5:-200}"

  local code
  if [ -n "$data" ]; then
    code=$(curl -s -o /tmp/smoke-body.txt -w "%{http_code}" -X "$method" \
      "$API$path" \
      -H "Content-Type: application/json" \
      -H "Origin: $ORIGIN" \
      -d "$data")
  else
    code=$(curl -s -o /tmp/smoke-body.txt -w "%{http_code}" -X "$method" \
      "$API$path" \
      -H "Origin: $ORIGIN")
  fi

  if [ "$code" = "$expect" ] || { [ "$expect" = "2xx" ] && [[ "$code" =~ ^2 ]]; }; then
    echo "PASS $name ($method $path) -> $code"
    pass=$((pass + 1))
  else
    echo "FAIL $name ($method $path) -> $code (expected $expect)"
    head -c 200 /tmp/smoke-body.txt
    echo
    fail=$((fail + 1))
  fi
}

echo "Testing API: $API"
echo "---"

check "health" GET "/health"
check "dashboard" GET "/analytics/dashboard"
check "list leads" GET "/leads"
check "create lead" POST "/leads" \
  '{"phone":"+971501234567","name":"Smoke Test","market":"uae","origin":"DEL","destination":"DXB","departure_date":"2026-08-15","opt_in_voice":false,"source":"website"}' \
  "201"
check "create lead with voice opt-in" POST "/leads" \
  '{"phone":"+971503333333","name":"Voice Opt-in","market":"uae","origin":"DEL","destination":"DXB","departure_date":"2026-08-15","opt_in_voice":true,"source":"website"}' \
  "201"
check "chat" POST "/chat" \
  '{"message":"Hello, I need a flight from Dubai to Delhi","session_id":"smoke-test-1"}' \
  "2xx"
check "flight search" POST "/flights/search" \
  '{"origin":"DXB","destination":"DEL","departure_date":"2026-08-15","passengers":1,"market":"uae"}' \
  "2xx"
check "price predict" GET "/pricing/predict?origin=DXB&destination=DEL&departure_date=2026-08-15&market=uae"
check "lead mining import" POST "/lead-mining/import" \
  '{"leads":[{"phone":"+971501111111","name":"Import Test","market":"uae"}]}' \
  "2xx"
check "referrals register" POST "/referrals/register" \
  '{"phone":"+971502222222","name":"Referral Test"}' \
  "2xx"

echo "---"
echo "Results: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
