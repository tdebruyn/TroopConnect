"""The TroopSettings calendar helpers.

Every school-year, age-reference, passage and retention date the application
computes is derived from these helpers. They are therefore tested against the
calendars a troop may actually configure — a September or a January year start,
an August age reference day — and not only against the shipped defaults.
"""

from datetime import date, datetime, timedelta
from unittest import mock

from django.utils import timezone

from members.models import (
    ARCHIVE_WARNING_DAYS,
    Person,
    Role,
    SchoolYear,
    TroopSettings,
)

from .base import TroopSettingsTestCase


class CalendarTestBase(TroopSettingsTestCase):
    """Helpers are pure settings arithmetic; each test sets its own calendar."""

    # A year the seed migration does not already own (SchoolYear.name is unique).
    YEAR = 2099

    def configure(self, **fields):
        """Write calendar fields, returning the reloaded (uncached) row."""
        troop = TroopSettings.get_settings()
        for field, value in fields.items():
            setattr(troop, field, value)
        troop.save(update_fields=list(fields))
        return TroopSettings.get_settings()

    def person(self, birthday):
        return Person.objects.create(
            first_name="Age",
            last_name="Test",
            primary_role=Role.objects.get(short="p"),
            birthday=birthday,
        )

    def aware(self, year, month, day):
        return timezone.make_aware(datetime(year, month, day, 0, 0))


class SchoolYearForTest(CalendarTestBase):
    """``school_year_for`` answers for a date no SchoolYear row covers."""

    def test_default_calendar_boundary(self):
        troop = TroopSettings.get_settings()  # 1 August by default
        self.assertEqual(troop.school_year_for(date(2026, 7, 31)), 2025)
        self.assertEqual(troop.school_year_for(date(2026, 8, 1)), 2026)
        self.assertEqual(troop.school_year_for(date(2027, 1, 1)), 2026)
        self.assertEqual(troop.school_year_for(date(2027, 7, 31)), 2026)

    def test_september_start(self):
        troop = self.configure(year_start_month=9, year_start_day=1)
        self.assertEqual(troop.school_year_for(date(2026, 8, 31)), 2025)
        self.assertEqual(troop.school_year_for(date(2026, 9, 1)), 2026)
        self.assertEqual(troop.school_year_for(date(2027, 8, 31)), 2026)

    def test_january_start(self):
        troop = self.configure(year_start_month=1, year_start_day=1)
        self.assertEqual(troop.school_year_for(date(2026, 12, 31)), 2026)
        self.assertEqual(troop.school_year_for(date(2027, 1, 1)), 2027)

    def test_a_leap_day_start_still_answers(self):
        # A 29 February year start is not a real day every year: the helper
        # falls back to 1 March rather than raising.
        troop = self.configure(year_start_month=2, year_start_day=29)
        self.assertEqual(troop.school_year_for(date(2027, 2, 28)), 2026)
        self.assertEqual(troop.school_year_for(date(2027, 3, 1)), 2027)


class SchoolYearBoundsTest(CalendarTestBase):
    def test_default_bounds(self):
        troop = TroopSettings.get_settings()
        self.assertEqual(
            troop.school_year_bounds(2026),
            (date(2026, 8, 1), date(2027, 7, 31)),
        )

    def test_september_start_bounds(self):
        troop = self.configure(year_start_month=9, year_start_day=1)
        self.assertEqual(
            troop.school_year_bounds(2026),
            (date(2026, 9, 1), date(2027, 8, 31)),
        )

    def test_january_start_bounds_are_the_calendar_year(self):
        troop = self.configure(year_start_month=1, year_start_day=1)
        self.assertEqual(
            troop.school_year_bounds(2027),
            (date(2027, 1, 1), date(2027, 12, 31)),
        )

    def test_a_year_is_twelve_months_long(self):
        troop = self.configure(year_start_month=2, year_start_day=29)
        start, end = troop.school_year_bounds(2024)
        self.assertEqual(start, date(2024, 2, 29))
        # The next year has no 29 February, so the year ends a day early.
        self.assertEqual(end, date(2025, 2, 28))

    def test_bounds_match_the_rows_create_year_writes(self):
        troop = self.configure(year_start_month=9, year_start_day=1)
        SchoolYear.objects.all().delete()
        year = SchoolYear.objects.create_year(2027)
        self.assertEqual((year.start_date, year.end_date), troop.school_year_bounds(2027))
        self.assertEqual(year.range, "2027-2028")


