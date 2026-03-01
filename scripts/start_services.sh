#!/usr/bin/env bash
# Launcher script for dual Citus + CockroachDB sliderule deployment
# Assumes databases have been initialized via scripts/setup.sh or scripts/init_all.py
# Usage: bash scripts/start_services.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Find the Python executable (prefer venv if available)
if [ -f "$ROOT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

# Setup environment variables
export PYTHONPATH="$ROOT_DIR"
export OTEL_LOGS_ENABLED="${OTEL_LOGS_ENABLED:-true}"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-http://localhost:4319}"
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/sliderule}"
export DATABASE_URL_COCKROACH="${DATABASE_URL_COCKROACH:-postgresql://root@localhost:26257/sliderule?sslmode=disable}"
export SLIDERULE_DETACH="${SLIDERULE_DETACH:-false}"

echo "=========================================="
echo "sliderule Dual Deployment (Citus + CockroachDB)"
echo "=========================================="
echo ""

# Kill any existing Uvicorn instances
echo "Cleaning up existing processes..."
pkill -f "uvicorn app_citus.main:app" || true
pkill -f "uvicorn app_cockroachdb.main:app" || true
sleep 1

# Start Citus app on port 8000
echo "Starting Citus API on http://localhost:8000"
PYTHONPATH="$PYTHONPATH" \
OTEL_LOGS_ENABLED="$OTEL_LOGS_ENABLED" \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="$OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" \
"$PYTHON_BIN" -m uvicorn app_citus.main:app --host 127.0.0.1 --port 8000 > /tmp/citus.log 2>&1 &
CITUS_PID=$!

# Start CockroachDB app on port 8001
echo "Starting CockroachDB API on http://localhost:8001"
PYTHONPATH="$PYTHONPATH" \
DATABASE_URL_COCKROACH="$DATABASE_URL_COCKROACH" \
OTEL_LOGS_ENABLED="$OTEL_LOGS_ENABLED" \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="$OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" \
"$PYTHON_BIN" -m uvicorn app_cockroachdb.main:app --host 127.0.0.1 --port 8001 > /tmp/cockroachdb.log 2>&1 &
CRDB_PID=$!

echo ""
echo "=========================================="
echo "APIs are starting..."
echo "=========================================="
echo ""
echo "Citus API:      http://localhost:8000"
echo "Citus Docs:     http://localhost:8000/docs"
echo ""
echo "CockroachDB API: http://localhost:8001"
echo "CockroachDB Docs: http://localhost:8001/docs"
echo ""
echo "Process IDs: Citus=$CITUS_PID, CockroachDB=$CRDB_PID"
echo ""
echo "Logs:"
echo "  Citus:      tail -f /tmp/citus.log"
echo "  CockroachDB: tail -f /tmp/cockroachdb.log"
echo ""
echo "To open both UIs:"
echo "  bash scripts/check_and_open_all_uis.sh"
echo ""
echo "Press Ctrl+C to stop both servers."
echo ""

if [ "$SLIDERULE_DETACH" = "true" ]; then
    echo "Detached mode enabled; leaving APIs running in background."
    exit 0
fi

# Wait for both processes and handle interruption gracefully
trap "kill $CITUS_PID $CRDB_PID 2>/dev/null || true; exit 0" INT TERM

wait
