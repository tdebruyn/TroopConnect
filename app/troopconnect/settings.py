from pathlib import Path
import json
from django.core.exceptions import ImproperlyConfigured
from celery.schedules import crontab
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.1/howto/deployment/checklist/

secret_settings = json.load(open(BASE_DIR / "troopconnect/.settings.json"))


def sec(setting, mysettings=secret_settings):
    try:
        return mysettings[setting]
    except KeyError:
        error_msg = "Set the {0} environment variable".format(setting)
        raise ImproperlyConfigured(error_msg)


SECRET_KEY = sec("SECRET_KEY")
AWS_ACCESS_KEY_ID = sec("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = sec("AWS_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = sec("AWS_SES_REGION_NAME")
AWS_SES_REGION_ENDPOINT = sec("AWS_SES_REGION_ENDPOINT")
DEFAULT_FROM_EMAIL = sec("DEFAULT_FROM_EMAIL")
ALIAS_EMAIL = sec("ALIAS_EMAIL")
CONTACT_EMAIL = sec("CONTACT_EMAIL")
EMAIL_HOST_PASSWORD = sec("EMAIL_HOST_PASSWORD")
DEBUG = sec("DEBUG")


# Set allowed hosts based on environment
if DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
else:
    ALLOWED_HOSTS = ["troop.tomctl.be"]

# Application definition

INSTALLED_APPS = [
    "members.apps.MembersConfig",
    "homepage.apps.HomepageConfig",
    "fontawesomefree",
    "simple_history",
    "django.contrib.admin",
    "django_ses",
    "widget_tweaks",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.facebook",
    "allauth.socialaccount.providers.google",
    "phonenumber_field",
    "post_office",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "debug_toolbar",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

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
            ],
        },
    },
]

WSGI_APPLICATION = "troopconnect.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "troopconnect",
        "USER": "dbuser",
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": "troopconnect-postgres-1",
        "PORT": "5432",
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
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = "fr-be"

TIME_ZONE = "Europe/Brussels"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

if DEBUG:
    # Development settings
    STATICFILES_DIRS = [
        BASE_DIR / "static",
    ]
    MEDIA_ROOT = BASE_DIR / "media"
else:
    # Production settings - use paths within the container that the app user can write to
    STATIC_ROOT = (
        BASE_DIR / "staticfiles"
    )  # Changed from /static to a directory within the app
    MEDIA_ROOT = (
        BASE_DIR / "mediafiles"
    )  # Changed from /media to a directory within the app
    DEBUG = True

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INTERNAL_IPS = [
    "127.0.0.1",
]

AUTH_USER_MODEL = "members.Account"

USE_SES_V2 = True
EMAIL_BACKEND = "post_office.EmailBackend"
POST_OFFICE = {
    "BACKENDS": {
        "default": "django_ses.SESBackend",
    },
    "DEFAULT_PRIORITY": "now",
    "CELERY_ENABLED": True,
}


AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

SITE_ID = 2

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_FORMS = {"signup": "members.forms.CustomSignupForm"}

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": True,
    }
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

CELERY_broker_url = "redis://troopconnect-redis-1:6379/0"
result_backend = "redis://troopconnect-redis-1:6379/0"
accept_content = ["application/json"]
result_serializer = "json"
task_serializer = "json"
result_backend = "django-db"
timezone = "Europe/Brussels"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_STATE_DB = "/tmp/celery-worker-state.db"


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://troopconnect-redis-1:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
