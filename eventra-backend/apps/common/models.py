import uuid

from django.db import models


class UUIDBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class AllObjectsManager(models.Manager):
    """
    Unfiltered manager — functionally identical to models.Manager(),
    just named so ruff's DJ012 check recognizes it as a manager
    declaration instead of miscategorizing it.
    """


class SoftDeleteModel(UUIDBaseModel):
    is_active = models.BooleanField(default=True)

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
