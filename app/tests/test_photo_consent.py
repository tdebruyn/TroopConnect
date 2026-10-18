"""Photo consent belongs to the family, not to the unit team.

The member management page shows the current answer but cannot change it:
only a parent (through their child's details) or the member themselves
(through their own profile) decides. The parent's child form therefore owns
the checkbox the admin page used to expose.
"""

from datetime import date

from django.urls import reverse

from members.forms import AdminUserUpdateForm, ChildForm
from members.models import (
    Account,
    Branch,
    ParentChild,
    Person,
    PersonRole,
    Role,
    TroopSettings,
)

from .base import TroopSettingsTestCase
from .mail import MailTestCase


class AdminCannotChangePhotoConsentTest(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_child = Role.objects.get(short=Person.CHILD_ROLE_SHORT)
        cls.role_parent = Role.objects.get(short="p")
        # The help text follows the age rule: a member of branch age is a child
        # whose parent decides.
        Branch.objects.create(
            name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12
        )
        cls.child = Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=cls.role_child,
            status="a",
            sex="M",
            birthday=date(2016, 6, 15),
            photo_consent=False,
        )

    def setUp(self):
        super().setUp()
        # setUpTestData's instance is shared between tests; a test that saved
        # it keeps the new value in memory after the transaction rolls back.
        self.child = Person.objects.get(pk=self.child.pk)

    def form_data(self, **overrides):
        data = {
            "first_name": self.child.first_name,
            "last_name": self.child.last_name,
            "primary_role": self.role_child.pk,
            "birthday": self.child.birthday.isoformat(),
            "sex": "M",
            "email": "",
        }
        data.update(overrides)
        return data

    def test_the_field_is_disabled(self):
        form = AdminUserUpdateForm(instance=self.child)

        self.assertTrue(form.fields["photo_consent"].disabled)

    def test_a_submit_cannot_turn_consent_on(self):
        form = AdminUserUpdateForm(
            instance=self.child, data=self.form_data(photo_consent="on")
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.child.refresh_from_db()
        self.assertFalse(self.child.photo_consent)

    def test_a_submit_cannot_turn_consent_off(self):
        self.child.photo_consent = True
        self.child.save(update_fields=["photo_consent"])
        form = AdminUserUpdateForm(instance=self.child, data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.child.refresh_from_db()
        self.assertTrue(self.child.photo_consent)

    def test_the_help_text_names_the_parent_for_a_child(self):
        form = AdminUserUpdateForm(instance=self.child)

        self.assertEqual(
            str(form.fields["photo_consent"].help_text),
            "Seul le parent peut modifier ce choix pour son enfant.",
        )

    def test_the_help_text_names_the_member_for_an_adult(self):
        adult = Person.objects.create(
            first_name="Parent",
            last_name="Test",
            primary_role=self.role_parent,
            status="a",
        )

        form = AdminUserUpdateForm(instance=adult)

        self.assertEqual(
            str(form.fields["photo_consent"].help_text),
            "Seul le membre peut modifier ce choix dans son propre profil.",
        )

    def test_a_parent_reader_keeps_the_field_enabled(self):
        form = AdminUserUpdateForm(
            instance=self.child, can_edit_photo_consent=True
        )

        self.assertFalse(form.fields["photo_consent"].disabled)

    def test_the_parent_reader_can_change_it(self):
        form = AdminUserUpdateForm(
            instance=self.child,
            data=self.form_data(photo_consent="on"),
            can_edit_photo_consent=True,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.child.refresh_from_db()
        self.assertTrue(self.child.photo_consent)


class StaffParentOnTheMemberPageTest(TroopSettingsTestCase):
    """The staff page asks who the reader is to this member, not what role
    they hold: a registration manager editing their own child is a parent
    there, and an unrelated admin is not."""

    @classmethod
    def setUpTestData(cls):
        cls.role_child = Role.objects.get(short=Person.CHILD_ROLE_SHORT)
        cls.role_parent = Role.objects.get(short="p")
        # The help text follows the age rule: a member of branch age is a child
        # whose parent decides.
        Branch.objects.create(
            name="Louveteaux", min_age_dec_31=10, max_age_dec_31=12
        )
        cls.child = Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=cls.role_child,
            status="a",
            sex="M",
            birthday=date(2016, 6, 15),
            photo_consent=False,
        )
        cls.parent = Person.objects.create(
            first_name="Parent",
            last_name="Test",
            primary_role=cls.role_parent,
            status="a",
        )
        PersonRole.objects.create(
            person=cls.parent, role=Role.objects.get(short="ri")
        )
        ParentChild.objects.create(parent=cls.parent, child=cls.child)
        cls.parent_account = Account.objects.create_user(
            email="parent@test.be", password="pass", person=cls.parent
        )
        cls.admin_account = Account.objects.create_user(
            email="admin@test.be",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Admin",
                last_name="Test",
                primary_role=cls.role_parent,
                status="a",
            ),
        )

    def setUp(self):
        super().setUp()
        self.child = Person.objects.get(pk=self.child.pk)

    def url(self):
        return reverse("members:admin_update", kwargs={"pk": self.child.pk})

    def form_data(self, **overrides):
        data = {
            "first_name": self.child.first_name,
            "last_name": self.child.last_name,
            "primary_role": self.role_child.pk,
            "birthday": self.child.birthday.isoformat(),
            "sex": "M",
            "email": "",
        }
        data.update(overrides)
        return data

    def test_the_parent_keeps_the_checkbox(self):
        self.client.force_login(self.parent_account)

        response = self.client.get(self.url())

        self.assertFalse(
            response.context["form"].fields["photo_consent"].disabled
        )

    def test_an_unrelated_admin_sees_it_disabled(self):
        self.client.force_login(self.admin_account)

        response = self.client.get(self.url())

        self.assertTrue(
            response.context["form"].fields["photo_consent"].disabled
        )

    def test_the_parents_submit_changes_it(self):
        self.client.force_login(self.parent_account)

        self.client.post(
            self.url(), self.form_data(photo_consent="on")
        )

        self.child.refresh_from_db()
        self.assertTrue(self.child.photo_consent)

    def test_an_unrelated_admins_submit_cannot(self):
        self.client.force_login(self.admin_account)

        self.client.post(
            self.url(), self.form_data(photo_consent="on")
        )

        self.child.refresh_from_db()
        self.assertFalse(self.child.photo_consent)


class ParentOwnsTheChildConsentTest(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.role_child = Role.objects.get(short=Person.CHILD_ROLE_SHORT)
        cls.parent = Person.objects.create(
            first_name="Parent",
            last_name="Test",
            primary_role=cls.role_parent,
            status="a",
            photo_consent=True,
        )
        cls.account = Account.objects.create_user(
            email="parent@test.be", password="pass", person=cls.parent
        )
        cls.child = Person.objects.create(
            first_name="Enfant",
            last_name="Test",
            primary_role=cls.role_child,
            status="a",
            sex="M",
            birthday=date(2016, 6, 15),
            photo_consent=False,
        )
        ParentChild.objects.create(parent=cls.parent, child=cls.child)

    def setUp(self):
        super().setUp()
        # ChildForm reads the troop's consent wording, which is cached.
        TroopSettings.clear_cache()
        self.addCleanup(TroopSettings.clear_cache)
        self.child = Person.objects.get(pk=self.child.pk)
        self.client.force_login(self.account)

    def child_data(self, **overrides):
        data = {
            "first_name": self.child.first_name,
            "last_name": self.child.last_name,
            "sex": "M",
            "birthday": self.child.birthday.isoformat(),
            "email": "",
        }
        data.update(overrides)
        return data

    def test_the_parent_child_form_offers_the_checkbox(self):
        form = ChildForm(instance=self.child)

        self.assertIn("photo_consent", form.fields)

    def test_the_add_form_prefills_the_parents_own_choice(self):
        response = self.client.get(reverse("members:add_new_child"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["form"]["photo_consent"].value()
        )

    def test_the_parent_can_change_it_for_their_child(self):
        response = self.client.post(
            reverse("members:edit_child", args=[self.child.pk]),
            self.child_data(photo_consent="on"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.child.refresh_from_db()
        self.assertTrue(self.child.photo_consent)

    def test_an_unticked_box_removes_consent(self):
        self.child.photo_consent = True
        self.child.save(update_fields=["photo_consent"])

        self.client.post(
            reverse("members:edit_child", args=[self.child.pk]),
            self.child_data(),
            HTTP_HX_REQUEST="true",
        )

        self.child.refresh_from_db()
        self.assertFalse(self.child.photo_consent)
