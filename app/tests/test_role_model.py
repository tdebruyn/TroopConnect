"""The secondary-role model after "Autre membre" and the Admin removal.

These tests pin the rules the forms enforce: a Parent or an Autre membre holds
the unit administration, an Animateur may lead the unit team or be their
section's communications lead, "Parent actif" is Parent-only, and Participants
and not-yet-validated accounts hold none. They also pin the access matrix: the
unit team's lead does members and money, the treasurer does money, the
registration manager does members, and site staff do everything.
"""

from django.test import TestCase
from django.urls import reverse

from members.forms import AdminUserUpdateForm
from members.models import (
    Account,
    Branch,
    Person,
    PersonRole,
    Role,
    Section,
    get_registration_admins,
)
from members.permissions import (
    can_access_finance,
    can_access_messaging,
    can_delete_member,
    can_manage_members,
    can_manage_roles,
    can_manage_unit,
    secondary_roles_for,
    visible_sections,
)

from .base import TroopSettingsTestCase


def make_account(email, primary="p", roles=(), is_staff=False):
    person = Person.objects.create(
        first_name=email.split("@")[0],
        last_name="Test",
        primary_role=Role.objects.get(short=primary),
        status="a",
    )
    for short in roles:
        PersonRole.objects.create(person=person, role=Role.objects.get(short=short))
    account = Account.objects.create_user(
        email=email, password="pass", person=person, is_staff=is_staff
    )
    return person, account


class SecondaryRoleOfferTest(TestCase):
    """Which secondary roles the member edit form offers."""

    def offered(self, person):
        form = AdminUserUpdateForm(instance=person)
        if "secondary_roles" not in form.fields:
            return None
        return {role.short for role in form.fields["secondary_roles"].queryset}

    def test_parent_gets_parent_actif_and_the_unit_roles(self):
        person, _ = make_account("p@test.be", primary="p")
        self.assertEqual(self.offered(person), {"pa", "ar", "t", "ri"})

    def test_autre_membre_gets_the_unit_roles_but_not_parent_actif(self):
        person, _ = make_account("am@test.be", primary="am")
        self.assertEqual(self.offered(person), {"ar", "t", "ri"})

    def test_animateur_gets_the_unit_lead_and_communications_roles(self):
        person, _ = make_account("a@test.be", primary="a")
        self.assertEqual(self.offered(person), {"ar", "rc"})

    def test_participant_has_no_secondary_role_field(self):
        person, _ = make_account("e@test.be", primary="e")
        self.assertIsNone(self.offered(person))

    def test_nouveau_has_no_secondary_role_field(self):
        person, _ = make_account("n@test.be", primary="n")
        self.assertIsNone(self.offered(person))

    def test_roles_for_each_primary_role(self):
        self.assertEqual(secondary_roles_for("p"), ("pa", "ar", "t", "ri"))
        self.assertEqual(secondary_roles_for("am"), ("ar", "t", "ri"))
        self.assertEqual(secondary_roles_for("a"), ("ar", "rc"))
        self.assertEqual(secondary_roles_for("e"), ())
        self.assertEqual(secondary_roles_for("n"), ())


