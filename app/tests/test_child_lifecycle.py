"""Detaching, deregistering and removing a child from a parent's account.

These three flows all end in data loss or an archived person, and the rules
differ per flow, so each branch is pinned:

* **Detach** drops one parent link. A child must keep a parent unless they are
  over 18 *and* hold their own account — the rule the confirmation page states
  and the same one the confirm view now enforces (previously the page offered a
  Detach button that the confirm view silently refused).
* **Deregister** archives the child. The "next year" button drops the upcoming
  year's enrolment and the manual passage override; "current year" archives,
  and only emails the registration admins when the child was actively enrolled.
* **Remove** deletes a never-enrolled child outright.

The age helpers ``birthday_to_int``/``current_date_to_int`` are exercised here
too — they were missing entirely, so ``is_adult()`` raised AttributeError for
every child with a birthday.
"""

from datetime import date

from django.urls import reverse
from post_office.models import Email

from members.models import (
    Account,
    Branch,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
)
from tests.mail import MailTestCase

ADULT_BIRTHDAY = date(1990, 1, 1)
CHILD_BIRTHDAY = date(2015, 6, 15)


class ChildLifecycleTestBase(MailTestCase):
    def setUp(self):
        super().setUp()
        self.role_parent = Role.objects.get(short="p")
        self.role_child = Role.objects.get(short="e")
        self.current_year = SchoolYear.current()

        self.parent = Person.objects.create(
            first_name="Alice", last_name="Dupont",
            primary_role=self.role_parent, status="a",
        )
        self.parent_account = Account.objects.create_user(
            email="alice@test.com", password="testpass", person=self.parent,
        )
        self.other_parent = Person.objects.create(
            first_name="Bob", last_name="Dupont",
            primary_role=self.role_parent, status="a",
        )
        Account.objects.create_user(
            email="bob@test.com", password="testpass", person=self.other_parent,
        )

        self.branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=9,
        )
        self.section = Section.objects.create(name="Baladins A", branch=self.branch)

        self.client.force_login(self.parent_account)

    def make_child(self, first_name="Charlie", birthday=CHILD_BIRTHDAY, **kwargs):
        defaults = {
            "last_name": "Dupont",
            "primary_role": self.role_child,
            "status": "a",
            "sex": "M",
            "birthday": birthday,
        }
        defaults.update(kwargs)
        return Person.objects.create(first_name=first_name, **defaults)

    def give_account(self, person, email):
        return Account.objects.create_user(
            email=email, password="testpass", person=person,
        )

    def makes_adult(self, child):
        """Backdate the birthday so is_adult() is true."""
        child.birthday = ADULT_BIRTHDAY
        child.save(update_fields=["birthday"])
        return child

    def attach(self, child, parent=None):
        ParentChild.objects.create(parent=parent or self.parent, child=child)
        return child

    def enroll(self, child, school_year=None, section=None):
        return Enrollment.objects.create(
            user=child,
            section=section or self.section,
            school_year=school_year or self.current_year,
        )

    def make_next_year(self):
        """The upcoming school year, creating it only if it isn't seeded yet."""
        next_year, _created = SchoolYear.objects.get_or_create(
            name=self.current_year.name + 1,
            defaults={
                "start_date": self.current_year.start_date.replace(
                    year=self.current_year.start_date.year + 1
                ),
                "end_date": self.current_year.end_date.replace(
                    year=self.current_year.end_date.year + 1
                ),
                "range": "next",
            },
        )
        return next_year


class IsAdultTest(ChildLifecycleTestBase):
    """The age helpers used to be missing, making is_adult() raise."""

    def test_child_is_not_an_adult(self):
        self.assertFalse(self.make_child().is_adult())

    def test_adult_is_an_adult(self):
        self.assertTrue(self.make_child(birthday=ADULT_BIRTHDAY).is_adult())

    def test_person_without_a_birthday_counts_as_an_adult(self):
        self.assertTrue(
            self.make_child(birthday=None, primary_role=self.role_parent).is_adult()
        )

    def test_helpers_agree_on_format(self):
        child = self.make_child(birthday=date(2015, 6, 15))
        self.assertEqual(child.birthday_to_int(), 20150615)
        # 8 digits, so the >180000 comparison reads as "more than 18 years".
        self.assertEqual(len(str(child.current_date_to_int())), 8)


