"""TroopConnect settings.

Everything deployment-specific is read from the environment, so a troop can
self-host an instance by filling in a ``.env`` file and never editing a shipped
file. The full list of variables, with examples, lives in ``docs/dev/CONTRACT.md``.

Parsing happens here; validation happens in ``troopconnect/checks.py`` so that
``manage.py check`` is the single place an operator sees what is wrong.
"""

from pathlib import Path

from celery.schedules import crontab

from troopconnect.env import (
    DEFAULT_SECRET_KEY_PATH,
    env,
    env_bool,
    env_int,
    load_secret_key,
    parse_database_url,
    parse_email_url,
    record_problem,
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Required configuration
#
# These four have no sensible default for somebody else's troop, so
# troopconnect.checks refuses to start production without them. See
# .env.example for a copy-paste starting point.
# ---------------------------------------------------------------------------

# Bare hostname this instance is served from, e.g. "troop.example.org".
SITE_DOMAIN = env("SITE_DOMAIN")

# Where outgoing mail goes. Schemes: console://, smtp://, smtp+tls://, smtp+ssl://.
EMAIL_URL = env("EMAIL_URL")

# Address troop mail is sent from.
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

# Let's Encrypt contact address. Read by the Caddy container, not by Django;
# Django only insists it is set so a deployment cannot forget it.
ACME_EMAIL = env("ACME_EMAIL")

# ---------------------------------------------------------------------------
# Core toggles
# ---------------------------------------------------------------------------

# Debug is opt-in. It defaults off so a forgotten variable fails safe rather
# than serving Django's debug pages (source code, settings, SQL) to the world.
DEBUG = env_bool("DJANGO_DEBUG")

# SECRET_KEY: an explicit environment variable wins; otherwise a key is read
# from (or created in) the secrets volume so it survives container recreation.
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY, _secret_key_problem = load_secret_key(
        env("SECRET_KEY_FILE", DEFAULT_SECRET_KEY_PATH)
    )
    if _secret_key_problem:
        record_problem("SECRET_KEY", _secret_key_problem)

# django.contrib.sites: the row allauth and get_current() read. Fresh installs
# get row 1 from migrate; instances migrated from the old .settings.json may
# still be on row 2 and can keep it by setting SITE_ID=2.
SITE_ID = env_int("SITE_ID", 1)

ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = []
if SITE_DOMAIN:
    ALLOWED_HOSTS = [SITE_DOMAIN, f"www.{SITE_DOMAIN}"]
    CSRF_TRUSTED_ORIGINS = [
        f"https://{SITE_DOMAIN}",
        f"https://www.{SITE_DOMAIN}",
    ]
if DEBUG:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1", "[::1]", "testserver"]
    CSRF_TRUSTED_ORIGINS += [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
    ]

# Application definition

INSTALLED_APPS = [
    "modeltranslation",
    "attestations.apps.AttestationsConfig",
    "finance.apps.FinanceConfig",
    "messaging.apps.MessagingConfig",
    "members.apps.MembersConfig",
    "homepage.apps.HomepageConfig",
    "fontawesomefree",
    "simple_history",
    "django.contrib.admin",
    "widget_tweaks",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.postgres",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "phonenumber_field",
    "post_office",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "members.middleware.AvailableLanguagesMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "members.middleware.OnboardingMiddleware",
]

# django-debug-toolbar exposes SQL, settings and source. Never in production.
if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

ROOT_URLCONF = "troopconnect.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "members.context_processors.contact_info",
                "members.context_processors.nav_sections",
                "messaging.context_processors.is_animateur",
                "members.context_processors.mail_queue_status",
            ],
        },
    },
]

WSGI_APPLICATION = "troopconnect.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases
#
# Set DATABASE_URL to describe the whole connection in one variable, or use the
# individual POSTGRES_* variables. PostgreSQL only: the project relies on
# ArrayField and django.contrib.postgres.

_database = {}
DATABASE_URL = env("DATABASE_URL")
if DATABASE_URL:
    try:
        _database = parse_database_url(DATABASE_URL)
    except ValueError as exc:
        record_problem("DATABASE_URL", str(exc))

