from django.db import models

from apps.common.models import UUIDBaseModel


class Notification(UUIDBaseModel):
    class NotificationType(models.TextChoices):
        BOOKING_CONFIRMATION = "booking_confirmation", "Booking Confirmation"
        EVENT_CANCELLED_REFUND = "event_cancelled_refund", "Event Cancelled Refund"
        PAYOUT_READY = "payout_ready", "Payout Ready"
        PAYOUT_SETTLED = "payout_settled", "Payout Settled"
        EVENT_REMINDER = "event_reminder", "Event Reminder"

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=32, choices=NotificationType.choices)
    message = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} to {self.user_id} ({self.status})"
