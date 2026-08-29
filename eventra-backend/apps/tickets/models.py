import secrets

from django.db import models

from apps.common.models import UUIDBaseModel


def _generate_ticket_code() -> str:
    return secrets.token_urlsafe(8)


class Ticket(UUIDBaseModel):
    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        USED = "used", "Used"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    event_seat = models.OneToOneField(
        "seating.EventSeat",
        on_delete=models.PROTECT,
        related_name="ticket",
    )
    ticket_code = models.CharField(
        max_length=32,
        unique=True,
        default=_generate_ticket_code,
        editable=False,
    )
    attendee_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VALID,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["booking"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket {self.ticket_code} ({self.status})"
