from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.common.constants import Roles
from apps.common.serializers import IntegrityErrorHandlingMixin

from .models import Event, TicketTier, TierSectionMapping
from .services import (
    ensure_tier_price_mutable,
    resolve_create_status,
    should_retrigger_approval,
    should_retrigger_approval_for_tier,
)


class EventSerializer(IntegrityErrorHandlingMixin, serializers.ModelSerializer):
    integrity_error_field = "slug"
    integrity_error_message = "An event with a conflicting slug already exists."

    class Meta:
        model = Event
        fields = [
            "id",
            "organizer",
            "venue",
            "category",
            "league",
            "home_team",
            "away_team",
            "title",
            "slug",
            "description",
            "event_type",
            "status",
            "is_seated",
            "cover_image",
            "start_datetime",
            "end_datetime",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organizer",
            "slug",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def _current(self, attrs, field):
        """Resolve a field's effective value for both create and partial update."""
        return attrs.get(field, getattr(self.instance, field, None))

    def validate(self, attrs):
        start = self._current(attrs, "start_datetime")
        end = self._current(attrs, "end_datetime")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_datetime": "end_datetime must be after start_datetime."}
            )

        event_type = self._current(attrs, "event_type")
        home_team = self._current(attrs, "home_team")
        away_team = self._current(attrs, "away_team")
        league = self._current(attrs, "league")

        if event_type == Event.EventType.SPORTS_MATCH:
            request = self.context.get("request")
            actor = getattr(request, "user", None)
            if not (actor and actor.is_authenticated and actor.role == Roles.ADMIN):
                raise PermissionDenied(
                    "Only admins can create or edit sports_match events "
                    "— sports fixtures are centrally curated data."
                )
            if not home_team or not away_team:
                raise serializers.ValidationError(
                    "sports_match events require both home_team and away_team."
                )
            if (
                home_team_id := getattr(home_team, "id", home_team)
            ) and home_team_id == getattr(away_team, "id", away_team):
                raise serializers.ValidationError(
                    {"away_team": "away_team must differ from home_team."}
                )
            if league and (
                home_team.sport_id != league.sport_id
                or away_team.sport_id != league.sport_id
            ):
                raise serializers.ValidationError(
                    "home_team/away_team must belong to the same sport as league."
                )
            if home_team.sport_id != away_team.sport_id:
                raise serializers.ValidationError(
                    "home_team and away_team must belong to the same sport."
                )
        elif home_team or away_team or league:
            raise serializers.ValidationError(
                "league/home_team/away_team may only be set on sports_match events."
            )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["organizer"] = request.user
        validated_data["status"] = resolve_create_status(request.user)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        changed_fields = {
            field
            for field in ("venue", "category", "start_datetime", "end_datetime")
            if field in validated_data
            and validated_data[field] != getattr(instance, field)
        }
        if should_retrigger_approval(event=instance, changed_fields=changed_fields):
            validated_data["status"] = Event.Status.PENDING_APPROVAL
        return super().update(instance, validated_data)


class TicketTierSerializer(IntegrityErrorHandlingMixin, serializers.ModelSerializer):
    class Meta:
        model = TicketTier
        fields = ["id", "event", "name", "price", "created_at"]
        read_only_fields = ["id", "event", "created_at"]

    def create(self, validated_data):
        validated_data["event"] = self.context["event"]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        price_changing = (
            "price" in validated_data and validated_data["price"] != instance.price
        )

        if price_changing:
            ensure_tier_price_mutable(instance)

            if should_retrigger_approval_for_tier(instance):
                instance.event.status = Event.Status.PENDING_APPROVAL
                instance.event.save(update_fields=["status", "updated_at"])

        return super().update(instance, validated_data)


class TierSectionMappingSerializer(
    IntegrityErrorHandlingMixin, serializers.ModelSerializer
):
    integrity_error_field = "section"
    integrity_error_message = (
        "This section is already mapped to a different tier for this event."
    )

    class Meta:
        model = TierSectionMapping
        fields = ["id", "ticket_tier", "event", "section", "created_at"]
        read_only_fields = ["id", "ticket_tier", "event", "created_at"]

    def validate(self, attrs):
        ticket_tier = self.context["ticket_tier"]
        event = self.context["event"]
        if ticket_tier.event_id != event.id:
            raise serializers.ValidationError(
                "Ticket tier does not belong to this event."
            )
        return attrs

    def create(self, validated_data):
        validated_data["ticket_tier"] = self.context["ticket_tier"]
        validated_data["event"] = self.context["event"]
        return super().create(validated_data)
