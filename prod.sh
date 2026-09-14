#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example and set DATABASE_URL before deploying." >&2
  exit 1
fi

docker compose up --build -d
docker compose ps
echo "Arandu Portal is available at http://localhost:5001"
