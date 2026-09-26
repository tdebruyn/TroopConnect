"""The cache the test suite runs on, in place of Redis.

``settings.CACHES`` swaps this in under ``manage.py test``. Tests run as
``--parallel`` worker processes with a database each, but they would otherwise
share one Redis: a ``TestCase`` rolls its database back and cannot roll a cache
back, so a row one worker caches outlives the rollback that undid it and the
next worker reads a row that is no longer there. A cache per process removes
the sharing, and with it any need for the workers to agree.

It is ``LocMemCache`` plus the one method the application uses that only
django-redis provides: ``members.wizard`` asks the cache how much of its
rate-limit window is left, to tell someone who has run out of attempts how long
to wait.
"""

import time

from django.core.cache.backends.locmem import LocMemCache as DjangoLocMemCache


class LocMemCache(DjangoLocMemCache):
    def ttl(self, key, version=None):
        """Seconds until ``key`` expires, or ``None`` when there is no wait left.

        Gone, already expired, or written without a timeout all answer ``None``,
        which is what ``attempts_left`` reads as a full window. The expiry kept
        for every entry is enough to answer without tracking anything extra.
        """
        with self._lock:
            expires = self._expire_info.get(self.make_key(key, version=version))
            if expires is None or expires <= time.time():
                return None
            return int(expires - time.time())
