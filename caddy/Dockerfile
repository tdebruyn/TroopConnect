FROM caddy:latest
LABEL maintainer="tomctl.be"

COPY ./Caddyfile-default.tpl /etc/caddy/Caddyfile-default.tpl
COPY ./gunicorn_headers /etc/caddy/gunicorn_headers
COPY ./run.sh /run.sh

ENV APP_HOST=troopconnect
ENV APP_PORT=9000

USER root

RUN mkdir -p /vol/static && \
    mkdir -p /vol/media && \
    chmod 755 /vol && \
    chmod +x /run.sh

VOLUME /vol/static
VOLUME /vol/media


CMD ["/run.sh"]
