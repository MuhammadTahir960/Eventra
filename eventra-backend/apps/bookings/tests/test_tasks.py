import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat
from apps.users.factories import UserFactory

from ..models import Booking
from ..services import create_booking_from_hold
from ..tasks import release_expired_bookings

pytestmark = pytest.mark.django_db


def _stale_pending_booking(user):
    event = EventFactory(status="approved")
    group_id = uuid.uuid4()
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.HELD, price_override=Decimal("25.00")
    )
    SeatHoldFactory(
        group_id=group_id,
        event_seat=seat,
        user=user,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    booking, _ = create_booking_from_hold(group_id, user)
    Booking.objects.filter(id=booking.id).update(
        created_at=timezone.now() - timedelta(minutes=10)
    )
    return booking, seat


class TestReleaseExpiredBookingsTask:
    def test_task_delegates_to_the_sweep_service_and_completes_it(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        monkeypatch.setattr(
            "apps.bookings.services.notify_internal_broadcast", MagicMock()
        )
        user = UserFactory()
        booking, seat = _stale_pending_booking(user)

        with django_capture_on_commit_callbacks(execute=True):
            release_expired_bookings()

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert seat.held_booking_id is None
