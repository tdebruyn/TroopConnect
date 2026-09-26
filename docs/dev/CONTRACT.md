# TroopConnect configuration contract

Two kinds of configuration, deliberately kept apart:

| Kind | Lives in | Changed by | Examples |
| --- | --- | --- | --- |
| Infrastructure | environment variables (`.env`) | whoever runs the server | domain, mail server, database password |
| Troop content | the database (`SiteSettings`) | the troop's admins, in the web UI | unit name, contact address, registration open/closed |

Neither requires editing a file shipped in this repository. A troop never
edits files; a hoster never edits the database by hand.

This document is the reference for both. **Update it whenever you add or
change an environment variable, a management command, a service or a
`SiteSettings` field.**

---

## 1. Environment variables

Read by a single settings module (`app/troopconnect/settings.py`) through the
helpers in `app/troopconnect/env.py`. Parsing happens in settings; validation
happens in `app/troopconnect/checks.py`, so `python manage.py check` is the one
place an operator sees what is wrong.

### Required

Missing or malformed values are reported as **errors** and stop the process.
With `DJANGO_DEBUG=1` they are reported as warnings instead, so a developer can
run the app before wiring up mail.

| Variable | Example | Notes |
| --- | --- | --- |
| `SITE_DOMAIN` | `troop.example.org` | Bare hostname. Drives `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, the `django.contrib.sites` row and Caddy's TLS certificate. No scheme, no path, no port. |
| `EMAIL_URL` | `smtp+tls://user:pass@mail.example.org:587` | Schemes: `smtp://`, `smtp+tls://`, `smtp+ssl://`, `console://`. Percent-encode `@`, `:` and `/` in credentials. Optional `?timeout=10`. |
| `DEFAULT_FROM_EMAIL` | `inscriptions@example.org` | Sender on every message the app sends. Must be an address the mail provider permits. |
| `ACME_EMAIL` | `admin@example.org` | Let's Encrypt contact address. Used by the Caddy container; Django reads it only to insist it is set. |

### Optional

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | generated | An explicit value wins. |
| `SECRET_KEY_FILE` | `/data/secrets/secret_key` | Where the key is read from, and generated into, when `SECRET_KEY` is unset. |
| `DJANGO_DEBUG` | off | `1`/`true`/`yes`/`on` turns debug on. Never set on a public domain; a system check warns if you do. |
| `SITE_ID` | `1` | The `django.contrib.sites` row allauth reads. Only change it for an instance migrated from the old `.settings.json`. |
| `TIME_ZONE` | `Europe/Brussels` | Used for dates and Celery schedules. |
| `POSTGRES_USER` | `troopconnect` | |
| `POSTGRES_DB` | `troopconnect` | |
| `POSTGRES_PASSWORD` | generated | Set it only to choose the password yourself, and only before the first start: the database is initialised with whatever the first run generated. |
| `POSTGRES_PASSWORD_FILE` | unset | Read when `POSTGRES_PASSWORD` is unset. The compose file points it at `/data/secrets/postgres_password`; the same convention on the Postgres side. |
| `POSTGRES_HOST` | `db` | The compose service name. |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_CONN_MAX_AGE` | `0` | Seconds to keep connections open. |
| `DATABASE_URL` | unset | `postgres://user:pass@host:5432/db`. Overrides the `POSTGRES_*` variables. |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker and Django cache. |
| `CELERY_BROKER_URL` | `REDIS_URL` | Override the broker only. |
| `CELERY_WORKER_STATE_DB` | `/tmp/celery-worker-state.db` | |
| `CACHE_URL` | `REDIS_URL` | |
| `SERVE_MEDIA_LOCALLY` | on in debug, off otherwise | `1` makes Django serve `/media/` instead of leaving it to the reverse proxy. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | unset | Both required. Without them the Google provider is not registered and no Google button appears. |
| `FACEBOOK_APP_ID` / `FACEBOOK_SECRET` | unset | As above, for Facebook. |
| `SENTRY_DSN` | unset | Enables Sentry error reporting. `send_default_pii` is off. |
| `SENTRY_ENVIRONMENT` | `production` | |
| `SENTRY_RELEASE` | unset | |
| `MAILERSEND_API_KEY` | unset | Setting it switches sending to MailerSend's HTTP API and takes precedence over `EMAIL_URL`. |
| `MAIL_SEND_MODE` | `mailersend` if an API key is set, else `EMAIL_URL` | `mailersend` (legacy alias `real`), `dummy`, or anything else to follow `EMAIL_URL`. |
| `UPDATE_CHECK` | off | Reserved. No outbound update check is implemented yet. |
| `UPDATE_CHECK_URL` | GitHub releases API | Reserved, as above. |

