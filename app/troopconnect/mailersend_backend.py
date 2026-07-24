"""Custom Django email backend for MailerSend HTTP API."""

import logging

import requests
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("post_office")


class MailerSendBackend(BaseEmailBackend):
    """Email backend that sends via the MailerSend HTTP API."""

    API_URL = "https://api.mailersend.com/v1/email"

    def __init__(self, api_key=None, **kwargs):
        super().__init__(**kwargs)
        from django.conf import settings

        self.api_key = api_key or getattr(settings, "MAILERSEND_API_KEY", "")

    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        count = 0
        for message in email_messages:
            if self._send(message):
                count += 1
        return count

    def _send(self, message):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Mailersend-Id": "troopconnect",
        }

        payload = {
            "from": {
                "email": message.from_email,
            },
            "to": [{"email": addr} for addr in message.to],
            "subject": message.subject,
        }

        if message.cc:
            payload["cc"] = [{"email": addr} for addr in message.cc]
        if message.bcc:
            payload["bcc"] = [{"email": addr} for addr in message.bcc]
        if message.reply_to:
            payload["reply_to"] = [{"email": addr} for addr in message.reply_to]

        # Build body
        if message.content_subtype == "html":
            payload["html"] = message.body
        else:
            payload["text"] = message.body

        # Handle multipart (both text and html)
        if hasattr(message, "alternatives") and message.alternatives:
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    payload["html"] = content
                elif mimetype == "text/plain":
                    payload["text"] = content

        # Handle attachments
        if message.attachments:
            payload["attachments"] = []
            for attachment in message.attachments:
                if isinstance(attachment, tuple):
                    filename, content, mimetype = attachment
                else:
                    continue
                import base64

                if isinstance(content, str):
                    content = content.encode("utf-8")
                payload["attachments"].append(
                    {
                        "id": filename,
                        "filename": filename,
                        "content": base64.b64encode(content).decode("utf-8"),
                        "disposition": "attachment",
                    }
                )

        try:
            response = requests.post(
                self.API_URL, json=payload, headers=headers, timeout=30
            )
            if response.status_code in (200, 202):
                logger.info("Email sent via MailerSend to %s", message.to)
                return True
            else:
                logger.error(
                    "MailerSend API error %s: %s",
                    response.status_code,
                    response.text,
                )
                return False
        except Exception:
            logger.exception("Failed to send email via MailerSend")
            if not self.fail_silently:
                raise
            return False
