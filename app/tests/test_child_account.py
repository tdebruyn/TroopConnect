from datetime import date

from django.core import mail
from django.urls import reverse
from post_office.models import Email, EmailTemplate

from members.forms import ChildForm
from members.models import Account, ParentChild, Person, PersonRole, Role
from tests.mail import MailTestCase


class ChildAccountTestBase(MailTestCase):
    """Shared setup: a logged-in parent, a registration admin (so the staff
    notification has a recipient), and the two notification templates."""

    @classmethod
    def setUpTestData(cls):
        # post_office looks templates up by exact (name, language); both
        # notifications are sent in "fr" (account default / LANGUAGE_CODE).
        # Migration 0019 already seeds these "fr" templates, so get-or-create
        # to avoid a duplicate (unique on name+language).
        EmailTemplate.objects.get_or_create(
            name="new_child_parent", language="fr",
            defaults={"subject": "Test", "content": "Test"},
        )
        EmailTemplate.objects.get_or_create(
            name="new_child_staff", language="fr",
            defaults={"subject": "Test", "content": "Test"},
        )
        cls.role_parent = Role.objects.get(short="p")
        cls.role_child = Role.objects.get(short="e")
        cls.role_admin = Role.objects.get(short="ad")

        cls.parent = Person.objects.create(
            first_name="Parent", last_name="One",
            primary_role=cls.role_parent, status="a",
            address="Rue Test 1", phone="+32 12 34 56 78",
        )
        cls.parent_account = Account.objects.create_user(
            email="parent@test.be", password="Test1234!", person=cls.parent,
        )

        # Secondary role "Admin" so get_registration_admins() is not empty.
        cls.admin = Person.objects.create(
            first_name="Reg", last_name="Admin",
            primary_role=cls.role_parent, status="a",
        )
        PersonRole.objects.create(person=cls.admin, role=cls.role_admin)
        Account.objects.create_user(
            email="admin@test.be", password="Test1234!", person=cls.admin,
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.parent_account)

    def password_mail_outbox(self, email_address):
        """Allauth sends the "choose a password" email through Django's email
        backend, which the test runner replaces with locmem."""
        return [
            m for m in mail.outbox if email_address in m.to
        ]

    def child_data(self, **overrides):
        data = {
            "first_name": "Child",
            "last_name": "One",
            "sex": "M",
            "birthday": "2015-06-15",
            "address": "Rue Test 1",
            "phone": "+32 12 34 56 78",
            "email": "",
        }
        data.update(overrides)
        return data


