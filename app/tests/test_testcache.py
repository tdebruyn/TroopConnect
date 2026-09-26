"""The cache the test suite runs on, ``troopconnect.testcache``."""

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase


class ProcessLocalCacheTest(SimpleTestCase):
    """Tests must not share a cache, or ``--parallel`` workers would share it."""

    def test_the_suite_runs_on_the_process_local_cache(self):
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "troopconnect.testcache.LocMemCache",
        )


class TtlTest(SimpleTestCase):
    """``ttl`` is what ``members.wizard`` asks for the rate-limit window."""

    KEY = "troopconnect.testcache.ttl"

    def setUp(self):
        super().setUp()
        self.addCleanup(cache.delete, self.KEY)

    def test_counts_down_from_the_timeout(self):
        cache.set(self.KEY, 1, 60)

        self.assertGreater(cache.ttl(self.KEY), 0)
        self.assertLessEqual(cache.ttl(self.KEY), 60)

    def test_a_key_that_is_not_there_has_no_ttl(self):
        self.assertIsNone(cache.ttl("troopconnect.testcache.absent"))

    def test_a_key_without_a_timeout_has_no_ttl(self):
        cache.set(self.KEY, 1, None)

        self.assertIsNone(cache.ttl(self.KEY))

    def test_an_expired_key_has_no_ttl(self):
        cache.set(self.KEY, 1, 0)

        self.assertIsNone(cache.ttl(self.KEY))
