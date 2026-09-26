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
| `POSTGRES_PASSWORD` | empty | |
| `POSTGRES_HOST` | `postgres` | |
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

### Reserved for the Self-Hosted Deployment

`ACME_EMAIL` and `SITE_DOMAIN` are also read by the Caddy container. The
`caddy/run.sh` entrypoint refuses to start without them rather than generating
a broken Caddyfile.

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
| `create_test_data` | Seeds the Playwright end-to-end users described in the README. Development only. |
| `import_legacy` | One-off import of members from the pre-TroopConnect system. |

The production entrypoint (`app/entrypoint.sh`) always runs `collectstatic` and
`migrate` before starting Gunicorn. `migrate` also rewrites the
`django.contrib.sites` row's domain from `SITE_DOMAIN`
(`app/troopconnect/siteconfig.py`), so links in outgoing email point at the
right host on a fresh install.

---

## 4. Services

`docker-compose-prod.yml`:

| Service | Image / build | Role |
| --- | --- | --- |
| `caddy` | `caddy/` | TLS termination and reverse proxy; serves `/static/` and `/media/` from volumes. |
| `troopconnect` | `app/Dockerfile.prod` | Gunicorn on port 9000. Runs `collectstatic` + `migrate` at start. |
| `celery` | `app/Dockerfile.prod` | Worker. `send_queued_mail`, `create_year_task`, `run_passage`, cleanup tasks. |
| `celery-beat` | `app/Dockerfile.prod` | Scheduler (`django_celery_beat`, database-backed). |
| `postgres` | `postgres:alpine` | Database. PostgreSQL only — the app uses `ArrayField`. |
| `redis` | `redis:alpine` | Celery broker and cache. |

Volumes: `postgres_data`, `static_volume`, `media_volume`, `caddy_data`,
`caddy_config`, and `app_secrets` (holds the generated `SECRET_KEY`).

`docker-compose-local.yml` mirrors this for development, with `DJANGO_DEBUG=1`,
`SITE_DOMAIN=localhost` and `EMAIL_URL=console://` so the app runs with no
external services.

The `shared_net` network is created by the Ansible `infra` role and declared
`external` in the production compose file.

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

**Self-hosted (recommended):** copy `.env.example` to `.env`, fill in the four
required variables, then

```bash
docker compose -f docker-compose-prod.yml up -d --build
```

**Ansible:** `deploy/ansible/`. Non-secret values go in `config.yml` (from
`config.yml-example`), secrets in `vault.yml` (edited with
`create-config.py`). The playbook writes them to `{{ project_dir }}/.env` as
uppercase variables and runs the compose file. See `INSTALL.md`.
