from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta

logger = get_task_logger(__name__)


@shared_task(name="cleanup_old_events")
def cleanup_old_events():
    """
    Delete events older than 30 days from today.
    Runs daily via Celery beat.
    """
    from homepage.models import Event

    cutoff = timezone.now().date() - timedelta(days=30)
    deleted_count, _ = Event.objects.filter(date__lt=cutoff).delete()
    if deleted_count:
        logger.info(f"Deleted {deleted_count} events older than {cutoff}")
    else:
        logger.info("No old events to clean up")
    return deleted_count