DATABASES = {
    "default": {
        "ENGINE": _database.get("ENGINE", "django.db.backends.postgresql"),
        "NAME": _database.get("NAME", env("POSTGRES_DB", "troopconnect")),
        "USER": _database.get("USER", env("POSTGRES_USER", "troopconnect")),
        "PASSWORD": _database.get("PASSWORD", env("POSTGRES_PASSWORD", "")),
        "HOST": _database.get("HOST", env("POSTGRES_HOST", "postgres")),
        "PORT": _database.get("PORT", env("POSTGRES_PORT", "5432")),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 0),
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "fr"

LANGUAGES = [
    ("fr", "Français"),
    ("nl", "Nederlands"),
    ("en", "English"),
]

# Translation catalogs (fr/nl/en). Generated via `manage.py makemessages`.
LOCALE_PATHS = [BASE_DIR / "locale"]

# django-modeltranslation — keep in sync with LANGUAGES. Untranslated DB
# values fall back to French (MODELTRANSLATION_FALLBACK_LANGUAGES).
MODELTRANSLATION_LANGUAGES = ("fr", "nl", "en")
MODELTRANSLATION_DEFAULT_LANGUAGE = "fr"
MODELTRANSLATION_FALLBACK_LANGUAGES = ("fr",)

TIME_ZONE = env("TIME_ZONE", "Europe/Brussels")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "mediafiles"

if DEBUG:
    STATICFILES_DIRS = [
        BASE_DIR / "static",
    ]

# Serve user-uploaded media through Django rather than letting the reverse
# proxy serve the media volume directly. Defaults to on in dev and off in
# production (where Caddy's handle_path /media/* does the job).
SERVE_MEDIA_LOCALLY = env_bool("SERVE_MEDIA_LOCALLY", DEBUG)

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INTERNAL_IPS = ["127.0.0.1"]

AUTH_USER_MODEL = "members.Account"

# ---------------------------------------------------------------------------
# Outgoing mail
#
# EMAIL_URL (parsed above) decides where mail goes. MAIL_SEND_MODE can override
# the post-office backend explicitly:
#   mailersend (or the legacy "real") -> MailerSend HTTP API
#   dummy                              -> records to django.core.mail.outbox
#   anything else                      -> whatever EMAIL_URL selected
# ---------------------------------------------------------------------------

_email = {}
if EMAIL_URL:
    try:
        _email = parse_email_url(EMAIL_URL)
    except ValueError as exc:
        record_problem("EMAIL_URL", str(exc))

EMAIL_BACKEND = _email.get(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = _email.get("EMAIL_HOST", "localhost")
EMAIL_PORT = _email.get("EMAIL_PORT", 25)
EMAIL_HOST_USER = _email.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _email.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _email.get("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = _email.get("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = _email.get("EMAIL_TIMEOUT", None)

MAILERSEND_API_KEY = env("MAILERSEND_API_KEY", "")

MAIL_SEND_MODE = env("MAIL_SEND_MODE")
if not MAIL_SEND_MODE:
    # Keeping an API key in the environment is the opt-in: unchanged behaviour
    # for the instance that has been using MailerSend, and a working SMTP or
    # console setup for everybody else.
    MAIL_SEND_MODE = "mailersend" if MAILERSEND_API_KEY else "email_url"

if MAIL_SEND_MODE in ("mailersend", "real"):
    _default_mail_backend = "troopconnect.mailersend_backend.MailerSendBackend"
elif MAIL_SEND_MODE == "dummy":
    _default_mail_backend = "troopconnect.dummy_backend.DummyEmailBackend"
else:
    _default_mail_backend = EMAIL_BACKEND

POST_OFFICE = {
    "BACKENDS": {
        "default": _default_mail_backend,
    },
    # Queue emails (status "queued") instead of dispatching synchronously;
    # Celery flushes them (immediate on queue, plus the 5-minute beat backstop).
    "DEFAULT_PRIORITY": "medium",
    # Retry a failed send a few times before marking it "failed" and warning.
    "MAX_RETRIES": 3,
    "CELERY_ENABLED": True,
}


AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = "members.adapters.SocialAccountAdapter"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_FORMS = {"signup": "members.forms.CustomSignupForm"}

# ---------------------------------------------------------------------------
# Social login
#
# A provider is only registered when its keys are present, so an instance that
# does not use Google (say) neither shows a Google button nor exposes a Google
# callback URL. The login/signup templates ask allauth for the configured
# providers rather than naming them.
# ---------------------------------------------------------------------------

SOCIALACCOUNT_PROVIDERS = {}

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    INSTALLED_APPS.append("allauth.socialaccount.providers.google")
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APP": {
            "client_id": GOOGLE_CLIENT_ID,
            "secret": GOOGLE_CLIENT_SECRET,
        },
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": True,
    }

FACEBOOK_APP_ID = env("FACEBOOK_APP_ID")
FACEBOOK_SECRET = env("FACEBOOK_SECRET")
if FACEBOOK_APP_ID and FACEBOOK_SECRET:
    INSTALLED_APPS.append("allauth.socialaccount.providers.facebook")
    SOCIALACCOUNT_PROVIDERS["facebook"] = {
        "APP": {
            "client_id": FACEBOOK_APP_ID,
            "secret": FACEBOOK_SECRET,
        },
        "SCOPE": ["email"],
        "FIELDS": ["email", "name"],
    }

LOGIN_REDIRECT_URL = "homepage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "post_office": {
            "format": "[%(levelname)s]%(asctime)s PID %(process)d: %(message)s",
            "datefmt": "%d-%m-%Y %H:%M:%S",
        },
    },
    "handlers": {
        "post_office": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "post_office",
        },
    },
    "loggers": {
        "post_office": {"handlers": ["post_office"], "level": "INFO"},
    },
}

