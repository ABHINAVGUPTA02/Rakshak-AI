#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example"
fi

echo "Starting PostgreSQL and Neo4j with Podman..."
"$ROOT/scripts/compose.sh" up -d

echo "Waiting for databases..."
sleep 5

cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

echo "Starting API on http://localhost:8000"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