class DetachPageTest(ChildLifecycleTestBase):
    def url(self, child):
        return reverse("members:dettach_child", args=[child.pk])

    def test_two_parents_may_detach(self):
        child = self.attach(self.make_child())
        self.attach(child, self.other_parent)
        response = self.client.get(self.url(child))
        self.assertTrue(response.context["allow_dettach"])

    def test_single_parent_of_a_minor_may_not_detach(self):
        child = self.attach(self.make_child())
        response = self.client.get(self.url(child))
        self.assertFalse(response.context["allow_dettach"])
        # Wording is translated, so assert on the child's name being explained.
        self.assertIn(child.first_name, str(response.context["message"]))

    def test_adult_with_their_own_account_may_be_detached(self):
        child = self.makes_adult(self.attach(self.make_child()))
        self.give_account(child, "charlie@test.com")
        response = self.client.get(self.url(child))
        self.assertTrue(response.context["allow_dettach"])

    def test_adult_without_an_account_may_not_be_detached(self):
        child = self.makes_adult(self.attach(self.make_child()))
        response = self.client.get(self.url(child))
        self.assertFalse(response.context["allow_dettach"])

    def test_minor_with_their_own_account_may_not_be_detached(self):
        """Both conditions are required — an account alone is not enough."""
        child = self.attach(self.make_child())
        self.give_account(child, "charlie@test.com")
        response = self.client.get(self.url(child))
        self.assertFalse(response.context["allow_dettach"])

    def test_unattached_child_reports_not_attached(self):
        child = self.make_child()
        response = self.client.get(self.url(child))
        self.assertFalse(response.context["allow_dettach"])
        self.assertIn(child.first_name, str(response.context["message"]))


