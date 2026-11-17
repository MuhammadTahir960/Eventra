from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.common.constants import Roles
from apps.common.permissions import has_role
from apps.common.serializers import (
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    RejectUnknownFieldsMixin,
    StrictCharField,
)
from apps.common.validators import validate_multiline_text
from apps.payments.services import refund_price_drops
from apps.venues.models import Venue

from .constants import (
    MAX_EVENT_LEAD_DAYS,
    MAX_EVENT_LENGTH_DAYS,
    MAX_REJECTION_REASON_LENGTH,
    ORGANIZER_MIN_NOTICE_HOURS,
    WALL_CLOCK_FORMATS,
)
from .models import Event, TicketTier, TierSectionMapping
from .services import (
    resolve_create_status,
    should_retrigger_approval,
    should_retrigger_approval_for_tier,
)


def _is_organizer_or_admin_for_event(request, event) -> bool:
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return False
    return user.role == Roles.ADMIN or event.organizer_id == user.id


def wall_clock_field():
    return serializers.DateTimeField(
        input_formats=WALL_CLOCK_FORMATS,
        error_messages={
            "invalid": "Send the venue's local time without a UTC offset, "
            "like 2026-11-01T18:30."
        },
    )


def read_in_time_zone(attrs, fields, time_zone):
    zone = ZoneInfo(time_zone)
    for field in fields:
        if field not in attrs:
            continue
        wall_clock = attrs[field].replace(tzinfo=None)
        moment = wall_clock.replace(tzinfo=zone)
        try:
            round_trip = moment.astimezone(UTC).astimezone(zone)
        except OverflowError as exc:
            raise serializers.ValidationError({field: "Enter a valid time."}) from exc
        if round_trip.replace(tzinfo=None) != wall_clock:
            raise serializers.ValidationError(
                {field: "This time doesn't exist at the venue: the clocks go forward."}
            )
        attrs[field] = moment


def validate_schedule(start, end, now):
    if end <= start:
        raise serializers.ValidationError(
            {"end_datetime": "The end must be after the start."}
        )
    if end - start > timedelta(days=MAX_EVENT_LENGTH_DAYS):
        raise serializers.ValidationError(
            {"end_datetime": f"An event can last at most {MAX_EVENT_LENGTH_DAYS} days."}
        )
    if start > now + timedelta(days=MAX_EVENT_LEAD_DAYS):
        raise serializers.ValidationError(
            {"start_datetime": "An event can start at most 2 years from now."}
        )


class EventSerializer(
    RejectUnknownFieldsMixin,
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    serializers.ModelSerializer,
):
    integrity_error_field = "slug"
    integrity_error_message = "An event with a conflicting slug already exists."

    start_datetime = wall_clock_field()
    end_datetime = wall_clock_field()
    time_zone = serializers.CharField(read_only=True)

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
            "rejection_reason",
            "is_seated",
            "max_tickets_per_buyer",
            "start_datetime",
            "end_datetime",
            "time_zone",
            "completed_at",
            "postponed_from",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organizer",
            "slug",
            "status",
            "rejection_reason",
            "completed_at",
            "postponed_from",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "description": {"max_length": 5000},
            "venue": {"required": True, "allow_null": False},
            "category": {"required": True, "allow_null": False},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not _is_organizer_or_admin_for_event(request, instance):
            data.pop("rejection_reason", None)
        return data

    def _actor_is_admin(self):
        return has_role(getattr(self.context.get("request"), "user", None), Roles.ADMIN)

    def _validate_start_window(self, start, now):
        if not self._actor_is_admin() and start < now + timedelta(
            hours=ORGANIZER_MIN_NOTICE_HOURS
        ):
            raise serializers.ValidationError(
                {
                    "start_datetime": f"An event must start at least {ORGANIZER_MIN_NOTICE_HOURS} "
                    "hours from now, so it can be reviewed in time."
                }
            )

    def _validate_category(self, attrs, event_type):
        category = self._current(attrs, "category")
        if not category:
            return
        if "category" in attrs and category.admin_only and not self._actor_is_admin():
            raise serializers.ValidationError(
                {"category": "Only admins can list events in this category."}
            )
        if event_type == Event.EventType.SPORTS_MATCH and not category.admin_only:
            raise serializers.ValidationError(
                {"category": "A sports match must be in the Sports category."}
            )

    def _current(self, attrs, field):
        return attrs.get(field, getattr(self.instance, field, None))

    def _read_times_at_venue(self, attrs):
        times = ("start_datetime", "end_datetime")
        if not any(field in attrs for field in ("venue", *times)):
            return
        venue = self._current(attrs, "venue")
        time_zone = (
            Venue.all_objects.select_for_update(no_key=True)
            .values_list("time_zone", flat=True)
            .get(pk=venue.pk)
            if venue
            else "UTC"
        )
        if (
            self.instance is not None
            and time_zone != self.instance.time_zone
            and not all(field in attrs for field in times)
        ):
            raise serializers.ValidationError(
                {
                    "venue": "This venue is in another time zone. Send the new "
                    "start and end times with it."
                }
            )
        read_in_time_zone(attrs, times, time_zone)

    def validate(self, attrs):
        self._read_times_at_venue(attrs)
        start = self._current(attrs, "start_datetime")
        end = self._current(attrs, "end_datetime")
        now = timezone.now()
        start_changed = "start_datetime" in attrs and (
            self.instance is None
            or attrs["start_datetime"] != self.instance.start_datetime
        )
        if start_changed and attrs["start_datetime"] <= now:
            raise serializers.ValidationError(
                {"start_datetime": "start_datetime must be in the future."}
            )
        if start_changed:
            self._validate_start_window(attrs["start_datetime"], now)
        dates_changed = "start_datetime" in attrs or "end_datetime" in attrs
        if dates_changed and start and end:
            validate_schedule(start, end, now)

        if self.instance is not None and self.instance.event_seats.exists():
            for field in ("venue", "is_seated"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        {
                            field: f"{field} cannot change once seats have been instantiated."
                        }
                    )

        event_type = self._current(attrs, "event_type")
        home_team = self._current(attrs, "home_team")
        away_team = self._current(attrs, "away_team")
        league = self._current(attrs, "league")

        if event_type == Event.EventType.SPORTS_MATCH:
            if not self._actor_is_admin():
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

        if "category" in attrs or "event_type" in attrs:
            self._validate_category(attrs, event_type)

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
        if should_retrigger_approval(event=instance, changed_fields=changed_fields) or (
            instance.status == Event.Status.REJECTED
            and instance.organizer.role != Roles.ADMIN
        ):
            validated_data["status"] = Event.Status.PENDING_APPROVAL
        return super().update(instance, validated_data)


class PostponementSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    start_datetime = wall_clock_field()
    end_datetime = wall_clock_field()

    def validate(self, attrs):
        read_in_time_zone(
            attrs,
            ("start_datetime", "end_datetime"),
            self.context["event"].time_zone,
        )
        start, end = attrs["start_datetime"], attrs["end_datetime"]
        if start <= self.context["event"].start_datetime:
            raise serializers.ValidationError(
                {"start_datetime": "The new start must be later than the current one."}
            )
        validate_schedule(start, end, timezone.now())
        return attrs


class RejectionSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    reason = StrictCharField(
        max_length=MAX_REJECTION_REASON_LENGTH, validators=[validate_multiline_text]
    )


class RunningLateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    end_datetime = wall_clock_field()

    def validate(self, attrs):
        read_in_time_zone(attrs, ("end_datetime",), self.context["event"].time_zone)
        return attrs


class PendingEventSerializer(EventSerializer):
    has_paid_bookings = serializers.BooleanField(read_only=True)

    class Meta(EventSerializer.Meta):
        fields = [*EventSerializer.Meta.fields, "has_paid_bookings"]


class TicketTierSerializer(
    RejectUnknownFieldsMixin,
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    serializers.ModelSerializer,
):
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

        needs_review = price_changing and should_retrigger_approval_for_tier(instance)
        if needs_review:
            instance.event.status = Event.Status.PENDING_APPROVAL
            instance.event.save(update_fields=["status", "updated_at"])

        tier = super().update(instance, validated_data)
        if price_changing and not needs_review:
            refund_price_drops(tier.event)
        return tier


class TierSectionMappingSerializer(
    RejectUnknownFieldsMixin,
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    serializers.ModelSerializer,
):
    integrity_error_field = "section"
    integrity_error_message = (
        "This section is already mapped to a different tier for this event."
    )

    class Meta:
        model = TierSectionMapping
        fields = ["id", "ticket_tier", "event", "section", "created_at"]
        read_only_fields = ["id", "ticket_tier", "event", "created_at"]

    def validate_section(self, value):
        venue = self.context["event"].venue
        if venue is None or not venue.seats.filter(section=value).exists():
            raise serializers.ValidationError(
                "This venue has no section with that name."
            )
        return value

    def validate(self, attrs):
        ticket_tier = self.context["ticket_tier"]
        event = self.context["event"]
        if ticket_tier.event_id != event.id:
            raise serializers.ValidationError(
                "Ticket tier does not belong to this event."
            )
        return attrs

    def create(self, validated_data):
        ticket_tier = self.context["ticket_tier"]
        event = self.context["event"]
        validated_data["ticket_tier"] = ticket_tier
        validated_data["event"] = event
        if should_retrigger_approval_for_tier(ticket_tier):
            event.status = Event.Status.PENDING_APPROVAL
            event.save(update_fields=["status", "updated_at"])
        return super().create(validated_data)
