from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.serializers import (
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    RejectUnknownFieldsMixin,
    StrictCharField,
)
from apps.common.validators import validate_multiline_text
from apps.events.models import Event

from .constants import COUNTRY_TIME_ZONES
from .models import Seat, Venue, VenueRequest

MAX_ADMIN_NOTES_LENGTH = 2000


class VenueSerializer(
    RejectUnknownFieldsMixin,
    AllowedTextMixin,
    IntegrityErrorHandlingMixin,
    serializers.ModelSerializer,
):
    integrity_error_field = "name"
    integrity_error_message = "A venue with this name already exists in this city."

    class Meta:
        model = Venue
        fields = [
            "id",
            "name",
            "address",
            "city",
            "country",
            "time_zone",
            "capacity",
            "layout_shape",
            "photo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"time_zone": {"required": False}}

    def _validate_place(self, attrs):
        country = attrs.get("country", getattr(self.instance, "country", None))
        zones = COUNTRY_TIME_ZONES.get(country, ())
        if "country" in attrs and "time_zone" not in attrs and len(zones) == 1:
            attrs["time_zone"] = zones[0]
        time_zone = attrs.get("time_zone", getattr(self.instance, "time_zone", ""))
        try:
            Venue(country=country, time_zone=time_zone).clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        moved = self.instance is not None and (
            country != self.instance.country or time_zone != self.instance.time_zone
        )
        if not moved:
            return
        Venue.all_objects.select_for_update(no_key=True).get(pk=self.instance.pk)
        if Event.all_objects.filter(venue=self.instance).exists():
            raise serializers.ValidationError(
                {
                    "country": "The country and time zone can't change once "
                    "the venue has events."
                }
            )

    def validate(self, attrs):
        if "country" in attrs or "time_zone" in attrs:
            self._validate_place(attrs)
        name = attrs.get("name", getattr(self.instance, "name", None))
        city = attrs.get("city", getattr(self.instance, "city", None))
        if name and city:
            qs = Venue.all_objects.filter(name__iexact=name, city__iexact=city)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            existing_venue = qs.first()
            if existing_venue is not None:
                if not existing_venue.is_active:
                    raise serializers.ValidationError(
                        {
                            "name": (
                                "A venue with this name already exists in this city (inactive). "
                                "If you want to add this venue, please restore the existing venue."
                            )
                        }
                    )
                raise serializers.ValidationError(
                    {"name": "A venue with this name already exists in this city."}
                )
        return attrs


class SeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = ["id", "section", "row_label", "seat_number"]
        read_only_fields = fields


class RowSpecSerializer(
    RejectUnknownFieldsMixin, AllowedTextMixin, serializers.Serializer
):
    row_label = serializers.CharField(max_length=10)
    seat_count = serializers.IntegerField(
        min_value=1,
        max_value=500,
    )


class SectionSpecSerializer(
    RejectUnknownFieldsMixin, AllowedTextMixin, serializers.Serializer
):
    name = serializers.CharField(max_length=50)
    rows = RowSpecSerializer(many=True, allow_empty=False)


class BulkSeatTemplateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    sections = SectionSpecSerializer(many=True, allow_empty=False)

    def validate_sections(self, sections):
        seen_row_keys = set()
        for section in sections:
            for row in section["rows"]:
                row_key = (section["name"], row["row_label"])
                if row_key in seen_row_keys:
                    raise serializers.ValidationError(
                        f"Duplicate row '{row['row_label']}' in section "
                        f"'{section['name']}' — each row must be unique "
                        "within a single payload."
                    )
                seen_row_keys.add(row_key)

        total_seats = sum(
            row["seat_count"] for section in sections for row in section["rows"]
        )
        if total_seats > 2000:
            raise serializers.ValidationError(
                f"Payload would create {total_seats} seats — over the 2000-seat sanity limit."
            )
        return sections


class VenueRequestSerializer(
    RejectUnknownFieldsMixin, AllowedTextMixin, serializers.ModelSerializer
):
    class Meta:
        model = VenueRequest
        fields = [
            "id",
            "requested_by",
            "venue_name",
            "city",
            "country",
            "notes",
            "status",
            "admin_notes",
            "created_at",
            "reviewed_at",
        ]
        extra_kwargs = {"notes": {"max_length": 2000}}
        read_only_fields = [
            "id",
            "requested_by",
            "status",
            "admin_notes",
            "created_at",
            "reviewed_at",
        ]


class VenueRequestRejectionSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    admin_notes = StrictCharField(
        max_length=MAX_ADMIN_NOTES_LENGTH, validators=[validate_multiline_text]
    )
