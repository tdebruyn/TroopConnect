"""Environment-variable parsing for TroopConnect's settings module.

Every deployment-specific value comes from the environment so that a troop can
self-host without editing shipped files. See ``docs/dev/CONTRACT.md`` for the
full list of variables.

Parsing never raises at import time: a bad value is recorded in :data:`PROBLEMS`
and the settings module keeps a placeholder so the app can still boot far
enough for ``troopconnect.checks`` to report one plain-language line per
problem. That is what makes ``manage.py check`` the single place an operator
sees configuration errors.
"""

import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# Where the SECRET_KEY is persisted when the operator does not supply one.
# Mounted as a volume in production so the key survives container recreation;
# see compose.yml.
DEFAULT_SECRET_KEY_PATH = Path("/data/secrets/secret_key")

# Emails are the only thing Django can be asked to send through, and a scout
# unit's outgoing mail is plain SMTP or nothing at all. ``console`` exists so
# a first run works before any mail provider is configured.
SUPPORTED_EMAIL_SCHEMES = ("console", "smtp", "smtp+tls", "smtp+ssl")

SUPPORTED_DATABASE_SCHEMES = ("postgres", "postgresql")


class ConfigProblem:
    """A single unusable environment variable, reported by ``manage.py check``."""

    def __init__(self, variable, message):
        self.variable = variable
        self.message = message

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"ConfigProblem({self.variable!r}, {self.message!r})"


# Populated as the settings module reads the environment. Consumed by checks.py.
PROBLEMS = []


def record_problem(variable, message):
    """Record a configuration problem for the system check to report."""
    PROBLEMS.append(ConfigProblem(variable, message))


def get_problems():
    """Return the configuration problems recorded so far."""
    return list(PROBLEMS)


def reset_problems():
    """Clear recorded problems (used by tests)."""
    PROBLEMS.clear()


def env(name, default=None):
    """Return an environment variable, treating blank/whitespace as unset."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def env_bool(name, default=False):
    """Return a boolean environment variable, recording a problem if unusable."""
    value = env(name)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    record_problem(
        name,
        f"{name} must be a boolean (1/0, true/false, yes/no), but it is set to "
        f"'{value}'.",
    )
    return default


def env_int(name, default):
    """Return an integer environment variable, recording a problem if unusable."""
    value = env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        record_problem(
            name, f"{name} must be a whole number, but it is set to '{value}'."
        )
        return default


def read_file_secret(variable, default=""):
    """Return ``VAR``, or the contents of the file ``VAR_FILE`` points at.

    This is the ``VAR`` / ``VAR_FILE`` convention the official PostgreSQL image
    uses, so the same variables work on both sides of the connection.

    A file that is configured but unreadable is recorded as a problem rather
    than silently becoming an empty value: the fallback would otherwise only
    surface later, as a confusing authentication failure.
    """
    value = env(variable)
    if value:
        return value

    path = env(f"{variable}_FILE")
    if not path:
        return default

    try:
        return Path(path).read_text().strip()
    except OSError as exc:
        record_problem(
            f"{variable}_FILE",
            f"{variable}_FILE points at {path}, which could not be read "
            f"({exc.strerror}). On a fresh install the init service creates it "
            f"at startup.",
        )
        return default


def parse_email_url(url):
    """Turn an EMAIL_URL into Django's EMAIL_* settings.

    Supported forms::

        console://                                   # print to stdout
        smtp://user:password@host:25                 # plain SMTP, STARTTLS off
        smtp+tls://user:password@host:587            # STARTTLS
        smtp+ssl://user:password@host:465            # implicit TLS

    The username and password must be URL-encoded when they contain ``@``,
    ``:`` or ``/``. Add ``?timeout=10`` to bound the connection attempt.
    """
    parsed = urlparse(url)

    if not parsed.scheme:
        raise ValueError(
            "EMAIL_URL must start with a scheme, for example "
            "smtp+tls://user:password@mail.example.org:587."
        )

    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_EMAIL_SCHEMES:
        supported = ", ".join(f"{s}://" for s in SUPPORTED_EMAIL_SCHEMES)
        raise ValueError(
            f"EMAIL_URL uses the unsupported scheme '{parsed.scheme}://'. "
            f"Supported schemes are: {supported}."
        )

    if scheme == "console":
        return {"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"}

    if not parsed.hostname:
        raise ValueError(
            f"EMAIL_URL is missing a mail server host, for example "
            f"{scheme}://user:password@mail.example.org:587."
        )

    use_tls = scheme == "smtp+tls"
    use_ssl = scheme == "smtp+ssl"
    default_port = 587 if use_tls else 465 if use_ssl else 25

    query = parse_qs(parsed.query)
    timeout = None
    if "timeout" in query:
        try:
            timeout = int(query["timeout"][0])
        except ValueError as exc:
            raise ValueError(
                f"EMAIL_URL's timeout must be a whole number of seconds, but it "
                f"is set to '{query['timeout'][0]}'."
            ) from exc

    return {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": parsed.hostname,
        "EMAIL_PORT": parsed.port or default_port,
        "EMAIL_HOST_USER": unquote(parsed.username) if parsed.username else "",
        "EMAIL_HOST_PASSWORD": unquote(parsed.password) if parsed.password else "",
        "EMAIL_USE_TLS": use_tls,
        "EMAIL_USE_SSL": use_ssl,
        "EMAIL_TIMEOUT": timeout,
    }


def parse_database_url(url):
    """Turn a DATABASE_URL into Django's DATABASES['default'] dict.

    Only the PostgreSQL schemes are accepted: the project relies on PostgreSQL
    (``ArrayField``, ``django.contrib.postgres``) and cannot run on anything
    else.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme not in SUPPORTED_DATABASE_SCHEMES:
        supported = ", ".join(f"{s}://" for s in SUPPORTED_DATABASE_SCHEMES)
        raise ValueError(
            f"DATABASE_URL uses the unsupported scheme '{parsed.scheme}://'. "
            f"TroopConnect needs PostgreSQL; supported schemes are: {supported}."
        )

    if not parsed.hostname:
        raise ValueError(
            "DATABASE_URL is missing a host, for example "
            "postgres://user:password@postgres:5432/troopconnect."
        )

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (parsed.path or "").lstrip("/") or "troopconnect",
        "USER": unquote(parsed.username) if parsed.username else "",
        "PASSWORD": unquote(parsed.password) if parsed.password else "",
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
    }


def load_secret_key(path=DEFAULT_SECRET_KEY_PATH):
    """Return a ``(secret_key, problem)`` pair.

    An operator-supplied ``SECRET_KEY`` always wins -- that is the caller's
    job. This reads (or creates) the on-disk key used when none is set, so a
    fresh container comes up with a stable key that survives restarts. The
    ``problem`` is a message when the key had to be generated in memory (no
    writable path), which loses every session on restart.
    """
    path = Path(path)

    try:
        existing = path.read_text().strip()
    except FileNotFoundError:
        existing = ""
    except OSError as exc:
        return secrets.token_urlsafe(64), (
            f"Could not read the SECRET_KEY file at {path} ({exc.strerror})."
        )

    if existing:
        return existing, None

    generated = secrets.token_urlsafe(64)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated + "\n")
        path.chmod(0o600)
    except OSError as exc:
        return generated, (
            f"Could not create the SECRET_KEY file at {path} "
            f"({exc.strerror}). A throwaway key was generated in memory, so "
            "every user will be logged out whenever the app restarts."
        )

    return generated, None
