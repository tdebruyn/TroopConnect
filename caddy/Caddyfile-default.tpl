{
	email ${LETSENCRYPT_CONTACT_EMAIL}
}

${WEBSERVER} {
	encode zstd gzip

	handle_path /static/* {
		file_server {
			root "/opt/TroopConnect/static"
		}
	}

	handle_path /media/* {
		file_server {
			root "/opt/TroopConnect/media"
		}
	}

	handle {
		reverse_proxy http://${APP_HOST}:${APP_PORT};
	}
}
