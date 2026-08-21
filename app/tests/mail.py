from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings

# Route all sends through the no-op dummy backend so mail tests never touch the
# real MailerSend API.
DUMMY_POST_OFFICE = {
    **settings.POST_OFFICE,
    "BACKENDS": {"default": "troopconnect.dummy_backend.DummyEmailBackend"},
}


class MailTestCase(TestCase):
    """Base TestCase that uses the dummy backend and never dispatches to Celery.

    With DEFAULT_PRIORITY="medium", ``mail.send()`` queues an Email and fires
    post_office's ``email_queued`` signal; with CELERY_ENABLED the handler calls
    ``send_queued_mail.delay()``, which would enqueue to the real broker (and a
    running worker would really send). Patching that out keeps queueing
    side-effect-free. Tests that want to exercise actual delivery can call
    ``post_office.mail.send_queued_mail_until_done()`` directly.
    """

    def setUp(self):
        super().setUp()
        self._po_override = override_settings(POST_OFFICE=DUMMY_POST_OFFICE)
        self._po_override.enable()
        self.addCleanup(self._po_override.disable)
        self._delay_patcher = mock.patch("post_office.tasks.send_queued_mail.delay")
        self._delay_patcher.start()
        self.addCleanup(self._delay_patcher.stop)
