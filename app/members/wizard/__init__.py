"""The first-run wizard's gate: when it is open, and the code that opens it.

Two questions, and everything else in the wizard depends on them:

* **Is this instance set up?** — :func:`setup_complete`, which is exactly "an
  administrator exists". That is the condition the requirement names, and it
  is the honest one: an instance with no superuser is an instance nobody can
  administer.
* **Was this deployment armed for setup?** — :func:`wizard_armed`, which is
  "a setup code has been issued". The code is generated once, on the first
  boot of a fresh instance (``app/entrypoint.sh`` runs ``manage.py
  setup_code``), printed to the web container's logs and kept in the secrets
  volume next to the secret key.

Both are needed. An instance that has an administrator never shows the
wizard, however it was booted; and an instance that was never armed — every
test run, and any deployment that skipped the entrypoint — is left alone
rather than redirected wholesale. That second half is what keeps the wizard
from being a thing every other part of the application has to know about.

The code is a *gate*, not a password: it says "whoever is reading the
container logs is the person setting this instance up". It is compared in
constant time and the comparison is rate-limited per address, because a
16-character code in front of a superuser-creating wizard is worth guessing
at only if guessing is free.
"""

import hmac
import logging
import secrets
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: The alphabet a code is drawn from: no 0/O, 1/I/L, so a code read off a
#: container log and typed by hand cannot be transcribed wrongly.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

#: Codes are grouped in fours for the same reason: ``K7QP-2M4T-9XWB-HR3F``.
CODE_GROUPS = 4
CODE_GROUP_LENGTH = 4

#: How many wrong codes an address may offer before it is made to wait.
MAX_ATTEMPTS = 10
ATTEMPT_WINDOW = 15 * 60

ATTEMPT_CACHE_KEY = "members.wizard.code_attempts.{address}"


def setup_code_path():
    """Where the one-time code is kept."""
    return Path(settings.SETUP_CODE_FILE)


def read_setup_code():
    """The stored code, or ``""`` when this deployment never issued one."""
    try:
        return setup_code_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def generate_setup_code():
    """A fresh code, formatted for reading off a screen."""
    groups = [
        "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP_LENGTH))
        for _ in range(CODE_GROUPS)
    ]
    return "-".join(groups)


def ensure_setup_code():
    """The stored code, generating and storing one if there is none.

    Called by ``manage.py setup_code``, which is what the container entrypoint
    runs and what an operator runs by hand. Nothing on the request path calls
    it: a wizard is opened by the deployment that armed it, not by a request
    that happened to arrive.
    """
    existing = read_setup_code()
    if existing:
        return existing

    code = generate_setup_code()
    path = setup_code_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError as exc:
        # The code still works for this boot -- the command prints it -- but a
        # restart issues a different one, which is worth saying out loud.
        logger.warning(
            "Could not write the setup code to %s (%s). This code is good for "
            "this boot only.",
            path,
            exc.strerror,
        )
    return code


def forget_setup_code():
    """Remove the stored code, so the wizard is no longer armed."""
    try:
        setup_code_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not remove %s (%s)", setup_code_path(), exc.strerror)


def wizard_armed():
    """Whether a setup code has been issued for this deployment."""
    return bool(read_setup_code())


def setup_complete():
    """Whether this instance has an administrator.

    One ``EXISTS`` over a table a scout unit keeps in the hundreds, asked on
    every request. It is deliberately not cached: a cache of "this instance is
    set up" outliving the row it was built from is a failure this project has
    already been bitten by twice (see ``CONTRACT.md`` §2a), and the query is
    cheaper than the ceremony that keeps a cache honest.
    """
    from members.models import Account

    return Account.objects.filter(is_superuser=True).exists()


def setup_required():
    """Whether the wizard is what this instance should be showing."""
    if setup_complete():
        return False
    return wizard_armed()


def normalise_code(candidate):
    """A typed code, reduced to what the alphabet could have produced."""
    return "".join(character for character in (candidate or "").upper() if character.isalnum())


def code_matches(candidate):
    """Whether ``candidate`` is the issued code, compared in constant time."""
    stored = read_setup_code()
    if not stored:
        return False
    return hmac.compare_digest(normalise_code(candidate), normalise_code(stored))


def client_address(request):
    """The address a rate limit is counted against.

    ``REMOTE_ADDR``, and deliberately not ``X-Forwarded-For``: behind Caddy
    that header is rewritten by the proxy, but anywhere else a client sets it
    itself, and a rate limit a header can reset is not a rate limit. The
    consequence in production is that every request shares the proxy's
    address, so the limit is effectively one for the whole instance — which
    for a code guarding a superuser-creating wizard is the safe direction to
    be wrong in.
    """
    return request.META.get("REMOTE_ADDR") or "unknown"


def attempts_left(address):
    """How many more wrong codes ``address`` may offer, and the wait if none.

    Returns ``(allowed, seconds_to_wait)``.
    """
    key = ATTEMPT_CACHE_KEY.format(address=address)
    used = cache.get(key, 0)
    if used < MAX_ATTEMPTS:
        return True, 0
    return False, cache.ttl(key) or ATTEMPT_WINDOW


def record_failed_attempt(address):
    """Count one wrong code against ``address``."""
    key = ATTEMPT_CACHE_KEY.format(address=address)
    if cache.add(key, 1, ATTEMPT_WINDOW):
        return
    try:
        cache.incr(key)
    except ValueError:
        # The entry expired between the read and the increment; the next
        # attempt starts a fresh window, which is the same as having waited.
        cache.set(key, 1, ATTEMPT_WINDOW)


def clear_attempts(address):
    """Forget the wrong codes ``address`` has offered."""
    cache.delete(ATTEMPT_CACHE_KEY.format(address=address))
