#!/usr/bin/env bash
# Start the local TroopConnect backend (postgres, redis, web, celery, celery-beat)
# and wait until it is actually serving requests.
#
# Usage:
#   scripts/dev-up.sh              start the stack in the background
#   scripts/dev-up.sh --build      rebuild the image first (after dep changes)
#   scripts/dev-up.sh --migrate    apply migrations once the stack is up
#   scripts/dev-up.sh --foreground run attached, Ctrl-C to stop
#
# Environment overrides:
#   COMPOSE_FILE   compose file to use (default: docker-compose-local.yml)
#   BASE_URL       URL polled for readiness (default: http://localhost:8000)
#   START_TIMEOUT  seconds to wait for readiness (default: 90)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-local.yml}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
START_TIMEOUT="${START_TIMEOUT:-90}"

# Resolve relative to the repo root, but honour an absolute COMPOSE_FILE.
case "$COMPOSE_FILE" in
    /*) COMPOSE_PATH="$COMPOSE_FILE" ;;
    *)  COMPOSE_PATH="${ROOT_DIR}/${COMPOSE_FILE}" ;;
esac
# --project-directory follows the compose file so the Docker project (and its
# ports/volumes) is the same no matter which worktree this script is run from.
COMPOSE=(docker compose -f "$COMPOSE_PATH" --project-directory "$(dirname "$COMPOSE_PATH")")

BUILD=0
RUN_MIGRATIONS=0
FOREGROUND=0

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -b|--build)      BUILD=1 ;;
        -m|--migrate)    RUN_MIGRATIONS=1 ;;
        -f|--foreground) FOREGROUND=1 ;;
        -h|--help)       usage 0 ;;
        *)               die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH"
[ -f "$COMPOSE_PATH" ] || die "compose file not found: $COMPOSE_FILE"

# --- start ----------------------------------------------------------------
build_args=()
[ "$BUILD" -eq 1 ] && build_args+=(--build)

if [ "$FOREGROUND" -eq 1 ]; then
    say "Starting backend from ${COMPOSE_FILE} in the foreground — press Ctrl-C to stop."
    exec "${COMPOSE[@]}" up "${build_args[@]}"
fi

if [ "$BUILD" -eq 1 ]; then
    say "Starting backend from ${COMPOSE_FILE} (rebuilding image)"
else
    say "Starting backend from ${COMPOSE_FILE}"
fi
"${COMPOSE[@]}" up -d "${build_args[@]}"

# --- wait for readiness ---------------------------------------------------
wait_for_postgres() {
    local deadline=$((SECONDS + START_TIMEOUT))
    printf 'Waiting for postgres'
    while ! "${COMPOSE[@]}" exec -T postgres pg_isready -q >/dev/null 2>&1; do
        [ "$SECONDS" -lt "$deadline" ] || { printf '\n'; die "postgres not ready after ${START_TIMEOUT}s"; }
        printf '.'
        sleep 1
    done
    printf ' ready\n'
}

wait_for_web() {
    command -v curl >/dev/null 2>&1 || return 0
    local deadline=$((SECONDS + START_TIMEOUT))
    printf 'Waiting for %s' "$BASE_URL"
    while ! curl -sf -o /dev/null --max-time 2 "$BASE_URL/"; do
        [ "$SECONDS" -lt "$deadline" ] || { printf '\n'; die "web did not respond on ${BASE_URL} after ${START_TIMEOUT}s (check: docker compose -f ${COMPOSE_FILE} logs web)"; }
        printf '.'
        sleep 1
    done
    printf ' up\n'
}

wait_for_postgres
wait_for_web

if [ "$RUN_MIGRATIONS" -eq 1 ]; then
    say ""
    # Pass the resolved path through so a custom COMPOSE_FILE is honoured.
    COMPOSE_FILE="$COMPOSE_PATH" "${ROOT_DIR}/scripts/dev-migrate.sh"
fi

say ""
"${COMPOSE[@]}" ps
say ""
say "Backend is up: ${BASE_URL}"
say "Logs:   docker compose -f ${COMPOSE_FILE} logs -f web"
say "Stop:   scripts/dev-down.sh"
