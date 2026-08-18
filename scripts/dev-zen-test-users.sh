#!/usr/bin/env bash
# Open four Zen Browser windows against the local dev server, one per test
# persona, each already logged in:
#
#   superadmin@test.be  (superuser)   -> /admin/
#   parent1@test.be     (parent)      -> /
#   anim1@test.be       (animateur)   -> /
#   child1@test.be      (anime)       -> /
#
# Zen windows share one cookie jar per profile, so simultaneous logins need
# one profile per persona. Profiles live in ~/.zen/troopconnect-<persona>/
# and persist between runs; the script logs in over HTTP and injects the
# sessionid cookie directly into each profile's cookies.sqlite.
#
# Usage:
#   scripts/dev-zen-test-users.sh           open the four windows
#   scripts/dev-zen-test-users.sh --seed    (re)create test accounts first
#
# Test accounts come from `manage.py create_test_data` (password Test1234!).

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
ZEN_BIN="${ZEN_BIN:-zen-browser}"
PROFILES_ROOT="${HOME}/.zen"
PASSWORD="Test1234!"
COMPOSE_FILE="docker-compose-local.yml"

# slug|email|start path
PERSONAS=(
    "superadmin|superadmin@test.be|/admin/"
    "parent|parent1@test.be|/"
    "animateur|anim1@test.be|/"
    "anime|child1@test.be|/"
)

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# Cookie host + secure flag derived from BASE_URL (cookies ignore the port).
URL_HOST="${BASE_URL#*://}"
URL_HOST="${URL_HOST%%/*}"
URL_HOST="${URL_HOST%%:*}"
case "$BASE_URL" in
    https://*) COOKIE_SECURE=1 ;;
    *) COOKIE_SECURE=0 ;;
esac

command -v "$ZEN_BIN" >/dev/null 2>&1 || die "Zen Browser not found ($ZEN_BIN)"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
curl -fsS -o /dev/null "$BASE_URL/" || {
    die "Dev server not reachable at $BASE_URL.
Start it with: docker compose -f $COMPOSE_FILE up --build"
}

if [ "${1:-}" = "--seed" ]; then
    say "Seeding test data..."
    docker compose -f "$COMPOSE_FILE" exec -T web \
        uv run /app/manage.py create_test_data
fi

# Create the profile's database files once, headlessly, so we can inject the
# cookie before the first GUI launch (and skip Zen's first-run noise).
prime_profile() {
    local prof="$1"
    [ -f "$prof/prefs.js" ] && return 0
    say "  priming new profile: $(basename "$prof")"
    "$ZEN_BIN" --profile "$prof" --new-instance --headless \
        --screenshot /dev/null about:blank >/dev/null 2>&1 ||
        die "failed to prime profile $prof"
}

# Keep first-run prompts out of the dedicated test profiles. user.js is
# re-applied at every startup, which is what we want here.
write_user_js() {
    local prof="$1"
    cat >"$prof/user.js" <<'EOF'
// Managed by scripts/dev-zen-test-users.sh
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("toolkit.telemetry.enabled", false);
EOF
}

# Print the sessionid for the given email: reuse the cached jar when the
# session is still valid, otherwise perform a fresh allauth login.
# jar format: domain  flag  path  secure  expiry  name  value
session_for() {
    local email="$1" jar="$2" code token
    if [ -s "$jar" ]; then
        code=$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' \
            "$BASE_URL/accounts/email/")
        if [ "$code" = "200" ]; then
            say "  session still valid, reusing it"
            awk '$6 == "sessionid" {print $7; exit}' "$jar"
            return 0
        fi
    fi
    curl -s -c "$jar" -b "$jar" -o /dev/null "$BASE_URL/accounts/login/"
    token=$(awk '$6 == "csrftoken" {print $7; exit}' "$jar")
    [ -n "$token" ] || die "no csrftoken cookie from $BASE_URL"
    # Django CSRF requires a Referer/Origin on the POST.
    code=$(curl -s -b "$jar" -c "$jar" -o /dev/null -w '%{http_code}' \
        -X POST "$BASE_URL/accounts/login/" \
        --data-urlencode "csrfmiddlewaretoken=$token" \
        --data-urlencode "login=$email" \
        --data-urlencode "password=$PASSWORD" \
        --data-urlencode "remember=on" \
        -e "$BASE_URL/accounts/login/")
    [ "$code" = "302" ] || die "login failed for $email (HTTP $code)"
    awk '$6 == "sessionid" {print $7; exit}' "$jar"
}

inject_cookie() {
    local prof="$1" sessionid="$2"
    python3 - "$prof" "$sessionid" "$URL_HOST" "$COOKIE_SECURE" <<'PY'
import sqlite3
import sys
import time

profile, sessionid, host, secure = sys.argv[1:5]
now = time.time()
us = int(now * 1_000_000)
# This Zen build stores expiry in MICROseconds (Firefox upstream is seconds);
# a seconds-based value lands in 1970 and the cookie is born expired.
expiry = us + 10 * 365 * 24 * 3600 * 1_000_000  # browser-side; server rules

db = sqlite3.connect(f"{profile}/cookies.sqlite")
try:
    db.execute(
        "DELETE FROM moz_cookies"
        " WHERE host = ? AND name = 'sessionid' AND originAttributes = ''",
        (host,),
    )
    # sameSite: 1 = Lax (Django default); schemeMap 3 = http + https;
    # sessionid is HttpOnly.
    db.execute(
        """
        INSERT INTO moz_cookies
            (originAttributes, name, value, host, path, expiry, lastAccessed,
             creationTime, isSecure, isHttpOnly, inBrowserElement, sameSite,
             schemeMap, isPartitionedAttributeSet, updateTime)
        VALUES ('', 'sessionid', ?, ?, '/', ?, ?, ?, ?, 1, 0, 1, 3, 0, ?)
        """,
        (sessionid, host, expiry, us, us, int(secure), us),
    )
    db.commit()
finally:
    db.close()
PY
}

profile_in_use() {
    pgrep -af "$ZEN_BIN" | grep -qF -- "$1"
}

say "Opening test-user windows for $BASE_URL"
for persona in "${PERSONAS[@]}"; do
    IFS='|' read -r slug email start_path <<<"$persona"
    prof="$PROFILES_ROOT/troopconnect-$slug"
    jar="$prof/session.jar"
    say "[$slug] $email"

    mkdir -p "$prof"
    prime_profile "$prof"
    write_user_js "$prof"

    if profile_in_use "$prof"; then
        say "  already running, skipping (close its window to refresh the login)"
        continue
    fi

    sessionid=$(session_for "$email" "$jar")
    [ -n "$sessionid" ] || die "no sessionid cookie for $email"
    inject_cookie "$prof" "$sessionid"

    "$ZEN_BIN" --profile "$prof" --new-instance \
        --new-window "$BASE_URL$start_path" >/dev/null 2>&1 &
    sleep 1
done

say "Done. Password for all test accounts: $PASSWORD"
