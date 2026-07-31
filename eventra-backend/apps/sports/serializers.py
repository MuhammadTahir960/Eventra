from rest_framework import serializers
from apps.common.serializers import IntegrityErrorHandlingMixin
from .models import League, Sport, Team
from .services import (
    DuplicateLeagueError,
    DuplicateSportError,
    DuplicateTeamError,
    ensure_unique_league_name,
    ensure_unique_sport_name,
    ensure_unique_team_name,
)


class SportSerializer(IntegrityErrorHandlingMixin, serializers.ModelSerializer):
    integrity_error_field = "name"
    integrity_error_message = "This name already exists in the given scope."

    class Meta:
        model = Sport
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be blank.")

        exclude_pk = self.instance.pk if self.instance is not None else None
        try:
            ensure_unique_sport_name(value, exclude_pk=exclude_pk)
        except DuplicateSportError as exc:
            raise serializers.ValidationError(str(exc))
        return value


class ScopedUniqueNameMixin:
    unique_check = None

    def validate(self, attrs):
        sport = attrs.get("sport", getattr(self.instance, "sport", None))
        name = attrs.get("name", getattr(self.instance, "name", None))

        if name is not None:
            name = name.strip()
            if not name:
                raise serializers.ValidationError({"name": "Name cannot be blank."})
            attrs["name"] = name

        if sport and name:
            exclude_pk = self.instance.pk if self.instance is not None else None
            try:
                self.unique_check(sport, name, exclude_pk=exclude_pk)
            except (DuplicateLeagueError, DuplicateTeamError) as exc:
                raise serializers.ValidationError({"name": str(exc)})
        return attrs


class LeagueSerializer(
    IntegrityErrorHandlingMixin, ScopedUniqueNameMixin, serializers.ModelSerializer
):
    unique_check = staticmethod(ensure_unique_league_name)
    integrity_error_field = "name"
    integrity_error_message = "This name already exists in the given scope."

    class Meta:
        model = League
        fields = ["id", "sport", "name"]
        read_only_fields = ["id"]


class TeamSerializer(
    IntegrityErrorHandlingMixin, ScopedUniqueNameMixin, serializers.ModelSerializer
):
    unique_check = staticmethod(ensure_unique_team_name)
    integrity_error_field = "name"
    integrity_error_message = "This name already exists in the given scope."

    class Meta:
        model = Team
        fields = ["id", "sport", "name"]
        read_only_fields = ["id"]
