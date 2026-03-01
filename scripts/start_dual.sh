#!/usr/bin/env bash
# Backward-compatible shim. Preferred entrypoint is scripts/start_services.sh.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "start_dual.sh has been renamed to start_services.sh"
exec "$ROOT_DIR/scripts/start_services.sh" "$@"
