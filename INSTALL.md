# Installing TroopConnect

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
   database, migrates and collects static files. Nothing else to do.

4. Create the first administrator:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

5. Log in, then fill in the unit's own details — name, contact address,
   registration window — under Site settings in the admin. Those live in the
   database, not in `.env`.

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
