# Ansible deployment (community-maintained, unsupported)

**This is not the supported way to install TroopConnect.** For that, see
[INSTALL.md](../../INSTALL.md) — the whole installation is `compose.yml` plus a
`.env`.

What lives here is one troop's automation for provisioning a RHEL/AlmaLinux/
Rocky VPS end to end: the `infra` role (Docker, firewall, `shared_net`), the
`mailforwarder` role (a Postfix forwarding container for the troop's own
domain), and the `troopconnect` role (the application stack).

It is published because it may be a useful starting point, not because it is
supported. It is maintained on a best-effort basis, it makes assumptions about
the host, and it may lag behind changes to the application — it was written
against the pre-`compose.yml` layout and has not been re-verified since.
Issues about it may be closed without a fix.

If you want to use it anyway:

1. `cp config.yml-example config.yml`, then run `python create-config.py` to
   fill in the non-secret values and the secrets in `clear-vault.yml` (which it
   encrypts into `vault.yml`).
2. `cp inventory.ini.example inventory.ini` and point it at your host.
3. `ansible-playbook -i inventory.ini playbook.yml`

The playbook writes the collected values to `.env` in the project directory as
uppercase variables (`site_domain` becomes `SITE_DOMAIN`) and then starts the
stack.

Known drift from the current layout:

- Keys in `vault.yml` were renamed: `db_password` → `postgres_password`,
  `db_user` → `postgres_user`, `letsencrypt_contact_email` → `acme_email`.

Anyone relying on this is welcome to send a pull request bringing it up to
date.
