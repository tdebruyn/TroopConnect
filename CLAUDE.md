# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TroopConnect is a Django 6.0 web application for managing a scout unit. It handles member registration (children, parents, animators), section enrollment by school year, email notifications, and admin management. UI languages: French, Dutch and English (`fr-be` default).

It is built to be self-hosted: a troop deploys an independent instance from the published images with a filled-in `.env` and no code edits. See `docs/dev/CONTRACT.md` for the full configuration contract and `.env.example` for a starting point.

## Development Commands

```bash
# Development runs compose.yml with the compose.dev.yml overlay, which builds
# the image locally, mounts app/, and turns on debug. scripts/dev-*.sh wrap this.
docker compose -f compose.yml -f compose.dev.yml up --build

# Run Django management commands inside the web container
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py migrate
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py createsuperuser
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py shell

# Run the test suite in app/tests/ (also runs a ruff lint check via test_lint.py).
# Note: bare `manage.py test` only discovers apps in INSTALLED_APPS; `tests` is a
# top-level package, so name it explicitly.
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests
# `--parallel 8` splits the suite across worker processes and takes the suite
# from ~195s to ~31s. Past 8 workers it stops paying: the run is bounded by the
# slowest worker, not by the CPU. Each worker gets its own test database, and
# its own cache (troopconnect/testcache.py) so the workers cannot see each
# other's state.
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests --parallel 8
# Run a single module, e.g. just the lint check:
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests.test_lint

# Lint with ruff (config: app/ruff.toml). Append `--fix` to auto-fix safe issues.
docker compose -f compose.yml -f compose.dev.yml exec web ruff check .

# Run Celery locally (outside Docker, needs Redis running)
celery -A troopconnect worker -l INFO
celery -A troopconnect beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Package management uses `uv` (not pip directly). Dependencies are pinned in `app/requirements.txt`.

## Architecture

### Django Apps
- **members** (`app/members/`) — Core app: accounts, persons, roles, sections, enrollments, profiles, child management, admin views
- **homepage** (`app/homepage/`) — Landing page (template-only, no models)

### Key Model Design

- **Person/Account separation**: `Person` is the real-world entity (parent, child, animator). `Account` is the login-capable user model (custom `AbstractBaseUser`, auth via email, no username). They are linked via OneToOneField. `AUTH_USER_MODEL = "members.Account"`.
- **Role system**: Primary roles (Nouveau, Animateur, Parent, Anime) and secondary roles (Admin, Tresorier, etc.) via M2M through `PersonRole`.
- **Parent-child**: Self-referential M2M on Person via `ParentChild` through model.
- **Enrollment**: Person + Section + SchoolYear (unique_together constraint).
- **TroopSettings**: Singleton model for the troop's own config (organisation, locale,
  calendar, module switches), edited on the staff settings page at `/users/settings`.

### Frontend Patterns
- HTMX for partial page updates (child list, child forms, secondary role loading). Views return `HX-Trigger` headers.
- `django-widget-tweaks` for template form rendering.
- Templates in `app/templates/` (project-level) and per-app `templates/` dirs.

### Email Pipeline
- `django-post_office` queues emails. `POST_OFFICE["DEFAULT_PRIORITY"]="medium"`, so `mail.send()` creates a queued `Email` instead of dispatching synchronously.
- Flushed asynchronously by Celery: the `send_queued_mail` beat task (every 5 min) plus the `email_queued` signal (with `CELERY_ENABLED`).
- Sending backend follows `EMAIL_URL` (`smtp://`, `smtp+tls://`, `smtp+ssl://` or `console://`), parsed in `troopconnect/env.py`. `MAIL_SEND_MODE` overrides it: `mailersend` (or the legacy `real`) → MailerSend HTTP API (`troopconnect/mailersend_backend.py`), `dummy` → `troopconnect/dummy_backend.py` (records to `django.core.mail.outbox`). Setting `MAILERSEND_API_KEY` selects MailerSend implicitly.
- Failed sends (after `MAX_RETRIES=3`) trigger a staff warning banner linking to the email queue page (`members:mail_queue`), where staff can **requeue** or **purge** failed emails.

### Configuration
- One settings module, `app/troopconnect/settings.py`, reads **only** the environment. There is no config file checked into or mounted into the app.
- Parsing helpers live in `troopconnect/env.py`; validation lives in `troopconnect/checks.py`, so `manage.py check` is the single place configuration problems surface. In production a bad variable is an error that stops startup; with `DJANGO_DEBUG=1` it is a warning.
- Required: `SITE_DOMAIN`, `EMAIL_URL`, `DEFAULT_FROM_EMAIL`, `ACME_EMAIL`. Everything else is optional with a safe default.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are derived from `SITE_DOMAIN`; `DEBUG` is off unless `DJANGO_DEBUG=1`. The secret key falls back to `/data/secrets/secret_key`, generated on first boot.
- Troop-editable content (unit name, languages, contact details, scout-year dates, module
  switches) lives in the database (`TroopSettings`), never in the environment. See
  `docs/dev/CONTRACT.md` for the split.

## Deployment

The installation is `compose.yml` plus a `.env`; see `docs/dev/CONTRACT.md`.
Services: `init` (one-shot secrets), `web`, `worker`, `beat`, `db`, `redis`,
`caddy`. Only caddy publishes ports. The application image is published to
`ghcr.io/tdebruyn/troopconnect`, tagged by `TC_VERSION`.

`app/entrypoint.sh` is the Dockerfile `ENTRYPOINT`: it generates the secrets
into `/data/secrets`, waits for the database, and — only for the web service,
which sets `RUN_MIGRATIONS` — migrates under a Postgres advisory lock and
collects static files.

Ansible automation lives in `contrib/ansible/`. It is community-maintained and
unsupported; see its README before relying on it.

## Comment Style

Comments explain **why**, never **what** — the code already says what it does.
Write one when it records something the code cannot show: a hidden constraint, a
workaround and what it works around, a subtle invariant a future edit could
break, or why the obvious alternative was rejected.

Delete one that:

- restates the next line (`# Build body`, `# Apply late penalty`)
- is dead code parked as a comment — git holds it, and a commented-out copy only
  reads to whoever saw the draft it came from
- refers to an earlier version of the code (`no longer`, `used to`, `previously`,
  `the old code`) instead of stating the current invariant
- assumes the reader watched the conversation that produced it

Keep functional directives — `# noqa`, `# type: ignore`, `# pragma: no cover`
are code, often the only reason a lint run passes.

The `TroopSettings` field docs in `members/models.py` are the reference standard:
each says what the field decides, not what it stores.

## Important Notes
- Test suite lives in `app/tests/` (plus per-app `tests.py` for `finance`/`homepage`). `manage.py test tests` also runs a ruff lint check (`tests/test_lint.py`); linter config is `app/ruff.toml`.
- No CI/CD pipelines configured.
- `django-simple-history` is installed but not actively used on models.
- `members/signals.py` defines a `post_save` handler that is still not imported, so it is dead. `MembersConfig.ready()` now only registers the system checks and the `Site`-domain sync.
- The SQLite files (`db.sqlite3`) are legacy; the project uses PostgreSQL exclusively.
- `django-ses` is still in `requirements.txt` and its dashboard/webhook URLs are still routed in `troopconnect/urls.py`, left over from before email moved off AWS SES. It is not in `INSTALLED_APPS`, so those views cannot work. Removal is a pending decision, not an oversight.
