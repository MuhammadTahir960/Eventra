from rest_framework import serializers

from apps.common.serializers import IntegrityErrorHandlingMixin

from .models import Category
from .services import (
    DuplicateCategoryError,
    InactiveDuplicateCategoryError,
    ensure_unique_category_name,
)


class CategorySerializer(IntegrityErrorHandlingMixin, serializers.ModelSerializer):
    integrity_error_field = "name"
    integrity_error_message = "A category with this name or slug already exists."

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "sort_order"]
        read_only_fields = ["id", "slug"]

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        if name:
            exclude_pk = self.instance.pk if self.instance is not None else None
            try:
                ensure_unique_category_name(name, exclude_pk=exclude_pk)
            except InactiveDuplicateCategoryError as exc:
                raise serializers.ValidationError({"name": str(exc)})
            except DuplicateCategoryError as exc:
                raise serializers.ValidationError({"name": str(exc)})
        return attrs
