{
	email ${LETSENCRYPT_CONTACT_EMAIL}
}

${WEBSERVER} {
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
		reverse_proxy troopconnect:9000 {
			header_up Host {host}
			header_up X-Real-IP {remote}
			header_up X-Forwarded-For {remote}
			header_up X-Forwarded-Proto {scheme}
		}
	}
}

www.tomctl.be {
	log {
		format console {
			time_format iso8601
		}
	}
    reverse_proxy http://siteperso:80
}

tomctl.be {
	redir https://www.tomctl.be{uri} permanent
}
