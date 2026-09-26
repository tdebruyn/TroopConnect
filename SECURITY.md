# Security Policy

TroopConnect handles personal data about children and their families, so
security reports are taken seriously and handled promptly.

## Reporting a vulnerability

Please report vulnerabilities through GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/tdebruyn/TroopConnect/security)
   of the repository.
2. Click **Report a vulnerability**.
3. Describe the issue, and include the steps or a proof of concept needed to
   reproduce it.

That form opens a private advisory visible only to the maintainers, so a report
is never exposed publicly while it is being fixed.

**Please do not open a public issue for a security problem**, and do not test
against a real troop's instance: the members listed there are real people.
Run your own instance from the instructions in the README if you need something
to test against.

## What to include

- The version or commit you tested.
- What an attacker can do, and what access they need to start.
- Reproduction steps, or a minimal proof of concept.
- Any suggested fix, if you have one.

## What to expect

- An acknowledgement within **7 days**.
- An assessment of the report and a planned fix within **30 days**.
- Credit in the advisory once a fix is released, unless you prefer to stay
  anonymous.

## Supported versions

Only the latest release on the `main` branch is supported. Fixes are not
backported to older tags; self-hosted instances are expected to update.

## Scope

In scope:

- The application code in this repository.
- The shipped container images and the default Docker Compose / Caddy setup.

Out of scope:

- Misconfiguration of a self-hosted instance (for example `DJANGO_DEBUG=1` on a
  public domain, or a weak `POSTGRES_PASSWORD`). Running
  `python manage.py check` reports the configuration problems we know about.
- Anything requiring an already-compromised server, database or SMTP account.
- Denial of service through traffic volume.
