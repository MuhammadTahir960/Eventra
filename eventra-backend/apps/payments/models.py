from django.db import models
from django.db.models import Q

from apps.bookings.models import Booking
from apps.common.models import UUIDBaseModel


class Payment(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    booking = models.OneToOneField(
        Booking,
        on_delete=models.PROTECT,
        related_name="payment",
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    client_secret = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["stripe_payment_intent_id"])]
        constraints = [
            models.UniqueConstraint(
                fields=["stripe_payment_intent_id"],
                condition=~Q(stripe_payment_intent_id=""),
                name="uniq_payment_stripe_payment_intent_id",
            )
        ]

    def __str__(self):
        return f"Payment for booking {self.booking_id} ({self.status})"


class Refund(UUIDBaseModel):
    class Reason(models.TextChoices):
        CANCELLED_EVENT = "cancelled_event", "Event cancelled"
        UNAVAILABLE = "unavailable", "Booking couldn't be completed"
        POSTPONED = "postponed", "Refund requested after postponement"
        ABANDONED_EVENT = "abandoned_event", "Event abandoned"
        PRICE_DROP = "price_drop", "Price lowered"

    FULL_REASONS = (Reason.CANCELLED_EVENT, Reason.UNAVAILABLE, Reason.POSTPONED)

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="refunds"
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    stripe_refund_id = models.CharField(max_length=255, blank=True, default="")
    key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking"],
                condition=Q(reason__in=["cancelled_event", "unavailable", "postponed"]),
                name="uniq_full_refund_per_booking",
            )
        ]

    def __str__(self):
        return f"Refund {self.id} ({self.reason}, {self.status})"


class RefundItem(UUIDBaseModel):
    refund = models.ForeignKey(Refund, on_delete=models.PROTECT, related_name="items")
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.PROTECT, related_name="refund_items"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refund", "ticket"], name="uniq_refund_item_seat"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="refund_item_amount_positive"
            ),
        ]

    def __str__(self):
        return f"{self.amount} for {self.ticket_id}"
