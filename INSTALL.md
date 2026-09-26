# Installing TroopConnect

If you have never run a server before, start with
[GETTING-STARTED.md](GETTING-STARTED.md) instead: it covers renting a machine,
DNS and installing Docker, with screenshots. What follows assumes you know your
way around a terminal and a `.env` file.

## What you need

- A server with Docker and the Compose plugin.
- A domain pointed at it (an A/AAAA record), with ports 80 and 443 reachable,
  because Caddy obtains the TLS certificate for that name.

That is the whole installation: **`compose.yml` and a `.env`**. There is no
build step — the images come from `ghcr.io/tdebruyn/troopconnect`.

## Install

1. Get the repository onto the server, or just the two files:

   ```bash
   cp .env.example .env
   ```

2. Fill in the four required values at the top of `.env`:

   | Variable | What to put there |
   | --- | --- |
   | `SITE_DOMAIN` | the domain from the DNS record, e.g. `troop.example.org` |
   | `EMAIL_URL` | your mail provider, e.g. `smtp+tls://user:pass@mail.example.org:587` |
   | `DEFAULT_FROM_EMAIL` | the address your troop's mail is sent from |
   | `ACME_EMAIL` | your address, for Let's Encrypt expiry warnings |

   Every other variable is optional. `.env.example` documents them.

3. Start it:

   ```bash
   docker compose up -d
   ```

   On first start a one-shot `init` service generates the database password and
   the Django secret key into a volume, then the web service waits for the
   database, migrates, collects static files and issues a one-time setup code.

4. Read the setup code out of the web container's log:

   ```bash
   docker compose logs web | grep -i "setup code"
   ```

   It looks like `K7QP-2M4T-9XWB-HR3F`. `docker compose exec web python
   manage.py setup_code` prints it again if it has scrolled away.

5. Open `https://your-domain/setup` and answer the wizard. Until you do, the
   whole site leads there: an instance with no administrator has nothing worth
   showing yet, so it shows the installer instead. The wizard asks for the
   administrator's details, the unit's name and contact address, the languages
   the site offers, the branches and sections (starting from Les Scouts' own),
   the shape of the scout year, and whether you use the fees, signing and
   agenda modules. It ends by sending a real test email, and does not finish
   until one arrives — a mail server that refuses is worth finding out about
   now rather than through parents who never heard anything.

   Prefer a terminal, or want to script it? `docker compose exec web python
   manage.py setup` does the same work from flags or an `answers.json`, and
   `--dry-run` shows what it would write. Both are described in
   `docs/dev/CONTRACT.md`.

6. Once the wizard finishes, the site is live. Log in with the account you
   created and fill in the rest under Site settings; branches and sections are
   edited in the Django admin. All of it lives in the database, not in `.env`.

If something is wrong, `manage.py check` names the variable and what to do
about it:

```bash
docker compose exec web python manage.py check
```

## Upgrading

Set `TC_VERSION` in `.env` to the release you want and recreate:

```bash
docker compose pull && docker compose up -d
```

Migrations run automatically, under a lock, so a rolling restart is safe.

## Backups

Two volumes matter: `db_data` (the database) and `media` (uploads). Two more
hold generated secrets: `app_secrets` (the Django secret key) and `db_secrets`
(the database password). Keep them, or every user is logged out and the
application can no longer authenticate to the database it already initialised.

They are separate so that the database container can read the password it was
initialised with and nothing else — it never gets the key that signs sessions.

Deleting `db_data` without deleting `db_secrets` leaves the stored password
pointing at a database that no longer has it. Delete both, or neither.

## Community-maintained deployment

`contrib/ansible/` contains one troop's Ansible automation for provisioning a
RHEL/AlmaLinux/Rocky host end to end, including a mail forwarder. It is
published as a starting point and is explicitly unsupported — read
[its README](contrib/ansible/README.md) before relying on it.
