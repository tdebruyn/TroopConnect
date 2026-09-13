#!/usr/bin/env bash
# Apply database migrations for the local TroopConnect backend.
#
# Runs inside the `web` container if the stack is up, otherwise falls back to a
# one-off container (docker compose run --rm), which starts its dependencies
# first — so this works whether or not scripts/dev-up.sh has been run.
#
# Usage:
#   scripts/dev-migrate.sh                    apply migrations
#   scripts/dev-migrate.sh --makemigrations   create migrations for all apps, then apply
#   scripts/dev-migrate.sh -m members         same, for one app only
#   scripts/dev-migrate.sh --show             list migration status (no changes)
#   scripts/dev-migrate.sh --check            exit 1 if anything is unapplied (no changes)
#   scripts/dev-migrate.sh -- <extra args>    pass extra args to `manage.py migrate`
#
# Environment overrides:
#   COMPOSE_FILE   compose file to use (default: docker-compose-local.yml)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-local.yml}"

# Resolve relative to the repo root, but honour an absolute COMPOSE_FILE.
case "$COMPOSE_FILE" in
    /*) COMPOSE_PATH="$COMPOSE_FILE" ;;
    *)  COMPOSE_PATH="${ROOT_DIR}/${COMPOSE_FILE}" ;;
esac
# --project-directory follows the compose file so the Docker project (and its
# ports/volumes) is the same no matter which worktree this script is run from.
COMPOSE=(docker compose -f "$COMPOSE_PATH" --project-directory "$(dirname "$COMPOSE_PATH")")
MANAGE=(uv run /app/manage.py)

MAKEMIGRATIONS=0
MAKEMIGRATIONS_APP=""
SHOW=0
CHECK=0
EXTRA=()

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -m|--makemigrations)
            MAKEMIGRATIONS=1
            # Optional app label: consume the next arg unless it is another flag.
            if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then
                MAKEMIGRATIONS_APP="$2"
                shift
            fi
            ;;
        -s|--show)  SHOW=1 ;;
        -c|--check) CHECK=1 ;;
        --)         shift; EXTRA=("$@"); break ;;
        -h|--help)  usage 0 ;;
        *)          die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH"
[ -f "$COMPOSE_PATH" ] || die "compose file not found: $COMPOSE_FILE"

# Use the running container when there is one (fast, no cold start), else spin
# up a throwaway one so migrations work on a stopped stack too.
web_running() {
    "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx web
}

run_manage() {
    if web_running; then
        "${COMPOSE[@]}" exec -T web "${MANAGE[@]}" "$@"
    else
        "${COMPOSE[@]}" run --rm -T web "${MANAGE[@]}" "$@"
    fi
}

if [ "$MAKEMIGRATIONS" -eq 1 ]; then
    if [ -n "$MAKEMIGRATIONS_APP" ]; then
        say "Creating migrations for app: ${MAKEMIGRATIONS_APP}"
        run_manage makemigrations "$MAKEMIGRATIONS_APP"
    else
        say "Creating migrations for all apps"
        run_manage makemigrations
    fi
    say ""
fi

if [ "$SHOW" -eq 1 ]; then
    say "Migration status:"
    run_manage showmigrations "${EXTRA[@]+"${EXTRA[@]}"}"
    exit 0
fi

if [ "$CHECK" -eq 1 ]; then
    say "Checking for unapplied migrations"
    if run_manage migrate --check "${EXTRA[@]+"${EXTRA[@]}"}"; then
        say "Up to date — nothing to apply."
        exit 0
    fi
    die "there are unapplied migrations (run: scripts/dev-migrate.sh)"
fi

say "Applying migrations"
run_manage migrate "${EXTRA[@]+"${EXTRA[@]}"}"

say ""
say "Migrations applied."
