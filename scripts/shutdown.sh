#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=========================================="
echo "Sliderule Clean Shutdown"
echo "=========================================="
echo ""

echo "Stopping API processes..."
pkill -f "uvicorn app_citus.main:app" || true
pkill -f "uvicorn app_cockroachdb.main:app" || true

if pgrep -f "uvicorn app_citus.main:app" >/dev/null 2>&1 || pgrep -f "uvicorn app_cockroachdb.main:app" >/dev/null 2>&1; then
    sleep 1
fi

if pgrep -f "uvicorn app_citus.main:app" >/dev/null 2>&1 || pgrep -f "uvicorn app_cockroachdb.main:app" >/dev/null 2>&1; then
    echo "Some API processes are still running; forcing stop..."
    pkill -9 -f "uvicorn app_citus.main:app" || true
    pkill -9 -f "uvicorn app_cockroachdb.main:app" || true
fi

echo "Stopping Docker services..."
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        docker compose -f docker/docker-compose.yml down --remove-orphans >/dev/null
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose -f docker/docker-compose.yml down --remove-orphans >/dev/null
    else
        echo "docker compose command not found; skipped Docker shutdown."
    fi
else
    echo "Docker not found; skipped Docker shutdown."
fi

echo ""
echo "Shutdown complete."
echo ""
echo "Checks:"
echo "  - APIs: ps aux | grep uvicorn | grep -v grep"
echo "  - Docker: cd docker && docker compose ps"