class AddNewChildAccountTest(ChildAccountTestBase):
    """add_new_child creates the child's Account when an email is provided."""

    def test_child_with_email_gets_account_and_password_email(self):
        response = self.client.post(
            reverse("members:add_new_child"),
            self.child_data(email="child@test.be"),
        )
        self.assertEqual(response.status_code, 204)
        child = Person.objects.get(first_name="Child")
        account = Account.objects.get(person=child)
        self.assertEqual(account.email, "child@test.be")
        self.assertTrue(
            ParentChild.objects.filter(parent=self.parent, child=child).exists()
        )
        # The "choose a password" email promised by the form was sent.
        self.assertTrue(self.password_mail_outbox("child@test.be"))

    def test_child_without_email_has_no_account(self):
        response = self.client.post(
            reverse("members:add_new_child"), self.child_data(),
        )
        self.assertEqual(response.status_code, 204)
        child = Person.objects.get(first_name="Child")
        self.assertFalse(Account.objects.filter(person=child).exists())
        self.assertFalse(self.password_mail_outbox("child@test.be"))

    def test_no_parent_confirmation_when_child_has_no_email(self):
        response = self.client.post(
            reverse("members:add_new_child"), self.child_data(),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Email.objects.filter(template__name="new_child_parent").exists()
        )

    def test_parent_confirmation_sent_when_child_has_email(self):
        response = self.client.post(
            reverse("members:add_new_child"),
            self.child_data(email="child@test.be"),
        )
        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            Email.objects.filter(template__name="new_child_parent").exists()
        )

    def test_duplicate_child_rejected(self):
        """Adding a child with the same first+last name for the same parent
        must not create a second Person."""
        self.client.post(reverse("members:add_new_child"), self.child_data())
        response = self.client.post(
            reverse("members:add_new_child"), self.child_data(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["form"].errors)
        self.assertEqual(
            Person.objects.filter(first_name="Child", last_name="One").count(), 1,
        )

    def test_duplicate_child_case_insensitive(self):
        """Duplicate detection ignores case, so "Child One" and "child one"
        are treated as the same child."""
        self.client.post(reverse("members:add_new_child"), self.child_data())
        response = self.client.post(
            reverse("members:add_new_child"),
            self.child_data(first_name="child", last_name="one"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["form"].errors)
        self.assertEqual(Person.objects.filter(first_name="Child").count(), 1)

    def test_parent_own_email_rejected(self):
        """The form warns against reusing the parent's address; validation
        must reject it instead of silently re-linking the parent account."""
        response = self.client.post(
            reverse("members:add_new_child"),
            self.child_data(email="parent@test.be"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(Person.objects.filter(first_name="Child").exists())


class EditChildAccountTest(ChildAccountTestBase):
    """edit_child keeps the child's Account in sync with the email field."""

    def setUp(self):
        super().setUp()
        self.child = Person.objects.create(
            first_name="Child", last_name="One",
            primary_role=self.role_child, status="a",
            birthday=date(2015, 6, 15), sex="M",
        )
        self.child.parents.add(self.parent)

    def test_existing_account_email_updated_without_new_mail(self):
        Account.objects.create(person=self.child, email="old@test.be")
        response = self.client.post(
            reverse("members:edit_child", kwargs={"pk": self.child.pk}),
            self.child_data(email="new@test.be"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Account.objects.filter(person=self.child).count(), 1)
        self.assertEqual(
            Account.objects.get(person=self.child).email, "new@test.be",
        )
        # Changing an existing account's email must not re-send the
        # "choose a password" email.
        self.assertFalse(self.password_mail_outbox("new@test.be"))

    def test_edit_creates_account_when_none_exists(self):
        response = self.client.post(
            reverse("members:edit_child", kwargs={"pk": self.child.pk}),
            self.child_data(email="created@test.be"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        account = Account.objects.get(person=self.child)
        self.assertEqual(account.email, "created@test.be")
        self.assertTrue(self.password_mail_outbox("created@test.be"))


class ChildFormSaveAccountTest(ChildAccountTestBase):
    """Unit tests for ChildForm.save/save_account. add_new_child_view saves
    with commit=False and calls save_account() itself, so the two must also
    work standalone."""

    def test_save_commit_false_does_not_persist_nor_create_account(self):
        form = ChildForm(self.child_data(email="child@test.be"))
        self.assertTrue(form.is_valid())
        form.save(commit=False)
        # Person.id is a UUID with a Python-side default, so check the DB.
        self.assertFalse(Person.objects.filter(first_name="Child").exists())
        self.assertFalse(Account.objects.filter(email="child@test.be").exists())

    def test_save_creates_account_and_sends_password_email(self):
        form = ChildForm(self.child_data(email="unit@test.be"))
        self.assertTrue(form.is_valid())
        person = form.save()
        account = Account.objects.get(person=person)
        self.assertEqual(account.email, "unit@test.be")
        self.assertTrue(self.password_mail_outbox("unit@test.be"))

    def test_save_account_updates_existing_email_without_new_mail(self):
        person = Person.objects.create(
            first_name="Kid", last_name="Two",
            primary_role=self.role_child, status="a",
            birthday=date(2014, 1, 1), sex="F",
        )
        Account.objects.create(person=person, email="kid@old.be")
        form = ChildForm(
            self.child_data(email="kid@new.be"), instance=person,
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(
            Account.objects.get(person=person).email, "kid@new.be",
        )
        self.assertFalse(self.password_mail_outbox("kid@new.be"))
