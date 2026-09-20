from django.conf import settings
from django.core.validators import MinLengthValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import SoftDeleteModel, UUIDBaseModel
from apps.common.validators import IMAGE_EXTENSION_VALIDATOR, validate_image_upload_size


class Venue(SoftDeleteModel):
    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    country = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    photo = models.ImageField(
        upload_to="venue_photos/",
        blank=True,
        null=True,
        validators=[IMAGE_EXTENSION_VALIDATOR, validate_image_upload_size],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                Lower("city"),
                condition=models.Q(is_active=True),
                name="unique_venue_name_per_city_ci",
            )
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} — ({self.city}, {self.country})"


class Seat(UUIDBaseModel):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="seats")
    section = models.CharField(max_length=50)
    row_label = models.CharField(max_length=10)
    seat_number = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "section", "row_label", "seat_number"],
                name="unique_seat_per_venue",
            )
        ]
        ordering = ["section", "row_label", "seat_number"]

    def __str__(self) -> str:
        return f"{self.venue.name} — {self.section}/{self.row_label}/{self.seat_number}"


class VenueRequest(UUIDBaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        FULFILLED = "fulfilled", "Fulfilled"
        REJECTED = "rejected", "Rejected"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="venue_requests",
    )
    venue_name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    admin_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["requested_by"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.venue_name} ({self.city}) — {self.status}"
