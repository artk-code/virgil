#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists"
fi

echo "Checking host tools..."
for tool in docker make; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Missing required tool: ${tool}" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required but unavailable." >&2
  exit 1
fi

echo
echo "Bootstrap complete."
echo "Next steps:"
echo "  1) Review .env values (especially POSTGRES_PASSWORD and DATABASE_URL)"
echo "  2) make test"
echo "  3) make up"
echo "  4) make verify"
