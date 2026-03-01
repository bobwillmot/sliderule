#!/usr/bin/env bash
# Backward-compatible shim. Preferred entrypoint is scripts/setup.sh.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "setup.sh has moved to scripts/setup.sh"
exec "$ROOT_DIR/scripts/setup.sh" "$@"
