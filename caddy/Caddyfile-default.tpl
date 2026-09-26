# Caddy configuration for a TroopConnect instance.
#
# run.sh substitutes ${SITE_DOMAIN}, ${ACME_EMAIL}, ${APP_HOST} and ${APP_PORT}
# from the container environment, so nothing here is tied to one troop.
# Caddy's own placeholders ({host}, {remote}, {scheme}) use single braces and
# are left alone by envsubst.

{
	# Address Let's Encrypt uses to warn about expiring certificates.
	email ${ACME_EMAIL}
}

${SITE_DOMAIN} {
	encode zstd gzip

	log {
		format console {
			time_format iso8601
		}
	}

	# Serve static files directly
	handle_path /static/* {
		uri strip_prefix /static
		root * /vol/static
		file_server
	}

	# Serve media files directly
	handle_path /media/* {
		uri strip_prefix /media
		root * /vol/media
		file_server
	}

	# Forward all other requests to the Django application
	handle {
		reverse_proxy ${APP_HOST}:${APP_PORT} {
			header_up Host {host}
			header_up X-Real-IP {remote}
			header_up X-Forwarded-For {remote}
			header_up X-Forwarded-Proto {scheme}
		}
	}
}
