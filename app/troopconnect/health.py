"""Readiness endpoint for the reverse proxy and the container healthcheck.

Reports on the two services the application cannot serve without: the database
and the cache (Redis, which is also the Celery broker). Anything that only
degrades a feature -- an unreachable SMTP server, a full disk -- deliberately
does not appear here, because taking a working instance out of rotation for it
would be worse than the degradation.
"""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

CACHE_PROBE_KEY = "troopconnect:healthz"
CACHE_PROBE_VALUE = "ok"


def _database_ok():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return False
    return True


def _cache_ok():
    try:
        cache.set(CACHE_PROBE_KEY, CACHE_PROBE_VALUE, 10)
        return cache.get(CACHE_PROBE_KEY) == CACHE_PROBE_VALUE
    except Exception:
        return False


@require_GET
@never_cache
def healthz(request):
    """200 while every dependency answers, 503 the moment one does not."""
    checks = {"database": _database_ok(), "cache": _cache_ok()}

    # Only whether each dependency answered, never the error itself: this
    # endpoint is public.
    return JsonResponse(
        {name: ("ok" if ok else "error") for name, ok in checks.items()},
        status=200 if all(checks.values()) else 503,
    )
