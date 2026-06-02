#!/usr/bin/env bash
# Podman Compose helper — uses podman compose (preferred) or podman-compose.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.yml}"

if command -v podman >/dev/null 2>&1; then
  if podman compose version >/dev/null 2>&1; then
    exec podman compose -f "$COMPOSE_FILE" "$@"
  fi
  if command -v podman-compose >/dev/null 2>&1; then
    exec podman-compose -f "$COMPOSE_FILE" "$@"
  fi
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  exec docker compose -f "$COMPOSE_FILE" "$@"
fi

echo "Error: podman (with compose) or docker compose is required." >&2
echo "Install Podman: https://podman.io/docs/installation" >&2
exit 1
