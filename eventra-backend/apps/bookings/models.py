import uuid  # noqa: F401

from django.conf import settings
from django.db import models

from apps.common.models import UUIDBaseModel


class Booking(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
        REFUND_FAILED = "refund_failed", "Refund Failed"

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

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=(
            "Decimal dollars, never cents. Cents conversion happens only at "
            "the Stripe checkout boundary -- see "
            "apps/bookings/services.py::checkout_booking()."
        ),
    )

    source_hold_group_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )

    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking {self.id} ({self.status})"
