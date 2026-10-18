from datetime import date

from django import forms
from django.urls import reverse

from members.forms import AdminUserUpdateForm, ProfileEditForm
from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
    Section,
)

from .base import TroopSettingsTestCase


class AdminUpdateParentActifTest(TroopSettingsTestCase):
    """The "Parent actif" role is only offered, kept or saved alongside the
    Parent primary role. An Animateur has secondary roles of their own, but this
    is not one of them."""

    @classmethod
    def setUpTestData(cls):
        cls.parent_role = Role.objects.get(short="p")
        cls.animator_role = Role.objects.get(short="a")
        cls.parent_actif = Role.objects.get(short="pa")
        cls.tresorier = Role.objects.get(short="t")
        cls.parent = Person.objects.create(
            first_name="Par", last_name="Ent",
            primary_role=cls.parent_role, status="a",
        )
        cls.animator = Person.objects.create(
            first_name="Ani", last_name="Mateur",
            primary_role=cls.animator_role, status="a",
        )

    def form_data(self, person, primary_role=None, **overrides):
        data = {
            "first_name": person.first_name,
            "last_name": person.last_name,
            "primary_role": (primary_role or person.primary_role).pk,
            "birthday": "",
            "email": "",
        }
        data.update(overrides)
        return data

    def offered_roles(self, form):
        return [role.short for role in form.fields["secondary_roles"].queryset]

    def test_offered_to_a_parent(self):
        form = AdminUserUpdateForm(instance=self.parent)
        self.assertIn("pa", self.offered_roles(form))

    def test_not_offered_to_an_animator(self):
        """An Animateur has roles of their own, but not "Parent actif"."""
        form = AdminUserUpdateForm(instance=self.animator)
        self.assertIn("secondary_roles", form.fields)
        offered = self.offered_roles(form)
        self.assertNotIn("pa", offered)
        self.assertEqual(set(offered), {"ar", "rc"})

    def test_offered_when_the_submitted_role_is_parent(self):
        """The queryset follows the role being submitted, not the one stored:
        this animator is being promoted to Parent in the same submit."""
        form = AdminUserUpdateForm(
            instance=self.animator,
            data=self.form_data(self.animator, primary_role=self.parent_role),
        )
        self.assertIn("pa", self.offered_roles(form))

    def test_submitted_roles_dropped_when_switching_to_animator(self):
        """A Parent Actif or Treasurer submitted in the same POST is discarded:
        neither is allowed beside an Animateur."""
        form = AdminUserUpdateForm(
            instance=self.parent,
            data=self.form_data(
                self.parent,
                primary_role=self.animator_role,
                secondary_roles=[self.parent_actif.pk, self.tresorier.pk],
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["secondary_roles"], [])
        form.save()
        self.assertFalse(
            PersonRole.objects.filter(
                person=self.parent, role__is_primary=False
            ).exists()
        )

    def test_save_clears_a_stored_parent_actif_when_switching_away_from_parent(self):
        PersonRole.objects.create(person=self.parent, role=self.parent_actif)
        form = AdminUserUpdateForm(
            instance=self.parent,
            data=self.form_data(
                self.parent, primary_role=self.animator_role, secondary_roles=[]
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(
            PersonRole.objects.filter(
                person=self.parent, role=self.parent_actif
            ).exists()
        )

    def test_parent_keeps_parent_actif(self):
        PersonRole.objects.create(person=self.parent, role=self.parent_actif)
        form = AdminUserUpdateForm(
            instance=self.parent,
            data=self.form_data(
                self.parent, secondary_roles=[self.parent_actif.pk]
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(
            PersonRole.objects.filter(
                person=self.parent, role=self.parent_actif
            ).exists()
        )


class ProfileParentActifTest(TroopSettingsTestCase):
    """The self-service checkbox is ignored when the submitted primary role is
    not Parent, and a locked Parent keeps the role through the hidden field."""

    def setUp(self):
        super().setUp()
        self.parent_role = Role.objects.get(short="p")
        self.parent_actif = Role.objects.get(short="pa")
        self.person = Person.objects.create(
            first_name="Par", last_name="Ent",
            primary_role=self.parent_role, status="a",
            birthday=date(1980, 1, 1),
        )
        self.account = Account.objects.create_user(
            email="parent@test.be", password="pass", person=self.person,
        )

    def profile_data(self, **overrides):
        data = {
            "first_name": self.person.first_name,
            "last_name": self.person.last_name,
            "email": self.account.email,
            "primary_role": "p",
            "parent_active": "on",
        }
        data.update(overrides)
        return data

    def test_a_parent_can_still_become_active(self):
        form = ProfileEditForm(instance=self.account, data=self.profile_data())
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(
            PersonRole.objects.filter(
                person=self.person, role=self.parent_actif
            ).exists()
        )

    def test_submitted_parent_active_is_ignored_for_a_non_parent(self):
        PersonRole.objects.create(person=self.person, role=self.parent_actif)
        form = ProfileEditForm(
            instance=self.account,
            data=self.profile_data(primary_role="a"),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["parent_active"])
        form.save()
        self.assertFalse(
            PersonRole.objects.filter(
                person=self.person, role=self.parent_actif
            ).exists()
        )

    def test_a_locked_parent_still_sees_the_parent_actif_choice(self):
        """A parent locked by a child is not locked out of helping.

        The account type is fixed, but "Parent actif" is a choice about the
        reader, so it stays a real checkbox rather than a hidden value that
        only preserves whatever was stored before.
        """
        child = Person.objects.create(
            first_name="Kid", last_name="One",
            primary_role=Role.objects.get(short="e"), status="a",
            birthday=date(2015, 3, 1), sex="M",
        )
        ParentChild.objects.create(parent=self.person, child=child)
        PersonRole.objects.create(person=self.person, role=self.parent_actif)

        form = ProfileEditForm(instance=self.account)
        self.assertNotIsInstance(
            form.fields["parent_active"].widget, forms.HiddenInput
        )
        self.assertTrue(form.fields["parent_active"].initial)

        self.client.force_login(self.account)
        response = self.client.get(
            reverse("members:profile", kwargs={"pk": self.account.pk})
        )
        self.assertContains(response, 'name="parent_active"')
        self.assertContains(response, "parent-active-choice")
        self.assertContains(response, "checked")

        # A save that keeps the box ticked keeps the role.
        response = self.client.post(
            reverse("members:profile", kwargs={"pk": self.account.pk}),
            {
                "first_name": self.person.first_name,
                "last_name": self.person.last_name,
                "email": self.account.email,
                "primary_role": "p",
                "parent_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PersonRole.objects.filter(
                person=self.person, role=self.parent_actif
            ).exists()
        )

    def test_a_locked_parent_can_stop_helping(self):
        child = Person.objects.create(
            first_name="Kid", last_name="Two",
            primary_role=Role.objects.get(short="e"), status="a",
            birthday=date(2015, 3, 1), sex="M",
        )
        ParentChild.objects.create(parent=self.person, child=child)
        PersonRole.objects.create(person=self.person, role=self.parent_actif)

        self.client.force_login(self.account)
        response = self.client.post(
            reverse("members:profile", kwargs={"pk": self.account.pk}),
            {
                "first_name": self.person.first_name,
                "last_name": self.person.last_name,
                "email": self.account.email,
                "primary_role": "p",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            PersonRole.objects.filter(
                person=self.person, role=self.parent_actif
            ).exists()
        )

    def test_a_locked_non_parent_does_not_get_the_choice(self):
        """An animateur with a section cannot hold "Parent actif"; the field
        stays hidden and only round-trips its stored (false) value."""
        animateur = Person.objects.create(
            first_name="Ani", last_name="Mateur",
            primary_role=Role.objects.get(short="a"), status="a",
        )
        section = Section.objects.create(name="A section")
        Enrollment.objects.create(
            user=animateur,
            section=section,
            school_year=SchoolYear.current(),
        )
        account = Account.objects.create_user(
            email="anim@test.be", password="pass", person=animateur,
        )

        form = ProfileEditForm(instance=account)
        self.assertIsInstance(form.fields["parent_active"].widget, forms.HiddenInput)
