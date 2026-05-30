#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=./lib/stack.sh
source "$SCRIPT_DIR/lib/stack.sh"


usage() {
    cat <<'EOF'
Usage: ./scripts/setup-db.sh [command] [args]

Commands:
  up      Start PostgreSQL with Docker Compose
  down    Stop PostgreSQL container
  status  Show PostgreSQL container status
  logs    Show PostgreSQL container logs
  build   Run the DART-based DB build pipeline

Examples:
  ./scripts/setup-db.sh up
  ./scripts/setup-db.sh build --year 2024 --sample-size 10
EOF
}


main() {
    local command="${1:-up}"

    if [[ $# -gt 0 ]]; then
        shift
    fi

    case "$command" in
        up)
            stack_start_database
            ;;
        down)
            stack_stop_database
            ;;
        status)
            stack_show_database_status_details
            ;;
        logs)
            stack_show_database_logs
            ;;
        build)
            stack_build_database "$@"
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            scripts_fail_with_usage usage "Unknown command: $command"
            ;;
    esac
}


main "$@"
