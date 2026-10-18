"""The staff page for branches and sections.

The first-run wizard already edits the structure; this page is the same editor
after setup, where removing a row can no longer assume the database is empty.
The tests pin the two things that makes different: a rename keeps the section
its references, and a row that members, activities or messages still use is
refused rather than cascaded away.
"""

from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext as _

from members.models import (
    Account,
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
)

from .base import TroopSettingsTestCase


class SectionsToolTestBase(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = Account.objects.create_user(
            email="manager@test.com",
            password="testpass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Mana",
                last_name="Ger",
                primary_role=Role.objects.get(short="p"),
                status="a",
            ),
        )
        cls.parent = Account.objects.create_user(
            email="parent@test.com",
            password="testpass",
            person=Person.objects.create(
                first_name="Paul",
                last_name="Parent",
                primary_role=Role.objects.get(short="p"),
                status="a",
            ),
        )
        cls.branch = Branch.objects.create(
            name="Louveteaux",
            key="louveteaux",
            min_age_dec_31=8,
            max_age_dec_31=11,
        )
        cls.section = Section.objects.create(
            name="Meute", branch=cls.branch, email="meute@example.org"
        )

    def setUp(self):
        super().setUp()
        self.url = reverse("members:sections")
        self.client.force_login(self.manager)

    def branch_row(self, branch, *, name=None, minimum=None, maximum=None):
        return {
            "branch-id": [branch.key or f"branch-{branch.pk}"],
            "branch-key": [branch.key],
            "branch-name-fr": [name or branch.name_fr],
            "branch-min": [str(branch.min_age_dec_31 or "")],
            "branch-max": [str(branch.max_age_dec_31 or "")],
            "section-email": [
                section.email for section in branch.section_set.order_by("pk")
            ],
            "section-id": [
                f"section-{section.pk}"
                for section in branch.section_set.order_by("pk")
            ],
            "section-branch": [
                branch.key or f"branch-{branch.pk}"
                for section in branch.section_set.order_by("pk")
            ],
            "section-sex": [
                section.sex or Section.Sex.BOTH
                for section in branch.section_set.order_by("pk")
            ],
            "section-name-fr": [
                section.name_fr
                for section in branch.section_set.order_by("pk")
            ],
        }

    def post_rows(self, *rows):
        """Post several branch rows, merging their equally named lists."""
        data = {}
        for row in rows:
            for key, values in row.items():
                data.setdefault(key, []).extend(values)
        return self.client.post(self.url, data)


