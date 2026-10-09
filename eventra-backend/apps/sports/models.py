from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDBaseModel
from apps.common.validators import IMAGE_EXTENSION_VALIDATOR, validate_image_upload_size

_LOGO_KWARGS = {
    "upload_to": "team_league_logos/",
    "blank": True,
    "validators": [IMAGE_EXTENSION_VALIDATOR, validate_image_upload_size],
}


class Sport(UUIDBaseModel):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unique_sport_name_ci"),
        ]

    def __str__(self) -> str:
        return self.name


class League(UUIDBaseModel):
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="leagues")
    name = models.CharField(max_length=100)
    logo = models.ImageField(**_LOGO_KWARGS)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "sport", name="unique_league_name_per_sport_ci"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.sport.name})"


class Team(UUIDBaseModel):
    sport = models.ForeignKey(Sport, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)
    logo = models.ImageField(**_LOGO_KWARGS)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "sport", name="unique_team_name_per_sport_ci"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
