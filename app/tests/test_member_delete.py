"""Admin-side deletion of a member: the archive half and the purge half.

The flow is reached from the member's modify page and is deliberately a soft
delete first (`member_delete` archives and disables the login) with a separate
hard delete (`member_purge`) that only ever runs on an already-archived member.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from finance.models import Payment
from members.models import (
    Account,
    Branch,
    Enrollment,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
)


class MemberDeleteTestBase(TestCase):
    """A superuser, an ADMIN-role staffer and a plain staffer, plus a target."""

    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.role_admin = Role.objects.get(short="ad")

        cls.superuser_person = Person.objects.create(
            first_name="Super", last_name="User",
            primary_role=cls.role_parent, status="a",
        )
        # create_superuser() supplies first_name/last_name for its own Person,
        # which clashes with an existing one — set the flags on create_user.
        cls.superuser = Account.objects.create_user(
            email="super@test.be", password="Test1234!",
            person=cls.superuser_person, is_staff=True, is_superuser=True,
        )

        # Staff AND holding the ADMIN secondary role — the intended deleter.
        cls.admin_person = Person.objects.create(
            first_name="Role", last_name="Admin",
            primary_role=cls.role_parent, status="a",
        )
        PersonRole.objects.create(person=cls.admin_person, role=cls.role_admin)
        cls.admin_user = Account.objects.create_user(
            email="roleadmin@test.be", password="Test1234!",
            person=cls.admin_person, is_staff=True,
        )

        # Staff, but no ADMIN role and not a superuser: may not delete.
        cls.staff_person = Person.objects.create(
            first_name="Plain", last_name="Staff",
            primary_role=cls.role_parent, status="a",
        )
        cls.staff_user = Account.objects.create_user(
            email="staff@test.be", password="Test1234!",
            person=cls.staff_person, is_staff=True,
        )

        cls.branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=11,
        )
        cls.section = Section.objects.create(name="Baladins", branch=cls.branch)
        cls.year = SchoolYear.current()

    def setUp(self):
        self.client.force_login(self.superuser)

    def make_member(self, with_account=True, **kwargs):
        fields = {
            "first_name": "Target",
            "last_name": "Member",
            "primary_role": self.role_parent,
            "status": "a",
        }
        fields.update(kwargs)
        member = Person.objects.create(**fields)
        if with_account:
            Account.objects.create_user(
                email=f"member-{member.pk}@test.be",
                password="Test1234!",
                person=member,
            )
        return member

    def enrol(self, member):
        return Enrollment.objects.create(
            user=member, section=self.section, school_year=self.year,
        )


class DeleteButtonVisibilityTest(MemberDeleteTestBase):
    """Only superusers and ADMIN-role holders are offered the button."""

    def test_superuser_is_offered_the_delete_button(self):
        member = self.make_member()
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": member.pk})
        )
        # Asserted on the link, not its label: the page renders in the active
        # language (fr by default), so the English source is never on it.
        self.assertContains(response, reverse("members:member_delete", kwargs={"pk": member.pk}))

    def test_admin_role_holder_is_offered_the_delete_button(self):
        member = self.make_member()
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": member.pk})
        )
        self.assertContains(response, reverse("members:member_delete", kwargs={"pk": member.pk}))

    def test_plain_staff_is_not_offered_the_delete_button(self):
        member = self.make_member()
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": member.pk})
        )
        self.assertNotContains(
            response, reverse("members:member_delete", kwargs={"pk": member.pk})
        )

    def test_own_page_has_no_delete_button(self):
        """Deleting yourself would lock you out of the screen that undoes it."""
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.superuser_person.pk})
        )
        self.assertNotContains(
            response,
            reverse("members:member_delete", kwargs={"pk": self.superuser_person.pk}),
        )

    def test_archived_member_is_offered_the_purge_button_instead(self):
        member = self.make_member(status="ar", archived_date=date(2026, 1, 1))
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": member.pk})
        )
        self.assertContains(response, reverse("members:member_purge", kwargs={"pk": member.pk}))
        self.assertNotContains(
            response, reverse("members:member_delete", kwargs={"pk": member.pk})
        )


class MemberDeletePermissionTest(MemberDeleteTestBase):
    """The views are hard-gated, not merely hidden in the template."""

    def test_plain_staff_cannot_open_the_delete_page(self):
        member = self.make_member()
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_plain_staff_cannot_post_the_delete(self):
        member = self.make_member()
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 403)
        member.refresh_from_db()
        self.assertEqual(member.status, "a")

    def test_plain_staff_cannot_purge(self):
        member = self.make_member(status="ar", archived_date=date(2026, 1, 1))
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse("members:member_purge", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Person.objects.filter(pk=member.pk).exists())

    def test_admin_role_holder_may_delete(self):
        member = self.make_member()
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.status, "ar")

    def test_anonymous_is_sent_to_the_login_page(self):
        member = self.make_member()
        self.client.logout()
        response = self.client.get(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])
        member.refresh_from_db()
        self.assertEqual(member.status, "a")


class MemberDeleteTest(MemberDeleteTestBase):
    """The archive half: gets show the page, only the POST changes anything."""

    def test_get_shows_the_consequences_without_archiving(self):
        member = self.make_member()
        self.enrol(member)
        response = self.client.get(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Target Member")
        member.refresh_from_db()
        self.assertEqual(member.status, "a")
        self.assertIsNone(member.archived_date)

    def test_post_archives_the_member_and_disables_the_login(self):
        member = self.make_member()
        response = self.client.post(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        member.account.refresh_from_db()
        self.assertEqual(member.status, "ar")
        self.assertEqual(member.archived_date, date.today())
        self.assertFalse(member.account.is_active)

    def test_post_archives_a_member_who_never_had_an_account(self):
        member = self.make_member(with_account=False)
        response = self.client.post(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.status, "ar")

    def test_archiving_keeps_history(self):
        """A soft delete must not touch enrolments or payments."""
        member = self.make_member()
        enrollment = self.enrol(member)
        payment = Payment.objects.create(
            person=member, school_year=self.year, amount=40,
        )
        self.client.post(reverse("members:member_delete", kwargs={"pk": member.pk}))
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_cannot_delete_your_own_record(self):
        response = self.client.post(
            reverse(
                "members:member_delete", kwargs={"pk": self.superuser_person.pk}
            )
        )
        self.assertEqual(response.status_code, 302)
        self.superuser_person.refresh_from_db()
        self.assertEqual(self.superuser_person.status, "a")

    def test_already_archived_member_redirects_to_the_purge_page(self):
        member = self.make_member(status="ar", archived_date=date(2026, 1, 1))
        response = self.client.get(
            reverse("members:member_delete", kwargs={"pk": member.pk})
        )
        self.assertRedirects(
            response, reverse("members:member_purge", kwargs={"pk": member.pk})
        )

    def test_unknown_member_is_a_404(self):
        import uuid

        response = self.client.get(
            reverse("members:member_delete", kwargs={"pk": uuid.uuid4()})
        )
        self.assertEqual(response.status_code, 404)


class MemberPurgeTest(MemberDeleteTestBase):
    """The hard half: archived members only, and it really destroys the record."""

    def archived_member(self, **kwargs):
        return self.make_member(
            status="ar", archived_date=date(2026, 1, 1), **kwargs
        )

    def test_get_on_a_non_archived_member_sends_you_back_to_modify(self):
        member = self.make_member()
        response = self.client.get(
            reverse("members:member_purge", kwargs={"pk": member.pk})
        )
        self.assertRedirects(
            response, reverse("members:admin_update", kwargs={"pk": member.pk})
        )

    def test_post_on_a_non_archived_member_deletes_nothing(self):
        member = self.make_member()
        response = self.client.post(
            reverse("members:member_purge", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Person.objects.filter(pk=member.pk).exists())

    def test_get_shows_what_will_be_destroyed(self):
        member = self.archived_member()
        self.enrol(member)
        response = self.client.get(
            reverse("members:member_purge", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Target Member")

    def test_post_deletes_the_person_and_their_account(self):
        member = self.archived_member()
        account_pk = member.account.pk
        response = self.client.post(
            reverse("members:member_purge", kwargs={"pk": member.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Person.objects.filter(pk=member.pk).exists())
        self.assertFalse(Account.objects.filter(pk=account_pk).exists())

    def test_post_cascades_to_enrolments_and_payments(self):
        member = self.archived_member()
        enrollment = self.enrol(member)
        payment = Payment.objects.create(
            person=member, school_year=self.year, amount=40,
        )
        self.client.post(reverse("members:member_purge", kwargs={"pk": member.pk}))
        self.assertFalse(Enrollment.objects.filter(pk=enrollment.pk).exists())
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    def test_cannot_purge_your_own_record(self):
        self.superuser_person.status = "ar"
        self.superuser_person.archived_date = date(2026, 1, 1)
        self.superuser_person.save()
        response = self.client.post(
            reverse(
                "members:member_purge", kwargs={"pk": self.superuser_person.pk}
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Person.objects.filter(pk=self.superuser_person.pk).exists())