class SectionsToolAccessTest(SectionsToolTestBase):
    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        self.client.logout()
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('account_login')}?next={self.url}")

    def test_a_member_without_the_unit_team_role_is_refused(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_the_page_lists_the_branches_and_sections(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Louveteaux")
        self.assertContains(response, "Meute")
        self.assertContains(response, 'name="section-email"')

    def test_the_dashboard_offers_the_sections_tool(self):
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, reverse("members:sections"))


class SectionsToolSaveTest(SectionsToolTestBase):
    def test_a_save_renames_without_losing_the_section(self):
        old_pk = self.section.pk
        section_row = self.branch_row(self.branch)
        section_row["section-name-fr"] = ["Meute des Loups"]
        section_row["section-email"] = ["loups@example.org"]

        response = self.client.post(
            self.url,
            {
                **{k: v for k, v in section_row.items() if k.startswith("branch-")},
                "section-id": [f"section-{self.section.pk}"],
                "section-branch": ["louveteaux"],
                "section-sex": ["B"],
                "section-name-fr": ["Meute des Loups"],
                "section-email": ["loups@example.org"],
            },
        )

        self.assertRedirects(response, self.url)
        self.section.refresh_from_db()
        self.assertEqual(self.section.pk, old_pk)
        self.assertEqual(self.section.name_fr, "Meute des Loups")
        self.assertEqual(self.section.email, "loups@example.org")

    def test_an_invalid_section_email_is_refused(self):
        response = self.client.post(
            self.url,
            {
                "branch-id": ["louveteaux"],
                "branch-key": ["louveteaux"],
                "branch-name-fr": ["Louveteaux"],
                "branch-min": ["8"],
                "branch-max": ["11"],
                "section-id": [f"section-{self.section.pk}"],
                "section-branch": ["louveteaux"],
                "section-sex": ["B"],
                "section-name-fr": ["Meute"],
                "section-email": ["not-an-email"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            escape(
                _("%(branch)s: %(section)s has an invalid email address.")
                % {"branch": "Louveteaux", "section": "Meute"}
            ),
        )
        self.section.refresh_from_db()
        self.assertEqual(self.section.email, "meute@example.org")

    def test_the_ladder_follows_the_row_order(self):
        second = Branch.objects.create(
            name="Éclaireurs", key="eclaireurs", min_age_dec_31=12, max_age_dec_31=15
        )
        Section.objects.create(name="Troupe", branch=second)

        first_row = self.branch_row(self.branch)
        second_row = self.branch_row(second)
        # Post the younger branch second: the last row is where members leave.
        self.post_rows(first_row, second_row)

        self.branch.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.branch.promotes_to, second)
        self.assertFalse(self.branch.is_top)
        self.assertIsNone(second.promotes_to)
        self.assertTrue(second.is_top)


class SectionsToolRemovalTest(SectionsToolTestBase):
    def setUp(self):
        super().setUp()
        self.unused = Section.objects.create(name="Réserve", branch=self.branch)

    def still_used(self, name):
        return escape(
            _(
                "“%(name)s” is still used by members, activities or messages, "
                "so it cannot be removed here. The Django admin can delete it."
            )
            % {"name": name}
        )

    def row_without(self, section):
        """The branch row, with one section left out of every list."""
        row = self.branch_row(self.branch)
        for key in (
            "section-id",
            "section-branch",
            "section-sex",
            "section-name-fr",
            "section-email",
        ):
            position = self.branch.section_set.order_by("pk").values_list(
                "pk", flat=True
            )
            del row[key][list(position).index(section.pk)]
        return row

    def test_an_unused_section_is_removed(self):
        response = self.post_rows(self.row_without(self.unused))

        self.assertRedirects(response, self.url)
        self.assertFalse(Section.objects.filter(pk=self.unused.pk).exists())
        self.assertTrue(Section.objects.filter(pk=self.section.pk).exists())

    def test_a_section_with_an_enrolment_is_refused(self):
        child = Person.objects.create(
            first_name="Léa",
            last_name="Louveteau",
            primary_role=Role.objects.get(short="e"),
            status="a",
        )
        Enrollment.objects.create(
            user=child, section=self.section, school_year=SchoolYear.current()
        )

        response = self.post_rows(self.row_without(self.section))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.still_used(self.section))
        self.assertTrue(Section.objects.filter(pk=self.section.pk).exists())

    def test_a_section_with_an_activity_is_refused(self):
        SectionEvent.objects.create(
            section=self.section,
            activity_type=SectionEvent.ActivityType.REUNION,
            title="Réunion",
            start_date=SchoolYear.current().start_date,
        )

        response = self.post_rows(self.row_without(self.section))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.still_used(self.section))
        self.assertTrue(Section.objects.filter(pk=self.section.pk).exists())


class SectionsRowEndpointTest(SectionsToolTestBase):
    def test_add_branch_returns_a_row(self):
        response = self.client.post(
            reverse("members:sections_row", args=["add-branch"]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="branch-id"')
        self.assertContains(response, 'name="section-name-fr"')

    def test_add_section_returns_a_row(self):
        response = self.client.post(
            reverse("members:sections_row", args=["add-section"]),
            {"branch-id": "louveteaux"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="section-email"')

    def test_remove_returns_an_empty_response(self):
        response = self.client.post(
            reverse("members:sections_row", args=["remove"]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.content, b"")

    def test_a_non_manager_cannot_use_the_row_endpoint(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse("members:sections_row", args=["add-branch"]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)
