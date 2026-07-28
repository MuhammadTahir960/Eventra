from django.db import IntegrityError, transaction
from rest_framework import serializers
from .models import League, Sport, Team


class IntegrityErrorHandlingMixin:
    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"name": "This name already exists in the given scope."}
            ) from exc

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"name": "This name already exists in the given scope."}
            ) from exc


class SportSerializer(IntegrityErrorHandlingMixin, serializers.ModelSerializer):
    class Meta:
        model = Sport
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")

        qs = Sport.objects.filter(name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A sport with this name already exists.")
        return value


class ScopedUniqueNameMixin:
    scoped_model = None

    def validate(self, attrs):
        sport = attrs.get("sport", getattr(self.instance, "sport", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        if name is not None:
            name = name.strip()
            if not name:
                raise serializers.ValidationError({"name": "Name cannot be blank."})
            attrs["name"] = name

        if sport and name:
            qs = self.scoped_model.objects.filter(sport=sport, name__iexact=name)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                model_label = self.scoped_model.__name__.lower()
                raise serializers.ValidationError(
                    {
                        "name": f"A {model_label} with this name already exists for this sport."
                    }
                )
        return attrs


class LeagueSerializer(
    IntegrityErrorHandlingMixin, ScopedUniqueNameMixin, serializers.ModelSerializer
):
    scoped_model = League

    class Meta:
        model = League
        fields = ["id", "sport", "name"]
        read_only_fields = ["id"]


class TeamSerializer(
    IntegrityErrorHandlingMixin, ScopedUniqueNameMixin, serializers.ModelSerializer
):
    scoped_model = Team

    class Meta:
        model = Team
        fields = ["id", "sport", "name"]
        read_only_fields = ["id"]
