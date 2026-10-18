from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from post_office.models import EmailTemplate

from members.models import Account, ImportantDocument, Person, Role


class ImportantDocumentModelTest(TestCase):
    """Test ImportantDocument model CRUD."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )

    def test_create_document(self):
        doc = ImportantDocument.objects.create(
            title="Statuts", url="https://example.com/statuts",
        )
        self.assertEqual(str(doc), "Statuts")
        self.assertEqual(ImportantDocument.objects.count(), 1)

    def test_document_ordering(self):
        ImportantDocument.objects.create(title="Old", url="https://a.com")
        ImportantDocument.objects.create(title="New", url="https://b.com")
        docs = list(ImportantDocument.objects.values_list("title", flat=True))
        self.assertEqual(docs, ["New", "Old"])

    def test_document_admin_registered(self):
        from django.contrib import admin
        self.assertIn(ImportantDocument, admin.site._registry)


class DocumentListViewAuthTest(TestCase):
    """Test that only authenticated users can list documents."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        role = Role.objects.get(short="p")
        person = Person.objects.create(
            first_name="Test", last_name="User", primary_role=role, status="a",
        )
        cls.user = Account.objects.create_user(
            email="test@test.com", password="pass", person=person,
        )
        ImportantDocument.objects.create(title="Guide", url="https://example.com")

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(reverse("members:documents"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_user_can_list(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("members:documents"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Guide")

    def test_documents_template_used(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("members:documents"))
        self.assertTemplateUsed(response, "members/documents.html")

    def test_empty_state(self):
        ImportantDocument.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.get(reverse("members:documents"))
        self.assertContains(response, "Aucun document disponible")


class DocumentManagementTest(TestCase):
    """The unit team's lead adds to the list every reader sees."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        role = Role.objects.get(short="p")
        cls.reader = Account.objects.create_user(
            email="reader@test.com",
            password="pass",
            person=Person.objects.create(
                first_name="Réa", last_name="Der", primary_role=role, status="a",
            ),
        )
        cls.manager = Account.objects.create_user(
            email="manager@test.com",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Mana", last_name="Ger", primary_role=role, status="a",
            ),
        )
        cls.document = ImportantDocument.objects.create(
            title="Règlement", url="https://example.com/reglement"
        )

    def test_a_reader_sees_the_list_without_the_controls(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse("members:documents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Règlement")
        self.assertNotContains(response, reverse("members:document_form"))

    def test_a_manager_sees_add_edit_and_delete(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("members:documents"))

        self.assertContains(response, reverse("members:document_form"))
        self.assertContains(
            response, reverse("members:document_edit", args=[self.document.pk])
        )
        self.assertContains(
            response, reverse("members:document_delete", args=[self.document.pk])
        )

    def test_a_manager_creates_a_document(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("members:document_form"),
            {"title": "Liste de camp", "url": "https://example.com/camp"},
        )

        self.assertRedirects(response, reverse("members:documents"))
        self.assertEqual(
            ImportantDocument.objects.get(title="Liste de camp").url,
            "https://example.com/camp",
        )

    def test_a_document_needs_a_link_or_a_file(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("members:document_form"), {"title": "Rien"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("Add a link or a file."))
        self.assertFalse(ImportantDocument.objects.filter(title="Rien").exists())

    def test_an_htmx_save_closes_the_modal_and_reloads_the_list(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("members:document_form"),
            {"title": "Trousseau", "url": "https://example.com/trousseau"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertIn("documentsChanged", response.headers["HX-Trigger"])

    def test_delete_is_a_post_and_removes_the_document(self):
        self.client.force_login(self.manager)
        url = reverse("members:document_delete", args=[self.document.pk])

        confirm = self.client.get(url)
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(ImportantDocument.objects.filter(pk=self.document.pk).exists())

        response = self.client.post(url)
        self.assertRedirects(response, reverse("members:documents"))
        self.assertFalse(ImportantDocument.objects.filter(pk=self.document.pk).exists())

    def test_a_reader_cannot_reach_the_management_views(self):
        self.client.force_login(self.reader)

        for url in (
            reverse("members:document_form"),
            reverse("members:document_edit", args=[self.document.pk]),
            reverse("members:document_delete", args=[self.document.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
