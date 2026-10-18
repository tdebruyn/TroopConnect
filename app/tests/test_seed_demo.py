"""``manage.py seed_demo``: the demo troop, and the promises it makes.

Three of those are worth a test in their own right — the command refuses to run
outside development, it writes nothing on a second run, and it never mails
anybody. The rest pin the shape of what it writes: the children land in
sections that take their age, the agenda has a past and a future, and the two
families the treasurer has to chase are the two nobody paid for.
"""

import shutil
import tempfile
from datetime import timedelta
from io import StringIO

from allauth.account.models import EmailAddress
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from post_office.models import Email

from finance.models import (
    Household,
    HouseholdAdjustment,
    Payment,
    calculate_balances,
    get_adults_with_balance,
)
from members.models import (
    Account,
    Branch,
    Enrollment,
    ImportantDocument,
    Person,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)
from messaging.models import SectionMessage

from .base import TroopSettingsTestCase
from .mail import MailTestCase


class SeedDemoTestCase(MailTestCase):
    """The demo command, run into a database the migrations have just made.

    ``MailTestCase`` for the dummy backend and the queued-mail guard;
    the settings row is cleared on the way in and out because the command reads
    it and can write to it.
    """

    def setUp(self):
        super().setUp()
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)

        # The meute's message carries an attachment, and a test has no business
        # writing into the media the dev instance shares.
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def seed(self):
        call_command("seed_demo", force=True, stdout=StringIO())


class SeedDemoGuardTest(TroopSettingsTestCase):
    def test_it_refuses_to_seed_an_instance_that_is_not_in_debug(self):
        # The test runner turns DEBUG off, which is exactly the situation the
        # guard exists for: the members it writes are fake people.
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())

        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Section.objects.count(), 0)


