#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080/api/v1}"
EMAIL="${EMAIL:-smoke-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-secret123}"
NEW_PASSWORD="${NEW_PASSWORD:-newsecret123}"
NAME="${NAME:-Smoke Tester}"

expect_http() {
  local expected="$1"
  shift
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" "$@")
  if [ "$code" != "$expected" ]; then
    echo "Expected HTTP $expected but got $code" >&2
    exit 1
  fi
  echo "HTTP $code"
}

echo "==> healthz"
curl -sS "$BASE_URL/healthz"
echo

echo "==> register invalid email should 400"
expect_http 400 -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"not-an-email\",\"password\":\"$PASSWORD\",\"name\":\"$NAME\"}"

echo "==> register"
curl -sS -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"name\":\"$NAME\"}"
echo

echo "==> login"
LOGIN=$(curl -sS -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
echo "$LOGIN"

ACCESS_TOKEN=$(echo "$LOGIN" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
REFRESH_TOKEN=$(echo "$LOGIN" | sed -n 's/.*"refresh_token":"\([^"]*\)".*/\1/p')

if [ -z "$ACCESS_TOKEN" ] || [ -z "$REFRESH_TOKEN" ]; then
  echo "Failed to parse tokens from login response" >&2
  exit 1
fi

echo "==> me"
curl -sS "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "==> refresh (token rotation)"
REFRESH=$(curl -sS -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}")
echo "$REFRESH"
ROTATED_REFRESH_TOKEN=$(echo "$REFRESH" | sed -n 's/.*"refresh_token":"\([^"]*\)".*/\1/p')
if [ -z "$ROTATED_REFRESH_TOKEN" ]; then
  echo "Expected refresh_token in refresh response" >&2
  exit 1
fi

echo "==> old refresh token should 401 after rotation"
expect_http 401 -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"

echo "==> rotated refresh token should work"
curl -sS -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$ROTATED_REFRESH_TOKEN\"}"
echo

echo "==> change-password"
curl -sS -X POST "$BASE_URL/auth/change-password" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"current_password\":\"$PASSWORD\",\"new_password\":\"$NEW_PASSWORD\"}"
echo

echo "==> refresh with old token should 401 after password change"
expect_http 401 -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$ROTATED_REFRESH_TOKEN\"}"

echo "==> login with new password"
LOGIN2=$(curl -sS -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$NEW_PASSWORD\"}")
echo "$LOGIN2"

REFRESH_TOKEN2=$(echo "$LOGIN2" | sed -n 's/.*"refresh_token":"\([^"]*\)".*/\1/p')

echo "==> logout"
curl -sS -X POST "$BASE_URL/auth/logout" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN2\"}"
echo

echo "==> logout again (idempotent) should 200"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE_URL/auth/logout" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN2\"}"

echo "==> wrong password should 401"
expect_http 401 -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrong-password\"}"

echo "==> rate limit should 429"
got429=0
for _ in $(seq 1 20); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"ratelimit@example.com","password":"wrong-password"}')
  if [ "$code" = "429" ]; then
    echo "HTTP 429"
    got429=1
    break
  fi
  if [ "$code" != "401" ]; then
    echo "Expected HTTP 401 or 429 but got $code" >&2
    exit 1
  fi
done
if [ "$got429" -ne 1 ]; then
  echo "Expected HTTP 429 but rate limit was not triggered" >&2
  exit 1
fi

echo "==> create llm session"
SESSION=$(curl -sS -X POST "$BASE_URL/llm/sessions" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"gemma-2-2b-it-q4f16_1-MLC","device_info":"smoke-test","model_load_ms":1200}')
echo "$SESSION"
SESSION_ID=$(echo "$SESSION" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

echo "==> create llm message"
MESSAGE=$(curl -sS -X POST "$BASE_URL/llm/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role":"assistant","content":"Hello from smoke test","ttft_ms":250,"tokens_prompt":12,"tokens_completion":8,"tokens_per_sec":18.5,"total_ms":900}')
echo "$MESSAGE"
MESSAGE_ID=$(echo "$MESSAGE" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

echo "==> create llm score"
curl -sS -X POST "$BASE_URL/llm/sessions/$SESSION_ID/scores" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message_id\":\"$MESSAGE_ID\",\"latency_score\":85,\"length_score\":70,\"format_score\":90,\"composite\":82,\"decision\":\"accept\"}"
echo

echo "==> get llm session detail"
curl -sS "$BASE_URL/llm/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "==> list llm sessions"
curl -sS "$BASE_URL/llm/sessions?page=1&limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "==> metrics summary"
curl -sS "$BASE_URL/llm/metrics/summary" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "==> scores summary"
curl -sS "$BASE_URL/llm/scores/summary" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "==> delete llm session"
curl -sS -X DELETE "$BASE_URL/llm/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
echo

echo "Smoke test complete."
