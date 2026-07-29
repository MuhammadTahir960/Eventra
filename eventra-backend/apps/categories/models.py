from django.db import models
from django.utils.text import slugify
from apps.common.models import SoftDeleteModel


class Category(SoftDeleteModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

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
