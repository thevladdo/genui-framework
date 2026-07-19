#!/usr/bin/env bash
# Post-bring-up acceptance check. Run from deploy/ after `docker compose up -d`:
#
#   ./smoke.sh [base_url]        (default http://localhost:8000)
#
# Verifies: liveness, health, readiness, fail-closed auth, and that every
# admin key declared in customer.env sees only its own tenant's data.
set -euo pipefail

BASE="${1:-http://localhost:8000}"
fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

# 1. Liveness + health (health is public by design; no key needed)
curl -fsS --max-time 5 "$BASE/live" >/dev/null || fail "/live not responding at $BASE"
health=$(curl -fsS --max-time 5 "$BASE/health") || fail "/health not responding"
echo "health: $health"
# This compose provisions every dependency, so a fresh stack must be fully
# healthy — "degraded" here means Redis/Qdrant/LLM wiring is broken.
echo "$health" | grep -q '"status": *"healthy"' \
  || fail "health status is not 'healthy' (body above)"

# 2. Readiness: 503 here means the LLM engine is not configured in customer.env
curl -fsS --max-time 5 "$BASE/ready" >/dev/null \
  || fail "/ready refused: LLM engine unconfigured? (LLM_PROVIDER / key in customer.env)"

# 3. Fail-closed: without a key, tenant-scoped routes must refuse (401/403).
#    A 200 means GENUI_DEV_OPEN leaked into a customer deployment.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE/api/v1/documents")
case "$code" in
  401|403) ;;
  *) fail "keyless request got $code, expected 401/403 (is GENUI_DEV_OPEN set?)" ;;
esac
echo "fail-closed: keyless request refused ($code)"

# 4. Tenant scoping: each declared admin key must see its own tenant only
if [ -f customer.env ]; then
  entries=$(grep '^ADMIN_API_KEYS=' customer.env | cut -d= -f2- | tr ',' '\n')
  [ -n "$entries" ] || fail "no ADMIN_API_KEYS in customer.env"
  while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    key="${entry%%:*}"
    tenant="${entry#*:}"; [ "$tenant" = "$entry" ] && tenant="default"
    body=$(curl -fsS --max-time 10 -H "X-API-Key: $key" "$BASE/api/v1/documents") \
      || fail "admin key for tenant '$tenant' was rejected"
    echo "$body" | grep -q "\"tenant\": *\"$tenant\"" \
      || fail "document list for '$tenant' not scoped to it (got: $body)"
    echo "tenant '$tenant': documents scoped OK"
  done <<< "$entries"
else
  echo "note: no customer.env here, skipping per-tenant checks"
fi

echo "SMOKE OK"
