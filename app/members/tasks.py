from celery import shared_task
from celery.utils.log import get_task_logger
from .views import create_year

logger = get_task_logger(__name__)


@shared_task(name="create_year_task")
def create_year_task():
    logger.info("Running create_year")
    create_year()
