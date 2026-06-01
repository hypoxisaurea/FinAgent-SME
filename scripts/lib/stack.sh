#!/usr/bin/env bash

if [[ -z "${PROJECT_ROOT:-}" ]]; then
    echo "PROJECT_ROOT must be set before sourcing stack.sh" >&2
    return 1 2>/dev/null || exit 1
fi

readonly STACK_BACKEND_DIR="$PROJECT_ROOT/backend"
readonly STACK_FRONTEND_DIR="$PROJECT_ROOT/frontend"
readonly STACK_VENV_DIR="$PROJECT_ROOT/.venv"
readonly STACK_RUN_DIR="$PROJECT_ROOT/.finagent"
readonly STACK_LOG_DIR="$STACK_RUN_DIR/logs"
readonly STACK_PID_DIR="$STACK_RUN_DIR/pids"
readonly STACK_REQUIREMENTS_HASH_FILE="$STACK_RUN_DIR/requirements.sha256"
readonly STACK_REQUIREMENT_FILES=(
    "$PROJECT_ROOT/requirements.txt"
    "$PROJECT_ROOT/requirements-backend.txt"
    "$PROJECT_ROOT/requirements-frontend.txt"
    "$PROJECT_ROOT/requirements-dev.txt"
)

readonly STACK_BACKEND_PID_FILE="$STACK_PID_DIR/backend.pid"
readonly STACK_FRONTEND_PID_FILE="$STACK_PID_DIR/frontend.pid"
readonly STACK_BACKEND_LOG_FILE="$STACK_LOG_DIR/backend.log"
readonly STACK_FRONTEND_LOG_FILE="$STACK_LOG_DIR/frontend.log"
readonly STACK_BACKEND_ENV_FILE="$STACK_BACKEND_DIR/.env"
readonly STACK_BACKEND_ENV_EXAMPLE_FILE="$STACK_BACKEND_DIR/.env.example"
readonly STACK_BACKEND_COMPOSE_FILE="$STACK_BACKEND_DIR/docker-compose.yml"
readonly STACK_POSTGRES_CONTAINER_NAME="finagent-postgres"

readonly STACK_DATABASE_READY_TIMEOUT_SECONDS="${DATABASE_READY_TIMEOUT_SECONDS:-60}"
readonly STACK_POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
readonly STACK_POSTGRES_PORT="${POSTGRES_PORT:-5432}"
readonly STACK_BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
readonly STACK_BACKEND_PORT="${BACKEND_PORT:-8000}"
readonly STACK_FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
readonly STACK_FRONTEND_PORT="${FRONTEND_PORT:-8501}"


stack_log() {
    printf '[scripts] %s\n' "$1"
}


stack_fail() {
    printf '%s\n' "$1" >&2
    exit 1
}


stack_command_exists() {
    command -v "$1" >/dev/null 2>&1
}


stack_ensure_runtime_dirs() {
    mkdir -p "$STACK_LOG_DIR" "$STACK_PID_DIR"
}


stack_sha256_file() {
    local file_path="$1"

    if stack_command_exists shasum; then
        shasum -a 256 "$file_path" | awk '{print $1}'
        return
    fi

    if stack_command_exists sha256sum; then
        sha256sum "$file_path" | awk '{print $1}'
        return
    fi

    if stack_command_exists openssl; then
        openssl dgst -sha256 "$file_path" | awk '{print $NF}'
        return
    fi

    stack_fail "A SHA-256 command is required (shasum, sha256sum, or openssl)."
}


stack_sha256_text() {
    local text="$1"

    if stack_command_exists shasum; then
        printf '%s' "$text" | shasum -a 256 | awk '{print $1}'
        return
    fi

    if stack_command_exists sha256sum; then
        printf '%s' "$text" | sha256sum | awk '{print $1}'
        return
    fi

    if stack_command_exists openssl; then
        printf '%s' "$text" | openssl dgst -sha256 | awk '{print $NF}'
        return
    fi

    stack_fail "A SHA-256 command is required (shasum, sha256sum, or openssl)."
}


