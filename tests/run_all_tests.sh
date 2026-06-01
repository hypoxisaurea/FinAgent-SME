#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PYTHONDONTWRITEBYTECODE=1

PYTEST_BIN="$PROJECT_ROOT/.venv/bin/pytest"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
MANUAL_SCRIPT="$PROJECT_ROOT/tests/manual/manual_financial_industry_agents_tools.py"
CLEAN_SCRIPT="$PROJECT_ROOT/tests/clean_test_cache.sh"

if [[ ! -x "$PYTEST_BIN" ]]; then
  PYTEST_BIN="pytest"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

show_help() {
  cat <<'EOF'
Usage: ./tests/run_all_tests.sh [--with-manual]

Options:
  --with-manual   Run the external-API manual validation script after pytest
  --help          Show this help message
EOF
}

run_manual=false

case "${1:-}" in
  "")
    ;;
  --with-manual)
    run_manual=true
    ;;
  --help|-h|help)
    show_help
    exit 0
    ;;
  *)
    echo "Unknown option: ${1}" >&2
    show_help >&2
    exit 1
    ;;
esac

cd "$PROJECT_ROOT"

echo "[1/2] Running automated pytest suite"
"$PYTEST_BIN" tests

if [[ "$run_manual" == true ]]; then
  echo "[2/2] Running manual external-API validation script"
  "$PYTHON_BIN" "$MANUAL_SCRIPT"
fi

"$CLEAN_SCRIPT"