class AgeReferenceDateTest(CalendarTestBase):
    """The reference day is the one *inside* the school year."""

    def test_default_reference_is_december_of_the_start_year(self):
        troop = TroopSettings.get_settings()
        year = SchoolYear.objects.create_year(self.YEAR)
        self.assertEqual(troop.age_reference_date(year), date(2099, 12, 31))
        # A bare year name works too.
        self.assertEqual(troop.age_reference_date(self.YEAR), date(2099, 12, 31))

    def test_september_start_keeps_december_inside_the_year(self):
        troop = self.configure(year_start_month=9, year_start_day=1)
        start, end = troop.school_year_bounds(2026)
        reference = troop.age_reference_date(2026)
        self.assertEqual(reference, date(2026, 12, 31))
        self.assertTrue(start <= reference <= end)

    def test_january_start_keeps_december_inside_the_year(self):
        troop = self.configure(year_start_month=1, year_start_day=1)
        start, end = troop.school_year_bounds(2027)
        reference = troop.age_reference_date(2027)
        self.assertEqual(reference, date(2027, 12, 31))
        self.assertTrue(start <= reference <= end)

    def test_a_september_start_still_takes_the_age_on_31_december(self):
        """The day is the federation's, not a troop setting: a September year
        still measures every child on 31 December inside that year."""
        troop = self.configure(year_start_month=9, year_start_day=1)
        self.assertEqual(troop.age_reference_date(2026), date(2026, 12, 31))

    def test_a_january_start_still_takes_the_age_on_31_december(self):
        troop = self.configure(year_start_month=1, year_start_day=1)
        self.assertEqual(troop.age_reference_date(2027), date(2027, 12, 31))


class AgeAtReferenceTest(CalendarTestBase):
    def test_default_age(self):
        troop = TroopSettings.get_settings()
        year = SchoolYear.objects.create_year(self.YEAR)
        self.assertEqual(
            troop.age_at_reference(self.person(date(2089, 6, 15)), year), 10
        )

    def test_birthday_on_the_reference_day_is_an_exact_year(self):
        troop = TroopSettings.get_settings()
        year = SchoolYear.objects.create_year(self.YEAR)
        self.assertEqual(
            troop.age_at_reference(self.person(date(2089, 12, 31)), year), 10
        )

    def test_a_september_start_does_not_change_the_age(self):
        """The reference day moves with the school year, not with the troop:
        a January child counts the same under either year boundary."""
        troop = self.configure(year_start_month=9, year_start_day=1)
        child = self.person(date(2017, 1, 15))
        self.assertEqual(troop.age_at_reference(child, 2026), 9)

    def test_accepts_a_year_name_as_well_as_a_row(self):
        troop = TroopSettings.get_settings()
        child = self.person(date(2016, 6, 15))
        self.assertEqual(troop.age_at_reference(child, 2026), 10)

    def test_no_birthday_is_none(self):
        troop = TroopSettings.get_settings()
        self.assertIsNone(troop.age_at_reference(self.person(None), 2026))

    def test_no_school_year_is_none(self):
        troop = TroopSettings.get_settings()
        with mock.patch.object(SchoolYear, "current", staticmethod(lambda: None)):
            self.assertIsNone(troop.age_at_reference(self.person(date(2016, 6, 15))))

    def test_falls_back_to_the_current_school_year(self):
        troop = TroopSettings.get_settings()
        child = self.person(date(2016, 6, 15))
        SchoolYear.objects.all().delete()
        SchoolYear.objects.create_year(2026)
        with mock.patch.object(
            SchoolYear, "current", staticmethod(lambda: SchoolYear.objects.get(name=2026))
        ):
            self.assertEqual(troop.age_at_reference(child), 10)


