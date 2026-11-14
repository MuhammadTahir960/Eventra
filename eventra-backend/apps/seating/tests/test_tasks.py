from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.events.factories import EventFactory

from ..factories import EventSeatFactory, SeatHoldFactory
from ..models import EventSeat
from ..tasks import release_expired_holds

pytestmark = pytest.mark.django_db


class TestReleaseExpiredHoldsTask:
    def test_released_seat_reaches_the_seat_map_group_through_redis(
        self, django_capture_on_commit_callbacks
    ):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        SeatHoldFactory(
            event_seat=seat, expires_at=timezone.now() - timedelta(minutes=1)
        )
        layer = get_channel_layer()
        channel = async_to_sync(layer.new_channel)()
        async_to_sync(layer.group_add)(f"seats_{event.slug}", channel)

        with django_capture_on_commit_callbacks(execute=True):
            release_expired_holds.delay()

        message = async_to_sync(layer.receive)(channel)
        assert message["type"] == "seat_update"
        assert message["seats"][0]["id"] == str(seat.id)
        assert message["seats"][0]["status"] == "available"