class SeedDemoTest(SeedDemoTestCase):
    def test_it_writes_a_troop_and_not_a_handful_of_fixtures(self):
        self.seed()

        self.assertGreaterEqual(Person.objects.count(), 20)
        self.assertEqual(Section.objects.count(), 4)
        self.assertEqual(ImportantDocument.objects.count(), 4)

        # Every primary role a troop is made of, and the two states besides the
        # enrolled ones: somebody archived and a registration not yet validated.
        self.assertEqual(
            set(Person.objects.values_list("primary_role__short", flat=True)),
            {"a", "am", "e", "n", "p"},
        )
        self.assertEqual(Person.objects.filter(status="ar").count(), 1)
        self.assertEqual(Person.objects.filter(status="r").count(), 1)

    def test_every_child_is_enrolled_in_a_section_that_takes_their_age(self):
        self.seed()
        year = SchoolYear.current()

        for child in Person.objects.filter(primary_role__short="e", status="a"):
            with self.subTest(child=str(child)):
                enrollment = child.enrollment_set.filter(school_year=year).first()
                self.assertIsNotNone(enrollment)

                branch = enrollment.section.branch
                age = child.age_on_dec_31(year)
                self.assertGreaterEqual(age, branch.min_age_dec_31)
                self.assertLessEqual(age, branch.max_age_dec_31)

    def test_it_places_members_on_the_ladder_the_troop_already_has(self):
        # A unit with its own sections keeps them: the roster is placed by age,
        # so nothing is added beside a section that was chosen deliberately.
        branch = Branch.objects.create(
            name_fr="Meute Saint-Michel",
            min_age_dec_31=8,
            max_age_dec_31=12,
            is_top=True,
        )
        section = Section.objects.create(
            name_fr="Meute Saint-Michel", branch=branch, sex=Section.Sex.BOTH
        )

        self.seed()

        self.assertEqual(Section.objects.count(), 1)
        year = SchoolYear.current()
        self.assertGreater(
            Enrollment.objects.filter(section=section, school_year=year).count(), 0
        )

    def test_the_agenda_has_a_past_and_a_future(self):
        self.seed()
        today = timezone.localdate()

        self.assertTrue(SectionEvent.objects.filter(start_date__lt=today).exists())
        self.assertTrue(SectionEvent.objects.filter(start_date__gte=today).exists())
        # A week-end is one activity over two days, not two activities.
        self.assertTrue(SectionEvent.objects.filter(end_date__isnull=False).exists())

    def test_it_mails_nobody(self):
        self.seed()

        self.assertEqual(Email.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

        # Exactly one message is left unsent, and it has recipients — a message
        # with none would look unsent for the wrong reason. That is what the
        # history page reads as "composed, not sent".
        unsent = SectionMessage.objects.filter(
            recipients__sent_at__isnull=True
        ).distinct()
        self.assertEqual(unsent.count(), 1)
        self.assertGreater(unsent.get().recipients.count(), 0)

    def test_a_second_run_writes_nothing(self):
        self.seed()
        before = self._counts()

        self.seed()

        self.assertEqual(before, self._counts())

    def test_it_reads_this_databases_settings_and_not_a_cached_copy(self):
        # The cache key names no database, so a server pointed at another one
        # leaves a copy the command would otherwise be served. That row decides
        # both what is filled in here and the calendar the roster's ages are
        # turned into birthdays against — so a stale copy silently places the
        # whole demo on the wrong dates, or fills nothing at all.
        cache.set(
            TroopSettings.CACHE_KEY,
            TroopSettings(pk=1, name_fr="Un autre groupe", site_keywords="autre"),
            None,
        )

        self.seed()

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Scouts de Limal")
        self.assertEqual(troop.contact_email, "contact@demo.test")

    def test_it_leaves_the_settings_a_troop_already_chose(self):
        troop = TroopSettings.get_settings()
        troop.name_fr = "Groupe Notre-Dame"
        troop.contact_email = "chef@exemple.be"
        troop.save()

        self.seed()

        troop.refresh_from_db()
        self.assertEqual(troop.name_fr, "Groupe Notre-Dame")
        self.assertEqual(troop.contact_email, "chef@exemple.be")

    def test_the_logins_work(self):
        self.seed()

        account = Account.objects.get(email="nicolas.dubois@demo.test")
        self.assertTrue(account.check_password("Demo1234!"))
        # allauth refuses a login whose address is not verified, and there is no
        # inbox at the other end of a `.test` address to verify it from.
        self.assertTrue(
            EmailAddress.objects.get(user=account).verified
        )

    def test_the_treasurer_has_something_to_chase(self):
        self.seed()
        year = SchoolYear.current()

        chased = {row["person"].last_name for row in get_adults_with_balance(year)}
        self.assertEqual(chased, {"Simon", "Petit"})

        # The family left owing is the one the adjustment was written for.
        self.assertTrue(HouseholdAdjustment.objects.exists())
        self.assertTrue(Household.objects.filter(name="Famille Petit").exists())

        # Everybody else is settled, so a balance only ever means "left owing".
        owing = [
            row for row in calculate_balances(year) if row["balance"] > 0
        ]
        self.assertTrue(owing)
        self.assertTrue(all(row["is_late"] for row in owing))
        self.assertGreater(Payment.objects.count(), 0)

    def test_the_archived_member_is_old_enough_for_the_retention_task(self):
        self.seed()

        leaver = Person.objects.get(external_id="DEMO-paul-vandenberghe")
        self.assertEqual(leaver.status, "ar")
        self.assertLess(leaver.archived_date, timezone.localdate() - timedelta(days=365))

    def _counts(self):
        """Everything the command writes, in one comparable tuple."""
        return (
            Person.objects.count(),
            Account.objects.count(),
            Section.objects.count(),
            Enrollment.objects.count(),
            SectionEvent.objects.count(),
            SectionMessage.objects.count(),
            Payment.objects.count(),
            ImportantDocument.objects.count(),
            Household.objects.count(),
        )
