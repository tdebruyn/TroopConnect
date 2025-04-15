#!/bin/sh
set -e

envsubst < /etc/caddy/Caddyfile-default.tpl > /etc/caddy/Caddyfile
caddy run --config /etc/caddy/Caddyfile