### Read by the images, not by Django

| Variable | Default | Read by |
| --- | --- | --- |
| `TC_VERSION` | `1` | `compose.yml`, to choose the image tag: `ghcr.io/tdebruyn/troopconnect:$TC_VERSION`. |
| `SECRETS_DIR` | `/data/secrets` | `app/entrypoint.sh`, where the generated secrets are written. |
| `RUN_MIGRATIONS` | unset | `app/entrypoint.sh`. Set on the web service only: it makes the entrypoint migrate and collect static files. |
| `SITE_DOMAIN`, `ACME_EMAIL` | required | Also read by Caddy, which substitutes `{$SITE_DOMAIN}` and `{$ACME_EMAIL}` into `caddy/Caddyfile` and refuses to serve an empty site address. |

---

## 2. Troop-editable settings (`SiteSettings`)

A singleton row edited by admins in the web UI. Defaults are generic, not
troop-specific. Read through `SiteSettings.get_settings()`, which caches in the
Django cache.

| Field | Purpose |
| --- | --- |
| `site_name` | Unit name, shown in the header and emails. |
| `site_description`, `site_keywords` | Meta description and keywords. |
| `contact_email`, `contact_phone`, `contact_address` | Public contact details, exposed to every template as `contact_email` via `members.context_processors.contact_info`. |
| `facebook_url`, `instagram_url` | Social links in the footer. |
| `email_signature` | Appended to outgoing mail. |
| `registration_open`, `registration_message` | Whether new registrations are accepted, and what to say when they are not. |
| `photo_consent_text` | Consent wording shown on the child form. |
| `address_placeholder` | Example address shown under the address field. |
| `available_languages` | Languages offered in the selector. With one entry the site is locked to it. |
| `default_language` | Language for visitors whose browser language is not enabled. Must be one of `available_languages`. |
| `last_passage_school_year` | Bookkeeping for the yearly section passage; do not edit by hand. |

`ImportantDocument` (title, description, url, file) is likewise admin-managed.

---

## 3. Management commands

| Command | Notes |
| --- | --- |
| `wait_for_db` | Blocks until the database answers. Used by the entrypoint. |
| `migrate_locked` | `migrate` under a Postgres advisory lock, so only one process migrates. Used by the entrypoint. |
| `create_test_data` | Seeds the Playwright end-to-end users described in the README. Development only. |
| `import_legacy` | One-off import of members from the pre-TroopConnect system. |

`migrate` also rewrites the `django.contrib.sites` row's domain from
`SITE_DOMAIN` (`app/troopconnect/siteconfig.py`), so links in outgoing email
point at the right host on a fresh install.

---

## 4. Services

`compose.yml`:

| Service | Image | Role |
| --- | --- | --- |
| `init` | app image | One shot. Runs `entrypoint.sh init-secrets` and exits. |
| `web` | app image | Gunicorn on 9000. The only service that migrates and collects static files. |
| `worker` | app image | Celery worker: `send_queued_mail`, `create_year_task`, `run_passage`, cleanup tasks. |
| `beat` | app image | Celery scheduler (`django_celery_beat`, database-backed). |
| `db` | `postgres:17-alpine` | Database. PostgreSQL only — the app uses `ArrayField`. |
| `redis` | `redis:7-alpine` | Celery broker and cache. |
| `caddy` | `caddy:2-alpine` | TLS termination and reverse proxy; serves `/static/` and `/media/` from volumes. |

