#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=./lib/stack.sh
source "$SCRIPT_DIR/lib/stack.sh"


usage() {
    cat <<'EOF'
Usage: ./scripts/setup-env.sh

Create the local Python virtual environment and install dependencies.
EOF
}


main() {
    if [[ $# -eq 0 ]]; then
        stack_install_environment
        return
    fi

    case "${1:-}" in
        -h|--help|help)
            usage
            ;;
        *)
            scripts_fail_with_usage usage "Unknown argument: $1"
            ;;
    esac
}


main "$@"
