import pytest
from ..factories import SeatFactory, VenueFactory
from ..serializers import (
    BulkSeatTemplateSerializer,
    SeatSerializer,
    VenueSerializer,
)

pytestmark = pytest.mark.django_db


def _venue_payload(**overrides):
    payload = {
        "name": "New Arena",
        "address": "123 Main St",
        "city": "Nairobi",
        "country": "Kenya",
        "capacity": 500,
    }
    payload.update(overrides)
    return payload


# ==================================================
# VenueSerializer — happy path
# ==================================================


def test_valid_payload_creates_venue():
    serializer = VenueSerializer(data=_venue_payload())
    assert serializer.is_valid(), serializer.errors
    venue = serializer.save()
    assert venue.name == "New Arena"
    assert venue.pk is not None


def test_id_created_at_updated_at_are_read_only():
    serializer = VenueSerializer(data=_venue_payload())
    serializer.is_valid()
    venue = serializer.save()
    assert "id" in VenueSerializer(venue).data
    assert "created_at" in VenueSerializer(venue).data


# ==================================================
# VenueSerializer — duplicate name+city validation
# ==================================================


def test_duplicate_active_name_and_city_rejected():
    VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer(data=_venue_payload(name="Arena One", city="Nairobi"))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_duplicate_check_is_case_insensitive():
    VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer(data=_venue_payload(name="ARENA ONE", city="NAIROBI"))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_duplicate_against_soft_deleted_venue_gives_restore_hint():
    VenueFactory(name="Arena One", city="Nairobi", is_active=False)
    serializer = VenueSerializer(data=_venue_payload(name="Arena One", city="Nairobi"))
    assert serializer.is_valid() is False
    assert "restore" in str(serializer.errors["name"]).lower()


def test_same_name_different_city_is_allowed():
    VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer(data=_venue_payload(name="Arena One", city="Mombasa"))
    assert serializer.is_valid(), serializer.errors


def test_update_excludes_self_from_duplicate_check():
    venue = VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer(
        venue, data={"name": "Arena One", "city": "Nairobi"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors


def test_update_still_detects_conflict_with_a_different_row():
    VenueFactory(name="Arena Two", city="Nairobi")
    venue = VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer(venue, data={"name": "Arena Two"}, partial=True)
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_race_condition_integrity_error_becomes_validation_error():
    from rest_framework import serializers as drf_serializers

    VenueFactory(name="Arena One", city="Nairobi")
    serializer = VenueSerializer()
    with pytest.raises(drf_serializers.ValidationError):
        serializer.create(_venue_payload(name="Arena One", city="Nairobi"))


def test_update_race_condition_integrity_error_becomes_validation_error():
    from rest_framework import serializers as drf_serializers

    VenueFactory(name="Arena One", city="Nairobi")
    other = VenueFactory(name="Arena Two", city="Nairobi")
    serializer = VenueSerializer()
    with pytest.raises(drf_serializers.ValidationError):
        serializer.update(other, {"name": "Arena One"})


# ==================================================
# VenueSerializer — field validation (min length / min value)
# ==================================================


def test_name_shorter_than_two_chars_rejected():
    serializer = VenueSerializer(data=_venue_payload(name="A"))
    assert serializer.is_valid() is False
    assert "name" in serializer.errors


def test_capacity_zero_rejected():
    serializer = VenueSerializer(data=_venue_payload(capacity=0))
    assert serializer.is_valid() is False
    assert "capacity" in serializer.errors


def test_capacity_negative_rejected():
    serializer = VenueSerializer(data=_venue_payload(capacity=-1))
    assert serializer.is_valid() is False
    assert "capacity" in serializer.errors


def test_missing_required_fields_rejected():
    serializer = VenueSerializer(data={"name": "Only A Name"})
    assert serializer.is_valid() is False
    assert "address" in serializer.errors
    assert "city" in serializer.errors
    assert "country" in serializer.errors
    assert "capacity" in serializer.errors


# ==================================================
# SeatSerializer
# ==================================================


def test_seat_serializer_exposes_expected_fields():
    seat = SeatFactory(section="A", row_label="1", seat_number=12)
    data = SeatSerializer(seat).data
    assert data["section"] == "A"
    assert data["row_label"] == "1"
    assert data["seat_number"] == 12


def test_seat_serializer_all_fields_read_only():
    assert set(SeatSerializer.Meta.read_only_fields) == set(SeatSerializer.Meta.fields)


# ==================================================
# BulkSeatTemplateSerializer
# ==================================================


def _seat_template_payload(**overrides):
    payload = {
        "sections": [
            {
                "name": "Main Stand",
                "rows": [
                    {"row_label": "A", "seat_count": 10},
                    {"row_label": "B", "seat_count": 10},
                ],
            }
        ]
    }
    payload.update(overrides)
    return payload


def test_valid_seat_template_payload_accepted():
    serializer = BulkSeatTemplateSerializer(data=_seat_template_payload())
    assert serializer.is_valid(), serializer.errors


def test_empty_sections_rejected():
    serializer = BulkSeatTemplateSerializer(data={"sections": []})
    assert serializer.is_valid() is False
    assert "sections" in serializer.errors


def test_section_with_no_rows_rejected():
    serializer = BulkSeatTemplateSerializer(
        data={"sections": [{"name": "Main Stand", "rows": []}]}
    )
    assert serializer.is_valid() is False


def test_seat_count_below_minimum_rejected():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {"name": "Main Stand", "rows": [{"row_label": "A", "seat_count": 0}]}
            ]
        }
    )
    assert serializer.is_valid() is False


def test_seat_count_above_maximum_rejected():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {"name": "Main Stand", "rows": [{"row_label": "A", "seat_count": 501}]}
            ]
        }
    )
    assert serializer.is_valid() is False


def test_duplicate_row_within_same_section_rejected():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {
                    "name": "Main Stand",
                    "rows": [
                        {"row_label": "A", "seat_count": 5},
                        {"row_label": "A", "seat_count": 5},
                    ],
                }
            ]
        }
    )
    assert serializer.is_valid() is False
    assert "sections" in serializer.errors


def test_same_row_label_in_different_sections_is_allowed():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {"name": "Main Stand", "rows": [{"row_label": "A", "seat_count": 5}]},
                {"name": "Away Stand", "rows": [{"row_label": "A", "seat_count": 5}]},
            ]
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_total_seats_over_sanity_limit_rejected():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {
                    "name": "Huge Stand",
                    "rows": [
                        {"row_label": label, "seat_count": 500}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                }
            ]
        }
    )
    assert serializer.is_valid() is False
    assert "sections" in serializer.errors


def test_total_seats_at_exactly_the_sanity_limit_is_allowed():
    serializer = BulkSeatTemplateSerializer(
        data={
            "sections": [
                {
                    "name": "Huge Stand",
                    "rows": [
                        {"row_label": label, "seat_count": 500}
                        for label in ["A", "B", "C", "D"]
                    ],
                }
            ]
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_missing_sections_key_rejected():
    serializer = BulkSeatTemplateSerializer(data={})
    assert serializer.is_valid() is False
    assert "sections" in serializer.errors