# ---------------------------------------------------------------------------
# Redis: broker, result backend and cache all share one server by default.
# ---------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_STATE_DB = env("CELERY_WORKER_STATE_DB", "/tmp/celery-worker-state.db")
CELERY_BEAT_SCHEDULE = {
    "send-queued-mail": {
        "task": "send_queued_mail",
        "schedule": crontab(minute="*/5"),
    },
    "create-year-daily": {
        "task": "create_year_task",
        "schedule": crontab(hour=3, minute=0),
    },
    "run-passage-daily": {
        "task": "run_passage",
        # Daily (not yearly) so that if Celery/beat was down on the intended
        # trigger day (May 1), the passage runs at the next start instead of
        # being skipped for a whole year. run_passage self-guards by date +
        # marker (SiteSettings.last_passage_school_year), so it only actually
        # promotes children once per target school year.
        "schedule": crontab(hour=3, minute=30),
    },
    "cleanup-old-events-daily": {
        "task": "cleanup_old_events",
        "schedule": crontab(hour=4, minute=0),
    },
    "cleanup-old-messages-daily": {
        "task": "cleanup_old_messages",
        "schedule": crontab(hour=4, minute=30),
    },
    "cleanup-orphaned-attachments-daily": {
        "task": "cleanup_orphaned_attachments",
        "schedule": crontab(hour=4, minute=45),
    },
}


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("CACHE_URL", REDIS_URL),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# ---------------------------------------------------------------------------
# Optional integrations
# ---------------------------------------------------------------------------

# Error reporting. Needs the sentry-sdk package; checks report it if missing.
SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    try:
        import sentry_sdk
    except ImportError:
        record_problem(
            "SENTRY_DSN",
            "SENTRY_DSN is set but the sentry-sdk package is not installed. "
            "Install it (pip install sentry-sdk) or unset SENTRY_DSN.",
        )
    else:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=env("SENTRY_ENVIRONMENT", "production"),
            release=env("SENTRY_RELEASE"),
            # Troops handle children's data; do not ship it to a third party
            # by default.
            send_default_pii=False,
        )

# Reserved: an outbound check for newer releases. Off by default so an instance
# never phones home unless its operator asks it to.
UPDATE_CHECK = env_bool("UPDATE_CHECK", False)
UPDATE_CHECK_URL = env(
    "UPDATE_CHECK_URL",
    "https://api.github.com/repos/tdebruyn/TroopConnect/releases/latest",
)