stack_compute_requirements_hash() {
    local requirement_file
    local file_hashes=""

    for requirement_file in "${STACK_REQUIREMENT_FILES[@]}"; do
        if [[ ! -f "$requirement_file" ]]; then
            continue
        fi

        file_hashes+="$(stack_sha256_file "$requirement_file")"
        file_hashes+=$'\n'
    done

    stack_sha256_text "$file_hashes"
}


stack_resolve_venv_python_path() {
    local candidate
    local candidates=(
        "$STACK_VENV_DIR/bin/python"
        "$STACK_VENV_DIR/bin/python3"
        "$STACK_VENV_DIR/Scripts/python"
        "$STACK_VENV_DIR/Scripts/python.exe"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return
        fi
    done

    printf '%s\n' "$STACK_VENV_DIR/bin/python"
}


stack_create_venv() {
    if stack_command_exists python3.11; then
        stack_log "Creating virtual environment with python3.11"
        python3.11 -m venv "$STACK_VENV_DIR"
        return
    fi

    if stack_command_exists python3; then
        stack_log "Creating virtual environment with python3"
        python3 -m venv "$STACK_VENV_DIR"
        return
    fi

    if stack_command_exists python; then
        stack_log "Creating virtual environment with python"
        python -m venv "$STACK_VENV_DIR"
        return
    fi

    if stack_command_exists py && py -3.11 -c "import sys" >/dev/null 2>&1; then
        stack_log "Creating virtual environment with py -3.11"
        py -3.11 -m venv "$STACK_VENV_DIR"
        return
    fi

    if stack_command_exists py && py -3 -c "import sys" >/dev/null 2>&1; then
        stack_log "Creating virtual environment with py -3"
        py -3 -m venv "$STACK_VENV_DIR"
        return
    fi

    stack_fail "Python 3.11+ is required."
}


stack_ensure_venv() {
    local venv_python

    venv_python="$(stack_resolve_venv_python_path)"
    if [[ -x "$venv_python" ]]; then
        return
    fi

    stack_create_venv
}


stack_install_environment() {
    local current_hash
    local installed_hash=""
    local venv_python

    stack_ensure_runtime_dirs
    stack_ensure_venv

    current_hash="$(stack_compute_requirements_hash)"
    if [[ -f "$STACK_REQUIREMENTS_HASH_FILE" ]]; then
        installed_hash="$(cat "$STACK_REQUIREMENTS_HASH_FILE")"
    fi

    if [[ "$current_hash" == "$installed_hash" ]]; then
        stack_log "Python dependencies are already up to date"
        return
    fi

    stack_log "Installing Python dependencies"
    venv_python="$(stack_resolve_venv_python_path)"
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
        "$venv_python" -m pip install -r "$PROJECT_ROOT/requirements.txt"
    printf '%s\n' "$current_hash" >"$STACK_REQUIREMENTS_HASH_FILE"
}


stack_ensure_compose_file() {
    if [[ -f "$STACK_BACKEND_COMPOSE_FILE" ]]; then
        return
    fi

    stack_fail "Docker Compose file not found: $STACK_BACKEND_COMPOSE_FILE"
}


stack_ensure_docker_compose() {
    if stack_command_exists docker && docker compose version >/dev/null 2>&1; then
        return
    fi

    if stack_command_exists docker-compose; then
        return
    fi

    stack_fail "Docker Compose is required. Install Docker Desktop or docker compose first."
}


stack_docker_daemon_available() {
    stack_command_exists docker && docker info >/dev/null 2>&1
}


stack_run_backend_compose() {
    local -a compose_command=()

    stack_ensure_compose_file
    stack_ensure_docker_compose

    if [[ ! -f "$STACK_BACKEND_ENV_FILE" && -f "$STACK_BACKEND_ENV_EXAMPLE_FILE" ]]; then
        stack_log "backend/.env not found. Copy $STACK_BACKEND_ENV_EXAMPLE_FILE to $STACK_BACKEND_ENV_FILE and fill required values if needed"
    fi

    if stack_command_exists docker && docker compose version >/dev/null 2>&1; then
        compose_command=(docker compose -f "$STACK_BACKEND_COMPOSE_FILE")
    else
        compose_command=(docker-compose -f "$STACK_BACKEND_COMPOSE_FILE")
    fi

    if [[ -f "$STACK_BACKEND_ENV_FILE" ]]; then
        compose_command+=(--env-file "$STACK_BACKEND_ENV_FILE")
    fi

    "${compose_command[@]}" "$@"
}


stack_is_pid_running() {
    local pid_file="$1"
    local pid=""

    if [[ ! -f "$pid_file" ]]; then
        return 1
    fi

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


stack_start_python_service() {
    local service_name="$1"
    local pid_file="$2"
    local log_file="$3"
    local working_directory="$4"
    local service_url="$5"
    local venv_python

    shift 5

    if stack_is_pid_running "$pid_file"; then
        stack_log "$service_name is already running"
        return
    fi

    venv_python="$(stack_resolve_venv_python_path)"
    stack_log "Starting $service_name on $service_url"
    (
        cd "$working_directory"
        nohup "$venv_python" -m "$@" >"$log_file" 2>&1 &
        echo $! >"$pid_file"
    )
}


stack_stop_service() {
    local service_name="$1"
    local pid_file="$2"
    local pid=""

    if ! stack_is_pid_running "$pid_file"; then
        stack_log "$service_name is not running"
        return
    fi

    pid="$(cat "$pid_file")"
    stack_log "Stopping $service_name (pid=$pid)"
    kill "$pid" >/dev/null 2>&1 || true
    rm -f "$pid_file"
}


stack_show_service_status() {
    local service_label="$1"
    local pid_file="$2"
    local service_url="$3"

    if stack_is_pid_running "$pid_file"; then
        stack_log "$service_label: running (pid=$(cat "$pid_file")) -> $service_url"
        return
    fi

    stack_log "$service_label: stopped"
}


stack_start_backend() {
    stack_start_python_service \
        "backend" \
        "$STACK_BACKEND_PID_FILE" \
        "$STACK_BACKEND_LOG_FILE" \
        "$STACK_BACKEND_DIR" \
        "http://$STACK_BACKEND_HOST:$STACK_BACKEND_PORT" \
        uvicorn backend.main:app --app-dir .. --host "$STACK_BACKEND_HOST" --port "$STACK_BACKEND_PORT"
}


stack_start_frontend() {
    stack_start_python_service \
        "frontend" \
        "$STACK_FRONTEND_PID_FILE" \
        "$STACK_FRONTEND_LOG_FILE" \
        "$STACK_FRONTEND_DIR" \
        "http://$STACK_FRONTEND_HOST:$STACK_FRONTEND_PORT" \
        streamlit run main.py --server.address "$STACK_FRONTEND_HOST" --server.port "$STACK_FRONTEND_PORT"
}


stack_start_servers() {
    stack_install_environment
    stack_start_backend
    stack_start_frontend
    stack_show_server_status
    stack_show_server_logs
}


stack_stop_servers() {
    stack_stop_service "frontend" "$STACK_FRONTEND_PID_FILE"
    stack_stop_service "backend" "$STACK_BACKEND_PID_FILE"
}


stack_restart_servers() {
    stack_stop_servers
    stack_start_servers
}


stack_show_server_status() {
    stack_show_service_status \
        "Backend" \
        "$STACK_BACKEND_PID_FILE" \
        "http://$STACK_BACKEND_HOST:$STACK_BACKEND_PORT"

    stack_show_service_status \
        "Frontend" \
        "$STACK_FRONTEND_PID_FILE" \
        "http://$STACK_FRONTEND_HOST:$STACK_FRONTEND_PORT"
}


stack_show_server_logs() {
    stack_log "Backend log: $STACK_BACKEND_LOG_FILE"
    stack_log "Frontend log: $STACK_FRONTEND_LOG_FILE"
}


stack_get_database_health_status() {
    docker inspect \
        -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$STACK_POSTGRES_CONTAINER_NAME" 2>/dev/null || true
}


stack_get_database_runtime_status() {
    docker inspect -f '{{.State.Status}}' "$STACK_POSTGRES_CONTAINER_NAME" 2>/dev/null || true
}


stack_wait_for_database() {
    local elapsed_seconds=0
    local health_status=""

    while (( elapsed_seconds < STACK_DATABASE_READY_TIMEOUT_SECONDS )); do
        health_status="$(stack_get_database_health_status)"
        if [[ "$health_status" == "healthy" || "$health_status" == "running" ]]; then
            stack_log "Backend PostgreSQL is ready (status=$health_status)"
            return
        fi

        sleep 2
        elapsed_seconds=$((elapsed_seconds + 2))
    done

    stack_fail "Backend PostgreSQL did not become ready within ${STACK_DATABASE_READY_TIMEOUT_SECONDS}s."
}


stack_start_database() {
    stack_log "Starting backend PostgreSQL with $STACK_BACKEND_COMPOSE_FILE"
    stack_run_backend_compose up -d postgres
    stack_wait_for_database
}


stack_stop_database() {
    stack_log "Stopping backend PostgreSQL"
    stack_run_backend_compose stop postgres
}


stack_can_manage_database() {
    if ! stack_command_exists docker; then
        stack_log "Database: Docker CLI not installed"
        return 1
    fi

    if ! docker compose version >/dev/null 2>&1 && ! stack_command_exists docker-compose; then
        stack_log "Database: Docker Compose not installed"
        return 1
    fi

    if ! stack_docker_daemon_available; then
        stack_log "Database: Docker daemon unavailable"
        return 1
    fi

    return 0
}


stack_show_database_status() {
    local health_status=""
    local runtime_status=""

    if ! stack_can_manage_database; then
        return
    fi

    health_status="$(stack_get_database_health_status)"
    runtime_status="$(stack_get_database_runtime_status)"

    if [[ -z "$runtime_status" ]]; then
        stack_log "Database: stopped (expected at $STACK_POSTGRES_HOST:$STACK_POSTGRES_PORT)"
        return
    fi

    if [[ -n "$health_status" ]]; then
        stack_log "Database: $health_status (container=$STACK_POSTGRES_CONTAINER_NAME, host=$STACK_POSTGRES_HOST, port=$STACK_POSTGRES_PORT)"
        return
    fi

    stack_log "Database: $runtime_status (container=$STACK_POSTGRES_CONTAINER_NAME, host=$STACK_POSTGRES_HOST, port=$STACK_POSTGRES_PORT)"
}


stack_show_database_status_details() {
    if ! stack_can_manage_database; then
        return
    fi

    stack_show_database_status
    stack_run_backend_compose ps postgres
}


stack_show_database_logs() {
    stack_run_backend_compose logs postgres
}


stack_build_database() {
    local venv_python

    stack_install_environment
    stack_start_database
    venv_python="$(stack_resolve_venv_python_path)"
    stack_log "Running company registry build pipeline"
    PYTHONPATH="$STACK_BACKEND_DIR" \
        "$venv_python" "$STACK_BACKEND_DIR/scripts/build_db.py" "$@"
}


stack_start_all() {
    stack_install_environment
    stack_start_database
    stack_start_backend
    stack_start_frontend
    stack_show_stack_status
    stack_show_stack_logs
}


stack_stop_all() {
    stack_stop_servers
    stack_stop_database
}


stack_restart_all() {
    stack_stop_all
    stack_start_all
}


stack_show_stack_status() {
    stack_show_server_status
    stack_show_database_status
}


stack_show_stack_logs() {
    stack_show_server_logs
}
