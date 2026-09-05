from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.events.factories import EventFactory

from ..factories import EventSeatFactory, SeatHoldFactory
from ..models import EventSeat, SeatHold
from ..tasks import release_expired_holds

pytestmark = pytest.mark.django_db


class TestReleaseExpiredHoldsTask:
    def test_task_delegates_to_the_service_and_releases_the_seat(self, monkeypatch):
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", MagicMock()
        )
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        hold = SeatHoldFactory(
            event_seat=seat, expires_at=timezone.now() - timedelta(minutes=1)
        )

        release_expired_holds()

        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.AVAILABLE
        assert not SeatHold.objects.filter(id=hold.id).exists()
