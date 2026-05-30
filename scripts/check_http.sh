#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${FUNCTIONS_URL:-http://localhost:7071}"
CODE="${FUNCTIONS_CODE:-}"

url() {
  local path="$1"
  if [ -n "$CODE" ]; then
    echo "${BASE_URL%/}$path?code=$CODE"
  else
    echo "${BASE_URL%/}$path"
  fi
}

curl -fsS "$(url /api/health)" >/dev/null

echo "health: OK"

curl -fsS "$(url /api/nlp/analyze)" \
  -H 'Content-Type: application/json' \
  -d '{"text":"unity-devの続きやって"}' \
  | python -m json.tool >/dev/null

echo "nlp_analyze: OK"
