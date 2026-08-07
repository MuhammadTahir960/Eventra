from datetime import timedelta
from unittest.mock import MagicMock
import pytest
from django.utils import timezone
from apps.categories.factories import CategoryFactory
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from apps.venues.factories import VenueFactory
from ..factories import EventFactory, TicketTierFactory
from ..models import Event
from ..services import TierPriceImmutableError
from ..serializers import (
    EventSerializer,
    TicketTierSerializer,
    TierSectionMappingSerializer,
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
        "start_datetime": start,
        "end_datetime": start + timedelta(hours=3),
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


def test_client_supplied_organizer_is_ignored():
    organizer = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data=_event_payload(organizer=str(other.id)),
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    event = serializer.save()
    assert event.organizer_id == organizer.id


def test_client_supplied_status_is_ignored_on_create():
    organizer = UserFactory(role=Roles.ORGANIZER)
    serializer = EventSerializer(
        data=_event_payload(status=Event.Status.APPROVED),
        context={"request": _request_for(organizer)},
    )
    assert serializer.is_valid(), serializer.errors
    event = serializer.save()
    assert event.status == Event.Status.PENDING_APPROVAL


# ==================================================
# EventSerializer — validation
# ==================================================


def test_end_datetime_before_start_datetime_rejected():
    organizer = UserFactory(role=Roles.ORGANIZER)
    start = timezone.now() + timedelta(days=5)
    serializer = EventSerializer(
        data=_event_payload(
            start_datetime=start, end_datetime=start - timedelta(hours=1)
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


def test_duplicate_slug_becomes_clean_validation_error_not_500():
    from rest_framework import serializers as drf_serializers

    EventFactory(title="Same Title Event")
    organizer = UserFactory(role=Roles.ORGANIZER)
    start = timezone.now() + timedelta(days=10)
    serializer = EventSerializer(context={"request": _request_for(organizer)})
    with pytest.raises(drf_serializers.ValidationError):
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


def test_negative_price_rejected():
    event = EventFactory()
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": "-5.00"}, context={"event": event}
    )
    assert serializer.is_valid() is False
    assert "price" in serializer.errors


def test_zero_price_rejected():
    event = EventFactory()
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": "0.00"}, context={"event": event}
    )
    assert serializer.is_valid() is False
    assert "price" in serializer.errors


def test_client_supplied_event_field_is_ignored_on_create():
    event = EventFactory()
    other_event = EventFactory()
    serializer = TicketTierSerializer(
        data={"name": "VIP", "price": "50.00", "event": str(other_event.id)},
        context={"event": event},
    )
    assert serializer.is_valid(), serializer.errors
    tier = serializer.save()
    assert tier.event_id == event.id


def test_price_update_allowed_when_no_seats_instantiated():
    tier = TicketTierFactory(price="10.00")
    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": tier.event}
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert str(updated.price) == "20.00"


def test_price_update_blocked_once_seats_instantiated():
    tier = TicketTierFactory(price="10.00")

    class _FakeEventSeats:
        def exists(self):
            return True

    tier.event_seats = _FakeEventSeats()
    serializer = TicketTierSerializer(
        tier, data={"price": "20.00"}, partial=True, context={"event": tier.event}
    )
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(TierPriceImmutableError):
        serializer.save()


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

    class _FakeEventSeats:
        def exists(self):
            return True

    tier.event_seats = _FakeEventSeats()
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
    from rest_framework import serializers as drf_serializers

    tier = TicketTierFactory()
    serializer = TierSectionMappingSerializer(
        context={"event": tier.event, "ticket_tier": tier}
    )
    serializer.create({"section": "A"})
    with pytest.raises(drf_serializers.ValidationError):
        serializer.create({"section": "A"})
