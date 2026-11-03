from django.db import models
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel


class Category(SoftDeleteModel):
    class Icon(models.TextChoices):
        MUSIC = "music", "Music"
        MICROPHONE = "microphone", "Microphone"
        LAUGH = "laugh", "Laughing face"
        FOOTBALL = "football", "Football"
        BOXING = "boxing", "Boxing glove"
        GAMEPAD = "gamepad", "Game controller"
        TOOLS = "tools", "Tools"
        PRESENTATION = "presentation", "Presentation"
        THEATRE = "theatre", "Theatre masks"
        QUILL = "quill", "Quill"
        PARTY = "party", "Party"
        FOOD = "food", "Food"
        PALETTE = "palette", "Palette"
        BALLOONS = "balloons", "Balloons"
        TICKET = "ticket", "Ticket"

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    icon = models.CharField(max_length=20, choices=Icon.choices, default=Icon.TICKET)
    sort_order = models.PositiveIntegerField(default=0)
    admin_only = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(is_active=True),
                name="uniq_active_category_name",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(is_active=True),
                name="uniq_active_category_slug",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_name = self.name

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            if not self.slug:
                self.slug = slugify(self.name, allow_unicode=True) or str(self.id)
        elif self.name != self._loaded_name:
            self.slug = slugify(self.name, allow_unicode=True) or str(self.id)

        super().save(*args, **kwargs)
        self._loaded_name = self.name

    def __str__(self) -> str:
        return self.name
