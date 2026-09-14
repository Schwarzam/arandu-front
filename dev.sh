#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example and set ADSS_BASE_URL before starting development." >&2
  exit 1
fi

set -a
source .env
set +a

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python -m uvicorn backend.app.main:app --reload --port 8000 &
API_PID=$!

cd frontend
npm run dev -- --host 0.0.0.0
