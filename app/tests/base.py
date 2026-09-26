"""Shared test bases.

``django.test.TestCase`` rolls the database back after each test, but a rollback
does not undo a write to the cache — and both the troop settings row and
post_office's templates live in the shared Redis. An entry written by one test
is still readable by the next, which then sees a row that has been rolled back
out from under it. ``tests.mail`` works around that for post_office; the base
here does it for :class:`members.models.TroopSettings`.
"""

from django.test import TestCase

from members.models import TroopSettings


class TroopSettingsTestCase(TestCase):
    """A TestCase that cannot leak the cached settings row into the next test.

    Use it for any test that changes ``TroopSettings``, and for any test that
    asserts on a value some other test might have changed.
    """

    def setUp(self):
        super().setUp()
        # Clear on the way in *and* out: on the way in because a test that ran
        # earlier may have left its version cached, and on the way out because
        # this test's own reads have just re-cached whatever it did.
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)
