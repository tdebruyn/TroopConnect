"""A parent writing to a section's communications lead or the unit team.

The feature joins two rights models: a parent may write, but only to the people
resolved from their own children; and a section's communications lead is a role
whose section comes from the holder's enrolment. The fallbacks matter as much
as the happy path — a section with no communications lead goes to all of its
leaders, and a section with no leader goes to the unit lead and the site
administrators.
"""

from django.urls import reverse
from post_office.models import Email

from members.contacts import contact_targets
from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
    TroopSettings,
)
from members.permissions import can_contact_leaders

from .mail import MailTestCase


class ContactTestBase(MailTestCase):
    """One staffed section, one unstaffed section, a unit lead and site staff."""

    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.current()

        cls.meute = Section.objects.create(name="Meute")
        cls.troupe = Section.objects.create(name="Troupe")
        cls.other_section = Section.objects.create(name="Pionniers")

        cls.leader = Person.objects.create(
            first_name="Lou",
            last_name="Meute",
            primary_role=Role.objects.get(short="a"),
            status="a",
        )
        PersonRole.objects.create(
            person=cls.leader, role=Role.objects.get(short="rc")
        )
        cls.second_leader = Person.objects.create(
            first_name="Bas",
            last_name="Meute",
            primary_role=Role.objects.get(short="a"),
            status="a",
        )
        cls.parent = Person.objects.create(
            first_name="Paul",
            last_name="Parent",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.unit_lead = Person.objects.create(
            first_name="Ada",
            last_name="Lead",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        PersonRole.objects.create(
            person=cls.unit_lead, role=Role.objects.get(short="ar")
        )
        cls.staff = Person.objects.create(
            first_name="Sam",
            last_name="Staff",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.treasurer = Person.objects.create(
            first_name="Tess",
            last_name="Treasurer",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        PersonRole.objects.create(
            person=cls.treasurer, role=Role.objects.get(short="t")
        )
        cls.other_parent = Person.objects.create(
            first_name="Olga",
            last_name="Other",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )

        cls.child = Person.objects.create(
            first_name="Chloe",
            last_name="Child",
            primary_role=Role.objects.get(short="e"),
            status="a",
        )
        cls.second_child = Person.objects.create(
            first_name="Brie",
            last_name="Parent",
            primary_role=Role.objects.get(short="e"),
            status="a",
        )
        cls.other_child = Person.objects.create(
            first_name="Oscar",
            last_name="Other",
            primary_role=Role.objects.get(short="e"),
            status="a",
        )
        ParentChild.objects.create(parent=cls.parent, child=cls.child)
        ParentChild.objects.create(parent=cls.parent, child=cls.second_child)
        ParentChild.objects.create(parent=cls.other_parent, child=cls.other_child)

        for person, section in (
            (cls.leader, cls.meute),
            (cls.second_leader, cls.meute),
            (cls.child, cls.meute),
            (cls.second_child, cls.troupe),
            (cls.other_child, cls.other_section),
        ):
            Enrollment.objects.create(
                user=person, section=section, school_year=cls.year
            )

        for person, email, language in (
            (cls.leader, "leader@test.be", "fr"),
            (cls.second_leader, "second@test.be", "fr"),
            (cls.parent, "parent@test.be", "fr"),
            (cls.unit_lead, "lead@test.be", "fr"),
        ):
            Account.objects.create_user(
                email=email,
                password="testpass",
                person=person,
                preferred_language=language,
            )
        Account.objects.create_user(
            email="staff@test.be",
            password="testpass",
            person=cls.staff,
            is_staff=True,
        )
        Account.objects.create_user(
            email="tres@test.be",
            password="testpass",
            person=cls.treasurer,
        )
        Account.objects.create_user(
            email="other@test.be",
            password="testpass",
            person=cls.other_parent,
        )

    def setUp(self):
        super().setUp()
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)

    def login(self, email="parent@test.be"):
        self.assertTrue(self.client.login(email=email, password="testpass"))

    def credentials(self, **overrides):
        data = {
            "recipient": f"section:{self.meute.pk}",
            "title": "Question about Saturday",
            "body": "Will the hike start at the usual place?",
        }
        data.update(overrides)
        return data

    def sent_to(self, address):
        return [email for email in Email.objects.all() if email.to == [address]]


class ContactTargetsTest(ContactTestBase):
    def test_the_section_lead_is_the_default_and_the_unit_is_the_last_choice(self):
        targets = contact_targets(self.parent_account())
        self.assertEqual(targets[0].key, f"section:{self.meute.pk}")
        self.assertEqual(
            [recipient.email for recipient in targets[0].recipients],
            ["leader@test.be"],
        )
        unit = next(target for target in targets if target.key == "unit")
        self.assertEqual(
            [recipient.email for recipient in unit.recipients],
            ["lead@test.be"],
        )

    def test_the_treasurer_is_a_target_of_their_own(self):
        target = next(
            target
            for target in contact_targets(self.parent_account())
            if target.key == "treasurer"
        )
        self.assertEqual(
            [recipient.email for recipient in target.recipients],
            ["tres@test.be"],
        )

    def parent_account(self):
        return Account.objects.get(email="parent@test.be")

    def test_another_family_s_section_is_not_offered(self):
        keys = {target.key for target in contact_targets(self.parent_account())}
        self.assertNotIn(f"section:{self.other_section.pk}", keys)

    def test_a_section_without_a_lead_goes_to_all_its_leaders(self):
        PersonRole.objects.filter(
            person=self.leader, role__short="rc"
        ).delete()
        target = contact_targets(self.parent_account())[0]
        self.assertTrue(target.missing_communication)
        self.assertEqual(
            {recipient.email for recipient in target.recipients},
            {"leader@test.be", "second@test.be"},
        )

    def test_a_section_without_a_leader_goes_to_the_unit_lead_and_staff(self):
        target = next(
            target
            for target in contact_targets(self.parent_account())
            if target.key == f"section:{self.troupe.pk}"
        )
        self.assertTrue(target.missing_communication)
        self.assertEqual(
            {recipient.email for recipient in target.recipients},
            {"lead@test.be", "staff@test.be"},
        )

    def test_without_a_unit_lead_the_site_administrator_receives_it(self):
        PersonRole.objects.filter(
            person=self.unit_lead, role__short="ar"
        ).delete()
        target = next(
            target
            for target in contact_targets(self.parent_account())
            if target.key == f"section:{self.troupe.pk}"
        )
        self.assertEqual(
            [recipient.email for recipient in target.recipients],
            ["staff@test.be"],
        )

    def test_a_non_parent_is_not_allowed_to_contact_leaders(self):
        leader = Account.objects.get(email="leader@test.be")
        self.assertFalse(can_contact_leaders(leader))
        self.assertTrue(can_contact_leaders(self.parent_account()))


class ContactViewTest(ContactTestBase):
    def test_a_parent_gets_the_form(self):
        self.login()
        response = self.client.get(reverse("members:contact_leaders"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lou Meute")
        self.assertContains(response, "Ada Lead")

    def test_the_form_explains_where_an_unstaffed_section_goes(self):
        self.login()
        response = self.client.get(reverse("members:contact_leaders"))
        self.assertContains(response, "pas encore de responsable communication")
        self.assertContains(response, "administrateur du site")

    def test_a_leader_does_not_get_the_form(self):
        self.login("leader@test.be")
        response = self.client.get(reverse("members:contact_leaders"))
        self.assertEqual(response.status_code, 404)

    def test_the_message_reaches_the_section_lead_and_copies_the_parent(self):
        self.login()
        response = self.client.post(
            reverse("members:contact_leaders"), self.credentials()
        )
        self.assertEqual(
            response.url, reverse("members:contact_leaders_sent")
        )

        message = self.sent_to("leader@test.be")[0]
        # No seeded mail template: the parent's title is the subject and their
        # words are the body, with only the wrapper composed here.
        self.assertIsNone(message.template)
        self.assertEqual(message.subject, "Question about Saturday")
        self.assertIn("Will the hike start", message.message)
        self.assertIn("Paul Parent", message.message)
        self.assertIn("parent@test.be", message.message)
        self.assertIn("Chloe Child", message.message)
        self.assertIn("Meute", message.message)
        self.assertEqual(message.headers["Reply-To"], "parent@test.be")

        # The communications lead is the target; the section's other leader
        # is not written to while the role is filled.
        self.assertEqual(self.sent_to("second@test.be"), [])

        copy = self.sent_to("parent@test.be")[0]
        self.assertIn("Copie de votre message – Question about Saturday", copy.subject)
        self.assertIn("Lou Meute", copy.message)
        self.assertIn("Une réponse vous parviendra par e-mail", copy.message)

    def test_the_copy_speaks_the_parent_s_language(self):
        account = Account.objects.get(email="parent@test.be")
        account.preferred_language = "nl"
        account.save()
        self.login()
        self.client.post(reverse("members:contact_leaders"), self.credentials())
        copy = self.sent_to("parent@test.be")[0]
        self.assertIn("Kopie van uw bericht", copy.subject)
        self.assertIn("Een antwoord komt per e-mail", copy.message)

    def test_a_section_without_a_lead_goes_to_all_its_leaders(self):
        PersonRole.objects.filter(
            person=self.leader, role__short="rc"
        ).delete()
        self.login()
        self.client.post(reverse("members:contact_leaders"), self.credentials())

        self.assertEqual(len(self.sent_to("leader@test.be")), 1)
        self.assertEqual(len(self.sent_to("second@test.be")), 1)
        self.assertEqual(self.sent_to("lead@test.be"), [])
        self.assertEqual(self.sent_to("staff@test.be"), [])
        self.assertEqual(len(self.sent_to("parent@test.be")), 1)

    def test_a_section_without_a_leader_goes_to_the_unit_lead_and_staff(self):
        self.login()
        self.client.post(
            reverse("members:contact_leaders"),
            self.credentials(
                recipient=f"section:{self.troupe.pk}",
                title="Question about the Troupe",
            ),
        )

        self.assertEqual(len(self.sent_to("lead@test.be")), 1)
        self.assertEqual(len(self.sent_to("staff@test.be")), 1)
        self.assertEqual(len(self.sent_to("parent@test.be")), 1)
        self.assertEqual(self.sent_to("leader@test.be"), [])
        self.assertIn("Brie Parent", self.sent_to("lead@test.be")[0].message)

    def test_the_balance_link_preselects_the_treasurer(self):
        self.login()
        response = self.client.get(
            f"{reverse('members:contact_leaders')}?to=treasurer"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["recipient"].value(), "treasurer"
        )

        self.client.post(
            reverse("members:contact_leaders"),
            self.credentials(recipient="treasurer", title="About the fee"),
        )
        self.assertEqual(len(self.sent_to("tres@test.be")), 1)
        self.assertIn("About the fee", self.sent_to("tres@test.be")[0].subject)
        self.assertEqual(self.sent_to("lead@test.be"), [])

    def test_the_balance_tile_opens_the_form_in_the_dialog(self):
        self.login()
        response = self.client.get(
            f"{reverse('members:contact_leaders')}?to=treasurer",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="modal-content"')
        self.assertContains(response, "Tess Treasurer")
        self.assertNotContains(response, "<!DOCTYPE html>")
        self.assertEqual(
            response.context["form"]["recipient"].value(), "treasurer"
        )

    def test_sending_from_the_dialog_toasts_and_closes_it(self):
        self.login()
        response = self.client.post(
            reverse("members:contact_leaders"),
            self.credentials(recipient="treasurer", title="About the fee"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertIn("showMessage", response.headers["HX-Trigger"])
        self.assertEqual(len(self.sent_to("tres@test.be")), 1)
        self.assertEqual(len(self.sent_to("parent@test.be")), 1)

    def test_a_title_with_a_line_break_is_refused(self):
        self.login()
        response = self.client.post(
            reverse("members:contact_leaders"),
            self.credentials(title="Question\nBcc: someone@test.be"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())

    def test_a_crafted_recipient_key_is_refused(self):
        self.login()
        response = self.client.post(
            reverse("members:contact_leaders"),
            self.credentials(recipient=f"section:{self.other_section.pk}"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Email.objects.exists())

    def test_the_confirmation_page_promises_an_email_answer(self):
        self.login()
        response = self.client.get(reverse("members:contact_leaders_sent"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Votre message a bien été envoyé. Une réponse vous parviendra "
            "par e-mail.",
        )
        self.assertContains(response, reverse("members:contact_leaders"))
        self.assertContains(response, reverse("homepage"))


class ContactToolTest(ContactTestBase):
    def test_the_board_offers_the_tool_to_a_parent(self):
        self.login()
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, reverse("members:contact_leaders"))

    def test_the_board_does_not_offer_it_to_a_leader(self):
        self.login("leader@test.be")
        response = self.client.get(reverse("homepage"))
        self.assertNotContains(response, reverse("members:contact_leaders"))
