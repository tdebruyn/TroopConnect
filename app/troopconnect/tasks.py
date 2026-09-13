"""Project-level Celery tasks."""

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="send_queued_mail")
def send_queued_mail():
    """Send all queued post_office emails via Celery worker.

    Calls ``send_queued_mail_until_done`` directly rather than going through the
    management command: ``Command.handle`` reads ``options['lockfile']`` and
    ``options['processes']`` straight out of the argparse namespace, so invoking
    it bare raises ``KeyError: 'lockfile'`` and the beat task never dispatches
    anything. The lockfile/processes/log-level arguments all have defaults.
    """
    from post_office.mail import send_queued_mail_until_done

    send_queued_mail_until_done()
    logger.info("Queued mail processed")
