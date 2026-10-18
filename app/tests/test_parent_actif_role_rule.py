from datetime import date

from django import forms
from django.urls import reverse

from members.forms import AdminUserUpdateForm, ProfileEditForm
from members.models import Account, ParentChild, Person, PersonRole, Role

from .base import TroopSettingsTestCase


class AdminUpdateParentActifTest(TroopSettingsTestCase):
    """The "Parent actif" role is only offered, kept or saved alongside the
    Parent primary role."""

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
        """An Animateur holds no secondary role at all, so the field is gone."""
        form = AdminUserUpdateForm(instance=self.animator)
        self.assertNotIn("secondary_roles", form.fields)

    def test_offered_when_the_submitted_role_is_parent(self):
        """The queryset follows the role being submitted, not the one stored:
        this animator is being promoted to Parent in the same submit."""
        form = AdminUserUpdateForm(
            instance=self.animator,
            data=self.form_data(self.animator, primary_role=self.parent_role),
        )
        self.assertIn("pa", self.offered_roles(form))

    def test_submitted_roles_dropped_when_switching_to_animator(self):
        """An Animator holds no secondary role, so a Parent Actif or Treasurer
        submitted in the same POST is discarded."""
        form = AdminUserUpdateForm(
            instance=self.parent,
            data=self.form_data(
                self.parent,
                primary_role=self.animator_role,
                secondary_roles=[self.parent_actif.pk, self.tresorier.pk],
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("secondary_roles", form.cleaned_data)
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

    def test_locked_parent_keeps_the_role_through_the_hidden_field(self):
        child = Person.objects.create(
            first_name="Kid", last_name="One",
            primary_role=Role.objects.get(short="e"), status="a",
            birthday=date(2015, 3, 1), sex="M",
        )
        ParentChild.objects.create(parent=self.person, child=child)
        PersonRole.objects.create(person=self.person, role=self.parent_actif)

        form = ProfileEditForm(instance=self.account)
        self.assertIsInstance(form.fields["parent_active"].widget, forms.HiddenInput)
        self.assertTrue(form.fields["parent_active"].initial)

        # The template has to submit that hidden value; without it the next
        # save reads "un-ticked" and removes the role.
        self.client.force_login(self.account)
        response = self.client.get(
            reverse("members:profile", kwargs={"pk": self.account.pk})
        )
        self.assertContains(response, 'name="parent_active"')
        self.assertContains(response, 'value="True"')

        # A save that submits what that hidden input renders keeps the role.
        response = self.client.post(
            reverse("members:profile", kwargs={"pk": self.account.pk}),
            {
                "first_name": self.person.first_name,
                "last_name": self.person.last_name,
                "email": self.account.email,
                "primary_role": "p",
                "parent_active": "True",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PersonRole.objects.filter(
                person=self.person, role=self.parent_actif
            ).exists()
        )
