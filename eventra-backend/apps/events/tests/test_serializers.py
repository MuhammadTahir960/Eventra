from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from rest_framework import serializers

from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.seating.factories import EventSeatFactory
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory, VenueFactory
from tests.helpers import wall_clock

from ..factories import EventFactory, TicketTierFactory
from ..models import Event
from ..serializers import (
    EventSerializer,
    TicketTierSerializer,
    TierSectionMappingSerializer,
    read_in_time_zone,
)

pytestmark = pytest.mark.django_db


def _event_payload(**overrides):
    start = timezone.now() + timedelta(days=10)
    payload = {
        "venue": VenueFactory().id,
        "category": CategoryFactory().id,
        "title": "New Event",
        "description": "Details here.",
        "event_type": Event.EventType.GENERAL,
        "is_seated": True,
        "start_datetime": wall_clock(start),
        "end_datetime": wall_clock(start + timedelta(hours=3)),
    }
    payload.update(overrides)
    return payload


def _request_for(user):
    request = MagicMock()
    request.user = user
    return request


# ==================================================
# EventSerializer — create
# ==================================================


def test_create_by_organizer_lands_pending_approval():
    organizer = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data=_event_payload(), context={"request": _request_for(organizer)}
    )
    assert serializer.is_valid(), serializer.errors
    event = serializer.save()
    assert event.status == Event.Status.PENDING_APPROVAL
    assert event.organizer_id == organizer.id


def test_create_by_admin_lands_approved_immediately():
    admin = UserFactory(role=Roles.ADMIN)
    serializer = EventSerializer(
        data=_event_payload(), context={"request": _request_for(admin)}
    )
    assert serializer.is_valid(), serializer.errors
    event = serializer.save()
    assert event.status == Event.Status.APPROVED


def test_client_supplied_organizer_is_refused():
    organizer = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data=_event_payload(organizer=str(other.id)),
        context={"request": _request_for(organizer)},
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"organizer"}


def test_client_supplied_status_is_refused_on_create():
    organizer = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data=_event_payload(status=Event.Status.APPROVED),
        context={"request": _request_for(organizer)},
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"status"}


# ==================================================
# EventSerializer — validation
# ==================================================


def test_end_datetime_before_start_datetime_rejected():
    organizer = UserFactory(role=Roles.ORGANIZER)
    start = timezone.now() + timedelta(days=5)
    serializer = EventSerializer(
        data=_event_payload(
            start_datetime=wall_clock(start),
            end_datetime=wall_clock(start - timedelta(hours=1)),
        ),
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid() is False
    assert "end_datetime" in serializer.errors


def test_missing_required_fields_rejected():
    organizer = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data={"title": "Only A Title"}, context={"request": _request_for(organizer)}
    )
    assert serializer.is_valid() is False
    assert "description" in serializer.errors
    assert "event_type" in serializer.errors
    assert "start_datetime" in serializer.errors
    assert "end_datetime" in serializer.errors


def test_duplicate_slug_becomes_clean_validation_error_not_500(monkeypatch):
    monkeypatch.setattr(Event, "_generate_unique_slug", lambda self: "same-title-event")
    EventFactory(title="Same Title Event", slug="same-title-event")
    organizer = UserFactory(role=Roles.ORGANIZER)
    start = timezone.now() + timedelta(days=10)
    serializer = EventSerializer(context={"request": _request_for(organizer)})
    with pytest.raises(serializers.ValidationError):
        serializer.create(
            {
                "venue": VenueFactory(),
                "category": CategoryFactory(),
                "title": "Same Title Event",
                "description": "Details here.",
                "event_type": Event.EventType.GENERAL,
                "is_seated": True,
                "start_datetime": start,
                "end_datetime": start + timedelta(hours=3),
            }
        )


# ==================================================
# EventSerializer — update / re-approval
# ==================================================


