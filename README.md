# TroopConnect

Web application for running a scout unit: member registration (children,
parents, animators), section enrollment by school year, email notifications,
fees, an agenda, and admin management. The interface is available in French,
Dutch and English.

Every troop runs its own independent instance: deploy the published images with
a filled-in `.env`, and change no code.

## ⚠️ Early-stage software

**TroopConnect is pre-1.0 and still moving.** Versions are `0.Y.Z`, and until
1.0 a *minor* bump is the signal for a breaking change — an upgrade can rewrite
the database schema, change a configuration variable, or alter what a screen
does. Read these before you point a real troop at it:

- **It is run by its authors, not by a company.** There is no support contract
  and no guarantee that a given release suits your unit. Nobody is on call.
- **Only install it if you can look after it yourself**: read a container log,
  run `docker compose` commands, and get a shell into the web container.
- **Take a backup before every upgrade**, and upgrade deliberately by pinning
  `TC_VERSION` rather than tracking whatever is newest (see
  [Upgrading](#upgrading)).
- **Features may change shape between releases.** A module can be rewritten
  while you are using it. The `TroopSettings` module switches let a troop turn
  fees, signing or the agenda off, but they are not a compatibility promise.
- The `contrib/ansible` automation is community-maintained and explicitly
  unsupported.

Found a bug or something rough? Open an issue on
[GitHub](https://github.com/tdebruyn/TroopConnect/issues). Reports from a real
troop are exactly what moves this forward.

## Deploy your own instance

The whole installation is **`compose.yml`, the `caddy/Caddyfile` it mounts, and
a `.env`**. There is no build step: the images come from
`ghcr.io/tdebruyn/troopconnect`.

> **Never run a server before?** [GETTING-STARTED.md](GETTING-STARTED.md) walks
> through the whole thing — renting a machine, pointing a domain at it,
> installing Docker — with a screenshot of every screen of the setup wizard.
> The rest of this section is the same install without the hand-holding.

### What you need

- A server with Docker and the Compose plugin.
- A domain pointed at it (an A/AAAA record), with ports 80 and 443 reachable —
  Caddy obtains the TLS certificate for that name from Let's Encrypt.
- A mail account to send from (any SMTP provider, or MailerSend). Registration
  and notification email is the point of the application, so a mail server that
  refuses will be found out about at install time rather than through parents
  who never heard anything.

### Install

1. Get the repository onto the server — or at least `compose.yml`, the
   `caddy/` directory it mounts, and `.env.example` — and create the
   environment file:

   ```bash
   cp .env.example .env
   ```

2. Fill in the four required values at the top of `.env`:

   | Variable | What to put there |
   | --- | --- |
   | `SITE_DOMAIN` | the domain from the DNS record, e.g. `troop.example.org`. A bare hostname: no scheme, no path, no port. |
   | `EMAIL_URL` | your mail provider, e.g. `smtp+tls://user:pass@mail.example.org:587` |
   | `DEFAULT_FROM_EMAIL` | the address your troop's mail is sent from |
   | `ACME_EMAIL` | your address, for Let's Encrypt expiry warnings |

   Everything else is optional and documented in `.env.example`. Leave
   `POSTGRES_PASSWORD` and `SECRET_KEY` unset in particular: they are generated
   on first start and kept in volumes.

3. Start it:

   ```bash
   docker compose up -d
   ```

   On first start a one-shot `init` service generates the database password and
   the Django secret key into volumes, then the web service waits for the
   database, migrates, collects static files and issues a one-time setup code.
   Only `caddy` publishes ports; nothing else is reachable from outside.

4. Read the setup code out of the web container's log:

   ```bash
   docker compose logs web | grep -i "setup code"
   ```

   It looks like `K7QP-2M4T-9XWB-HR3F`. `docker compose exec web python
   manage.py setup_code` prints it again if it has scrolled away, and
   `setup_code --reset` issues a new one.

5. Open `https://your-domain/setup` and answer the wizard. **Until you do, the
   whole site leads there**: an instance with no administrator has nothing worth
   showing yet, so it serves the installer instead. The wizard asks for the
   administrator's details, the unit's name and contact address, the languages
   the site offers, the branches and sections (starting from Les Scouts' own),
   the shape of the scout year, and whether you use the fees, signing and agenda
   modules. It ends by sending a **real test email**, and does not finish until
   one arrives — a wrong port or a rejected sender is shown with the mail
   server's own words, and the step can be retried.

   Prefer a terminal, or want to script it? `docker compose exec web python
   manage.py setup` does the same work from flags or an `answers.json`, and
   `--dry-run` reports what it would write without writing it. Both are
   described in [docs/dev/CONTRACT.md](docs/dev/CONTRACT.md).

6. Once the wizard finishes, the site is live. Log in with the account you
   created and fill in the rest under Site settings (`/users/settings`).
   Branches and sections are edited in the Django admin. All of that lives in
   the database, not in `.env` — a troop never edits a shipped file.

The wizard's one-time code is a gate, not a password: it says "whoever can read
this container's log is the person setting the instance up". It is compared in
constant time and rate-limited, and an existing code is never replaced, so
recreating a container does not invalidate one you have already noted down.

### Choosing a version

`compose.yml` uses `ghcr.io/tdebruyn/troopconnect:${TC_VERSION:-0}`, so an
instance with `TC_VERSION` unset tracks the 0.x line:

| `TC_VERSION` | You get |
| --- | --- |
| *unset* (= `0`) | every 0.x release |
| `0.4` | patch releases of 0.4 only |
| `0.4.2` | exactly 0.4.2, and never moves |

`latest` is deliberately never published, so nothing resolves to "the newest
thing" by accident. The tag-to-image mapping and the release process are in
[RELEASING.md](RELEASING.md).

### Upgrading

Set `TC_VERSION` in `.env` to the release you want, then recreate:

```bash
docker compose pull
docker compose up -d
```

Migrations run automatically, under a Postgres advisory lock, so a rolling
restart is safe. The secrets live in volumes and are never regenerated, so
existing sessions and the database connection survive the upgrade.

Back up first — see below. While the project is pre-1.0, an upgrade is the
moment to expect a breaking change.

### Backups

Two volumes hold your data:

| Volume | Holds |
| --- | --- |
| `db_data` | the database |
| `media` | uploads (logo, favicon, attachments, signed documents) |

Two more hold generated secrets: `app_secrets` (the Django secret key) and
`db_secrets` (the database password). **Keep them.** Lose the key and every user
is logged out; lose the password and the application can no longer authenticate
to the database it already initialised. They are separate so that the database
container can read the password it was initialised with and nothing else — it
never gets the key that signs sessions.

Deleting `db_data` without deleting `db_secrets` leaves the stored password
pointing at a database that no longer has it. **Delete both, or neither.**

### When something is wrong

`manage.py check` names the variable and what to do about it, one plain-language
line per problem:

```bash
docker compose exec web python manage.py check
```

`GET /healthz` answers `200` while the database and the cache both respond, and
`503` the moment either does not, with a small JSON body naming which one
failed. It is public and reports *whether* each dependency answered, never the
error itself. `docker compose logs web` (and `worker`) is where the rest is.

### Reference

- [GETTING-STARTED.md](GETTING-STARTED.md) — the same install for someone who
  has never run a server: choosing a host, DNS, Docker, and the wizard screen
  by screen.
- [INSTALL.md](INSTALL.md) — the same install, step by step, plus the
  community-maintained Ansible playbook.
- [docs/dev/CONTRACT.md](docs/dev/CONTRACT.md) — the full configuration
  contract: every environment variable, every `TroopSettings` field, every
  management command, the services, the entrypoint and the health endpoint.
- [.env.example](.env.example) — a commented starting point.

## Development

Everything below runs against the dev overlay, `compose.yml` plus
`compose.dev.yml`, which builds the image locally, mounts `app/` into the
container, turns on `DJANGO_DEBUG`, sets `SITE_DOMAIN=localhost` and
`EMAIL_URL=console://`, publishes the web port and keeps Caddy out of the way.
The `scripts/dev-*.sh` wrappers cover the common cases.

### Getting the stack up

```bash
cp .env.example .env          # required: compose reads it for substitution
scripts/dev-up.sh --build     # builds, starts, waits until it serves
scripts/dev-up.sh --migrate   # ...and applies migrations
```

The app is then at <http://localhost:8000>, reloading on save because the
working copy is mounted. PostgreSQL is published on 5432 and Redis on 6379 for
GUI clients and `psql`.

To run it by hand instead of through the wrapper:

```bash
docker compose -f compose.yml -f compose.dev.yml up --build
```

Commands go through the `web` container:

```bash
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py migrate
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py createsuperuser
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py shell
```

A fresh dev database can also be brought to a usable state the way a real one
is: `manage.py setup`, or the `/setup` wizard with the code printed in the web
container's log. `createsuperuser` is the shortcut when you only want an admin
account.

### Tests

```bash
# The Django suite. `tests` is a top-level package, not an installed app, so
# name it explicitly: a bare `manage.py test` finds nothing.
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests

# The same suite across 8 worker processes: ~195s down to ~31s. Each worker
# gets its own database and its own cache, so they cannot see each other.
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests --parallel 8

# One module:
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py test tests.test_lint
```

Past 8 workers it stops paying: the run is bounded by the slowest worker, not by
the CPU. The suite includes a ruff lint check (`tests/test_lint.py`), so a lint
failure shows up as a test failure too. Lint on its own, with `--fix` to
auto-fix what is safe:

```bash
docker compose -f compose.yml -f compose.dev.yml exec web ruff check .
```

### End-to-end tests

The Playwright suite in `e2e/` drives a real browser against the dev stack at
`http://localhost:8000`. It needs the test accounts seeded first:

```bash
docker compose -f compose.yml -f compose.dev.yml exec web python manage.py create_test_data
npx playwright test                       # everything
npx playwright test e2e/child.spec.js     # one spec
```

Password for all of them: `Test1234!`.

| Role | Email |
|------|-------|
| Parent | parent1@test.be |
| Parent | parent2@test.be |
| Animateur | anim1@test.be |
| Staff (Admin) | staff1@test.be |
| Child (Animé) | child1@test.be |
| Superadmin | superadmin@test.be |

The config is `playwright.config.js` (headed, one worker, no retries) and the
login helper is `e2e/helpers/auth.js`. To *look* at the app as each persona
rather than test it, `scripts/dev-zen-test-users.sh` opens four Zen Browser
windows, one per account, each already logged in.

### Dev scripts

Wrappers around `docker compose -f compose.yml -f compose.dev.yml`; `--help` on
any of them prints the full usage.

```bash
scripts/dev-up.sh                  # start the stack, wait until it serves
scripts/dev-up.sh --build          # ...rebuilding the image first
scripts/dev-up.sh --migrate        # ...then apply migrations
scripts/dev-up.sh --foreground     # run attached, Ctrl-C to stop
scripts/dev-down.sh                # stop it (data kept)
scripts/dev-down.sh --volumes      # ...and delete the postgres volume
scripts/dev-migrate.sh             # apply migrations
scripts/dev-migrate.sh -m members  # makemigrations + migrate
scripts/dev-migrate.sh --show      # migration status
scripts/dev-migrate.sh --check     # exit 1 if anything is unapplied
scripts/worktree-tidy.sh           # review git worktrees, merge and clean up
scripts/dev-zen-test-users.sh      # four logged-in browser windows
```

`dev-migrate.sh` works whether or not the stack is running (it falls back to
`docker compose run --rm`). Set `COMPOSE_FILE` to target a different dev
overlay; `compose.yml` is always included.

### Layout

- `app/` — the Django project. `members/` is the core app (accounts, persons,
  roles, sections, enrollments, finance, agenda, messaging); `homepage/` is the
  landing page; `troopconnect/` holds settings and the environment parsing.
- `app/tests/` — the test suite; `e2e/` — the Playwright suite.
- `docs/dev/CONTRACT.md` — how configuration is split between the environment
  and the database, and the reference for both.
- `niche-tools/` — one-off scripts (importing the old site's data, repairing a
  table) that 99% of the time you can ignore. They sit outside `app/` on purpose
  so they are never built into the image; you run them by hand, mounted into a
  throwaway container. See [niche-tools/README.md](niche-tools/README.md).

## Licence and security

Licensed under the [AGPL-3.0](LICENSE). To report a vulnerability, see
[SECURITY.md](SECURITY.md).
