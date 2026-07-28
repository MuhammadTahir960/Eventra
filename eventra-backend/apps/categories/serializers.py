from django.db.models import Q
from django.utils.text import slugify
from rest_framework import serializers
from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "sort_order"]
        read_only_fields = ["id", "slug"]

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        if name:
            slug = slugify(name, allow_unicode=True)
            qs = Category.all_objects.filter(
                Q(name__iexact=name) | Q(slug__iexact=slug)
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            existing = qs.first()
            if existing is not None:
                if not existing.is_active:
                    raise serializers.ValidationError(
                        {
                            "name": (
                                "A category with this name or slug already exists (inactive). "
                                "Please restore the existing category."
                            )
                        }
                    )
                raise serializers.ValidationError(
                    {"name": "A category with this name or slug already exists."}
                )
        return attrs
