from django.core.validators import MinLengthValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import SoftDeleteModel, UUIDBaseModel


class Venue(SoftDeleteModel):
    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    country = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
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
