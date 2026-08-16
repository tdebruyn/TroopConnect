from datetime import date

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from post_office.models import EmailTemplate

from members.forms import AdminUserUpdateForm, ProfileEditForm
from members.models import (
    Account,
    Branch,
    ParentChild,
    Person,
    PersonRole,
    Role,
    SchoolYear,
)


class AdminUpdateParticipantSecondaryRolesTest(TestCase):
    """Rule 1: a Participant (primary role "e") can never have secondary
    roles. The admin update form drops the field, discards submitted values
    when switching to Participant, and clears stored ones on save."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        cls.role_e = Role.objects.get(short="e")
        cls.role_p = Role.objects.get(short="p")
        cls.role_tresorier = Role.objects.get(short="t")

        cls.participant = Person.objects.create(
            first_name="Enfant", last_name="Un",
            primary_role=cls.role_e, status="a",
            birthday=date(2015, 3, 1), sex="M",
        )
        cls.parent = Person.objects.create(
            first_name="Parent", last_name="Un",
            primary_role=cls.role_p, status="a",
        )

    def _switch_to_participant_data(self, **overrides):
        data = {
            "first_name": self.parent.first_name,
            "last_name": self.parent.last_name,
            "primary_role": self.role_e.pk,
            "birthday": "2014-06-15",
            "sex": "F",
            "email": "",
        }
        if "secondary_roles" in overrides or "secondary_roles" not in data:
            data.setdefault("secondary_roles", [self.role_tresorier.pk])
        data.update(overrides)
        return data

    def test_field_dropped_for_participant(self):
        form = AdminUserUpdateForm(instance=self.participant)
        self.assertNotIn("secondary_roles", form.fields)

    def test_field_kept_for_non_participant(self):
        form = AdminUserUpdateForm(instance=self.parent)
        self.assertIn("secondary_roles", form.fields)

    def test_admin_update_view_hides_secondary_roles_for_participant(self):
        staff = Account.objects.create_user(
            email="staff@test.be", password="pass", is_staff=True,
            person=Person.objects.create(
                first_name="Admin", last_name="Staff",
                primary_role=self.role_p, status="a",
            ),
        )
        self.client.force_login(staff)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.participant.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "secondary_roles", response.context["form"].fields
        )
        self.assertNotContains(response, 'name="secondary_roles"')

    def test_clean_drops_submitted_roles_when_switching_to_participant(self):
        form = AdminUserUpdateForm(
            instance=self.parent, data=self._switch_to_participant_data()
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.cleaned_data["secondary_roles"]), [])

    def test_clean_keeps_roles_for_other_roles(self):
        data = self._switch_to_participant_data(primary_role=self.role_p.pk)
        form = AdminUserUpdateForm(instance=self.parent, data=data)
        self.assertTrue(form.is_valid())
        self.assertEqual(
            list(form.cleaned_data["secondary_roles"]), [self.role_tresorier]
        )

    def test_save_clears_stored_roles_when_switching_to_participant(self):
        PersonRole.objects.create(person=self.parent, role=self.role_tresorier)
        form = AdminUserUpdateForm(
            instance=self.parent, data=self._switch_to_participant_data()
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.primary_role, self.role_e)
        self.assertEqual(
            PersonRole.objects.filter(
                person=self.parent, role__is_primary=False
            ).count(),
            0,
        )

    def test_save_keeps_roles_for_other_roles(self):
        PersonRole.objects.create(person=self.parent, role=self.role_tresorier)
        form = AdminUserUpdateForm(
            instance=self.parent,
            data=self._switch_to_participant_data(primary_role=self.role_p.pk),
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(
            PersonRole.objects.filter(
                person=self.parent, role__is_primary=False
            ).count(),
            1,
        )


class Migration0018PurgeTest(TestCase):
    """Migration 0018 removes secondary roles from stored Participants."""

    def test_participant_secondary_roles_purged(self):
        role_e = Role.objects.get(short="e")
        role_p = Role.objects.get(short="p")
        role_t = Role.objects.get(short="t")

        participant = Person.objects.create(
            first_name="Kid", last_name="One",
            primary_role=role_e, status="a",
            birthday=date(2015, 1, 1), sex="M",
        )
        PersonRole.objects.create(person=participant, role=role_t)
        parent = Person.objects.create(
            first_name="Par", last_name="Two",
            primary_role=role_p, status="a",
        )
        PersonRole.objects.create(person=parent, role=role_t)

        call_command("migrate", "members", "0017", verbosity=0)
        self.assertEqual(
            PersonRole.objects.filter(person=participant).count(), 1
        )
        self.assertEqual(PersonRole.objects.filter(person=parent).count(), 1)

        call_command("migrate", "members", verbosity=0)

        self.assertEqual(
            PersonRole.objects.filter(
                person=participant, role__is_primary=False
            ).count(),
            0,
        )
        # Non-participants keep their secondary roles.
        self.assertEqual(
            PersonRole.objects.filter(person=parent, role__is_primary=False).count(),
            1,
        )


class ProfileBranchAgeTest(TestCase):
    """Rule 2: a person whose age on Dec 31 fits a Branch can only be a
    Participant. Enforced in ProfileEditForm (choices + clean)."""

    ERROR_MESSAGE = "Une personne en âge de branche ne peut être qu'un Animé."

    def setUp(self):
        year = SchoolYear.current()
        Branch.objects.create(name="Baladins", min_age_dec_31=6, max_age_dec_31=9)
        # Age 8 on Dec 31 of the current school year.
        self.person = Person.objects.create(
            first_name="Branch", last_name="Age",
            primary_role=Role.objects.get(short="p"), status="a",
            birthday=date(year.name - 8, 6, 15),
        )
        self.account = Account.objects.create_user(
            email="branchage@test.be", password="pass", person=self.person,
        )

    def _profile_data(self, primary_role):
        return {
            "first_name": self.person.first_name,
            "last_name": self.person.last_name,
            "email": self.account.email,
            "primary_role": primary_role,
        }

    def test_choices_restricted_to_participant(self):
        form = ProfileEditForm(instance=self.account)
        self.assertEqual(
            [c[0] for c in form.fields["primary_role"].choices], ["e"]
        )

    def test_post_non_participant_rejected(self):
        """Submitting a non-Participant role is rejected: the choices are
        restricted to "e", so the field validation refuses anything else."""
        self.client.force_login(self.account)
        url = reverse("members:profile", kwargs={"pk": self.account.pk})
        response = self.client.post(url, self._profile_data("a"))
        self.assertEqual(response.status_code, 200)
        self.person.refresh_from_db()
        self.assertEqual(self.person.primary_role.short, "p")

    def test_clean_raises_when_choices_not_restricted(self):
        """Defense-in-depth: clean() itself raises even if the submitted
        value got past the (restricted) field choices."""
        form = ProfileEditForm(
            instance=self.account, data=self._profile_data("a")
        )
        # Simulate a caller that did not restrict the field choices.
        from members.constants import ROLE_CHOICES

        form.fields["primary_role"].choices = ROLE_CHOICES
        self.assertFalse(form.is_valid())
        self.assertIn(self.ERROR_MESSAGE, form.errors["__all__"])

    def test_post_participant_allowed(self):
        self.client.force_login(self.account)
        url = reverse("members:profile", kwargs={"pk": self.account.pk})
        response = self.client.post(url, self._profile_data("e"))
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.primary_role.short, "e")

    def test_locked_role_skips_branch_age_check(self):
        """A person with role dependencies is locked; clean() must not raise
        even though their age fits a branch."""
        other_child = Person.objects.create(
            first_name="Other", last_name="Child",
            primary_role=Role.objects.get(short="e"), status="a",
            birthday=date(2015, 5, 1), sex="M",
        )
        ParentChild.objects.create(parent=self.person, child=other_child)
        form = ProfileEditForm(
            instance=self.account, data=self._profile_data("p")
        )
        self.assertTrue(form.is_valid())
