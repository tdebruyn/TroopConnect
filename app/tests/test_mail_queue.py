from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.mail import EmailMessage
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from post_office import mail as post_office_mail
from post_office.models import STATUS, Email

from members.context_processors import mail_queue_status
from members.models import Account, Person, Role
from tests.mail import DUMMY_POST_OFFICE, MailTestCase
from troopconnect.dummy_backend import DummyEmailBackend
from troopconnect.tasks import send_queued_mail


class EmailQueueTest(MailTestCase):
    def test_mail_send_queues(self):
        post_office_mail.send(
            recipients=["to@test.be"],
            sender="from@test.be",
            subject="Hello",
            message="Body",
        )
        self.assertEqual(Email.objects.get().status, STATUS.queued)

    def test_dummy_backend_records_to_outbox(self):
        backend = DummyEmailBackend()
        message = EmailMessage(
            subject="Hi", body="Body", to=["to@test.be"], from_email="from@test.be"
        )
        sent = backend.send_messages([message])
        self.assertEqual(sent, 1)
        self.assertEqual(mail.outbox[-1].subject, "Hi")

    def test_dispatch_marks_sent_via_dummy(self):
        post_office_mail.send(
            recipients=["to@test.be"],
            sender="from@test.be",
            subject="Hello",
            message="Body",
        )
        Email.objects.get().dispatch()
        self.assertEqual(Email.objects.get().status, STATUS.sent)


class SendQueuedMailTaskTest(TransactionTestCase):
    """The beat task that flushes the queue is the email pipeline's heartbeat.

    Schedule: CELERY_BEAT_SCHEDULE["send-queued-mail"], every 5 minutes. It had
    no coverage, and these tests caught it calling post_office's management
    command bare — ``Command.handle`` reads ``options['lockfile']`` out of the
    argparse namespace, so every run raised KeyError and dispatched nothing.

    TransactionTestCase rather than TestCase because
    ``send_queued_mail_until_done`` closes the DB connection when it finishes —
    right for a worker process, fatal inside TestCase's wrapping transaction.
    """

    def setUp(self):
        super().setUp()
        self._po_override = override_settings(POST_OFFICE=DUMMY_POST_OFFICE)
        self._po_override.enable()
        self.addCleanup(self._po_override.disable)
        # Same guard as MailTestCase: queueing fires post_office's email_queued
        # signal, whose handler would .delay() to the real broker. The whole
        # point here is that the mail stays queued until the beat task runs.
        self._delay_patcher = patch("post_office.tasks.send_queued_mail.delay")
        self._delay_patcher.start()
        self.addCleanup(self._delay_patcher.stop)

    def test_task_runs_on_an_empty_queue(self):
        """Regression guard: the task must not need options configured."""
        send_queued_mail()
        self.assertFalse(Email.objects.exists())

    def test_queued_mail_is_actually_sent(self):
        post_office_mail.send(
            recipients=["to@test.be"],
            sender="from@test.be",
            subject="Hello",
            message="Body",
        )
        self.assertEqual(Email.objects.get().status, STATUS.queued)

        send_queued_mail()

        self.assertEqual(Email.objects.get().status, STATUS.sent)


class MailQueueViewTest(MailTestCase):
    def setUp(self):
        super().setUp()
        self.role_parent = Role.objects.get(short="p")
        self.staff = Person.objects.create(
            first_name="Staff", last_name="User",
            primary_role=self.role_parent, status="a",
        )
        self.staff_account = Account.objects.create_user(
            email="staff@test.be", password="pw", person=self.staff, is_staff=True,
        )
        self.client.force_login(self.staff_account)

    def _failed_email(self):
        post_office_mail.send(
            recipients=["to@test.be"],
            sender="from@test.be",
            subject="Hello",
            message="Body",
        )
        Email.objects.update(status=STATUS.failed)
        return Email.objects.get()

    def test_anonymous_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("members:mail_queue"))
        self.assertEqual(response.status_code, 302)

    def test_non_staff_forbidden(self):
        other = Person.objects.create(
            first_name="No", last_name="Staff",
            primary_role=self.role_parent, status="a",
        )
        other_account = Account.objects.create_user(
            email="nostaff@test.be", password="pw", person=other,
        )
        self.client.force_login(other_account)
        response = self.client.get(reverse("members:mail_queue"))
        self.assertEqual(response.status_code, 403)

    def test_staff_sees_failed_count(self):
        self._failed_email()
        response = self.client.get(reverse("members:mail_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["failed_count"], 1)
        self.assertEqual(response.context["failed_mail_count"], 1)

    def test_requeue_moves_failed_to_queued(self):
        self._failed_email()
        response = self.client.post(reverse("members:mail_queue"), {"action": "requeue"})
        self.assertRedirects(response, reverse("members:mail_queue"))
        email = Email.objects.get()
        self.assertEqual(email.status, STATUS.queued)
        self.assertEqual(email.number_of_retries, 0)

    def test_purge_deletes_failed(self):
        self._failed_email()
        response = self.client.post(reverse("members:mail_queue"), {"action": "purge"})
        self.assertRedirects(response, reverse("members:mail_queue"))
        self.assertFalse(Email.objects.exists())


class MailQueueContextProcessorTest(MailTestCase):
    def setUp(self):
        super().setUp()
        self.role_parent = Role.objects.get(short="p")
        self.staff = Person.objects.create(
            first_name="Staff", last_name="User",
            primary_role=self.role_parent, status="a",
        )
        self.staff_account = Account.objects.create_user(
            email="staff@test.be", password="pw", person=self.staff, is_staff=True,
        )
        post_office_mail.send(
            recipients=["to@test.be"],
            sender="from@test.be",
            subject="Hello",
            message="Body",
        )
        Email.objects.update(status=STATUS.failed)

    def test_anonymous_gets_nothing(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertEqual(mail_queue_status(request), {})

    def test_staff_gets_failed_count(self):
        request = RequestFactory().get("/")
        request.user = self.staff_account
        self.assertEqual(mail_queue_status(request)["failed_mail_count"], 1)
