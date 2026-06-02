#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

find "$PROJECT_ROOT/tests" -type d -name "__pycache__" -prune -exec rm -rf {} +
rm -rf "$PROJECT_ROOT/tests/.pytest_cache" "$PROJECT_ROOT/.pytest_cache"

echo "Cleaned test cache directories."
