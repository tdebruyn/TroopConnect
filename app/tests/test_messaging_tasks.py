"""Tests for the messaging cleanup Celery tasks.

These two tasks run on a schedule and delete rows and files with no undo, and
neither had any coverage. The boundary worth pinning down is the 365-day cutoff
(the filter is ``created_at__lt``, so a message aged exactly 365 days survives)
and the split of responsibility between the two tasks: the message cleanup
leaves attachment blobs alone, and only the orphan sweep deletes them.
"""

import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from members.models import Person, Role, SchoolYear
from messaging.models import MessageAttachment, SectionMessage, SectionMessageRecipient
from messaging.tasks import cleanup_old_messages, cleanup_orphaned_attachments

OLD = timedelta(days=365 + 1)
JUST_UNDER = timedelta(days=365 - 1)


class MessagingTaskTestBase(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.tmp_media)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.sender = Person.objects.create(
            first_name="Marie", last_name="Staff",
            primary_role=Role.objects.get(short="a"), status="a",
        )
        self.recipient = Person.objects.create(
            first_name="Paul", last_name="Parent",
            primary_role=Role.objects.get(short="p"), status="a",
        )
        self.year = SchoolYear.current()

    def make_message_at(self, created_at, recipients=()):
        """Create a message with an exact created_at (auto_now_add is bypassed)."""
        message = SectionMessage.objects.create(
            sender=self.sender,
            school_year=self.year,
            subject="Kotkot",
            body="Body",
        )
        SectionMessage.objects.filter(pk=message.pk).update(created_at=created_at)
        for person in recipients:
            SectionMessageRecipient.objects.create(message=message, parent=person)
        return message

    def make_message(self, age, recipients=()):
        """Create a message whose created_at is ``age`` before now."""
        return self.make_message_at(timezone.now() - age, recipients)

    def make_attachment(self, age, message=None, name="plan.pdf"):
        attachment = MessageAttachment.objects.create(
            file=ContentFile(b"DATA", name=name),
            original_name=name,
            content_hash="deadbeef",
        )
        MessageAttachment.objects.filter(pk=attachment.pk).update(
            created_at=timezone.now() - age
        )
        if message is not None:
            message.attachments.add(attachment)
        attachment.refresh_from_db()
        return attachment


class CleanupOldMessagesTest(MessagingTaskTestBase):
    def test_message_older_than_a_year_is_deleted(self):
        message = self.make_message(OLD)
        self.assertEqual(cleanup_old_messages(), 1)
        self.assertFalse(SectionMessage.objects.filter(pk=message.pk).exists())

    def test_recent_message_is_kept(self):
        message = self.make_message(JUST_UNDER)
        self.assertEqual(cleanup_old_messages(), 0)
        self.assertTrue(SectionMessage.objects.filter(pk=message.pk).exists())

    def test_message_aged_exactly_one_year_is_kept(self):
        """The filter is ``created_at__lt`` cutoff, so exactly 365 days survives.

        Time is frozen because the cutoff is derived from a fresh ``now()``:
        computing the fixture age from an earlier ``now()`` would always land a
        few microseconds short of the boundary.
        """
        now = timezone.now()
        message = self.make_message_at(now - timedelta(days=365))
        with patch("messaging.tasks.timezone.now", return_value=now):
            self.assertEqual(cleanup_old_messages(), 0)
        self.assertTrue(SectionMessage.objects.filter(pk=message.pk).exists())

    def test_message_one_second_past_the_cutoff_is_deleted(self):
        now = timezone.now()
        self.make_message_at(now - timedelta(days=365, seconds=1))
        with patch("messaging.tasks.timezone.now", return_value=now):
            self.assertEqual(cleanup_old_messages(), 1)

    def test_recipients_are_deleted_with_the_message(self):
        self.make_message(OLD, recipients=[self.recipient])
        self.assertEqual(SectionMessageRecipient.objects.count(), 1)
        cleanup_old_messages()
        self.assertEqual(SectionMessageRecipient.objects.count(), 0)

    def test_recipients_of_kept_messages_survive(self):
        self.make_message(JUST_UNDER, recipients=[self.recipient])
        cleanup_old_messages()
        self.assertEqual(SectionMessageRecipient.objects.count(), 1)

    def test_returns_the_number_of_messages_removed(self):
        self.make_message(OLD)
        self.make_message(OLD)
        self.make_message(JUST_UNDER)
        self.assertEqual(cleanup_old_messages(), 2)
        self.assertEqual(SectionMessage.objects.count(), 1)

    def test_no_messages_to_clean_returns_zero(self):
        self.assertEqual(cleanup_old_messages(), 0)

    def test_attachment_row_survives_its_message(self):
        """Only the orphan sweep may delete blobs — this task must not.

        Deleting the message drops the M2M row, so an attachment shared with a
        kept message would lose its file if this task deleted attachments too.
        """
        shared = self.make_attachment(OLD)
        kept = self.make_message(JUST_UNDER)
        kept.attachments.add(shared)

        self.make_message(OLD).attachments.add(shared)

        cleanup_old_messages()
        self.assertTrue(MessageAttachment.objects.filter(pk=shared.pk).exists())


class CleanupOrphanedAttachmentsTest(MessagingTaskTestBase):
    def test_old_orphan_is_deleted_with_its_file(self):
        attachment = self.make_attachment(OLD)
        stored_name = attachment.file.name
        self.assertTrue(attachment.file.storage.exists(stored_name))

        self.assertEqual(cleanup_orphaned_attachments(), 1)

        self.assertFalse(MessageAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(attachment.file.storage.exists(stored_name))

    def test_old_attachment_still_linked_to_a_message_is_kept(self):
        message = self.make_message(JUST_UNDER)
        attachment = self.make_attachment(OLD, message=message)
        self.assertEqual(cleanup_orphaned_attachments(), 0)
        self.assertTrue(MessageAttachment.objects.filter(pk=attachment.pk).exists())

    def test_recent_orphan_is_kept(self):
        """A just-uploaded attachment is briefly orphaned while composing."""
        attachment = self.make_attachment(JUST_UNDER)
        self.assertEqual(cleanup_orphaned_attachments(), 0)
        self.assertTrue(MessageAttachment.objects.filter(pk=attachment.pk).exists())

    def test_returns_the_number_of_attachments_removed(self):
        self.make_attachment(OLD, name="a.pdf")
        self.make_attachment(OLD, name="b.pdf")
        self.make_attachment(JUST_UNDER, name="c.pdf")
        self.assertEqual(cleanup_orphaned_attachments(), 2)
        self.assertEqual(MessageAttachment.objects.count(), 1)

    def test_no_orphans_returns_zero(self):
        self.assertEqual(cleanup_orphaned_attachments(), 0)

    def test_attachment_without_a_file_is_still_removed(self):
        """A row whose file was already lost must not wedge the sweep."""
        attachment = self.make_attachment(OLD)
        MessageAttachment.objects.filter(pk=attachment.pk).update(file="")
        self.assertEqual(cleanup_orphaned_attachments(), 1)
        self.assertFalse(MessageAttachment.objects.filter(pk=attachment.pk).exists())
