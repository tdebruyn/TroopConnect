from datetime import date

from django.test import TestCase
from django.urls import reverse

from members.models import (
    Account,
    Branch,
    Enrollment,
    Person,
    Role,
    SchoolYear,
    Section,
)


class RemoveChildTestBase(TestCase):
    """A logged-in parent with one attached child, plus a section to enroll in."""

    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.role_child = Role.objects.get(short="e")

        cls.parent = Person.objects.create(
            first_name="Parent", last_name="One",
            primary_role=cls.role_parent, status="a",
        )
        cls.parent_account = Account.objects.create_user(
            email="parent@test.be", password="Test1234!", person=cls.parent,
        )

        cls.branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=9,
        )
        cls.section = Section.objects.create(name="Baladins", branch=cls.branch)
        cls.current_year = SchoolYear.current()

    def setUp(self):
        self.client.force_login(self.parent_account)
        self.child = Person.objects.create(
            first_name="Child", last_name="One",
            primary_role=self.role_child, status="a",
            birthday=date(2015, 6, 15), sex="M",
        )
        self.child.parents.add(self.parent)

    def enroll(self):
        Enrollment.objects.create(
            user=self.child, section=self.section, school_year=self.current_year,
        )


class HasSectionTest(RemoveChildTestBase):
    def test_no_section_by_default(self):
        self.assertFalse(self.child.has_section)

    def test_has_section_when_enrolled(self):
        self.enroll()
        self.assertTrue(self.child.has_section)


class ChildListActionTest(RemoveChildTestBase):
    def _html(self):
        return self.client.get(
            reverse("members:child_list"), HTTP_HX_REQUEST="true",
        ).content.decode()

    def test_remove_shown_when_no_section(self):
        html = self._html()
        self.assertIn(reverse("members:remove_child", kwargs={"pk": self.child.pk}), html)
        self.assertNotIn(
            reverse("members:deregister_child", kwargs={"pk": self.child.pk}), html,
        )

    def test_deregister_shown_when_section_assigned(self):
        self.enroll()
        html = self._html()
        self.assertIn(
            reverse("members:deregister_child", kwargs={"pk": self.child.pk}), html,
        )
        self.assertNotIn(
            reverse("members:remove_child", kwargs={"pk": self.child.pk}), html,
        )


class RemoveChildViewTest(RemoveChildTestBase):
    def test_confirmation_page_allows_remove_for_unenrolled_child(self):
        response = self.client.get(
            reverse("members:remove_child", kwargs={"pk": self.child.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["allow_remove"])

    def test_confirmation_page_refuses_enrolled_child(self):
        self.enroll()
        response = self.client.get(
            reverse("members:remove_child", kwargs={"pk": self.child.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["allow_remove"])

    def test_confirm_deletes_child_and_account(self):
        account = Account.objects.create(person=self.child, email="child@test.be")
        response = self.client.get(
            reverse("members:remove_child_confirm", kwargs={"pk": self.child.pk}),
        )
        self.assertRedirects(
            response,
            reverse("members:profile", kwargs={"pk": self.parent_account.pk}),
            fetch_redirect_response=False,
        )
        self.assertFalse(Person.objects.filter(pk=self.child.pk).exists())
        self.assertFalse(Account.objects.filter(pk=account.pk).exists())

    def test_confirm_does_not_delete_enrolled_child(self):
        self.enroll()
        self.client.get(
            reverse("members:remove_child_confirm", kwargs={"pk": self.child.pk}),
        )
        self.assertTrue(Person.objects.filter(pk=self.child.pk).exists())

    def test_confirm_redirects_for_other_parents_child(self):
        other = Person.objects.create(
            first_name="Other", last_name="Parent",
            primary_role=self.role_parent, status="a",
        )
        other_account = Account.objects.create_user(
            email="other@test.be", password="Test1234!", person=other,
        )
        self.client.force_login(other_account)
        response = self.client.get(
            reverse("members:remove_child_confirm", kwargs={"pk": self.child.pk}),
        )
        self.assertEqual(response.status_code, 302)
        # The child is still attached to the real parent, so it survives.
        self.assertTrue(Person.objects.filter(pk=self.child.pk).exists())
