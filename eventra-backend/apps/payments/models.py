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
        REFUNDED = "refunded", "Refunded"

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

    amount = models.IntegerField(
        help_text=(
            "Smallest currency unit (cents) -- int(round(total_amount * 100)). "
            "Never the same decimal-dollars representation as Booking.total_amount."
        )
    )

    currency = models.CharField(max_length=3, default="usd")

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
