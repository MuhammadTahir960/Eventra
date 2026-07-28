from rest_framework import serializers
from .models import Venue, Seat


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = [
            "id",
            "name",
            "address",
            "city",
            "country",
            "capacity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
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


class RowSpecSerializer(serializers.Serializer):
    row_label = serializers.CharField(max_length=10)
    seat_count = serializers.IntegerField(
        min_value=1,
        max_value=500,
    )


class SectionSpecSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    rows = RowSpecSerializer(many=True, allow_empty=False)


class BulkSeatTemplateSerializer(serializers.Serializer):
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
