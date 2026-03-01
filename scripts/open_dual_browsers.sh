#!/usr/bin/env bash
# Deprecated: use scripts/check_and_open_all_uis.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "open_dual_browsers.sh is deprecated; use scripts/check_and_open_all_uis.sh"
exec "$ROOT_DIR/scripts/check_and_open_all_uis.sh" "$@"
