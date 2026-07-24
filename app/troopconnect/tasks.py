"""Project-level Celery tasks."""

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="send_queued_mail")
def send_queued_mail():
    """Send all queued post_office emails via Celery worker."""
    from post_office.management.commands.send_queued_mail import Command

    command = Command()
    command.handle()
    logger.info("Queued mail processed")
