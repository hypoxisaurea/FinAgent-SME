#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=./lib/stack.sh
source "$SCRIPT_DIR/lib/stack.sh"


usage() {
    cat <<'EOF'
Usage: ./scripts/run-server.sh [command]

Commands:
  up       Start backend and frontend
  down     Stop backend and frontend
  restart  Restart backend and frontend
  status   Show backend and frontend status
  logs     Show backend and frontend log file locations
EOF
}


main() {
    local command="${1:-up}"

    case "$command" in
        up)
            stack_start_servers
            ;;
        down)
            stack_stop_servers
            ;;
        restart)
            stack_restart_servers
            ;;
        status)
            stack_show_server_status
            ;;
        logs)
            stack_show_server_logs
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
