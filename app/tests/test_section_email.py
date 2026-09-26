"""A section's own email address, and where it is set.

There is no staff page for sections: they are configured in the Django admin,
which is also the only place this address is edited. What it is *for* — the
``Reply-To`` on that section's messages — is covered by
``tests.test_messaging_compose.ComposeReplyToTest``.
"""

from django.test import TestCase
from django.urls import reverse

from members.models import Account, Person, Role, Section


class SectionEmailAdminTest(TestCase):
    """A superuser sets the address on the section's admin page."""

    def setUp(self):
        self.client.force_login(
            Account.objects.create_user(
                email="super@test.be",
                password="pass",
                is_staff=True,
                is_superuser=True,
                person=Person.objects.create(
                    first_name="Super", last_name="User",
                    primary_role=Role.objects.get(short="p"), status="a",
                ),
            )
        )
        self.section = Section.objects.create(name="Louveteaux")
        self.change_url = reverse(
            "admin:members_section_change", args=[self.section.pk]
        )

    def test_the_page_offers_the_field(self):
        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')

    def test_the_address_saves(self):
        response = self.client.post(
            self.change_url,
            {
                "name_fr": "Louveteaux",
                "name_nl": "Welpen",
                "name_en": "Cubs",
                "sex": "",
                "branch": "",
                "email": "meute@limal.be",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.section.refresh_from_db()
        self.assertEqual(self.section.email, "meute@limal.be")

    def test_a_section_without_an_address_is_fine(self):
        # The address is optional: most sections never get one, and the troop's
        # own reply-to address answers for those.
        self.assertEqual(Section.objects.create(name="Baladins").email, "")
