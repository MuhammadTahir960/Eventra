from django.db import models

from apps.common.models import UUIDBaseModel


class EventSeat(UUIDBaseModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        HELD = "held", "Held"
        BOOKED = "booked", "Booked"

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="event_seats"
    )
    seat = models.ForeignKey(
        "venues.Seat", on_delete=models.PROTECT, related_name="event_seats"
    )
    ticket_tier = models.ForeignKey(
        "events.TicketTier", on_delete=models.PROTECT, related_name="event_seats"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )
    price_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    held_booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="held_event_seats",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "seat"], name="unique_event_seat"),
        ]
        indexes = [
            models.Index(fields=["event", "status"]),
        ]
        ordering = ["seat__section", "seat__row_label", "seat__seat_number"]

    def __str__(self) -> str:
        return f"{self.event.title} — {self.seat} ({self.status})"


class SeatHold(UUIDBaseModel):
    group_id = models.UUIDField()
    event_seat = models.OneToOneField(
        EventSeat, on_delete=models.CASCADE, related_name="hold"
    )
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="seat_holds"
    )
    held_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"]),
            models.Index(fields=["group_id"]),
        ]

    def __str__(self) -> str:
        return f"Hold on {self.event_seat_id} by user {self.user_id}, expires {self.expires_at}"
