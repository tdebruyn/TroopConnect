from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.mail import EmailMessage
from django.test import RequestFactory
from django.urls import reverse
from post_office import mail as post_office_mail
from post_office.models import STATUS, Email

from members.context_processors import mail_queue_status
from members.models import Account, Person, Role
from tests.mail import MailTestCase
from troopconnect.dummy_backend import DummyEmailBackend


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
