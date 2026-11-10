from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import UUIDBaseModel
from apps.seating.models import EventSeat


class Booking(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    PAID_STATUSES = (Status.CONFIRMED, Status.REFUNDED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    source_hold_group_id = models.UUIDField(unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking {self.id} ({self.status})"

    @property
    def total_amount(self):
        return sum((ticket.price for ticket in self.tickets.all()), Decimal("0.00"))

    def held_seats(self):
        return EventSeat.objects.filter(
            tickets__booking=self, tickets__status="pending"
        )

    @property
    def event(self):
        ticket = self.tickets.select_related("event_seat__event").first()
        return ticket.event_seat.event if ticket else None
