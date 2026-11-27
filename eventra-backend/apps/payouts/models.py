from django.db import models
from django.db.models import Q

from apps.common.models import UUIDBaseModel
from apps.common.validators import validate_display_name


class OrganizerPayout(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"

    event = models.OneToOneField(
        "events.Event", on_delete=models.PROTECT, related_name="payout"
    )

    gross_revenue = models.DecimalField(max_digits=18, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=18, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    settled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payout for {self.event_id} ({self.status})"

    @property
    def net_amount(self):
        return self.gross_revenue - self.platform_fee


class PartnerQuerySet(models.QuerySet):
    def payable(self):
        return self.filter(is_active=True, payout_account__isnull=False)


class Partner(UUIDBaseModel):
    objects = PartnerQuerySet.as_manager()

    name = models.CharField(max_length=200, validators=[validate_display_name])
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PayoutAccount(UUIDBaseModel):
    class Method(models.TextChoices):
        BANK = "bank", "Bank account"
        WALLET = "wallet", "Mobile wallet"

    organizer = models.OneToOneField(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payout_account",
    )
    partner = models.OneToOneField(
        Partner,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payout_account",
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    provider = models.CharField(max_length=100, validators=[validate_display_name])
    holder_name = models.CharField(max_length=200, validators=[validate_display_name])
    account_number = models.BinaryField(unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(organizer__isnull=False, partner__isnull=True)
                | Q(organizer__isnull=True, partner__isnull=False),
                name="payout_account_has_one_owner",
            )
        ]

    def __str__(self) -> str:
        return f"{self.holder_name} ({self.get_method_display()})"
