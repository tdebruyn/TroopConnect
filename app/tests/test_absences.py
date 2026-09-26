"""Reporting a child absent from a future activity.

The feature has two readers with different rights, and most of what can go
wrong is a boundary between them: a parent must be able to report for their own
child and nobody else's, a leader must be able to read the whole section's
notices without being able to file one, and the email has to leave for the
section's own address. Those edges are what this module tests.
"""

from datetime import time, timedelta
from urllib.parse import urlencode

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from post_office.models import Email

from members.absences import section_recipients
from members.models import (
    Absence,
    Account,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
    TroopSettings,
)

from .mail import MailTestCase


def url(name, **params):
    """A named URL with query parameters, which is how these views are driven."""
    return f"{reverse(name)}?{urlencode(params)}"


class AbsenceTestBase(MailTestCase):
    """One section with a leader, a parent with a child in it, and an outsider.

    `MailTestCase` for the dummy mail backend and the template cache, and the
    settings row cleared on the way in and out because the module switch and
    the troop's own addresses are read on every request.
    """

    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.current()
        animateur_role = Role.objects.get(short="a")
        cls.child_role = Role.objects.get(short="e")

        cls.meute = Section.objects.create(name="Meute", email="meute@test.be")
        cls.troupe = Section.objects.create(name="Troupe")

        cls.leader = Person.objects.create(
            first_name="Lou",
            last_name="Meute",
            primary_role=animateur_role,
            status="a",
        )
        cls.parent = Person.objects.create(
            first_name="Paul",
            last_name="Parent",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.other_parent = Person.objects.create(
            first_name="Olga",
            last_name="Other",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        # Both read every section's agenda without leading one, which is the
        # state most troop staff are in: a unit admin is not enrolled in the
        # section, and a site staff member need not hold a role at all.
        cls.unit_admin = Person.objects.create(
            first_name="Ada",
            last_name="Responsable",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.unit_admin.roles.add(Role.objects.get(short="ar"))
        cls.staff = Person.objects.create(
            first_name="Sam",
            last_name="Staff",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.child = Person.objects.create(
            first_name="Chloe",
            last_name="Child",
            primary_role=cls.child_role,
            status="a",
            birthday=timezone.localdate() - timedelta(days=365 * 10),
            sex="F",
        )
        cls.other_child = Person.objects.create(
            first_name="Oscar",
            last_name="Other",
            primary_role=cls.child_role,
            status="a",
            birthday=timezone.localdate() - timedelta(days=365 * 10),
            sex="M",
        )

        ParentChild.objects.create(parent=cls.parent, child=cls.child)
        ParentChild.objects.create(parent=cls.other_parent, child=cls.other_child)

        for person, section in (
            (cls.leader, cls.meute),
            (cls.child, cls.meute),
            (cls.other_child, cls.meute),
        ):
            Enrollment.objects.create(user=person, section=section, school_year=cls.year)

        for person, email in (
            (cls.leader, "leader@test.be"),
            (cls.parent, "parent@test.be"),
            (cls.other_parent, "other@test.be"),
            (cls.child, "child@test.be"),
            (cls.other_child, "otherchild@test.be"),
            (cls.unit_admin, "unitadmin@test.be"),
        ):
            Account.objects.create_user(email=email, password="testpass", person=person)
        Account.objects.create_user(
            email="staff@test.be",
            password="testpass",
            person=cls.staff,
            is_staff=True,
        )

        cls.today = timezone.localdate()
        cls.event = SectionEvent.objects.create(
            title="Grand jeu",
            section=cls.meute,
            start_date=cls.today + timedelta(days=3),
            start_time=time(14, 0),
            end_time=time(17, 0),
        )
        cls.past_event = SectionEvent.objects.create(
            title="Sortie d'octobre",
            section=cls.meute,
            start_date=cls.today - timedelta(days=2),
        )

    def setUp(self):
        super().setUp()
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)

    def login(self, email):
        self.assertTrue(self.client.login(email=email, password="testpass"))

    def report(self, child, reason="Chez le médecin", event=None):
        return self.client.post(
            reverse("members:absence_report", args=[(event or self.event).pk]),
            {"child": child.pk, "reason": reason},
        )

    def latest_email(self):
        return Email.objects.latest("created")


class AbsenceModelTest(AbsenceTestBase):
    def test_a_child_is_reported_once_per_activity(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        with self.assertRaises(IntegrityError):
            # The constraint, not the form: this is the admin/shell path.
            with transaction.atomic():
                Absence.objects.create(
                    event=self.event, child=self.child, reason="Malade encore"
                )

    def test_an_activity_is_past_only_after_its_last_day(self):
        weekend = SectionEvent.objects.create(
            title="Week-end",
            section=self.meute,
            activity_type=SectionEvent.ActivityType.WEEKEND,
            start_date=self.today - timedelta(days=1),
            end_date=self.today + timedelta(days=1),
        )
        self.assertFalse(weekend.is_past)
        self.assertTrue(self.past_event.is_past)

    def test_deleting_the_activity_takes_its_notices_with_it(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.event.delete()
        self.assertFalse(Absence.objects.exists())


class SectionRecipientsTest(AbsenceTestBase):
    def test_the_section_address_wins(self):
        self.assertEqual(section_recipients(self.meute), ["meute@test.be"])

    def test_an_empty_section_address_falls_back_to_the_troop(self):
        settings_row = TroopSettings.get_settings()
        settings_row.reply_to_email = "unite@test.be"
        settings_row.save()
        self.assertEqual(section_recipients(self.troupe), ["unite@test.be"])

    def test_no_address_anywhere_means_nobody_to_tell(self):
        settings_row = TroopSettings.get_settings()
        settings_row.reply_to_email = ""
        settings_row.save()
        self.assertEqual(section_recipients(self.troupe), [])


class ReportAbsenceTest(AbsenceTestBase):
    def test_a_parent_reports_their_child(self):
        self.login("parent@test.be")
        response = self.report(self.child)
        self.assertEqual(response.status_code, 302)
        absence = Absence.objects.get()
        self.assertEqual(absence.child, self.child)
        self.assertEqual(absence.event, self.event)
        self.assertEqual(absence.reason, "Chez le médecin")
        self.assertEqual(absence.reported_by, self.parent)

    def test_the_notice_is_emailed_to_the_section(self):
        self.login("parent@test.be")
        self.report(self.child)
        email = self.latest_email()
        self.assertEqual(email.to, ["meute@test.be"])
        self.assertEqual(email.template.name, "absence_reported")
        self.assertIn("Chloe Child", email.subject)
        self.assertIn("Grand jeu", email.subject)
        self.assertIn("Chez le médecin", email.message)

    def test_the_notice_still_lands_when_no_address_is_configured(self):
        settings_row = TroopSettings.get_settings()
        settings_row.reply_to_email = ""
        settings_row.save()
        Section.objects.filter(pk=self.meute.pk).update(email="")
        self.login("parent@test.be")
        self.report(self.child)
        self.assertTrue(Absence.objects.exists())
        self.assertFalse(Email.objects.exists())

    def test_reporting_again_corrects_the_notice_in_place(self):
        self.login("parent@test.be")
        self.report(self.child, reason="Chez le médecin")
        self.report(self.child, reason="Finalement au hockey")
        self.assertEqual(Absence.objects.count(), 1)
        self.assertEqual(Absence.objects.get().reason, "Finalement au hockey")

    def test_a_reason_is_required(self):
        self.login("parent@test.be")
        response = self.report(self.child, reason="   ")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Absence.objects.exists())

    def test_a_parent_cannot_report_for_another_family_s_child(self):
        self.login("parent@test.be")
        self.report(self.other_child)
        self.assertFalse(Absence.objects.exists())

    def test_a_leader_does_not_report_absences(self):
        """Reporting is a family's act; a leader reads, and clears, notices."""
        self.login("leader@test.be")
        response = self.client.get(
            reverse("members:absence_report", args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_a_past_activity_cannot_be_reported(self):
        self.login("parent@test.be")
        response = self.client.get(
            reverse("members:absence_report", args=[self.past_event.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_form_offers_only_the_reporter_s_children(self):
        self.login("parent@test.be")
        response = self.client.get(
            reverse("members:absence_report", args=[self.event.pk])
        )
        self.assertContains(response, "Chloe Child")
        self.assertNotContains(response, "Oscar Other")


class WithdrawAbsenceTest(AbsenceTestBase):
    def setUp(self):
        super().setUp()
        self.absence = Absence.objects.create(
            event=self.event, child=self.child, reason="Malade", reported_by=self.parent
        )

    def test_the_family_withdraws_its_own_notice(self):
        self.login("parent@test.be")
        response = self.client.post(
            reverse("members:absence_cancel", args=[self.absence.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Absence.objects.exists())

    def test_a_leader_withdraws_a_notice_their_section_carries(self):
        self.login("leader@test.be")
        self.client.post(reverse("members:absence_cancel", args=[self.absence.pk]))
        self.assertFalse(Absence.objects.exists())

    def test_another_family_cannot_withdraw_it(self):
        self.login("other@test.be")
        response = self.client.post(
            reverse("members:absence_cancel", args=[self.absence.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Absence.objects.exists())


class DayViewTest(AbsenceTestBase):
    """Who the day frame tells about a reported absence."""

    def day_url(self):
        return url(
            "members:agenda_day", section=self.meute.pk, date=self.event.start_date
        )

    def test_a_leader_sees_the_notice(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.login("leader@test.be")
        response = self.client.get(self.day_url())
        self.assertContains(response, "Chloe Child")
        self.assertContains(response, "Malade")

    def test_a_unit_admin_sees_the_notices_of_a_section_they_do_not_lead(self):
        """Staff read every section's agenda, so they see who is missing."""
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.login("unitadmin@test.be")
        response = self.client.get(self.day_url())
        self.assertContains(response, "Chloe Child")
        self.assertContains(response, "Malade")

    def test_site_staff_see_the_notices_of_a_section_they_do_not_lead(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.login("staff@test.be")
        self.assertContains(self.client.get(self.day_url()), "Chloe Child")

    def test_reading_the_list_does_not_allow_reporting_or_withdrawing(self):
        """Seeing every notice is reading; a family's act stays a family's."""
        absence = Absence.objects.create(
            event=self.event, child=self.child, reason="Malade"
        )
        self.login("unitadmin@test.be")
        self.assertNotContains(
            self.client.get(self.day_url()), self.report_link()
        )
        response = self.client.post(
            reverse("members:absence_cancel", args=[absence.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Absence.objects.exists())

    def test_the_reporting_family_sees_its_own_notice(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.login("parent@test.be")
        self.assertContains(self.client.get(self.day_url()), "Chloe Child")

    def test_another_family_does_not_see_it(self):
        Absence.objects.create(event=self.event, child=self.child, reason="Malade")
        self.login("other@test.be")
        self.assertNotContains(self.client.get(self.day_url()), "Chloe Child")

    def report_link(self):
        """The report button's URL, which is what these tests are about.

        Asserting on the URL rather than on the button's label keeps them
        correct in every language the site is read in.
        """
        return reverse("members:absence_report", args=[self.event.pk])

    def test_the_report_button_is_offered_to_a_parent(self):
        self.login("parent@test.be")
        self.assertContains(self.client.get(self.day_url()), self.report_link())

    def test_the_report_button_is_not_offered_to_a_leader(self):
        self.login("leader@test.be")
        self.assertNotContains(self.client.get(self.day_url()), self.report_link())

    def test_the_report_button_is_not_offered_for_a_past_activity(self):
        self.login("parent@test.be")
        response = self.client.get(
            url(
                "members:agenda_day",
                section=self.meute.pk,
                date=self.past_event.start_date,
            )
        )
        self.assertNotContains(
            response, reverse("members:absence_report", args=[self.past_event.pk])
        )


class AbsenceModuleSwitchTest(AbsenceTestBase):
    """The absence screens belong to the agenda module, and go away with it."""

    def test_the_report_screen_404s_while_the_agenda_is_off(self):
        settings_row = TroopSettings.get_settings()
        settings_row.agenda_enabled = False
        settings_row.save()
        self.login("parent@test.be")
        response = self.client.get(
            reverse("members:absence_report", args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 404)