class PassageDatetimeTest(CalendarTestBase):
    def test_default_passage_day(self):
        troop = TroopSettings.get_settings()
        trigger = troop.passage_datetime(2026)
        self.assertEqual(trigger, self.aware(2026, 5, 1))
        self.assertTrue(timezone.is_aware(trigger))

    def test_the_passage_day_does_not_follow_the_year_start(self):
        """1 May is fixed; a January-starting year keeps that passage day in
        the start calendar year it prepares."""
        troop = self.configure(year_start_month=1, year_start_day=1)
        self.assertEqual(troop.passage_datetime(2026), self.aware(2026, 5, 1))

    def test_the_next_run_is_the_first_of_the_next_month(self):
        troop = TroopSettings.get_settings()
        self.assertEqual(
            troop.next_passage_datetime(on_date=date(2026, 9, 15)),
            self.aware(2026, 10, 1),
        )
        self.assertEqual(
            troop.next_passage_datetime(on_date=date(2026, 5, 15)),
            self.aware(2026, 6, 1),
        )

    def test_on_the_first_the_run_due_today_is_returned(self):
        """The page may be read before that day's run has happened."""
        troop = TroopSettings.get_settings()
        self.assertEqual(
            troop.next_passage_datetime(on_date=date(2026, 5, 1)),
            self.aware(2026, 5, 1),
        )

    def test_the_next_run_does_not_depend_on_the_school_year(self):
        """The passage runs every month, whatever the year's boundary is."""
        troop = self.configure(year_start_month=1, year_start_day=1)
        self.assertEqual(
            troop.next_passage_datetime(on_date=date(2027, 1, 15)),
            self.aware(2027, 2, 1),
        )

    def test_the_year_rolls_over_at_december(self):
        troop = TroopSettings.get_settings()
        self.assertEqual(
            troop.next_passage_datetime(on_date=date(2026, 12, 15)),
            self.aware(2027, 1, 1),
        )


class ArchiveRetentionTest(CalendarTestBase):
    def test_purge_date_default_retention(self):
        # The convention is retention years × 365 days, not calendar years, so
        # the purge day drifts by the leap days the span contains.
        troop = TroopSettings.get_settings()
        archived = date(2020, 1, 1)
        self.assertEqual(
            troop.archive_purge_date(archived) - archived, timedelta(days=5 * 365)
        )

    def test_purge_date_follows_the_configured_retention(self):
        troop = self.configure(archive_retention_years=3)
        archived = date(2020, 1, 1)
        self.assertEqual(
            troop.archive_purge_date(archived) - archived, timedelta(days=3 * 365)
        )

    def test_cutoffs_are_the_inverse_of_the_purge_date(self):
        troop = TroopSettings.get_settings()
        archived = date(2020, 1, 1)
        # Everyone archived on or before the cutoff is due on that day, and the
        # person archived exactly a retention period ago is the last of them.
        purge = troop.archive_purge_date(archived)
        self.assertEqual(troop.archive_purge_cutoff(purge), archived)

    def test_the_warning_goes_out_a_month_before_the_purge(self):
        troop = TroopSettings.get_settings()
        today = date(2030, 1, 1)
        self.assertEqual(ARCHIVE_WARNING_DAYS, 30)
        self.assertEqual(
            troop.archive_warning_cutoff(today),
            troop.archive_purge_cutoff(today) + timedelta(days=30),
        )

    def test_warning_and_purge_agree_on_one_date(self):
        """A person archived on the warning cutoff is purged exactly
        ARCHIVE_WARNING_DAYS later."""
        troop = TroopSettings.get_settings()
        today = date(2030, 1, 1)
        archived = troop.archive_warning_cutoff(today)
        self.assertEqual(
            troop.archive_purge_date(archived), today + timedelta(days=ARCHIVE_WARNING_DAYS)
        )
