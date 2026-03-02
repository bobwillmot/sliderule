#!/usr/bin/env bash
# Launcher script for dual Citus + CockroachDB sliderule deployment
# Assumes databases have been initialized via scripts/setup.sh
# Usage: bash scripts/start.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Find the Python executable (prefer venv if available)
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
    PYTHON_BIN="python"
fi

# Setup environment variables
export PYTHONPATH="$ROOT_DIR"
export OTEL_LOGS_ENABLED="${OTEL_LOGS_ENABLED:-true}"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-http://localhost:4319}"
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/sliderule}"
export DATABASE_URL_COCKROACH="${DATABASE_URL_COCKROACH:-postgresql://root@localhost:26257/sliderule?sslmode=disable}"

check_endpoint() {
    local name="$1"
    local url="$2"
    local tmp_file
    local http_code
    local body

    tmp_file="$(mktemp)"
    http_code="$(curl -sS --max-time 8 -o "$tmp_file" -w "%{http_code}" "$url" || true)"
    body="$(cat "$tmp_file")"
    rm -f "$tmp_file"

    if [[ "$http_code" != "200" ]]; then
        echo "❌ $name failed ($http_code): $url"
        return 1
    fi

    if [[ -z "$body" || "$body" == Internal\ Server\ Error* ]]; then
        echo "❌ $name returned invalid body: $url"
        return 1
    fi

    if [[ "$body" != \[* && "$body" != \{* ]]; then
        echo "❌ $name returned non-JSON response: $url"
        return 1
    fi

    echo "✅ $name healthy: $url"
    return 0
}

wait_for_endpoint() {
    local name="$1"
    local url="$2"
    local timeout_seconds="$3"
    local start_time

    start_time="$SECONDS"
    while (( SECONDS - start_time < timeout_seconds )); do
        if check_endpoint "$name" "$url" >/dev/null 2>&1; then
            echo "✅ $name healthy: $url"
            return 0
        fi
        sleep 2
    done

    check_endpoint "$name" "$url" || true
    return 1
}

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
echo "Waiting for API health checks..."
echo ""
failed=0

readonly SANITY_ENDPOINTS=(
    "Citus books|http://127.0.0.1:8000/books"
    "Citus instruments|http://127.0.0.1:8000/instruments"
    "Cockroach books|http://127.0.0.1:8001/books"
    "Cockroach instruments|http://127.0.0.1:8001/instruments"
)

for entry in "${SANITY_ENDPOINTS[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    wait_for_endpoint "$name" "$url" 60 || failed=1
done

if [[ "$failed" -ne 0 ]]; then
    echo ""
    echo "Sanity checks failed. APIs are running in background; inspect logs:"
    echo "  tail -f /tmp/citus.log"
    echo "  tail -f /tmp/cockroachdb.log"
    exit 1
fi

echo ""
echo "All sanity checks passed. Opening all UIs..."
echo ""

UI_URLS=(
    "http://127.0.0.1:8000/docs"
    "http://127.0.0.1:8001/docs"
    "http://127.0.0.1:3000/d/sliderule-traces"
    "http://127.0.0.1:3000/d/sliderule-host-metrics"
    "http://127.0.0.1:3000/d/trace-context-viewer/trace-context-viewer"
    "http://127.0.0.1:8000"
    "http://127.0.0.1:8001"
)

LOCAL_DOCS_INDEX="$ROOT_DIR/docs/_build/html/index.html"
if [[ -f "$LOCAL_DOCS_INDEX" ]]; then
    UI_URLS+=("$LOCAL_DOCS_INDEX")
else
    echo "ℹ️ Local Sphinx docs not found at $LOCAL_DOCS_INDEX (skipping)"
fi

open "${UI_URLS[@]}"

echo "✓ Opened API UIs:"
echo "  - Citus API: http://127.0.0.1:8000/docs"
echo "  - CockroachDB API: http://127.0.0.1:8001/docs"
echo ""
echo "✓ Opened Observability UIs:"
echo "  - Grafana Dashboard (Tempo): http://127.0.0.1:3000/d/sliderule-traces"
echo "  - Grafana Dashboard (Host Metrics): http://127.0.0.1:3000/d/sliderule-host-metrics"
echo "  - Grafana Dashboard (Trace Context Viewer): http://127.0.0.1:3000/d/trace-context-viewer/trace-context-viewer"
echo ""
echo "Services started in background."
echo "Use 'bash scripts/shutdown.sh' to stop both APIs."
echo ""

exit 0
