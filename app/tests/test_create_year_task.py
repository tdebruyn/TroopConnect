from datetime import date
from unittest import mock

from django.test import TestCase

from members.models import SchoolYear, TroopSettings
from members.tasks import create_year_task

from .base import TroopSettingsTestCase


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


class CreateYearCustomYearStartTest(TroopSettingsTestCase):
    """The task and the rows it writes follow the troop's year start, which is
    configurable — August 1st is only the default."""

    def setUp(self):
        super().setUp()
        troop = TroopSettings.get_settings()
        troop.year_start_month, troop.year_start_day = 9, 1
        troop.save(update_fields=["year_start_month", "year_start_day"])
        SchoolYear.objects.all().delete()

    def test_mid_august_is_still_the_previous_school_year(self):
        # 15 Aug 2026 is before the 1 Sep 2026 boundary, so the current school
        # year is 2025-2026 and the next one is 2026-2027.
        with mock.patch("members.tasks._today", return_value=date(2026, 8, 15)):
            create_year_task()

        self.assertTrue(SchoolYear.objects.filter(name=2025).exists())
        self.assertTrue(SchoolYear.objects.filter(name=2026).exists())
        self.assertFalse(SchoolYear.objects.filter(name=2027).exists())

    def test_on_the_boundary_the_new_year_starts(self):
        with mock.patch("members.tasks._today", return_value=date(2026, 9, 1)):
            create_year_task()

        self.assertTrue(SchoolYear.objects.filter(name=2026).exists())
        self.assertTrue(SchoolYear.objects.filter(name=2027).exists())

    def test_created_rows_use_the_configured_bounds(self):
        with mock.patch("members.tasks._today", return_value=date(2026, 8, 15)):
            create_year_task()

        year = SchoolYear.objects.get(name=2025)
        self.assertEqual(year.start_date, date(2025, 9, 1))
        self.assertEqual(year.end_date, date(2026, 8, 31))


class CreateYearStartupHookTest(TestCase):
    """The worker_ready hook enqueues create_year_task on worker boot so a
    restart outside the 03:00 beat window still backfills missing years."""

    def test_worker_ready_enqueues_create_year(self):
        from troopconnect.celery import run_create_year_on_startup

        with mock.patch("members.tasks.create_year_task.delay") as delay:
            run_create_year_on_startup()
            delay.assert_called_once()
