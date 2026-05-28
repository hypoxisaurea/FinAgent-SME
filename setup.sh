#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
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
BACKEND_ENV_FILE="$BACKEND_DIR/.env"
BACKEND_ENV_EXAMPLE_FILE="$BACKEND_DIR/.env.example"
BACKEND_COMPOSE_FILE="$BACKEND_DIR/docker-compose.yml"
POSTGRES_CONTAINER_NAME="finagent-postgres"
DATABASE_READY_TIMEOUT_SECONDS="${DATABASE_READY_TIMEOUT_SECONDS:-60}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

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
  build-db  Run DART-based company registry build and save results to DB
  db-up     Start backend PostgreSQL with Docker Compose
  db-down   Stop backend PostgreSQL container
  db-status Show backend PostgreSQL container status
  db-logs   Show backend PostgreSQL container logs
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
    if command_exists python.11; then
        echo "python.11"
        return
    fi
    if command_exists python; then
        echo "python"
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

    if [[ -x "$VENV_DIR/Scripts/python" ]]; then
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
        "$VENV_DIR/Scripts/python" -m pip install -r "$ROOT_DIR/requirements.txt"
    printf '%s\n' "$current_hash" >"$REQUIREMENTS_HASH_FILE"
}


compute_requirements_hash() {
    local requirement_file
    local file_hashes=""

    for requirement_file in "${REQUIREMENT_FILES[@]}"; do
        if [[ ! -f "$requirement_file" ]]; then
            continue
        fi
        file_hashes+=$(shasum -a 256 "$requirement_file")
        file_hashes+=$'\n'
    done

    printf '%s' "$file_hashes" | shasum -a 256 | awk '{print $1}'
}


ensure_compose_file() {
    if [[ -f "$BACKEND_COMPOSE_FILE" ]]; then
        return
    fi

    echo "Docker Compose file not found: $BACKEND_COMPOSE_FILE" >&2
    exit 1
}


ensure_docker_compose() {
    if command_exists docker && docker compose version >/dev/null 2>&1; then
        return
    fi

    if command_exists docker-compose; then
        return
    fi

    echo "Docker Compose is required. Install Docker Desktop or docker compose first." >&2
    exit 1
}


docker_daemon_available() {
    command_exists docker && docker info >/dev/null 2>&1
}


run_backend_compose() {
    ensure_compose_file
    ensure_docker_compose

    if [[ ! -f "$BACKEND_ENV_FILE" && -f "$BACKEND_ENV_EXAMPLE_FILE" ]]; then
        log "backend/.env not found. Copy $BACKEND_ENV_EXAMPLE_FILE to $BACKEND_ENV_FILE and fill required values if needed"
    fi

    if command_exists docker && docker compose version >/dev/null 2>&1; then
        if [[ -f "$BACKEND_ENV_FILE" ]]; then
            docker compose -f "$BACKEND_COMPOSE_FILE" --env-file "$BACKEND_ENV_FILE" "$@"
            return
        fi
        docker compose -f "$BACKEND_COMPOSE_FILE" "$@"
        return
    fi

    if [[ -f "$BACKEND_ENV_FILE" ]]; then
        docker-compose -f "$BACKEND_COMPOSE_FILE" --env-file "$BACKEND_ENV_FILE" "$@"
        return
    fi
    docker-compose -f "$BACKEND_COMPOSE_FILE" "$@"
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
        nohup "$VENV_DIR/Scripts/python" -m uvicorn main:app \
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
        nohup "$VENV_DIR/Scripts/python" -m streamlit run main.py \
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


get_database_health_status() {
    docker inspect \
        -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$POSTGRES_CONTAINER_NAME" 2>/dev/null || true
}


get_database_runtime_status() {
    docker inspect -f '{{.State.Status}}' "$POSTGRES_CONTAINER_NAME" 2>/dev/null || true
}


wait_for_database() {
    local elapsed_seconds=0
    local health_status=""

    while (( elapsed_seconds < DATABASE_READY_TIMEOUT_SECONDS )); do
        health_status="$(get_database_health_status)"
        if [[ "$health_status" == "healthy" || "$health_status" == "running" ]]; then
            log "Backend PostgreSQL is ready (status=$health_status)"
            return
        fi

        sleep 2
        elapsed_seconds=$((elapsed_seconds + 2))
    done

    echo "Backend PostgreSQL did not become ready within ${DATABASE_READY_TIMEOUT_SECONDS}s." >&2
    if [[ -n "$health_status" ]]; then
        echo "Last known database status: $health_status" >&2
    fi
    exit 1
}


start_database() {
    log "Starting backend PostgreSQL with $BACKEND_COMPOSE_FILE"
    run_backend_compose up -d postgres
    wait_for_database
}


stop_database() {
    log "Stopping backend PostgreSQL"
    run_backend_compose stop postgres
}


show_database_status() {
    local health_status=""
    local runtime_status=""

    if ! command_exists docker; then
        log "Database: Docker CLI not installed"
        return
    fi

    if ! docker compose version >/dev/null 2>&1 && ! command_exists docker-compose; then
        log "Database: Docker Compose not installed"
        return
    fi

    if ! docker_daemon_available; then
        log "Database: Docker daemon unavailable"
        return
    fi

    health_status="$(get_database_health_status)"
    runtime_status="$(get_database_runtime_status)"

    if [[ -z "$runtime_status" ]]; then
        log "Database: stopped (expected at $POSTGRES_HOST:$POSTGRES_PORT)"
        return
    fi

    if [[ -n "$health_status" ]]; then
        log "Database: $health_status (container=$POSTGRES_CONTAINER_NAME, host=$POSTGRES_HOST, port=$POSTGRES_PORT)"
    else
        log "Database: $runtime_status (container=$POSTGRES_CONTAINER_NAME, host=$POSTGRES_HOST, port=$POSTGRES_PORT)"
    fi
}


show_database_status_details() {
    if ! command_exists docker; then
        log "Database: Docker CLI not installed"
        return
    fi

    if ! docker compose version >/dev/null 2>&1 && ! command_exists docker-compose; then
        log "Database: Docker Compose not installed"
        return
    fi

    if ! docker_daemon_available; then
        log "Database: Docker daemon unavailable"
        return
    fi

    show_database_status
    run_backend_compose ps postgres
}


show_database_logs() {
    run_backend_compose logs postgres
}


start_all() {
    ensure_runtime_dirs
    ensure_dependencies
    start_database
    start_backend
    start_frontend
    show_status
    show_logs
}


build_database() {
    ensure_runtime_dirs
    ensure_dependencies
    start_database
    log "Running company registry build pipeline"
    PYTHONPATH="$BACKEND_DIR" \
        "$VENV_DIR/Scripts/python" "$BACKEND_DIR/scripts/build_db.py" "$@"
}


main() {
    local command="${1:-up}"
    if [[ $# -gt 0 ]]; then
        shift
    fi

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
            stop_database
            ;;
        restart)
            stop_service "frontend" "$FRONTEND_PID_FILE"
            stop_service "backend" "$BACKEND_PID_FILE"
            stop_database
            start_all
            ;;
        build-db)
            build_database "$@"
            ;;
        db-up)
            start_database
            ;;
        db-down)
            stop_database
            ;;
        db-status)
            show_database_status_details
            ;;
        db-logs)
            show_database_logs
            ;;
        status)
            ensure_runtime_dirs
            show_status
            show_database_status
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