class SecondaryRoleSaveTest(TestCase):
    """What a submit may keep, drop and replace."""

    def form_data(self, person, primary_role=None, secondary_roles=None):
        return {
            "first_name": person.first_name,
            "last_name": person.last_name,
            "primary_role": (primary_role or person.primary_role).pk,
            "birthday": "",
            "email": "",
            "secondary_roles": [role.pk for role in secondary_roles or []],
        }

    def test_parent_switching_to_autre_membre_loses_parent_actif(self):
        person, _ = make_account("p@test.be", primary="p")
        pa = Role.objects.get(short="pa")
        ar = Role.objects.get(short="ar")
        PersonRole.objects.create(person=person, role=pa)

        form = AdminUserUpdateForm(
            instance=person,
            data=self.form_data(
                person,
                primary_role=Role.objects.get(short="am"),
                secondary_roles=[pa, ar],
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            {role.short for role in form.cleaned_data["secondary_roles"]}, {"ar"}
        )

        form.save()
        kept = set(person.roles.values_list("short", flat=True))
        self.assertEqual(kept, {"ar"})

    def test_switching_to_animator_drops_the_unit_administration(self):
        """A treasurer's role is not allowed beside an animateur; it goes."""
        person, _ = make_account("p@test.be", primary="p")
        PersonRole.objects.create(person=person, role=Role.objects.get(short="t"))

        form = AdminUserUpdateForm(
            instance=person,
            data=self.form_data(
                person, primary_role=Role.objects.get(short="a")
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["secondary_roles"], [])
        form.save()
        self.assertFalse(
            PersonRole.objects.filter(person=person, role__is_primary=False).exists()
        )

    def test_an_animateur_keeps_the_communications_role(self):
        person, _ = make_account("a@test.be", primary="a")
        rc = Role.objects.get(short="rc")
        PersonRole.objects.create(person=person, role=rc)

        form = AdminUserUpdateForm(
            instance=person,
            data=self.form_data(
                person, primary_role=person.primary_role, secondary_roles=[rc]
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(
            set(person.roles.values_list("short", flat=True)), {"rc"}
        )

    def test_a_reader_without_role_rights_keeps_the_stored_roles(self):
        """A registration manager edits records, not role assignments."""
        person, _ = make_account("p@test.be", primary="p")
        PersonRole.objects.create(person=person, role=Role.objects.get(short="ar"))

        form = AdminUserUpdateForm(
            instance=person,
            data={
                "first_name": person.first_name,
                "last_name": person.last_name,
                "primary_role": person.primary_role.pk,
                "birthday": "",
                "email": "",
            },
            can_assign_roles=False,
        )
        self.assertNotIn("secondary_roles", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(
            PersonRole.objects.filter(
                person=person, role__short="ar"
            ).exists()
        )

    def test_a_reader_without_role_rights_cannot_make_someone_an_animateur_with_roles(
        self,
    ):
        person, _ = make_account("p@test.be", primary="p")
        PersonRole.objects.create(person=person, role=Role.objects.get(short="t"))

        form = AdminUserUpdateForm(
            instance=person,
            data={
                "first_name": person.first_name,
                "last_name": person.last_name,
                "primary_role": Role.objects.get(short="a").pk,
                "birthday": "",
                "email": "",
            },
            can_assign_roles=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(
            PersonRole.objects.filter(person=person, role__is_primary=False).exists()
        )


class PermissionMatrixTest(TroopSettingsTestCase):
    """Who reaches members, money, the unit-wide tools and role assignment."""

    @classmethod
    def setUpTestData(cls):
        cls.parent, cls.parent_account = make_account("parent@test.be")
        cls.lead, cls.lead_account = make_account("lead@test.be", roles=("ar",))
        cls.treasurer, cls.treasurer_account = make_account(
            "tres@test.be", roles=("t",)
        )
        cls.registration, cls.registration_account = make_account(
            "ri@test.be", roles=("ri",)
        )
        cls.animateur, cls.animateur_account = make_account("anim@test.be", primary="a")
        cls.staff, cls.staff_account = make_account(
            "staff@test.be", is_staff=True
        )

    def test_finance_is_the_lead_and_the_treasurer(self):
        self.assertTrue(can_access_finance(self.lead_account))
        self.assertTrue(can_access_finance(self.treasurer_account))
        self.assertFalse(can_access_finance(self.registration_account))
        self.assertFalse(can_access_finance(self.parent_account))
        self.assertTrue(can_access_finance(self.staff_account))

    def test_members_are_the_lead_and_the_registration_manager(self):
        self.assertTrue(can_manage_members(self.lead_account))
        self.assertTrue(can_manage_members(self.registration_account))
        self.assertFalse(can_manage_members(self.treasurer_account))
        self.assertFalse(can_manage_members(self.parent_account))
        self.assertTrue(can_manage_members(self.staff_account))

    def test_only_the_lead_or_site_staff_may_delete(self):
        self.assertTrue(can_delete_member(self.lead_account))
        self.assertTrue(can_delete_member(self.staff_account))
        self.assertFalse(can_delete_member(self.registration_account))
        self.assertFalse(can_delete_member(self.treasurer_account))
        self.assertFalse(can_delete_member(self.parent_account))

    def test_unit_wide_tools_belong_to_the_lead(self):
        self.assertTrue(can_manage_unit(self.lead_account))
        self.assertTrue(can_manage_unit(self.staff_account))
        self.assertFalse(can_manage_unit(self.registration_account))
        self.assertFalse(can_manage_unit(self.treasurer_account))
        self.assertFalse(can_manage_unit(self.parent_account))

    def test_role_assignment_is_the_leads_job(self):
        self.assertTrue(can_manage_roles(self.lead_account))
        self.assertTrue(can_manage_roles(self.staff_account))
        self.assertFalse(can_manage_roles(self.registration_account))
        self.assertFalse(can_manage_roles(self.treasurer_account))

    def test_messaging_is_the_lead_and_section_animateurs(self):
        self.assertTrue(can_access_messaging(self.lead_account))
        self.assertTrue(can_access_messaging(self.animateur_account))
        self.assertTrue(can_access_messaging(self.staff_account))
        self.assertFalse(can_access_messaging(self.registration_account))
        self.assertFalse(can_access_messaging(self.treasurer_account))
        self.assertFalse(can_access_messaging(self.parent_account))

    def test_unit_leads_read_every_agenda(self):
        branch = Branch.objects.create(name="Baladins")
        section = Section.objects.create(name="Baladins", branch=branch)
        self.assertEqual(list(visible_sections(self.lead_account)), [section])
        self.assertEqual(list(visible_sections(self.registration_account)), [])
        self.assertEqual(list(visible_sections(self.treasurer_account)), [])

    def test_registration_notices_go_to_the_lead_and_the_registration_manager(self):
        self.assertEqual(
            set(get_registration_admins()),
            {self.lead_account.email, self.registration_account.email},
        )


class MemberAdminViewTest(TroopSettingsTestCase):
    """The member list and edit page follow can_manage_members()."""

    @classmethod
    def setUpTestData(cls):
        cls.target, _ = make_account("target@test.be")
        cls.child, _ = make_account("kid@test.be", primary="e")
        cls.lead, cls.lead_account = make_account("lead@test.be", roles=("ar",))
        cls.registration, cls.registration_account = make_account(
            "ri@test.be", roles=("ri",)
        )
        cls.treasurer, cls.treasurer_account = make_account(
            "tres@test.be", roles=("t",)
        )
        cls.staff, cls.staff_account = make_account(
            "staff@test.be", is_staff=True
        )

    def status_for(self, account, name="members:admin_list", **kwargs):
        self.client.force_login(account)
        url = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
        return self.client.get(url).status_code

    def test_member_list(self):
        self.assertEqual(self.status_for(self.lead_account), 200)
        self.assertEqual(self.status_for(self.registration_account), 200)
        self.assertEqual(self.status_for(self.staff_account), 200)
        self.assertEqual(self.status_for(self.treasurer_account), 403)

    def test_member_edit(self):
        kwargs = {"pk": self.target.pk}
        self.assertEqual(
            self.status_for(self.lead_account, "members:admin_update", **kwargs), 200
        )
        self.assertEqual(
            self.status_for(self.registration_account, "members:admin_update", **kwargs),
            200,
        )
        self.assertEqual(
            self.status_for(self.treasurer_account, "members:admin_update", **kwargs),
            403,
        )

    def test_the_edit_page_offers_autre_membre_and_the_role_filter_data(self):
        self.client.force_login(self.lead_account)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.target.pk})
        )
        self.assertContains(response, "Autre membre")
        self.assertContains(response, 'id="secondary-roles"')
        self.assertContains(response, 'id="secondary-roles-by-primary"')

    def test_the_child_edit_page_shows_the_key_to_the_member_managers(self):
        url = reverse("members:admin_update", kwargs={"pk": self.child.pk})
        for account in (
            self.lead_account,
            self.registration_account,
            self.staff_account,
        ):
            with self.subTest(account=account.email):
                self.client.force_login(account)
                response = self.client.get(url)
                self.assertContains(response, 'id="child-secret-key"')
                self.assertContains(response, self.child.secret_key)

    def test_the_edit_page_hides_the_key_outside_a_child_profile(self):
        self.client.force_login(self.lead_account)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.target.pk})
        )
        self.assertNotContains(response, 'id="child-secret-key"')

    def test_the_registration_manager_cannot_assign_roles(self):
        self.client.force_login(self.registration_account)
        response = self.client.get(
            reverse("members:admin_update", kwargs={"pk": self.target.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("secondary_roles", response.context["form"].fields)
        self.assertNotContains(response, 'name="secondary_roles"')

    def test_passage_is_unit_wide(self):
        self.assertEqual(self.status_for(self.lead_account, "members:passage"), 200)
        self.assertEqual(self.status_for(self.staff_account, "members:passage"), 200)
        self.assertEqual(
            self.status_for(self.registration_account, "members:passage"), 403
        )
        self.assertEqual(self.status_for(self.treasurer_account, "members:passage"), 403)

    def test_settings_stay_with_site_staff(self):
        self.assertEqual(
            self.status_for(self.staff_account, "members:troop_settings"), 200
        )
        self.assertEqual(
            self.status_for(self.lead_account, "members:troop_settings"), 403
        )
        self.assertEqual(
            self.status_for(self.registration_account, "members:troop_settings"), 403
        )
