# TroopConnect

Web application for running a scout unit: member registration (children,
parents, animators), section enrollment by school year, email notifications and
admin management. The interface is available in French, Dutch and English.

Any troop can run its own independent instance: deploy the published images
with a filled-in `.env`, and no code changes.

The whole installation is `compose.yml` plus a `.env`:

```bash
cp .env.example .env     # fill in SITE_DOMAIN, EMAIL_URL,
                         # DEFAULT_FROM_EMAIL and ACME_EMAIL
docker compose up -d
docker compose exec web python manage.py createsuperuser
```

The database password and the secret key are generated on first start and kept
in a volume; nothing has to be built, and no shipped file is edited.

`python manage.py check` reports any configuration problem, one plain-language
line per variable. Step-by-step instructions are in [INSTALL.md](INSTALL.md);
the full configuration contract is in
[docs/dev/CONTRACT.md](docs/dev/CONTRACT.md).

Licensed under the [AGPL-3.0](LICENSE). To report a vulnerability, see
[SECURITY.md](SECURITY.md).

## Development notes

TODO

1. http://127.0.0.1:8000/users/adminlist
   => update section
2. Création d'une nouvelle année
3. Assignation de la section année+1
4. Effacer année - 5
5. Créer un évènement
6. Pièces jointes et liens
7. Cotisations
8. Ajouter les liens importants

Starting REDIS
redis-server /opt/homebrew/etc/redis.conf
celery -A siteunite worker -l INFO
celery -A siteunite beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

mail sender:
https://www.mailersend.com

Nom de domaine:
tomctl.be

Registrar: regery.com
Hosting: contabo.com

Terraform

Docker

## E2E Test Users (local)

The following users are seeded for Playwright end-to-end tests. Password for all: `Test1234!`

| Role | Email |
|------|-------|
| Parent | parent1@test.be |
| Parent | parent2@test.be |
| Animateur | anim1@test.be |
| Staff (Admin) | staff1@test.be |
| Child (Animé) | child1@test.be |
| Superadmin | superadmin@test.be |

docker compose -f compose.yml -f compose.dev.yml exec web python /app/manage.py create_test_data
npx playwright test e2e/child.spec.js e2e/superadmin.spec.js

## Local dev scripts

Wrappers around `docker compose -f compose.yml -f compose.dev.yml` (`--help` on any of them).

```bash
scripts/dev-up.sh                  # start the stack, wait until it serves
scripts/dev-up.sh --build          # ...rebuilding the image first
scripts/dev-up.sh --migrate        # ...then apply migrations
scripts/dev-down.sh                # stop it (data kept)
scripts/dev-down.sh --volumes      # ...and delete the postgres volume
scripts/dev-migrate.sh             # apply migrations
scripts/dev-migrate.sh -m members  # makemigrations + migrate
scripts/dev-migrate.sh --show      # migration status
scripts/dev-migrate.sh --check     # exit 1 if anything is unapplied
```

`dev-migrate.sh` works whether or not the stack is running (it falls back to
`docker compose run --rm`). Set `COMPOSE_FILE` to target a different dev overlay;
`compose.yml` is always included.
