#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
UVICORN_BIN="$ROOT_DIR/.venv/bin/uvicorn"

if [[ ! -x "$PYTHON_BIN" || ! -x "$UVICORN_BIN" ]]; then
  echo "Missing virtualenv executables. Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# Ensure Docker Compose stack is running (Citus, CockroachDB, Tempo/Grafana)
echo "=== Starting Docker Compose stack (Citus, CockroachDB, Tempo/Grafana) ==="
cd docker
docker-compose up -d
cd ..

export PYTHONPATH=.
export OTEL_LOGS_ENABLED="${OTEL_LOGS_ENABLED:-true}"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-http://localhost:4319}"

pkill -f "$ROOT_DIR/.venv/bin/uvicorn app_citus.main:app" || true

"$PYTHON_BIN" scripts/init_db.py
"$PYTHON_BIN" scripts/book_sample.py

exec "$UVICORN_BIN" app_citus.main:app --host 127.0.0.1 --port 8000