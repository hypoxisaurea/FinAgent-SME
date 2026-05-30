#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=./lib/stack.sh
source "$SCRIPT_DIR/lib/stack.sh"


usage() {
    cat <<'EOF'
Usage: ./scripts/run-all.sh [command]

Commands:
  up       Set up the environment if needed, then start PostgreSQL, backend, and frontend
  down     Stop frontend, backend, and PostgreSQL
  restart  Restart PostgreSQL, backend, and frontend
  status   Show backend, frontend, and PostgreSQL status
  logs     Show backend and frontend log file locations
EOF
}


main() {
    local command="${1:-up}"

    case "$command" in
        up)
            stack_start_all
            ;;
        down)
            stack_stop_all
            ;;
        restart)
            stack_restart_all
            ;;
        status)
            stack_show_stack_status
            ;;
        logs)
            stack_show_stack_logs
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
