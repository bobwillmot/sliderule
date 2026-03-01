#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_ONLY=false

if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=true
fi

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

echo "Running backend sanity checks..."
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
  check_endpoint "$name" "$url" || failed=1
done

if [[ "$failed" -ne 0 ]]; then
  echo ""
  echo "Sanity checks failed. Start/fix APIs before opening UI tabs."
  exit 1
fi

if [[ "$CHECK_ONLY" == true ]]; then
  echo ""
  echo "All sanity checks passed."
  exit 0
fi

echo ""
echo "All sanity checks passed. Opening all UIs..."

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

echo ""
echo "✓ Opened API UIs:"
echo "  - Citus API: http://127.0.0.1:8000/docs"
echo "  - CockroachDB API: http://127.0.0.1:8001/docs"
echo ""
echo "✓ Opened Observability UIs:"
echo "  - Grafana Dashboard (Tempo): http://127.0.0.1:3000/d/sliderule-traces"
echo "  - Grafana Dashboard (Host Metrics): http://127.0.0.1:3000/d/sliderule-host-metrics"
echo "  - Grafana Dashboard (Trace Context Viewer): http://127.0.0.1:3000/d/trace-context-viewer/trace-context-viewer"
