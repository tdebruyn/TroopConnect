from django.test import TestCase
from django.urls import reverse

from members.models import Account, Person, Role, ImportantDocument
from post_office.models import EmailTemplate


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
        d1 = ImportantDocument.objects.create(title="Old", url="https://a.com")
        d2 = ImportantDocument.objects.create(title="New", url="https://b.com")
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
