from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from members.models import (
    Account, Person, Role, SchoolYear, Section, Branch, Enrollment, ParentChild,
)
from members.tasks import delete_archived_users, notify_upcoming_deletion
from post_office.models import EmailTemplate


class DataRetentionTestBase(TestCase):
    """Shared setup for data retention tests."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        EmailTemplate.objects.create(
            name="archive_deletion_warning",
            subject="Warning",
            content="Your account {{ person_name }} will be deleted on {{ deletion_date }}.",
        )

    def setUp(self):
        self.role_parent = Role.objects.get(short="p")
        self.role_anime = Role.objects.get(short="e")
        self.today = timezone.now().date()


class DeleteArchivedUsersTest(DataRetentionTestBase):
    """Tests for deleting users archived 5+ years."""

    def test_user_archived_5_years_is_deleted(self):
        person = Person.objects.create(
            first_name="Old", last_name="Archived",
            primary_role=self.role_anime, status="ar",
            archived_date=self.today - timedelta(days=5 * 365 + 1),
        )
        count = delete_archived_users()
        self.assertEqual(count, 1)
        self.assertFalse(Person.objects.filter(pk=person.pk).exists())

    def test_user_archived_less_than_5_years_not_deleted(self):
        person = Person.objects.create(
            first_name="Recent", last_name="Archived",
            primary_role=self.role_anime, status="ar",
            archived_date=self.today - timedelta(days=4 * 365),
        )
        count = delete_archived_users()
        self.assertEqual(count, 0)
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def test_active_user_not_deleted(self):
        person = Person.objects.create(
            first_name="Active", last_name="User",
            primary_role=self.role_parent, status="a",
        )
        count = delete_archived_users()
        self.assertEqual(count, 0)
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def test_archived_without_date_not_deleted(self):
        person = Person.objects.create(
            first_name="NoDate", last_name="Archived",
            primary_role=self.role_anime, status="ar",
            archived_date=None,
        )
        count = delete_archived_users()
        self.assertEqual(count, 0)
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())


class NotifyUpcomingDeletionTest(DataRetentionTestBase):
    """Tests for notification emails before deletion."""

    def test_notification_sent_at_4_years_11_months(self):
        """User archived 4 years 11 months ago should trigger notification."""
        parent = Person.objects.create(
            first_name="Parent", last_name="Test",
            primary_role=self.role_parent, status="a",
        )
        parent_account = Account.objects.create_user(
            email="parent@test.com", password="testpass", person=parent,
        )
        child = Person.objects.create(
            first_name="Child", last_name="Test",
            primary_role=self.role_anime, status="ar",
            archived_date=self.today - timedelta(days=5 * 365 - 30),
        )
        ParentChild.objects.create(parent=parent, child=child)

        with patch("post_office.mail.send") as mock_send:
            count = notify_upcoming_deletion()

        self.assertEqual(count, 1)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        self.assertEqual(call_kwargs[1]["recipients"], ["parent@test.com"])

    def test_no_notification_for_recently_archived(self):
        """User archived only 1 year ago should not be notified."""
        parent = Person.objects.create(
            first_name="Parent", last_name="Test",
            primary_role=self.role_parent, status="a",
        )
        Account.objects.create_user(
            email="parent2@test.com", password="testpass", person=parent,
        )
        child = Person.objects.create(
            first_name="YoungArch", last_name="Child",
            primary_role=self.role_anime, status="ar",
            archived_date=self.today - timedelta(days=365),
        )
        ParentChild.objects.create(parent=parent, child=child)

        with patch("post_office.mail.send") as mock_send:
            count = notify_upcoming_deletion()

        self.assertEqual(count, 0)
        mock_send.assert_not_called()

    def test_notification_fallback_to_own_account(self):
        """If no parent with account, notify the person's own account."""
        person = Person.objects.create(
            first_name="Solo", last_name="User",
            primary_role=self.role_parent, status="ar",
            archived_date=self.today - timedelta(days=5 * 365 - 30),
        )
        Account.objects.create_user(
            email="solo@test.com", password="testpass", person=person,
        )

        with patch("post_office.mail.send") as mock_send:
            count = notify_upcoming_deletion()

        self.assertEqual(count, 1)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        self.assertEqual(call_kwargs[1]["recipients"], ["solo@test.com"])
