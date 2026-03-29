import uuid

from django.db import models


class SectionMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        "members.Person", on_delete=models.CASCADE, related_name="sent_messages"
    )
    section = models.ForeignKey(
        "members.Section",
        on_delete=models.CASCADE,
        related_name="messages",
        null=True,
        blank=True,
    )
    school_year = models.ForeignKey(
        "members.SchoolYear", on_delete=models.CASCADE, related_name="messages"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        section_name = self.section.name if self.section else "Tous les utilisateurs"
        return f"{self.subject} ({section_name} - {self.created_at:%d/%m/%Y})"


class SectionMessageRecipient(models.Model):
    message = models.ForeignKey(
        SectionMessage, on_delete=models.CASCADE, related_name="recipients"
    )
    parent = models.ForeignKey(
        "members.Person", on_delete=models.CASCADE, related_name="received_messages"
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("message", "parent")]

    def __str__(self):
        status = "envoyé" if self.sent_at else "ignoré"
        return f"{self.parent} - {self.message.subject} ({status})"
