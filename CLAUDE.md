# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TroopConnect is a Django 5.2 web application for managing a Belgian scout unit ("Scouts de Limal"). It handles member registration (children, parents, animators), section enrollment by school year, email notifications via AWS SES, and admin management. Production domain: `troop.tomctl.be`. Language: Belgian French (`fr-be`).

## Development Commands

```bash
# Start all dev services (Postgres, Redis, web, celery worker, celery-beat)
docker compose -f docker-compose-local.yml up --build

# Run Django management commands inside the web container
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py migrate
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py createsuperuser
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py shell

# Run tests (currently empty stubs)
docker compose -f docker-compose-local.yml exec web uv run /app/manage.py test

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
- `django-post_office` queues emails (Celery-integrated)
- `django-ses` sends via AWS SES
- Email backend: `post_office.EmailBackend` wrapping `django_ses.SESBackend`

### Secrets & Config
- Secrets loaded from `app/troopconnect/.settings.json` (gitignored). Template at `.settings.json-default`.
- DB password from `POSTGRES_PASSWORD` env var.
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
- No test suite exists (only empty stubs in `app/tests/` and `app/homepage/tests.py`).
- No CI/CD pipelines configured.
- `django-simple-history` is installed but not actively used on models.
- `members/signals.py` exists but is entirely commented out.
- The SQLite files (`db.sqlite3`) are legacy; the project uses PostgreSQL exclusively.
