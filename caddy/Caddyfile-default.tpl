{
	email ${LETSENCRYPT_CONTACT_EMAIL}
}

${WEBSERVER} {
	encode zstd gzip

	handle_path /static/* {
		file_server {
			root "/vol/static"
		}
	}

	handle_path /media/* {
		file_server {
			root "/vol/media"
		}
	}

	handle {
		reverse_proxy http://${APP_HOST}:${APP_PORT}
	}
}
