"""A no-op email backend for testing / when no mail service is configured.

Unlike Django's built-in ``dummy`` backend (which discards messages), this one
records what it "sends" into ``django.core.mail.outbox`` so tests and admins can
inspect the output. It never raises, so post_office marks emails as sent.
"""

import logging

from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("post_office")


class DummyEmailBackend(BaseEmailBackend):
    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        for message in email_messages:
            mail.outbox.append(message)
            logger.info("Dummy email to %s: %s", message.to, message.subject)
        return len(email_messages)
