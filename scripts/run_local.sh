#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v func >/dev/null 2>&1; then
  echo "Missing 'func' (Azure Functions Core Tools)." >&2
  echo "Install: https://learn.microsoft.com/azure/azure-functions/functions-run-local" >&2
  exit 1
fi

# Optional: load local env (do not commit secrets)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

python -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -r requirements.txt

exec func start
