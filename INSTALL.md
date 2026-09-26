# Installing TroopConnect

## Option A — Docker Compose (any VPS with Docker)

1. Point an A/AAAA record for your chosen domain at the server. Ports 80 and
   443 must be reachable, because Caddy obtains the TLS certificate for it.
2. Install Docker and the Compose plugin.
3. Get the repository onto the server.
4. Copy `.env.example` to `.env` and fill in the four required values:

   | Variable | What to put there |
   | --- | --- |
   | `SITE_DOMAIN` | the domain from step 1, e.g. `troop.example.org` |
   | `EMAIL_URL` | your SMTP provider, e.g. `smtp+tls://user:pass@mail.example.org:587` |
   | `DEFAULT_FROM_EMAIL` | the address your troop's mail is sent from |
   | `ACME_EMAIL` | your address, for Let's Encrypt expiry warnings |

   `.env.example` documents every other variable; none of them need setting to
   get a working instance.
5. Start it:

   ```bash
   docker compose -f docker-compose-prod.yml up -d --build
   ```

6. Create the first administrator:

   ```bash
   docker compose -f docker-compose-prod.yml exec troopconnect python manage.py createsuperuser
   ```

   Log in, then fill in the unit's own details (name, contact address,
   registration window) under Site settings in the admin. Those live in the
   database, not in `.env`.

If something is wrong, `python manage.py check` names the variable and what to
do about it:

```bash
docker compose -f docker-compose-prod.yml exec troopconnect python manage.py check
```

## Option B — Ansible (RHEL / AlmaLinux / Rocky Linux)

Provisions the VPS, the mail forwarder and the application together.

1. Get a VPS with Red Hat Enterprise Linux, AlmaLinux or Rocky Linux.
2. Create an A DNS record (with your registrar) and a PTR record (with your VPS
   provider, who can also be your DNS registrar).
3. Create a user with sudo access and configure password-less SSH.
4. Download this repo on your local computer.
5. Rename `deploy/ansible/config.yml-example` to `config.yml` and run
   `python deploy/ansible/create-config.py` to fill in its values. It prompts
   for the non-secret keys (`site_domain`, `acme_email`, `default_from_email`,
   `email_url`, ...) and then for the secrets in `clear-vault.yml`, which it
   encrypts into `vault.yml`.
6. Rename `inventory.ini.example` to `inventory.ini` and update the values.
7. Run the playbook:

   ```bash
   ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/playbook.yml
   ```

   It writes the collected values to `.env` in the project directory and starts
   the stack from `docker-compose-prod.yml`.
8. Put the content of
   `/var/lib/docker/volumes/troopconnect_dkim/_data/yourdomain/default.txt` as a
   TXT record in DNS (check the DKIM guide).
