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

echo "==> wrong password should 401"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrong-password\"}"

echo "Smoke test complete."
