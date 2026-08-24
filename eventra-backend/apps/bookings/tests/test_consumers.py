import uuid
from datetime import timedelta

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.utils import timezone

from apps.events.factories import EventFactory, TicketTierFactory
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat
from apps.seating.routing import websocket_urlpatterns
from apps.users.factories import UserFactory
from apps.users.services import issue_ws_ticket

from ..services import cancel_booking, create_booking_from_hold

pytestmark = pytest.mark.django_db(transaction=True)
application = URLRouter(websocket_urlpatterns)


async def _connect(event_slug, ticket):
    communicator = WebsocketCommunicator(
        application, f"/ws/seats/{event_slug}/?ticket={ticket}"
    )
    connected, _ = await communicator.connect()
    return communicator, connected


async def test_cancel_booking_broadcasts_seat_release_to_connected_clients():
    def _setup():
        booking_user = UserFactory()
        event = EventFactory(status="approved")
        tier = TicketTierFactory(event=event)
        seat = EventSeatFactory(
            event=event, ticket_tier=tier, status=EventSeat.Status.HELD
        )
        group_id = uuid.uuid4()
        SeatHoldFactory(
            group_id=group_id,
            event_seat=seat,
            user=booking_user,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        booking, _ = create_booking_from_hold(group_id, booking_user)
        return event, seat, booking

    event, seat, booking = await database_sync_to_async(_setup)()
    viewer = await database_sync_to_async(UserFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(viewer)

    communicator, connected = await _connect(event.slug, ticket)
    assert connected
    await communicator.receive_json_from()

    await database_sync_to_async(cancel_booking)(booking)

    message = await communicator.receive_json_from()
    assert message["type"] == "seat_update"
    assert len(message["seats"]) == 1
    assert message["seats"][0]["id"] == str(seat.id)
    assert message["seats"][0]["status"] == "available"

    await communicator.disconnect()
