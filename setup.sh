#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
RUN_DIR="$ROOT_DIR/.finagent"
LOG_DIR="$RUN_DIR/logs"
PID_DIR="$RUN_DIR/pids"
REQUIREMENTS_HASH_FILE="$RUN_DIR/requirements.sha256"
REQUIREMENT_FILES=(
    "$ROOT_DIR/requirements.txt"
    "$ROOT_DIR/requirements-backend.txt"
    "$ROOT_DIR/requirements-frontend.txt"
    "$ROOT_DIR/requirements-dev.txt"
)

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-8501}"


usage() {
    cat <<'EOF'
Usage: ./setup.sh [command]

Commands:
  install   Create .venv and install Python dependencies
  up        Install if needed, then start backend and frontend
  down      Stop backend and frontend
  restart   Restart backend and frontend
  status    Show service status
  logs      Show log file locations

Environment overrides:
  BACKEND_HOST, BACKEND_PORT, FRONTEND_HOST, FRONTEND_PORT
EOF
}


log() {
    printf '[setup] %s\n' "$1"
}


command_exists() {
    command -v "$1" >/dev/null 2>&1
}


choose_python() {
    if command_exists python3.11; then
        echo "python3.11"
        return
    fi
    if command_exists python3; then
        echo "python3"
        return
    fi
    if command_exists python; then
        echo "python"
        return
    fi

    echo "Python 3 is required." >&2
    exit 1
}


ensure_runtime_dirs() {
    mkdir -p "$LOG_DIR" "$PID_DIR"
}


ensure_venv() {
    local python_bin

    if [[ -x "$VENV_DIR/bin/python" ]]; then
        return
    fi

    python_bin="$(choose_python)"
    log "Creating virtual environment with $python_bin"
    "$python_bin" -m venv "$VENV_DIR"
}


ensure_dependencies() {
    ensure_venv

    local current_hash
    local installed_hash=""

    current_hash="$(compute_requirements_hash)"
    if [[ -f "$REQUIREMENTS_HASH_FILE" ]]; then
        installed_hash="$(cat "$REQUIREMENTS_HASH_FILE")"
    fi

    if [[ "$current_hash" == "$installed_hash" ]]; then
        log "Python dependencies are already up to date"
        return
    fi

    log "Installing Python dependencies"
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
        "$VENV_DIR/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"
    printf '%s\n' "$current_hash" >"$REQUIREMENTS_HASH_FILE"
}


compute_requirements_hash() {
    local requirement_file
    local file_hashes=""

    for requirement_file in "${REQUIREMENT_FILES[@]}"; do
        file_hashes+=$(shasum -a 256 "$requirement_file")
        file_hashes+=$'\n'
    done

    printf '%s' "$file_hashes" | shasum -a 256 | awk '{print $1}'
}


is_pid_running() {
    local pid_file="$1"

    if [[ ! -f "$pid_file" ]]; then
        return 1
    fi

    local pid
    pid="$(cat "$pid_file")"
    if [[ -z "$pid" ]]; then
        return 1
    fi

    if kill -0 "$pid" >/dev/null 2>&1; then
        return 0
    fi

    rm -f "$pid_file"
    return 1
}


start_backend() {
    if is_pid_running "$BACKEND_PID_FILE"; then
        log "Backend is already running on port $BACKEND_PORT"
        return
    fi

    log "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT"
    (
        cd "$ROOT_DIR/backend"
        nohup "$VENV_DIR/bin/python" -m uvicorn main:app \
            --host "$BACKEND_HOST" \
            --port "$BACKEND_PORT" \
            >"$BACKEND_LOG_FILE" 2>&1 &
        echo $! >"$BACKEND_PID_FILE"
    )
}


start_frontend() {
    if is_pid_running "$FRONTEND_PID_FILE"; then
        log "Frontend is already running on port $FRONTEND_PORT"
        return
    fi

    log "Starting frontend on http://$FRONTEND_HOST:$FRONTEND_PORT"
    (
        cd "$ROOT_DIR/frontend"
        nohup "$VENV_DIR/bin/python" -m streamlit run main.py \
            --server.address "$FRONTEND_HOST" \
            --server.port "$FRONTEND_PORT" \
            >"$FRONTEND_LOG_FILE" 2>&1 &
        echo $! >"$FRONTEND_PID_FILE"
    )
}


stop_service() {
    local service_name="$1"
    local pid_file="$2"

    if ! is_pid_running "$pid_file"; then
        log "$service_name is not running"
        return
    fi

    local pid
    pid="$(cat "$pid_file")"
    log "Stopping $service_name (pid=$pid)"
    kill "$pid" >/dev/null 2>&1 || true
    rm -f "$pid_file"
}


show_status() {
    if is_pid_running "$BACKEND_PID_FILE"; then
        log "Backend: running (pid=$(cat "$BACKEND_PID_FILE")) -> http://$BACKEND_HOST:$BACKEND_PORT"
    else
        log "Backend: stopped"
    fi

    if is_pid_running "$FRONTEND_PID_FILE"; then
        log "Frontend: running (pid=$(cat "$FRONTEND_PID_FILE")) -> http://$FRONTEND_HOST:$FRONTEND_PORT"
    else
        log "Frontend: stopped"
    fi
}


show_logs() {
    log "Backend log: $BACKEND_LOG_FILE"
    log "Frontend log: $FRONTEND_LOG_FILE"
}


start_all() {
    ensure_runtime_dirs
    ensure_dependencies
    start_backend
    start_frontend
    show_status
    show_logs
}


main() {
    local command="${1:-up}"

    case "$command" in
        install)
            ensure_runtime_dirs
            ensure_dependencies
            ;;
        up)
            start_all
            ;;
        down)
            stop_service "frontend" "$FRONTEND_PID_FILE"
            stop_service "backend" "$BACKEND_PID_FILE"
            ;;
        restart)
            stop_service "frontend" "$FRONTEND_PID_FILE"
            stop_service "backend" "$BACKEND_PID_FILE"
            start_all
            ;;
        status)
            ensure_runtime_dirs
            show_status
            ;;
        logs)
            ensure_runtime_dirs
            show_logs
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}


main "$@"
