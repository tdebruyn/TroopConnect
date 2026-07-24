from datetime import date
from unittest import mock

from django.test import TestCase

from members.models import SchoolYear
from members.tasks import create_year_task


class CreateYearTaskTest(TestCase):
    """create_year_task keeps the current and next school years in sync with
    today's date. It must (a) compute the current year from the date, not the
    raw calendar year, (b) create the current year even when none exists, and
    (c) never delete a school year it (or anything else) created."""

    def _run_at(self, today):
        with mock.patch("members.tasks._today", return_value=today):
            create_year_task()

    def test_july_creates_correct_next_year_not_calendar_plus_one(self):
        """Regression: on 2026-07-23 the current school year is 2025-2026, so
        the next year must be 2026-2027 (name 2026), not 2027-2028 (name 2027)
        — the old ``datetime.now().year + 1`` code was off by one Jan–Jul."""
        SchoolYear.objects.all().delete()
        self._run_at(date(2026, 7, 23))

        # Before Aug 1 → current start year is last year.
        self.assertTrue(SchoolYear.objects.filter(name=2025).exists())  # current
        self.assertTrue(SchoolYear.objects.filter(name=2026).exists())  # next
        self.assertFalse(SchoolYear.objects.filter(name=2027).exists())

    def test_creates_current_year_when_missing(self):
        """With no school years at all, the task creates the current one too."""
        SchoolYear.objects.all().delete()
        self._run_at(date(2026, 7, 23))

        self.assertTrue(SchoolYear.objects.filter(name=2025).exists())  # current
        self.assertTrue(SchoolYear.objects.filter(name=2026).exists())  # next

    def test_after_august_current_year_is_calendar_year(self):
        """On/after Aug 1 the current school year starts this calendar year."""
        SchoolYear.objects.all().delete()
        self._run_at(date(2026, 9, 15))

        self.assertTrue(SchoolYear.objects.filter(name=2026).exists())  # current
        self.assertTrue(SchoolYear.objects.filter(name=2027).exists())  # next
        self.assertFalse(SchoolYear.objects.filter(name=2028).exists())

    def test_does_not_delete_existing_future_years(self):
        """A future school year created out of band must survive the task — the
        task is strictly additive and never deletes."""
        SchoolYear.objects.create(
            name=2099,
            start_date=date(2099, 8, 1),
            end_date=date(2100, 7, 31),
            range="2099-2100",
        )
        self._run_at(date(2026, 7, 23))

        self.assertTrue(SchoolYear.objects.filter(name=2099).exists())

    def test_is_idempotent(self):
        """Running twice does not duplicate or error (name is unique)."""
        SchoolYear.objects.all().delete()
        self._run_at(date(2026, 7, 23))
        self._run_at(date(2026, 7, 23))  # second run is a no-op

        self.assertEqual(SchoolYear.objects.filter(name=2025).count(), 1)
        self.assertEqual(SchoolYear.objects.filter(name=2026).count(), 1)


class CreateYearStartupHookTest(TestCase):
    """The worker_ready hook enqueues create_year_task on worker boot so a
    restart outside the 03:00 beat window still backfills missing years."""

    def test_worker_ready_enqueues_create_year(self):
        from troopconnect.celery import run_create_year_on_startup

        with mock.patch("members.tasks.create_year_task.delay") as delay:
            run_create_year_on_startup()
            delay.assert_called_once()
