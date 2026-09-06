from django.db import models

from apps.common.models import UUIDBaseModel


class OrganizerPayout(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"

    event = models.OneToOneField(
        "events.Event", on_delete=models.PROTECT, related_name="payout"
    )

    gross_revenue = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    payout_reference = models.CharField(max_length=50, unique=True)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    settled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payout {self.payout_reference} ({self.status})"
