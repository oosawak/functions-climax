#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  cat <<'MSG'
Usage:
  bash scripts/set_appsettings_from_env.sh [--env-file .env]

Loads variables from .env and applies them to an Azure Function App (Application settings).

Required in .env:
  AZ_RESOURCE_GROUP
  AZ_FUNCTION_APP

Optional (if set, will be applied):
  CHRONICLE_STORAGE
  CHRONICLE_FILE_PATH
  LANGUAGE_ENDPOINT
  LANGUAGE_KEY
  LANGUAGE_PROJECT
  LANGUAGE_DEPLOYMENT
MSG
}

ENV_FILE=".env"
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${AZ_RESOURCE_GROUP:?Missing AZ_RESOURCE_GROUP in .env}"
: "${AZ_FUNCTION_APP:?Missing AZ_FUNCTION_APP in .env}"

settings=()
for k in CHRONICLE_STORAGE CHRONICLE_FILE_PATH LANGUAGE_ENDPOINT LANGUAGE_KEY LANGUAGE_PROJECT LANGUAGE_DEPLOYMENT; do
  v="${!k:-}"
  if [ -n "$v" ]; then
    settings+=("$k=$v")
  fi
done

if [ ${#settings[@]} -eq 0 ]; then
  echo "No settings found in $ENV_FILE." >&2
  exit 1
fi

echo "Target: $AZ_FUNCTION_APP ($AZ_RESOURCE_GROUP)"
for kv in "${settings[@]}"; do
  echo "  - ${kv%%=*}"
done

read -r -p "Proceed to update Azure Application settings? (y/N): " ans
case "${ans:-}" in
  y|Y) ;;
  *) echo "Cancelled."; exit 0 ;;
esac

az functionapp config appsettings set \
  -g "$AZ_RESOURCE_GROUP" -n "$AZ_FUNCTION_APP" \
  --settings "${settings[@]}" \
  >/dev/null

az functionapp restart -g "$AZ_RESOURCE_GROUP" -n "$AZ_FUNCTION_APP" >/dev/null

echo "Done."