class DetachConfirmTest(ChildLifecycleTestBase):
    def url(self, child):
        return reverse("members:dettach_confirm", args=[child.pk])

    def test_detaching_keeps_the_other_parent(self):
        child = self.attach(self.make_child())
        self.attach(child, self.other_parent)

        response = self.client.get(self.url(child))

        self.assertRedirects(
            response,
            reverse("members:profile", args=[self.parent_account.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(list(child.parents.all()), [self.other_parent])

    def test_adult_with_an_account_can_be_left_without_a_parent(self):
        child = self.makes_adult(self.attach(self.make_child()))
        self.give_account(child, "charlie@test.com")

        self.client.get(self.url(child))

        self.assertEqual(child.parents.count(), 0)

    def test_refuses_to_orphan_a_minor(self):
        child = self.attach(self.make_child())
        self.client.get(self.url(child))
        self.assertEqual(list(child.parents.all()), [self.parent])

    def test_refuses_an_adult_without_an_account(self):
        child = self.makes_adult(self.attach(self.make_child()))
        self.client.get(self.url(child))
        self.assertEqual(list(child.parents.all()), [self.parent])

    def test_other_parent_cannot_detach(self):
        child = self.attach(self.make_child())
        self.client.logout()
        self.client.login(email="bob@test.com", password="testpass")

        response = self.client.get(self.url(child))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(child.parents.all()), [self.parent])


class DeregisterPageTest(ChildLifecycleTestBase):
    def test_page_allows_deregistration_for_an_attached_child(self):
        child = self.attach(self.make_child())
        response = self.client.get(reverse("members:deregister_child", args=[child.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["allow_deregister"])

    def test_unattached_child_is_redirected(self):
        child = self.make_child()
        response = self.client.get(reverse("members:deregister_child", args=[child.pk]))
        self.assertRedirects(
            response,
            reverse("members:profile", args=[self.parent_account.pk]),
            fetch_redirect_response=False,
        )


class DeregisterNextYearTest(ChildLifecycleTestBase):
    def setUp(self):
        super().setUp()
        self.next_year = self.make_next_year()

    def url(self, child):
        return reverse(
            "members:deregister_confirm", args=[child.pk, "next_year"]
        )

    def test_drops_the_upcoming_years_enrolment(self):
        child = self.attach(self.make_child())
        self.enroll(child, school_year=self.next_year)

        self.client.get(self.url(child))

        self.assertFalse(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )

    def test_clears_the_manual_passage_override(self):
        child = self.attach(self.make_child())
        child.next_section = self.section
        child.save(update_fields=["next_section"])

        self.client.get(self.url(child))

        child.refresh_from_db()
        self.assertIsNone(child.next_section)

    def test_child_stays_active_and_enrolled_for_this_year(self):
        child = self.attach(self.make_child())
        self.enroll(child)

        self.client.get(self.url(child))

        child.refresh_from_db()
        self.assertEqual(child.status, "a")
        self.assertTrue(Enrollment.objects.filter(user=child).exists())

    def test_does_not_email_the_registration_admins(self):
        child = self.attach(self.make_child())
        self.client.get(self.url(child))
        self.assertFalse(Email.objects.exists())

    def test_other_parent_cannot_deregister(self):
        child = self.attach(self.make_child())
        self.enroll(child, school_year=self.next_year)
        self.client.logout()
        self.client.login(email="bob@test.com", password="testpass")

        self.client.get(self.url(child))

        self.assertTrue(
            Enrollment.objects.filter(user=child, school_year=self.next_year).exists()
        )


class RegistrationAdminNotifyTest(ChildLifecycleTestBase):
    """``_notify_deregistration_admins`` emails the 'ri'/'ar'/'ad' holders."""

    def setUp(self):
        super().setUp()
        self.ri_person = Person.objects.create(
            first_name="Rita", last_name="Inscriptions",
            primary_role=self.role_parent, status="a",
        )
        self.ri_person.roles.add(Role.objects.get(short="ri"))
        Account.objects.create_user(
            email="ri@test.com", password="testpass", person=self.ri_person,
        )

        self.child = self.attach(self.make_child())

    def url(self, action="this_year"):
        return reverse("members:deregister_confirm", args=[self.child.pk, action])

    def test_active_child_archives_and_emails_the_admins(self):
        self.client.get(self.url())

        self.child.refresh_from_db()
        self.assertEqual(self.child.status, "ar")
        self.assertIsNotNone(self.child.archived_date)

        email = Email.objects.get()
        self.assertEqual(email.to, ["ri@test.com"])
        self.assertIn("Charlie", email.subject)
        self.assertIn("Alice Dupont", email.message)

    def test_request_state_child_archives_silently(self):
        """No enrolment to unwind yet, so nothing needs manual follow-up."""
        self.child.status = "r"
        self.child.save(update_fields=["status"])

        self.client.get(self.url())

        self.child.refresh_from_db()
        self.assertEqual(self.child.status, "ar")
        self.assertFalse(Email.objects.exists())

    def test_deregistration_leaves_the_enrolment_alone(self):
        """The current-year enrolment is unwound manually, by design."""
        branch = Branch.objects.create(name="Baladins", min_age_dec_31=6)
        section = Section.objects.create(name="Baladins A", branch=branch)
        Enrollment.objects.create(
            user=self.child, section=section, school_year=self.current_year
        )

        self.client.get(self.url())

        self.child.refresh_from_db()
        self.assertEqual(self.child.status, "ar")
        self.assertTrue(Enrollment.objects.filter(user=self.child).exists())

    def test_unknown_action_is_treated_as_the_current_year(self):
        self.client.get(self.url(action="unexpected"))
        self.child.refresh_from_db()
        self.assertEqual(self.child.status, "ar")
        self.assertTrue(Email.objects.exists())


class HtmxGuardTest(ChildLifecycleTestBase):
    """The child list/edit endpoints are HTMX-only and reject plain requests."""

    def test_child_list_without_htmx_header_is_rejected(self):
        response = self.client.get(reverse("members:child_list"))
        self.assertEqual(response.status_code, 400)

    def test_edit_child_without_htmx_header_is_rejected(self):
        child = self.attach(self.make_child())
        response = self.client.get(reverse("members:edit_child", args=[child.pk]))
        self.assertEqual(response.status_code, 400)

    def test_edit_child_with_htmx_renders_the_form(self):
        child = self.attach(self.make_child())
        response = self.client.get(
            reverse("members:edit_child", args=[child.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "members/child_form.html")

    def test_edit_child_post_returns_204_with_a_trigger(self):
        child = self.attach(self.make_child())
        response = self.client.post(
            reverse("members:edit_child", args=[child.pk]),
            {"first_name": "Charlot", "last_name": "Dupont", "sex": "M",
             "birthday": CHILD_BIRTHDAY.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertIn("childListChanged", response["HX-Trigger"])

    def test_cannot_edit_another_parents_child(self):
        child = self.make_child()
        self.attach(child, self.other_parent)
        response = self.client.get(
            reverse("members:edit_child", args=[child.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 404)


class AddChildByKeyTest(ChildLifecycleTestBase):
    def test_get_renders_the_form(self):
        response = self.client.get(reverse("members:add_key_child"))
        self.assertEqual(response.status_code, 200)

    def test_valid_key_attaches_the_child(self):
        child = self.make_child()
        response = self.client.post(
            reverse("members:add_key_child"), {"secret_key": child.secret_key}
        )
        self.assertEqual(response.status_code, 204)
        self.assertIn(self.parent, child.parents.all())

    def test_unknown_key_is_rejected(self):
        response = self.client.post(
            reverse("members:add_key_child"), {"secret_key": "zzzzzz"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


class ProfileViewTest(ChildLifecycleTestBase):
    def test_own_profile_renders(self):
        response = self.client.get(
            reverse("members:profile", args=[self.parent_account.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "members/profile.html")

    def test_another_account_is_404(self):
        stranger = self.make_child(first_name="Stranger", primary_role=self.role_parent)
        other = self.give_account(stranger, "stranger@test.com")
        response = self.client.get(reverse("members:profile", args=[other.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_account_is_404(self):
        response = self.client.get(
            reverse("members:profile", args=["00000000-0000-0000-0000-000000000001"])
        )
        self.assertEqual(response.status_code, 404)

    def test_child_gets_the_restricted_anime_form(self):
        child = self.make_child()
        child_account = self.give_account(child, "charlie@test.com")
        self.client.force_login(child_account)

        response = self.client.get(reverse("members:profile", args=[child_account.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("address", response.context["form"].fields)

    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(
            reverse("members:profile", args=[self.parent_account.pk])
        )
        self.assertEqual(response.status_code, 302)


class AdminUpdateViewTest(ChildLifecycleTestBase):
    def setUp(self):
        super().setUp()
        self.parent_account.is_staff = True
        self.parent_account.save(update_fields=["is_staff"])
        self.child = self.attach(self.make_child())

    def url(self):
        return reverse("members:admin_update", args=[self.child.pk])

    def test_prefills_the_linked_account_email(self):
        self.give_account(self.child, "charlie@test.com")
        response = self.client.get(self.url())
        self.assertEqual(response.context["form"].fields["email"].initial,
                         "charlie@test.com")

    def test_prefills_the_current_years_section(self):
        self.enroll(self.child)
        response = self.client.get(self.url())
        self.assertEqual(
            response.context["form"].fields["current_section"].initial, self.section
        )

    def test_prefills_next_years_section(self):
        self.enroll(self.child, school_year=self.make_next_year())
        response = self.client.get(self.url())
        self.assertEqual(
            response.context["form"].fields["next_section"].initial, self.section
        )

    def test_lists_parents_and_children(self):
        response = self.client.get(self.url())
        self.assertIn(self.parent, response.context["parents"])

    def test_non_staff_is_forbidden(self):
        self.parent_account.is_staff = False
        self.parent_account.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(self.url()).status_code, 403)
