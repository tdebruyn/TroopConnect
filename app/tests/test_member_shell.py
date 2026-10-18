"""How a signed-in page gets back to the board.

The board is the hub, and the header carries no menu for a signed-in reader, so
a tool page has to name its way back itself. The logo alone is a brand mark,
not a signpost: a member on a tool page has no reason to expect that clicking
the troop's logo returns them to their own page.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from members.models import Account, Person, Role


class MemberShellBackLinkTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        person = Person.objects.create(
            first_name="Parent",
            last_name="Test",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        cls.user = Account.objects.create_user(
            email="shell@test.com", password="pass", person=person,
        )

    def test_a_tool_page_names_the_way_back_to_the_board(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("members:documents"))

        self.assertContains(response, 'class="page-back"')
        self.assertContains(response, f'href="{reverse("homepage")}"')

    def test_the_link_carries_the_destination_in_words(self):
        """A word, not just an arrow: the whole point is that a reader who has
        never tried the logo learns where the way back is."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("members:documents"))

        self.assertContains(response, str(translation.gettext("My space")))

    def test_the_board_does_not_offer_a_way_back_to_itself(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("homepage"))

        self.assertNotContains(response, "page-back")

    def test_an_anonymous_page_does_not_offer_it(self):
        response = self.client.get(reverse("account_login"))

        self.assertNotContains(response, "page-back")
