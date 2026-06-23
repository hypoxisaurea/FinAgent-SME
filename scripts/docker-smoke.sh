#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

COMPOSE_FILE="$PROJECT_ROOT/backend/docker-compose.yml"
PROJECT_NAME="${FINAGENT_DOCKER_PROJECT_NAME:-finagent-smoke}"
BACKEND_PORT="${BACKEND_PORT:-18000}"
FRONTEND_PORT="${FRONTEND_PORT:-18501}"
POSTGRES_PORT="${POSTGRES_PORT:-15433}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-180}"
OUTPUT_PATH="${DOCKER_SMOKE_OUTPUT_PATH:-$PROJECT_ROOT/artifacts/docker_smoke_verification.json}"


usage() {
    cat <<'EOF'
Usage: ./scripts/docker-smoke.sh

Builds and starts the Docker Compose stack, checks backend/frontend health,
prints non-sensitive evidence, and tears the stack down on exit.

Optional environment:
  FINAGENT_DOCKER_PROJECT_NAME  Compose project name (default: finagent-smoke)
  BACKEND_PORT                  Host backend port (default: 18000)
  FRONTEND_PORT                 Host frontend port (default: 18501)
  POSTGRES_PORT                 Host postgres port (default: 15433)
  HEALTH_TIMEOUT_SECONDS        Health wait timeout (default: 180)
  DOCKER_SMOKE_OUTPUT_PATH      Evidence JSON path (default: artifacts/docker_smoke_verification.json)
EOF
}


wait_for_http() {
    local name="$1"
    local url="$2"
    local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))

    until curl --fail --silent "$url" >/dev/null 2>&1; do
        if (( SECONDS >= deadline )); then
            scripts_print_error "Timed out waiting for $name health endpoint: $url"
            return 1
        fi
        sleep 3
    done
}


cleanup() {
    docker compose \
        -p "$PROJECT_NAME" \
        -f "$COMPOSE_FILE" \
        down --remove-orphans --volumes
}


write_evidence() {
    local verified_at
    verified_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    mkdir -p "$(dirname "$OUTPUT_PATH")"
    cat >"$OUTPUT_PATH" <<EOF
{
  "verified": true,
  "verified_at": "$verified_at",
  "compose_file": "$COMPOSE_FILE",
  "project_name": "$PROJECT_NAME",
  "command": "docker compose -p $PROJECT_NAME -f $COMPOSE_FILE up --build -d",
  "services": ["postgres", "backend", "frontend"],
  "health_endpoints": {
    "backend": "http://127.0.0.1:${BACKEND_PORT}/api/health",
    "frontend": "http://127.0.0.1:${FRONTEND_PORT}/_stcore/health"
  },
  "cleanup": "docker compose -p $PROJECT_NAME -f $COMPOSE_FILE down --remove-orphans --volumes"
}
EOF
}


main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
        usage
        return 0
    fi

    trap cleanup EXIT

    echo "docker_smoke_started project=$PROJECT_NAME compose_file=$COMPOSE_FILE"
    BACKEND_PORT="$BACKEND_PORT" \
    FRONTEND_PORT="$FRONTEND_PORT" \
    POSTGRES_PORT="$POSTGRES_PORT" \
        docker compose \
            -p "$PROJECT_NAME" \
            -f "$COMPOSE_FILE" \
            up --build -d

    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps
    wait_for_http "backend" "http://127.0.0.1:${BACKEND_PORT}/api/health"
    wait_for_http "frontend" "http://127.0.0.1:${FRONTEND_PORT}/_stcore/health"
    write_evidence
    echo "docker_smoke_passed backend=http://127.0.0.1:${BACKEND_PORT}/api/health frontend=http://127.0.0.1:${FRONTEND_PORT}/_stcore/health"
    echo "docker_smoke_evidence output_path=$OUTPUT_PATH"
}


main "$@"
