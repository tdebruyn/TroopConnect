#!/usr/bin/env bash
# Seed the demo troop into the local dev instance.
#
# This runs `manage.py seed_demo` from the host rather than inside a container,
# because the container's own environment names services that only exist on the
# compose network ("db", "redis") and Django reads every deployment value from
# the environment rather than from a file. So the script assembles the
# environment a host run needs — the four the app insists on, and the database
# and Redis pointed at the ports the dev stack publishes — and runs the command
# from the host's own Python.
#
# It writes into the dev instance's database: about twenty-five members, an
# agenda, a mailbox, a fee grid and the unit's own settings, all in French and
# all idempotent. Running it twice adds nothing the second time.
#
# Usage:
#   scripts/dev-seed-demo.sh                  seed the dev instance
#   scripts/dev-seed-demo.sh --force          (any argument goes to seed_demo)
#   scripts/dev-seed-demo.sh -h               this text
#
#   POSTGRES_DB=scratch scripts/dev-seed-demo.sh
#       seed another database instead. It has to exist and be migrated already
#       (scripts/dev-migrate.sh applies the dev instance's migrations, not
#       another database's) — and a scratch run should also set
#       CACHE_URL=redis://127.0.0.1:6379/5, see below.
#
# Environment overrides:
#   COMPOSE_FILE    compose overlay to use (default: compose.dev.yml)
#   PYTHON_BIN      interpreter to run (default: uv run python, else .venv)
#   POSTGRES_DB     database to seed (default: the dev instance's own)
#   CACHE_URL       shared with the dev server by default, which is what makes
#                   the dev server pick the new settings up. A run against
#                   *another* database must point this at its own Redis index
#                   (redis://127.0.0.1:6379/5): the settings row is cached under
#                   a key that names no database, so the dev server would
#                   otherwise read the other one's row until it restarted.
#   SITE_DOMAIN, EMAIL_URL, DEFAULT_FROM_EMAIL, ACME_EMAIL
#                   the four the app requires; the development values below are
#                   the defaults, so a plain run needs none of them

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-compose.dev.yml}"

# Resolve relative to the repo root, but honour an absolute COMPOSE_FILE.
case "$COMPOSE_FILE" in
    /*) COMPOSE_PATH="$COMPOSE_FILE" ;;
    *)  COMPOSE_PATH="${ROOT_DIR}/${COMPOSE_FILE}" ;;
esac
# --project-directory follows the compose file so the Docker project (and its
# ports/volumes) is the same no matter which worktree this script is run from.
COMPOSE=(docker compose -f "$ROOT_DIR/compose.yml" -f "$COMPOSE_PATH" --project-directory "$ROOT_DIR")

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '/^#/!q; 1d; s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
    exit "${1:-0}"
}

case "${1:-}" in
    -h|--help) usage 0 ;;
esac
# Everything else belongs to the command, so `--force` and friends pass through
# without this script having to know them.
EXTRA=("$@")

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH"
[ -f "$COMPOSE_PATH" ] || die "compose file not found: $COMPOSE_FILE"

# The project the running stack belongs to. Worth naming in the failure below:
# compose derives it from the directory it is run from, so a stack started from
# a worktree is a *different* project with its own containers, and this script
# would find nothing to seed.
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"

"${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx db \
    || die "no running 'db' service in the compose project '${PROJECT}'. Start the dev stack from the repository root (scripts/dev-up.sh), or set COMPOSE_PROJECT_NAME to the project it is running in."

if [ -n "${PYTHON_BIN:-}" ]; then
    PY=("$PYTHON_BIN")
elif command -v uv >/dev/null 2>&1; then
    PY=(uv run python)
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PY=("$ROOT_DIR/.venv/bin/python")
else
    die "no Python found: install uv, or point PYTHON_BIN at an interpreter"
fi

# The database's user, password and name, asked of the container rather than
# read out of .env: the stack is what is being seeded, so its own values are the
# ones that matter — and a worktree has no .env to read. The password is
# generated into a file inside the container (see app/entrypoint.sh), so there
# is no copy on the host either way.
#
# `|| true` throughout because `set -e` would otherwise take a variable the
# container does not carry for a fatal error, and exit without saying why.
stack_env() { "${COMPOSE[@]}" exec -T db printenv "$1" 2>/dev/null || true; }

POSTGRES_USER="${POSTGRES_USER:-$(stack_env POSTGRES_USER)}"
POSTGRES_USER="${POSTGRES_USER:-troopconnect}"
POSTGRES_DB="${POSTGRES_DB:-$(stack_env POSTGRES_DB)}"
POSTGRES_DB="${POSTGRES_DB:-troopconnect}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$("${COMPOSE[@]}" exec -T db cat /data/db-secrets/postgres_password 2>/dev/null || true)}"
[ -n "$POSTGRES_PASSWORD" ] || die "could not read the database password from the 'db' container"

# The four the app refuses to start without. Assigning rather than overwriting,
# so a real SITE_DOMAIN in the environment still wins.
: "${SITE_DOMAIN:=troop.example.org}"
: "${EMAIL_URL:=console://}"
: "${DEFAULT_FROM_EMAIL:=inscriptions@example.org}"
: "${ACME_EMAIL:=admin@example.org}"
export SITE_DOMAIN EMAIL_URL DEFAULT_FROM_EMAIL ACME_EMAIL

export DJANGO_DEBUG=1
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"

# EMAIL_URL=console:// prints mail instead of sending it, but MAILERSEND_API_KEY
# selects MailerSend whichever EMAIL_URL says — and the demo must not be able to
# reach one, so the selector is dropped rather than trusted to be absent.
unset MAILERSEND_API_KEY MAIL_SEND_MODE

# A clearer error than the traceback Django raises for a database that is not
# there — which is what anyone overriding POSTGRES_DB will hit first.
"${COMPOSE[@]}" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    psql -U "$POSTGRES_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'" \
    | grep -q 1 \
    || die "database '${POSTGRES_DB}' does not exist. Create it, or drop POSTGRES_DB to seed the dev instance's own."

say "Seeding the demo troop into '${POSTGRES_DB}' on ${POSTGRES_HOST}:${POSTGRES_PORT}"

cd "$ROOT_DIR/app"
exec "${PY[@]}" manage.py seed_demo ${EXTRA[@]+"${EXTRA[@]}"}
