from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta

logger = get_task_logger(__name__)


@shared_task(name="cleanup_old_messages")
def cleanup_old_messages():
    """Delete messages older than 1 year.

    SectionMessageRecipient rows are deleted via CASCADE.
    """
    from messaging.models import SectionMessage

    cutoff = timezone.now() - timedelta(days=365)
    deleted_count, _ = SectionMessage.objects.filter(created_at__lt=cutoff).delete()
    if deleted_count:
        logger.info(f"Deleted {deleted_count} messages older than {cutoff.date()}")
    else:
        logger.info("No old messages to clean up")
    return deleted_count


@shared_task(name="cleanup_orphaned_attachments")
def cleanup_orphaned_attachments():
    """Delete file attachments not linked to any message and older than 1 year."""
    from messaging.models import MessageAttachment

    cutoff = timezone.now() - timedelta(days=365)
    orphaned = MessageAttachment.objects.filter(
        created_at__lt=cutoff,
        messages__isnull=True,
    )

    deleted_count = 0
    for attachment in orphaned:
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        deleted_count += 1

    if deleted_count:
        logger.info(f"Deleted {deleted_count} orphaned attachments older than {cutoff.date()}")
    else:
        logger.info("No orphaned attachments to clean up")
    return deleted_count
