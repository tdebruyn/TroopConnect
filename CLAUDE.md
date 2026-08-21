# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TroopConnect is a Django 6.0 web application for managing a Belgian scout unit ("Scouts de Limal"). It handles member registration (children, parents, animators), section enrollment by school year, email notifications via AWS SES, and admin management. Production domain: `troop.tomctl.be`. Language: Belgian French (`fr-be`).

## Development Commands

```bash
# Start all dev services (Postgres, Redis, web, celery worker, celery-beat)
docker compose -f docker-compose-local.yml up --build

# Run Django management commands inside the web container
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py migrate
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py createsuperuser
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py shell

# Run the test suite in app/tests/ (also runs a ruff lint check via test_lint.py).
# Note: bare `manage.py test` only discovers apps in INSTALLED_APPS; `tests` is a
# top-level package, so name it explicitly.
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py test tests
# Run a single module, e.g. just the lint check:
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py test tests.test_lint

# Lint with ruff (config: app/ruff.toml). Append `--fix` to auto-fix safe issues.
docker compose -f docker-compose-local.yml exec web uv run ruff check /app

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
- **SiteSettings**: Singleton model for site-wide config (name, contact, registration toggle).

### Frontend Patterns
- HTMX for partial page updates (child list, child forms, secondary role loading). Views return `HX-Trigger` headers.
- `django-widget-tweaks` for template form rendering.
- Templates in `app/templates/` (project-level) and per-app `templates/` dirs.

### Email Pipeline
- `django-post_office` queues emails. `POST_OFFICE["DEFAULT_PRIORITY"]="medium"`, so `mail.send()` creates a queued `Email` instead of dispatching synchronously.
- Flushed asynchronously by Celery: the `send_queued_mail` beat task (every 5 min) plus the `email_queued` signal (with `CELERY_ENABLED`).
- Sending backend is chosen by `MAIL_SEND_MODE` (`.settings.json`): `"real"` → MailerSend HTTP API (`troopconnect/mailersend_backend.py`), `"dummy"` → `troopconnect/dummy_backend.py` (records to `django.core.mail.outbox`). Defaults to `"real"` when `MAILERSEND_API_KEY` is set.
- Failed sends (after `MAX_RETRIES=3`) trigger a staff warning banner linking to the email queue page (`members:mail_queue`), where staff can **requeue** or **purge** failed emails.
- `MAILERSEND_API_KEY` comes from a gitignored `.env` (referenced via `${MAILERSEND_API_KEY}` in docker-compose).

### Secrets & Config
- Secrets loaded from `app/troopconnect/.settings.json` (gitignored). Template at `.settings.json-default`.
- DB password from `POSTGRES_PASSWORD` env var.
- `MAILERSEND_API_KEY` from a gitignored `.env` at the repo root.
- `ALLOWED_HOSTS` is set based on `DEBUG` flag: localhost in dev, `troop.tomctl.be` in prod.

## Deployment

Production runs via Docker Compose (`docker-compose-prod.yml`) on a RHEL/AlmaLinux/Rocky VPS:
- **Caddy** reverse proxy (auto-LetsEncrypt, ports 80/443)
- **Gunicorn** on port 9000 (production entrypoint runs `collectstatic` + `migrate`)
- **PostgreSQL**, **Redis**, **Celery worker**, **Celery beat**

Ansible automation in `deploy/ansible/` with roles: `infra`, `mailforwarder`, `troopconnect`. Deploy with:
```bash
ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbook.yml
```

## Important Notes
- Test suite lives in `app/tests/` (plus per-app `tests.py` for `finance`/`homepage`). `manage.py test tests` also runs a ruff lint check (`tests/test_lint.py`); linter config is `app/ruff.toml`.
- No CI/CD pipelines configured.
- `django-simple-history` is installed but not actively used on models.
- `members/signals.py` defines a `post_save` handler but is never imported (`members/apps.py` `ready()` is `pass`), so it is dead.
- The SQLite files (`db.sqlite3`) are legacy; the project uses PostgreSQL exclusively.
