from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.events.factories import EventFactory, TicketTierFactory
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory, VenueFactory

from ..factories import EventSeatFactory, SeatHoldFactory
from ..models import EventSeat, SeatHold

pytestmark = pytest.mark.django_db


# ==================================================
# EventSeat
# ==================================================


def test_event_seat_defaults_to_available():
    event_seat = EventSeatFactory()
    assert event_seat.status == EventSeat.Status.AVAILABLE


def test_event_seat_unique_per_event_and_seat():
    venue = VenueFactory()
    seat = SeatFactory(venue=venue)
    event = EventFactory(venue=venue)
    tier = TicketTierFactory(event=event)
    EventSeatFactory(event=event, seat=seat, ticket_tier=tier)

    with pytest.raises(IntegrityError):
        EventSeatFactory(event=event, seat=seat, ticket_tier=tier)


def test_event_seat_seat_fk_is_protected():
    event_seat = EventSeatFactory()
    with pytest.raises(ProtectedError):
        event_seat.seat.delete()


def test_event_seat_ticket_tier_fk_is_protected():
    event_seat = EventSeatFactory()
    with pytest.raises(ProtectedError):
        event_seat.ticket_tier.delete()


def test_event_seat_ticket_tier_related_name_is_event_seats():
    event_seat = EventSeatFactory()
    assert event_seat.ticket_tier.event_seats.filter(pk=event_seat.pk).exists()


# ==================================================
# SeatHold
# ==================================================


def test_seat_hold_one_per_event_seat():
    event_seat = EventSeatFactory()
    SeatHoldFactory(event_seat=event_seat)

    with pytest.raises(IntegrityError):
        SeatHoldFactory(event_seat=event_seat)


def test_seat_hold_group_id_shared_across_rows():
    event = EventFactory()
    tier = TicketTierFactory(event=event)
    seat_a = EventSeatFactory(event=event, ticket_tier=tier)
    seat_b = EventSeatFactory(event=event, ticket_tier=tier)
    user = UserFactory(role="attendee")
    group_id = "11111111-1111-1111-1111-111111111111"

    hold_a = SeatHoldFactory(event_seat=seat_a, user=user, group_id=group_id)
    hold_b = SeatHoldFactory(event_seat=seat_b, user=user, group_id=group_id)

    assert hold_a.group_id == hold_b.group_id
    assert SeatHold.objects.filter(group_id=group_id).count() == 2


def test_seat_hold_expires_at_is_stored_as_given():
    expires_at = timezone.now() + timedelta(minutes=10)
    hold = SeatHoldFactory(expires_at=expires_at)
    hold.refresh_from_db()
    assert hold.expires_at == expires_at
