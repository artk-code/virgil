#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ensure_env_is_gitignored() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return
  fi

  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo ".env is tracked by git; refusing to write local secrets." >&2
    exit 1
  fi

  if ! git check-ignore -q .env; then
    echo ".env is not ignored by git; refusing to write local secrets." >&2
    echo "Add .env to .gitignore before running bootstrap again." >&2
    exit 1
  fi
}

generate_postgres_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
    return
  fi

  echo "Cannot generate a Postgres password: install openssl or python3." >&2
  exit 1
}

if [[ ! -f ".env" ]]; then
  ensure_env_is_gitignored
  postgres_password="$(generate_postgres_password)"
  sed \
    -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${postgres_password}/" \
    -e "s#^DATABASE_URL=.*#DATABASE_URL=postgres://app:${postgres_password}@postgres:5432/app?sslmode=disable#" \
    .env.example > .env
  chmod 600 .env
  echo "Created .env from .env.example with a generated local Postgres password."
else
  echo ".env already exists; leaving it unchanged."
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
echo "  1) Review .env values if you need custom local settings"
echo "  2) make test"
echo "  3) make up"
echo "  4) make verify"