def test_sensitive_field_update_retriggers_approval_for_organizer_owned_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer, status=Event.Status.APPROVED)
    new_venue = VenueFactory()
    serializer = EventSerializer(
        event,
        data={"venue": new_venue.id},
        partial=True,
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.status == Event.Status.PENDING_APPROVAL


def test_cosmetic_field_update_does_not_retrigger_approval():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer, status=Event.Status.APPROVED)
    serializer = EventSerializer(
        event,
        data={"title": "Updated Title"},
        partial=True,
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.status == Event.Status.APPROVED


def test_sensitive_field_update_does_not_retrigger_approval_for_admin_owned_event():
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=admin, status=Event.Status.APPROVED)
    new_venue = VenueFactory()
    serializer = EventSerializer(
        event,
        data={"venue": new_venue.id},
        partial=True,
        context={"request": _request_for(admin)},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.status == Event.Status.APPROVED


def test_setting_same_venue_value_does_not_retrigger_approval():
    organizer = UserFactory(role=Roles.ORGANIZER)
    venue = VenueFactory()
    event = EventFactory(organizer=organizer, venue=venue, status=Event.Status.APPROVED)
    serializer = EventSerializer(
        event,
        data={"venue": venue.id},
        partial=True,
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.status == Event.Status.APPROVED


# ==================================================
# TicketTierSerializer
# ==================================================


def test_create_ticket_tier_assigns_event_from_context():
    event = EventFactory()
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": "100.00"}, context={"event": event}
    )
    assert serializer.is_valid(), serializer.errors
    tier = serializer.save()
    assert tier.event_id == event.id


@pytest.mark.parametrize(
    "price, valid",
    [
        ("-5.00", False),
        ("-0.01", False),
        ("0.01", False),
        ("0.49", False),
        ("0.00", True),
        ("0.50", True),
        ("100.00", True),
    ],
)
def test_a_tier_is_free_or_costs_at_least_fifty_cents(price, valid):
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": price}, context={"event": EventFactory()}
    )
    assert serializer.is_valid() is valid
    if not valid:
        assert serializer.errors["price"] == [
            "A ticket is free (0.00) or costs at least 0.50."
        ]


def test_client_supplied_event_field_is_refused_on_create():
    event = EventFactory()
    other_event = EventFactory()
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": "50.00", "event": str(other_event.id)},
        context={"event": event},
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"event"}


def test_price_update_allowed_when_no_seats_instantiated():
    tier = TicketTierFactory(price="10.00")
    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": tier.event}
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert str(updated.price) == "20.00"


def test_price_can_change_after_seats_exist():
    tier = TicketTierFactory(price="10.00")
    EventSeatFactory(event=tier.event, ticket_tier=tier)

    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": tier.event}
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    tier.refresh_from_db()
    assert str(tier.price) == "20.00"


def test_price_update_retriggers_approval_for_organizer_owned_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer, status=Event.Status.APPROVED)
    tier = TicketTierFactory(event=event, price="10.00")
    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": event}
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    event.refresh_from_db()
    assert event.status == Event.Status.PENDING_APPROVAL


def test_price_update_does_not_retrigger_approval_for_admin_owned_event():
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=admin, status=Event.Status.APPROVED)
    tier = TicketTierFactory(event=event, price="10.00")
    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": event}
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    event.refresh_from_db()
    assert event.status == Event.Status.APPROVED


