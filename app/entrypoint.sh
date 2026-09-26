#!/bin/sh
#
# TroopConnect container entrypoint.
#
# Runs for every service built from this image -- web, worker and beat -- and
# for the one-shot `init` service, which does nothing but run the secret step.
# Only the web service sets RUN_MIGRATIONS, so it is the only one that
# migrates and collects static files.
set -e

SECRETS_DIR="${SECRETS_DIR:-/data/secrets}"

# ---------------------------------------------------------------------------
# Secrets
#
# Both are generated once and kept in the app_data volume. Losing the secret
# key logs every user out; losing the database password locks the application
# out of PostgreSQL. An existing file is never overwritten, so an operator can
# take control of either value by setting SECRET_KEY or POSTGRES_PASSWORD in
# .env before the first start.
# ---------------------------------------------------------------------------

generate_secret() {
    # 48 random bytes as base64, restricted to an alphabet that is safe in a
    # URL and in a shell.
    head -c 48 /dev/urandom | base64 | tr -d '\n' | tr '+/' '-_'
}

ensure_secret_file() {
    file="$1"
    mode="$2"
    supplied="$3"

    if [ -s "$file" ]; then
        return 0
    fi

    if [ -n "$supplied" ]; then
        printf '%s' "$supplied" > "$file"
    else
        generate_secret > "$file"
        echo "Generated $file"
    fi

    chmod "$mode" "$file"
}

if ! mkdir -p "$SECRETS_DIR"; then
    echo "Cannot create $SECRETS_DIR -- is the app_data volume mounted and writable?" >&2
    exit 1
fi

ensure_secret_file "$SECRETS_DIR/secret_key" 600 "${SECRET_KEY:-}"

# PostgreSQL reads this one itself, as its own user, through
# POSTGRES_PASSWORD_FILE, so it cannot be root-only.
ensure_secret_file "$SECRETS_DIR/postgres_password" 644 "${POSTGRES_PASSWORD:-}"

# The init service exists only to create these files before PostgreSQL and the
# application start, so it has nothing left to do.
if [ "${1:-}" = "init-secrets" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# Compose waits for the database healthcheck before starting the application,
# but checking here too covers running the image outside compose and a
# database that is restarting.
python manage.py wait_for_db

if [ -n "${RUN_MIGRATIONS:-}" ]; then
    # Once-per-deploy work, owned by the web service. migrate_locked holds a
    # Postgres advisory lock so a second replica, or somebody running migrate
    # by hand, cannot race it.
    python manage.py migrate_locked
    python manage.py collectstatic --noinput
fi

exec "$@"
