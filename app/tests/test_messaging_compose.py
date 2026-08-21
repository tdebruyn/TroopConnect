from django.test import Client

from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
)
from messaging.models import SectionMessage
from tests.mail import MailTestCase


class ComposeRecipientAccumulationTest(MailTestCase):
    """Loading several recipient groups accumulates instead of replacing."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.current_year = SchoolYear.current()

        self.role_animateur = Role.objects.get(short="a")
        self.role_parent = Role.objects.get(short="p")
        self.role_ar = Role.objects.get(short="ar")

        self.section = Section.objects.create(name="Louveteaux")
        self.other_section = Section.objects.create(name="Baladins")

        # Staff sender (secondary role "ar") — may send to all groups/sections
        self.staff_person = Person.objects.create(
            first_name="Marie", last_name="Staff",
            primary_role=self.role_parent, status="a",
        )
        self.staff_person.roles.add(self.role_ar)
        Account.objects.create_user(
            email="staff@test.com", password="testpass", person=self.staff_person,
        )

        # Animateur enrolled in section (also a loadable recipient)
        self.anim_person = Person.objects.create(
            first_name="Jean", last_name="Anim",
            primary_role=self.role_animateur, status="a",
        )
        Account.objects.create_user(
            email="anim@test.com", password="testpass", person=self.anim_person,
        )
        Enrollment.objects.create(
            user=self.anim_person, section=self.section,
            school_year=self.current_year,
        )

        # Animateur enrolled in the other section
        self.other_anim_person = Person.objects.create(
            first_name="Luc", last_name="Autre",
            primary_role=self.role_animateur, status="a",
        )
        Account.objects.create_user(
            email="luc@test.com", password="testpass", person=self.other_anim_person,
        )
        Enrollment.objects.create(
            user=self.other_anim_person, section=self.other_section,
            school_year=self.current_year,
        )

        # Parent + child enrolled in section
        self.parent_person = Person.objects.create(
            first_name="Paul", last_name="Parent",
            primary_role=self.role_parent, status="a",
        )
        Account.objects.create_user(
            email="parent@test.com", password="testpass", person=self.parent_person,
        )
        self.child_person = Person.objects.create(
            first_name="Camille", last_name="Parent",
            primary_role=Role.objects.get(short="e"), status="a",
        )
        ParentChild.objects.create(parent=self.parent_person, child=self.child_person)
        Enrollment.objects.create(
            user=self.child_person, section=self.section,
            school_year=self.current_year,
        )

        self.client.login(email="staff@test.com", password="testpass")

    def _load(self, group, section_id=None, **extra_post):
        post = {"recipient_group": group, "hx_load_recipients": "1"}
        if section_id is not None:
            post["section"] = section_id
        post.update(extra_post)
        return self.client.post("/messaging/compose/", post)

    def test_first_load_returns_group_recipients(self):
        response = self._load("section_parents", self.section.pk)
        html = response.content.decode()
        self.assertIn(f'name="recipient_{self.parent_person.pk}"', html)
        self.assertNotIn(f'name="recipient_{self.anim_person.pk}"', html)
        self.assertNotIn(f'name="recipient_{self.child_person.pk}"', html)
        # Hidden token is rendered so the next load accumulates
        self.assertIn(f'value="section_parents:{self.section.pk}"', html)

    def test_second_load_merges_instead_of_replacing(self):
        first = self._load("section_parents", self.section.pk)
        self.assertIn(f'name="recipient_{self.parent_person.pk}"', first.content.decode())

        # Simulate the browser posting back hidden state from the first render
        second = self._load(
            "section_animateurs", self.section.pk,
            loaded_groups=f"section_parents:{self.section.pk}",
            known_recipients=str(self.parent_person.pk),
        )
        html = second.content.decode()
        # Combined: parents of section + animateurs of section
        self.assertIn(f'name="recipient_{self.parent_person.pk}"', html)
        self.assertIn(f'name="recipient_{self.anim_person.pk}"', html)
        # Both tokens now present in hidden state
        self.assertIn(f'value="section_parents:{self.section.pk}"', html)
        self.assertIn(f'value="section_animateurs:{self.section.pk}"', html)

    def test_deduplication_across_overlapping_groups(self):
        # section_all already contains the animateur; loading animateurs too must not duplicate
        response = self._load(
            "section_animateurs", self.section.pk,
            loaded_groups=f"section_all:{self.section.pk}",
            known_recipients=f"{self.parent_person.pk},{self.child_person.pk},{self.anim_person.pk}",
        )
        html = response.content.decode()
        self.assertEqual(html.count(f'name="recipient_{self.anim_person.pk}"'), 1)
        self.assertIn(f'name="recipient_{self.parent_person.pk}"', html)
        self.assertIn(f'name="recipient_{self.child_person.pk}"', html)

    def test_unchecked_state_survives_next_load(self):
        # Load parents, then load animateurs with the parent checkbox NOT posted
        # (i.e. user unchecked it) — parent must render unchecked
        response = self._load(
            "section_animateurs", self.section.pk,
            loaded_groups=f"section_parents:{self.section.pk}",
            known_recipients=str(self.parent_person.pk),
        )
        html = response.content.decode()
        self.assertRegex(
            html,
            rf'name="recipient_{self.parent_person.pk}"(?![^>]*\bchecked\b)',
        )
        # New rows default to checked
        self.assertRegex(
            html,
            rf'name="recipient_{self.anim_person.pk}"[^>]*\bchecked\b',
        )

    def test_send_after_two_loads_delivers_to_both_groups(self):
        post = {
            "recipient_group": "section_animateurs",
            "section": str(self.section.pk),
            "subject": "Test",
            "body": "Hello",
            "loaded_groups": [
                f"section_parents:{self.section.pk}",
                f"section_animateurs:{self.section.pk}",
            ],
            "known_recipients": f"{self.parent_person.pk},{self.anim_person.pk}",
            # Parent unchecked: checkbox absent; animateur checked
            f"recipient_{self.anim_person.pk}": "on",
        }
        response = self.client.post("/messaging/compose/", post)
        self.assertRedirects(response, "/messaging/history/")

        msg = SectionMessage.objects.get()
        recipient_pks = set(msg.recipients.values_list("parent__pk", flat=True))
        # Animateur (checked) was sent to; parent (unchecked) recorded as not sent
        self.assertIn(self.anim_person.pk, recipient_pks)
        self.assertIn(self.parent_person.pk, recipient_pks)
        sent_pks = set(
            msg.recipients.filter(sent_at__isnull=False).values_list("parent__pk", flat=True)
        )
        self.assertEqual(sent_pks, {self.anim_person.pk})

    def test_send_without_load_uses_dropdown_group(self):
        post = {
            "recipient_group": "section_animateurs",
            "section": str(self.section.pk),
            "subject": "Test",
            "body": "Hello",
            f"recipient_{self.anim_person.pk}": "on",
        }
        response = self.client.post("/messaging/compose/", post)
        self.assertRedirects(response, "/messaging/history/")
        msg = SectionMessage.objects.get()
        recipient_pks = set(msg.recipients.values_list("parent__pk", flat=True))
        self.assertEqual(recipient_pks, {self.anim_person.pk})

    def test_sender_excluded_from_recipients(self):
        # Staff loads "everyone": they must not appear in their own list
        response = self._load("everyone")
        html = response.content.decode()
        self.assertNotIn(f'name="recipient_{self.staff_person.pk}"', html)

    def test_locked_animateur_cannot_load_foreign_section(self):
        # Log in as the plain animateur (no staff role): section is forced to their own
        self.client.login(email="anim@test.com", password="testpass")
        response = self._load(
            "section_parents", self.other_section.pk,
            loaded_groups="",
        )
        html = response.content.decode()
        # Parents of THEIR section (Paul), not of the posted foreign section
        self.assertIn(f'name="recipient_{self.parent_person.pk}"', html)
        # Token records their own section, not the posted one
        self.assertIn(f'value="section_parents:{self.section.pk}"', html)
        self.assertNotIn(f'value="section_parents:{self.other_section.pk}"', html)


class ComposeEmptyGroupTest(MailTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.current_year = SchoolYear.current()
        self.role_ar = Role.objects.get(short="ar")
        self.role_parent = Role.objects.get(short="p")

        self.staff_person = Person.objects.create(
            first_name="Marie", last_name="Staff",
            primary_role=self.role_parent, status="a",
        )
        self.staff_person.roles.add(self.role_ar)
        Account.objects.create_user(
            email="staff@test.com", password="testpass", person=self.staff_person,
        )
        self.client.login(email="staff@test.com", password="testpass")

    def test_empty_group_renders_message_not_table(self):
        response = self.client.post(
            "/messaging/compose/",
            {"recipient_group": "active_parents", "hx_load_recipients": "1"},
        )
        html = response.content.decode()
        self.assertIn("Aucun destinataire trouvé.", html)
        self.assertNotIn('<table class="table table-striped">', html)
