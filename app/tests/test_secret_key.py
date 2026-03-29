from django.test import TestCase

from members.models import Account, Person, Role, SchoolYear, Section, Branch, Enrollment
from post_office.models import EmailTemplate


class SecretKeyTest(TestCase):
    """Test 6-character secret key generation and lookup."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        cls.role_parent = Role.objects.get(short="p")
        cls.role_anime = Role.objects.get(short="e")

    def test_secret_key_is_6_chars(self):
        person = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
        )
        self.assertEqual(len(person.secret_key), 6)

    def test_secret_key_matches_uuid_prefix(self):
        person = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
        )
        self.assertEqual(person.secret_key, str(person.id)[:6])

    def test_secret_key_persists_on_save(self):
        person = Person.objects.create(
            first_name="Test", last_name="Child",
            primary_role=self.role_anime, status="a",
        )
        original_key = person.secret_key
        person.first_name = "Updated"
        person.save()
        person.refresh_from_db()
        self.assertEqual(person.secret_key, original_key)

    def test_lookup_by_secret_key(self):
        person = Person.objects.create(
            first_name="Find", last_name="Me",
            primary_role=self.role_anime, status="a",
        )
        found = Person.objects.get(secret_key=person.secret_key)
        self.assertEqual(found, person)

    def test_child_from_key_form_max_length(self):
        from members.forms import ChildFromKey
        form = ChildFromKey()
        self.assertEqual(form.fields["secret_key"].max_length, 6)

    def test_child_from_key_label(self):
        from members.forms import ChildFromKey
        form = ChildFromKey()
        self.assertIn("6", str(form.fields["secret_key"].label))
