#!/bin/sh
set -e

# Without these the generated Caddyfile would have an empty site block and
# Caddy would fail with a syntax error far less readable than these lines.
: "${SITE_DOMAIN:?SITE_DOMAIN must be set to the domain this instance is served from}"
: "${ACME_EMAIL:?ACME_EMAIL must be set to the Let's Encrypt contact address}"

envsubst < /etc/caddy/Caddyfile-default.tpl > /etc/caddy/Caddyfile
caddy fmt --overwrite /etc/caddy/Caddyfile
caddy run --config /etc/caddy/Caddyfile
