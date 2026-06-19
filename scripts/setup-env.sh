#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=./lib/stack.sh
source "$SCRIPT_DIR/lib/stack.sh"


usage() {
    cat <<'EOF'
Usage: ./scripts/setup-env.sh [--dev|--runtime]

Create the local Python virtual environment and install dependencies.
Default profile: --dev
EOF
}


main() {
    local profile="dev"

    if [[ $# -gt 1 ]]; then
        scripts_fail_with_usage usage "Too many arguments"
    fi

    case "${1:-}" in
        "")
            ;;
        --dev)
            profile="dev"
            ;;
        --runtime)
            profile="runtime"
            ;;
        -h|--help|help)
            usage
            return
            ;;
        *)
            scripts_fail_with_usage usage "Unknown argument: $1"
            ;;
    esac

    stack_install_environment "$profile"
}


main "$@"
