import secrets

from django.db import models

from apps.common.models import UUIDBaseModel


def _generate_ticket_code() -> str:
    return secrets.token_urlsafe(8)


class Ticket(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        VALID = "valid", "Valid"
        USED = "used", "Used"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    event_seat = models.ForeignKey(
        "seating.EventSeat",
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    ticket_code = models.CharField(
        max_length=32,
        unique=True,
        default=_generate_ticket_code,
        editable=False,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["booking"])]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "event_seat"], name="uniq_ticket_booking_seat"
            ),
            models.UniqueConstraint(
                fields=["event_seat"],
                condition=~models.Q(status="cancelled"),
                name="uniq_active_ticket_per_seat",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket {self.ticket_code} ({self.status})"

    @property
    def attendee_name(self):
        user = self.booking.user
        return "" if user.deleted_at else user.full_name