The four application services run the same image,
`ghcr.io/tdebruyn/troopconnect:${TC_VERSION:-1}`. Only `caddy` publishes ports
(80 and 443); the rest are reachable only from the compose network, by service
name. There are no `container_name` overrides, so the project name keeps two
instances on one host from colliding.

Volumes:

| Volume | Mounted at | Holds |
| --- | --- | --- |
| `db_data` | `db:/var/lib/postgresql/data` | Database files. |
| `app_data` | `init`, `web`, `worker`, `beat`, `db` (ro) | Generated secrets: `secret_key` and `postgres_password`. |
| `media` | `web`, `worker`, `beat`, `caddy` (ro) | User uploads. |
| `static` | `web`, `caddy` (ro) | `collectstatic` output. |
| `caddy_data`, `caddy_config` | caddy | Certificates and Caddy's autosaved config. |

`app_data` is shared deliberately: `db` reads its password from the same file
the entrypoint generated, so the two can never disagree. The consequence is
that deleting `db_data` without deleting `app_data` leaves the generated
password pointing at a database that no longer has it — delete both, or
neither.

`compose.dev.yml` overlays the same file for development: it builds the image
locally as `troopconnect-dev:local` (so it never shadows a release tag), mounts
`app/`, sets `DJANGO_DEBUG=1` with `SITE_DOMAIN=localhost` and
`EMAIL_URL=console://`, publishes the web port and the database ports, and puts
`caddy` behind a profile so it does not start.

The `init` service exists because Postgres reads `POSTGRES_PASSWORD_FILE` once,
when it first initialises an empty data directory. Something has to create that
file before then, and compose can only express that ordering with a one-shot
service and `depends_on: condition: service_completed_successfully`.

---

## 4a. Container entrypoint

`app/entrypoint.sh` runs for every service built from the app image, as the
Dockerfile `ENTRYPOINT` with the service's `command` as arguments.

1. **Secrets.** Creates `/data/secrets/secret_key` (mode 600) and
   `/data/secrets/postgres_password` (mode 644, because Postgres reads it as a
   different user). An existing file is never overwritten, so `SECRET_KEY` or
   `POSTGRES_PASSWORD` in the environment wins on the first start and is
   ignored afterwards. With the argument `init-secrets` it stops here — that is
   all the `init` service does.
2. **Wait for the database.** `manage.py wait_for_db`, which fails with a
   clear message after `--timeout` (60s) rather than a connection traceback.
3. **Once-per-deploy work**, only when `RUN_MIGRATIONS` is set, which only the
   web service does. `manage.py migrate_locked` takes a Postgres advisory lock
   and gives up with a plain-language message if another process is still
   migrating; then `collectstatic`.
4. `exec "$@"` — the service's command, usually Gunicorn or Celery.

---

## 5. Email pipeline

`django-post-office` queues messages (status `queued`) rather than sending on
the request path. Celery flushes them: immediately on the `email_queued` signal,
with the `send_queued_mail` beat task every 5 minutes as a backstop. After
`MAX_RETRIES` (3) failures a message is marked `failed` and staff see a warning
banner linking to the queue page, where they can requeue or purge.

The backend is chosen from `MAIL_SEND_MODE` / `MAILERSEND_API_KEY` / `EMAIL_URL`
(see the table above). `troopconnect/dummy_backend.py` records to
`django.core.mail.outbox` without sending, for tests and dry runs.

---

## 6. Deployment

**Self-hosted (supported):** the installation is two files. Copy `.env.example`
to `.env`, fill in the four required variables, then

```bash
docker compose up -d
```

Nothing in the shipped files is edited, and there is no build step: the images
come from `ghcr.io/tdebruyn/troopconnect`.

**Ansible (community-maintained, unsupported):** `contrib/ansible/`. Non-secret
values go in `config.yml` (from `config.yml-example`), secrets in `vault.yml`
(edited with `create-config.py`). The playbook writes them to
`{{ project_dir }}/.env` as uppercase variables and starts `compose.yml`. See
that directory's README before relying on it.
