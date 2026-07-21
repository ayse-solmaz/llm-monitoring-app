#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080/api/v1}"
EMAIL="${EMAIL:-smoke-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-secret123}"
NEW_PASSWORD="${NEW_PASSWORD:-newsecret123}"
NAME="${NAME:-Smoke Tester}"

echo "==> healthz"
curl -sS "$BASE_URL/healthz"
echo

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

echo "==> refresh"
curl -sS -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"
echo

echo "==> change-password"
curl -sS -X POST "$BASE_URL/auth/change-password" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"current_password\":\"$PASSWORD\",\"new_password\":\"$NEW_PASSWORD\"}"
echo

echo "==> refresh with old token should 401 after password change"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}")
if [ "$HTTP_CODE" != "401" ]; then
  echo "Expected HTTP 401 but got $HTTP_CODE" >&2
  exit 1
fi
echo "HTTP $HTTP_CODE"

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
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrong-password\"}"

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
