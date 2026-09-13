"""Tests for the MailerSend HTTP backend — the only path real email takes.

``MAIL_SEND_MODE`` defaults to "real" whenever ``MAILERSEND_API_KEY`` is set, so
in production every reminder, attestation and section message ends up in
``MailerSendBackend._send``. A mistake building the payload or reading the
response drops mail silently: post_office only sees a falsy return value.

``requests.post`` is mocked throughout, so nothing leaves the test process.
"""

import base64
from unittest.mock import Mock, patch

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase

from troopconnect.mailersend_backend import MailerSendBackend

POST_PATH = "troopconnect.mailersend_backend.requests.post"


def _response(status_code, text=""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    return response


class MailerSendTestBase(SimpleTestCase):
    def setUp(self):
        self.backend = MailerSendBackend(api_key="test-key")

    def post_for(self, message, response=None):
        """Send one message with requests.post mocked; return (count, post_mock)."""
        with patch(POST_PATH, return_value=response or _response(200)) as post:
            count = self.backend.send_messages([message])
        return count, post

    def payload_for(self, message, response=None):
        """Send one message and return the JSON payload handed to the API."""
        _, post = self.post_for(message, response)
        return post.call_args.kwargs["json"]


class PayloadTest(MailerSendTestBase):
    def test_plain_email_uses_text_body(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        payload = self.payload_for(message)
        self.assertEqual(payload["text"], "Corps")
        self.assertNotIn("html", payload)

    def test_html_content_subtype_uses_html_body(self):
        message = EmailMessage("Sujet", "<p>Corps</p>", "from@test.be", ["to@test.be"])
        message.content_subtype = "html"
        payload = self.payload_for(message)
        self.assertEqual(payload["html"], "<p>Corps</p>")
        self.assertNotIn("text", payload)

    def test_alternatives_override_the_body(self):
        """A text body plus an HTML alternative must send both parts."""
        message = EmailMultiAlternatives("Sujet", "texte", "from@test.be", ["to@test.be"])
        message.attach_alternative("<p>html</p>", "text/html")
        payload = self.payload_for(message)
        self.assertEqual(payload["text"], "texte")
        self.assertEqual(payload["html"], "<p>html</p>")

    def test_from_and_to_are_mapped(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["a@test.be", "b@test.be"])
        payload = self.payload_for(message)
        self.assertEqual(payload["from"], {"email": "from@test.be"})
        self.assertEqual(
            payload["to"], [{"email": "a@test.be"}, {"email": "b@test.be"}]
        )
        self.assertEqual(payload["subject"], "Sujet")

    def test_optional_recipient_fields_omitted_when_empty(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        payload = self.payload_for(message)
        for key in ("cc", "bcc", "reply_to", "attachments"):
            self.assertNotIn(key, payload)

    def test_cc_bcc_and_reply_to_are_included_when_set(self):
        message = EmailMessage(
            "Sujet",
            "Corps",
            "from@test.be",
            ["to@test.be"],
            cc=["cc@test.be"],
            bcc=["bcc@test.be"],
            reply_to=["reply@test.be"],
        )
        payload = self.payload_for(message)
        self.assertEqual(payload["cc"], [{"email": "cc@test.be"}])
        self.assertEqual(payload["bcc"], [{"email": "bcc@test.be"}])
        self.assertEqual(payload["reply_to"], [{"email": "reply@test.be"}])

    def test_attachment_content_is_base64_encoded(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        message.attach("attestation.pdf", b"PDFDATA", "application/pdf")
        attachment = self.payload_for(message)["attachments"][0]
        self.assertEqual(attachment["filename"], "attestation.pdf")
        self.assertEqual(attachment["id"], "attestation.pdf")
        self.assertEqual(attachment["disposition"], "attachment")
        self.assertEqual(
            base64.b64decode(attachment["content"]), b"PDFDATA"
        )

    def test_string_attachment_content_is_utf8_encoded(self):
        """Django keeps str attachment content as str; the API needs base64."""
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        message.attach("note.txt", "héllo", "text/plain")
        attachment = self.payload_for(message)["attachments"][0]
        self.assertEqual(base64.b64decode(attachment["content"]), "héllo".encode())

    def test_malformed_attachment_is_skipped(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        message.attachments = ["not-a-tuple"]
        payload = self.payload_for(message)
        self.assertEqual(payload["attachments"], [])

    def test_authorization_header_uses_api_key(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        _, post = self.post_for(message)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer test-key")

    def test_request_has_a_timeout(self):
        """Without a timeout a hung MailerSend call would wedge the worker."""
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        _, post = self.post_for(message)
        self.assertEqual(post.call_args.kwargs["timeout"], 30)


class ApiKeyTest(SimpleTestCase):
    def test_api_key_falls_back_to_settings(self):
        with self.settings(MAILERSEND_API_KEY="from-settings"):
            self.assertEqual(MailerSendBackend().api_key, "from-settings")

    def test_explicit_api_key_wins_over_settings(self):
        with self.settings(MAILERSEND_API_KEY="from-settings"):
            self.assertEqual(MailerSendBackend(api_key="explicit").api_key, "explicit")


class ResponseHandlingTest(MailerSendTestBase):
    def test_accepted_returns_one(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        for status in (200, 202):
            with self.subTest(status=status):
                count, _ = self.post_for(message, _response(status))
                self.assertEqual(count, 1)

    def test_client_error_returns_zero_and_logs(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        with self.assertLogs("post_office", level="ERROR") as logs:
            count, _ = self.post_for(message, _response(422, "unprocessable"))
        self.assertEqual(count, 0)
        self.assertIn("422", "".join(logs.output))
        self.assertIn("unprocessable", "".join(logs.output))

    def test_server_error_returns_zero(self):
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        count, _ = self.post_for(message, _response(500))
        self.assertEqual(count, 0)

    def test_partial_failure_counts_only_successes(self):
        """One bad recipient must not mask the messages that did go out."""
        good = EmailMessage("Sujet", "Corps", "from@test.be", ["good@test.be"])
        bad = EmailMessage("Sujet", "Corps", "from@test.be", ["bad@test.be"])
        with patch(
            POST_PATH, side_effect=[_response(200), _response(422, "bad")]
        ) as post:
            count = self.backend.send_messages([good, bad])
        self.assertEqual(count, 1)
        self.assertEqual(post.call_count, 2)

    def test_multiple_messages_all_succeed(self):
        messages = [
            EmailMessage("Sujet", "Corps", "from@test.be", [f"{i}@test.be"])
            for i in range(3)
        ]
        with patch(POST_PATH, return_value=_response(202)):
            self.assertEqual(self.backend.send_messages(messages), 3)

    def test_no_messages_short_circuits_without_calling_the_api(self):
        with patch(POST_PATH) as post:
            self.assertEqual(self.backend.send_messages([]), 0)
        post.assert_not_called()


class ExceptionHandlingTest(MailerSendTestBase):
    def test_exception_is_swallowed_when_fail_silently(self):
        self.backend.fail_silently = True
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        with patch(POST_PATH, side_effect=ConnectionError("boom")):
            count = self.backend.send_messages([message])
        self.assertEqual(count, 0)

    def test_exception_propagates_when_not_fail_silently(self):
        """post_office relies on this to retry and eventually mark the mail failed."""
        message = EmailMessage("Sujet", "Corps", "from@test.be", ["to@test.be"])
        with patch(POST_PATH, side_effect=ConnectionError("boom")):
            with self.assertRaises(ConnectionError):
                self.backend.send_messages([message])


class ConnectionTest(MailerSendTestBase):
    def test_open_and_close_are_noops(self):
        """BaseEmailBackend.open() returns None; post_office calls both."""
        self.assertTrue(self.backend.open())
        self.assertIsNone(self.backend.close())
