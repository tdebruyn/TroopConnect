#!/bin/sh
#
# TroopConnect container entrypoint.
#
# Runs for every service built from this image -- web, worker and beat -- and
# for the one-shot `init` service, which does nothing but run the secret step.
# Only the web service sets RUN_MIGRATIONS, so it is the only one that
# migrates and collects static files.
set -e

SECRET_KEY_FILE="${SECRET_KEY_FILE:-/data/secrets/secret_key}"
POSTGRES_PASSWORD_FILE="${POSTGRES_PASSWORD_FILE:-/data/db-secrets/postgres_password}"

# ---------------------------------------------------------------------------
# Secrets
#
# Each is generated once, into its own volume. Losing the secret key logs every
# user out; losing the database password locks the application out of
# PostgreSQL. An existing file is never overwritten, so an operator can take
# control of either value by setting SECRET_KEY or POSTGRES_PASSWORD in .env
# before the first start.
#
# They are kept apart on purpose: the database password lives in a volume that
# is mounted read-only into the database container, and the secret key does
# not. A database container that can read the key that signs every session is
# a privilege it has no use for.
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
    directory="$(dirname "$file")"

    if [ -s "$file" ]; then
        return 0
    fi

    if ! mkdir -p "$directory"; then
        echo "Cannot create $directory -- is its volume mounted and writable?" >&2
        exit 1
    fi

    if [ -n "$supplied" ]; then
        printf '%s' "$supplied" > "$file"
    else
        generate_secret > "$file"
        echo "Generated $file"
    fi

    chmod "$mode" "$file"
}

ensure_secret_file "$SECRET_KEY_FILE" 600 "${SECRET_KEY:-}"

# PostgreSQL reads this one itself, as its own user, through
# POSTGRES_PASSWORD_FILE, so it cannot be root-only.
ensure_secret_file "$POSTGRES_PASSWORD_FILE" 644 "${POSTGRES_PASSWORD:-}"

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

    # The first-run wizard's gate. On an instance with no administrator this
    # issues the one-time setup code (or reprints the one already issued) into
    # this container's log, which is where whoever is installing reads it
    # from; on a configured instance it says there is nothing to set up.
    # Only the web service is armed by it, because only the web service
    # serves the wizard.
    python manage.py setup_code
fi

exec "$@"
