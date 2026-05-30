#!/usr/bin/env bash

readonly SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPTS_DIR="$(cd "$SCRIPT_LIB_DIR/.." && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPTS_DIR/.." && pwd)"


scripts_print_error() {
    printf '%s\n' "$1" >&2
}


scripts_fail_with_usage() {
    local usage_function_name="$1"
    local message="$2"

    scripts_print_error "$message"
    "$usage_function_name"
    exit 1
}
