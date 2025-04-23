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
