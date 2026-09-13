#!/usr/bin/env bash
# Stop the local TroopConnect backend started by scripts/dev-up.sh.
#
# Usage:
#   scripts/dev-down.sh              stop and remove the containers (data kept)
#   scripts/dev-down.sh --volumes    also delete postgres/celery volumes (DESTROYS local data)
#   scripts/dev-down.sh --images     also remove the built dev image
#   scripts/dev-down.sh --all        --volumes --images
#
# Flags: -v/--volumes, -i/--images, -a/--all, -y/--yes (skip confirmation), -h/--help
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

VOLUMES=0
IMAGES=0
ASSUME_YES=0

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        -v|--volumes) VOLUMES=1 ;;
        -i|--images)  IMAGES=1 ;;
        -a|--all)     VOLUMES=1; IMAGES=1 ;;
        -y|--yes)     ASSUME_YES=1 ;;
        -h|--help)    usage 0 ;;
        *)            die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH"
[ -f "$COMPOSE_PATH" ] || die "compose file not found: $COMPOSE_FILE"

if [ "$VOLUMES" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
    say "This deletes the local postgres volume: all local database content is lost."
    printf 'Type "yes" to continue: '
    read -r reply || reply=""
    [ "$reply" = "yes" ] || die "aborted — nothing was stopped"
fi

down_args=(down --remove-orphans)
[ "$VOLUMES" -eq 1 ] && down_args+=(--volumes)

say "Stopping backend from ${COMPOSE_FILE}"
"${COMPOSE[@]}" "${down_args[@]}"

if [ "$IMAGES" -eq 1 ]; then
    say "Removing the built dev image (troopconnect-dev:latest)"
    docker image rm troopconnect-dev:latest || say "Image not found, skipping."
fi

say "Backend stopped."
