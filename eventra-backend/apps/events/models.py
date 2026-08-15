from decimal import Decimal

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, UUIDBaseModel

MAX_COVER_IMAGE_SIZE_MB = 5
EVENT_SEARCH_CONFIG = "english"


def validate_cover_image_size(file) -> None:
    max_bytes = MAX_COVER_IMAGE_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(
            f"Cover image must be {MAX_COVER_IMAGE_SIZE_MB}MB or smaller."
        )


class Event(SoftDeleteModel):
    class EventType(models.TextChoices):
        GENERAL = "general", "General"
        SPORTS_MATCH = "sports_match", "Sports Match"

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    organizer = models.ForeignKey(
        "users.User", on_delete=models.PROTECT, related_name="organized_events"
    )
    venue = models.ForeignKey(
        "venues.Venue", on_delete=models.SET_NULL, null=True, related_name="events"
    )
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.SET_NULL,
        null=True,
        related_name="events",
    )

    league = models.ForeignKey(
        "sports.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    home_team = models.ForeignKey(
        "sports.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="home_events",
    )
    away_team = models.ForeignKey(
        "sports.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="away_events",
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True, db_index=True)
    description = models.TextField()
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING_APPROVAL
    )
    is_seated = models.BooleanField(default=True)
    cover_image = models.ImageField(
        upload_to="event_covers/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "webp"]),
            validate_cover_image_size,
        ],
    )
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["organizer"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["event_type", "start_datetime"]),
            GinIndex(
                SearchVector("title", "description", config=EVENT_SEARCH_CONFIG),
                name="event_search_gin_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(is_active=True),
                name="uniq_active_event_slug",
            ),
            models.CheckConstraint(
                condition=Q(end_datetime__gt=F("start_datetime")),
                name="event_end_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    Q(home_team__isnull=True)
                    | Q(away_team__isnull=True)
                    | ~Q(home_team=F("away_team"))
                ),
                name="event_home_away_team_distinct",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_title = self.title

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            if not self.slug:
                self.slug = slugify(self.title, allow_unicode=True) or str(self.id)
        elif self.title != self._loaded_title:
            self.slug = slugify(self.title, allow_unicode=True) or str(self.id)

        super().save(*args, **kwargs)
        self._loaded_title = self.title

    def __str__(self) -> str:
        return self.title


class TicketTier(UUIDBaseModel):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ticket_tiers"
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price"]
        indexes = [models.Index(fields=["event"])]

    def __str__(self) -> str:
        return f"{self.name} — {self.event.title} (${self.price})"


class TierSectionMapping(UUIDBaseModel):
    ticket_tier = models.ForeignKey(
        TicketTier, on_delete=models.CASCADE, related_name="section_mappings"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="tier_section_mappings"
    )
    section = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "section"], name="unique_event_section_mapping"
            ),
        ]
        indexes = [models.Index(fields=["event"])]

    def __str__(self) -> str:
        return f"{self.event.title} — {self.section} → {self.ticket_tier.name}"