def test_updating_name_only_does_not_touch_immutability_check():
    tier = TicketTierFactory()
    EventSeatFactory(event=tier.event, ticket_tier=tier)

    serializer = TicketTierSerializer(
        tier, data={"name": "Renamed"}, partial=True, context={"event": tier.event}
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.name == "Renamed"


# ==================================================
# TierSectionMappingSerializer
# ==================================================


def test_create_section_mapping_happy_path():
    tier = TicketTierFactory()
    SeatFactory(venue=tier.event.venue, section="A")
    serializer = TierSectionMappingSerializer(
        data={"section": "A"}, context={"event": tier.event, "ticket_tier": tier}
    )
    assert serializer.is_valid(), serializer.errors
    mapping = serializer.save()
    assert mapping.event_id == tier.event_id
    assert mapping.ticket_tier_id == tier.id


def test_tier_event_mismatch_rejected():
    tier = TicketTierFactory()
    other_event = EventFactory()
    serializer = TierSectionMappingSerializer(
        data={"section": "A"}, context={"event": other_event, "ticket_tier": tier}
    )
    assert serializer.is_valid() is False


def test_duplicate_section_for_same_event_becomes_validation_error_not_500():
    tier = TicketTierFactory()
    serializer = TierSectionMappingSerializer(
        context={"event": tier.event, "ticket_tier": tier}
    )
    serializer.create({"section": "A"})
    with pytest.raises(serializers.ValidationError):
        serializer.create({"section": "A"})


@pytest.mark.parametrize(
    "name, valid",
    [
        ("VIP", True),
        ("Stalls (front rows) & Circle", True),
        ("Family / Kids 50% off", True),
        ("گیلری", True),
        ("<script>alert(1)</script>", False),
        ("<img src=x onerror=alert(1)>", False),
        ("VIP!!!", False),
        ("Seat $5", False),
        ("--", False),
    ],
)
def test_tier_names_follow_the_event_title_rule(name, valid):
    serializer = TicketTierSerializer(
        data={"name": name, "price": "10.00"}, context={"event": EventFactory()}
    )
    assert serializer.is_valid() is valid


# ==================================================
# Event times are the venue's wall-clock time
# ==================================================


def test_times_are_read_in_the_venues_zone_and_returned_with_it():
    organizer = UserFactory(role=Roles.ORGANIZER)
    venue = VenueFactory(country="PK", time_zone="Asia/Karachi")
    day = (timezone.now() + timedelta(days=10)).date().isoformat()
    serializer = EventSerializer(
        data=_event_payload(
            venue=venue.id,
            start_datetime=f"{day}T18:30",
            end_datetime=f"{day}T21:30",
        ),
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    event = serializer.save()
    assert event.start_datetime.astimezone(UTC).strftime("%H:%M") == "13:30"
    assert serializer.data["time_zone"] == "Asia/Karachi"


@pytest.mark.parametrize("suffix", ["Z", "+00:00", "+05:00"])
def test_a_time_with_a_utc_offset_is_refused(suffix):
    start = wall_clock(timezone.now() + timedelta(days=10))
    serializer = EventSerializer(
        data=_event_payload(start_datetime=start + suffix),
        context={"request": _request_for(UserFactory(role=Roles.ORGANIZER))},
    )
    assert serializer.is_valid() is False
    assert "without a UTC offset" in serializer.errors["start_datetime"][0]


def test_a_time_the_clocks_skip_is_refused_and_a_repeated_one_means_the_first():
    skipped = {"start_datetime": datetime(2027, 3, 14, 2, 30, tzinfo=UTC)}
    with pytest.raises(serializers.ValidationError) as error:
        read_in_time_zone(skipped, ("start_datetime",), "America/New_York")
    assert "clocks go forward" in error.value.detail["start_datetime"]

    repeated = {"start_datetime": datetime(2027, 11, 7, 1, 30, tzinfo=UTC)}
    read_in_time_zone(repeated, ("start_datetime",), "America/New_York")
    assert repeated["start_datetime"].astimezone(UTC).hour == 5


@pytest.mark.parametrize(
    "edge, time_zone",
    [
        (datetime(9999, 12, 31, 23, 59, tzinfo=UTC), "America/New_York"),
        (datetime(1, 1, 1, 0, 0, tzinfo=UTC), "Asia/Karachi"),
    ],
)
def test_a_time_at_the_edge_of_the_calendar_is_refused_not_a_crash(edge, time_zone):
    with pytest.raises(serializers.ValidationError) as error:
        read_in_time_zone({"start_datetime": edge}, ("start_datetime",), time_zone)
    assert "valid time" in error.value.detail["start_datetime"]


def test_moving_to_a_venue_in_another_zone_needs_the_new_times():
    event = EventFactory(status=Event.Status.PENDING_APPROVAL)
    elsewhere = VenueFactory(country="PK", time_zone="Asia/Karachi")
    context = {"request": _request_for(event.organizer)}

    venue_only = EventSerializer(
        event, data={"venue": elsewhere.id}, partial=True, context=context
    )
    assert venue_only.is_valid() is False and "venue" in venue_only.errors

    start = event.start_datetime + timedelta(days=1)
    with_times = EventSerializer(
        event,
        data={
            "venue": elsewhere.id,
            "start_datetime": wall_clock(start, "Asia/Karachi"),
            "end_datetime": wall_clock(start + timedelta(hours=2), "Asia/Karachi"),
        },
        partial=True,
        context=context,
    )
    assert with_times.is_valid(), with_times.errors
    assert with_times.validated_data["start_datetime"] == start.replace(microsecond=0)
