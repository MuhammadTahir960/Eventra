import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.events.factories import (
    EventFactory,
    TicketTierFactory,
    TierSectionMappingFactory,
)
from apps.events.models import Event
from apps.users.factories import UserFactory
from apps.users.services import issue_ws_ticket
from apps.venues.factories import SeatFactory, VenueFactory

from ..consumers import (
    CLOSE_INVALID_TICKET,
    CLOSE_RATE_LIMITED,
    CLOSE_UNEXPECTED_MESSAGE,
    SeatConsumer,
)
from ..models import EventSeat
from ..routing import websocket_urlpatterns
from ..services import hold_seats, instantiate_event_seats

pytestmark = pytest.mark.django_db(transaction=True)
application = URLRouter(websocket_urlpatterns)


async def _connect(event_slug, ticket):
    communicator = WebsocketCommunicator(
        application, f"/ws/seats/{event_slug}/?ticket={ticket}"
    )
    connected, close_code_or_subprotocol = await communicator.connect()
    return communicator, connected, close_code_or_subprotocol


async def test_valid_ticket_is_accepted_and_sends_initial_state():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, _ = await _connect(event.slug, ticket)
    assert connected

    message = await communicator.receive_json_from()
    assert message == {"type": "initial_state", "seats": []}

    await communicator.disconnect()


async def test_invalid_ticket_is_rejected_before_accept():
    event = await database_sync_to_async(EventFactory)()

    communicator, connected, close_code = await _connect(
        event.slug, "not-a-real-ticket"
    )

    assert not connected
    assert close_code == 4401


async def test_ticket_cannot_be_reused_for_a_second_connection():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    first_communicator, first_connected, _ = await _connect(event.slug, ticket)
    assert first_connected
    await first_communicator.disconnect()

    second_communicator, second_connected, close_code = await _connect(
        event.slug, ticket
    )
    assert not second_connected
    assert close_code == 4401


async def test_event_not_visible_to_user_is_rejected():
    user = await database_sync_to_async(UserFactory)()
    hidden_event = await database_sync_to_async(EventFactory)(
        status=Event.Status.PENDING_APPROVAL
    )
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, close_code = await _connect(hidden_event.slug, ticket)

    assert not connected
    assert close_code == 4404


async def test_nonexistent_event_slug_is_rejected():
    user = await database_sync_to_async(UserFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, close_code = await _connect("no-such-event-slug", ticket)

    assert not connected
    assert close_code == 4404


async def test_deactivated_user_is_rejected_even_with_a_valid_unused_ticket():
    user = await database_sync_to_async(UserFactory)(is_active=False)
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, close_code = await _connect(event.slug, ticket)

    assert not connected
    assert close_code == CLOSE_INVALID_TICKET


async def test_deleted_user_is_rejected_even_with_a_valid_unused_ticket():
    def _issue_then_delete():
        user = UserFactory()
        ticket, _ = issue_ws_ticket(user)
        user.delete()
        return ticket

    ticket = await database_sync_to_async(_issue_then_delete)()
    event = await database_sync_to_async(EventFactory)()

    communicator, connected, close_code = await _connect(event.slug, ticket)

    assert not connected
    assert close_code == CLOSE_INVALID_TICKET


async def test_organizer_can_connect_to_own_pending_event():
    organizer = await database_sync_to_async(UserFactory)(role="organizer")
    own_pending_event = await database_sync_to_async(EventFactory)(
        organizer=organizer, status=Event.Status.PENDING_APPROVAL
    )
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(organizer)

    communicator, connected, _ = await _connect(own_pending_event.slug, ticket)

    assert connected
    await communicator.disconnect()


async def test_attendee_cannot_connect_to_someone_elses_pending_event():
    attendee = await database_sync_to_async(UserFactory)(role="attendee")
    someone_elses_pending_event = await database_sync_to_async(EventFactory)(
        status=Event.Status.PENDING_APPROVAL
    )
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(attendee)

    communicator, connected, close_code = await _connect(
        someone_elses_pending_event.slug, ticket
    )

    assert not connected
    assert close_code == 4404


async def test_client_sent_message_closes_connection():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, _ = await _connect(event.slug, ticket)
    assert connected
    await communicator.receive_json_from()

    await communicator.send_json_to({"type": "hold_seat", "seat_id": "whatever"})

    closed_frame = await communicator.receive_output(timeout=1)
    assert closed_frame["type"] == "websocket.close"
    assert closed_frame["code"] == CLOSE_UNEXPECTED_MESSAGE


async def test_disconnect_after_rejected_connect_does_not_raise():
    event = await database_sync_to_async(EventFactory)()

    communicator, connected, _ = await _connect(event.slug, "garbage-ticket")
    assert not connected

    await communicator.disconnect()


async def test_group_broadcast_reaches_connected_client():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, _ = await _connect(event.slug, ticket)
    assert connected
    await communicator.receive_json_from()

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"seats_{event.slug}",
        {"type": "seat_update", "seats": [{"id": "fake", "status": "held"}]},
    )

    message = await communicator.receive_json_from()
    assert message == {
        "type": "seat_update",
        "seats": [{"id": "fake", "status": "held"}],
    }

    await communicator.disconnect()


async def test_initial_state_with_real_seats_serializes_correctly():
    def _setup():
        venue = VenueFactory()
        SeatFactory(venue=venue, section="Main", row_label="A", seat_number=1)
        event = EventFactory(venue=venue, is_seated=True)
        tier = TicketTierFactory(event=event)
        TierSectionMappingFactory(event=event, ticket_tier=tier, section="Main")
        instantiate_event_seats(event)
        return event

    event = await database_sync_to_async(_setup)()
    user = await database_sync_to_async(UserFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator, connected, _ = await _connect(event.slug, ticket)
    assert connected

    message = await communicator.receive_json_from()
    assert message["type"] == "initial_state"
    assert len(message["seats"]) == 1
    seat_payload = message["seats"][0]
    assert isinstance(seat_payload["id"], str)
    assert seat_payload["status"] == "available"
    assert seat_payload["section"] == "Main"

    await communicator.disconnect()


async def test_hold_seats_broadcasts_to_connected_clients():
    def _setup():
        venue = VenueFactory()
        SeatFactory(venue=venue, section="Main", row_label="A", seat_number=1)
        event = EventFactory(venue=venue, is_seated=True)
        tier = TicketTierFactory(event=event)
        TierSectionMappingFactory(event=event, ticket_tier=tier, section="Main")
        instantiate_event_seats(event)
        seat = EventSeat.objects.get(event=event)
        holding_user = UserFactory()
        return event, seat, holding_user

    event, seat, holding_user = await database_sync_to_async(_setup)()
    viewer = await database_sync_to_async(UserFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(viewer)

    communicator, connected, _ = await _connect(event.slug, ticket)
    assert connected
    await communicator.receive_json_from()

    await database_sync_to_async(hold_seats)(
        event=event, seat_ids=[seat.id], user=holding_user
    )

    message = await communicator.receive_json_from()
    assert message["type"] == "seat_update"
    assert len(message["seats"]) == 1
    assert message["seats"][0]["id"] == str(seat.id)
    assert message["seats"][0]["status"] == "held"

    await communicator.disconnect()


def test_get_client_ip_prefers_x_forwarded_for_over_everything_else():
    consumer = SeatConsumer()
    consumer.scope = {
        "headers": [
            (b"x-forwarded-for", b"203.0.113.5, 10.0.0.1"),
            (b"x-real-ip", b"10.0.0.1"),
        ],
        "client": ("10.0.0.1", 12345),
    }
    assert consumer._get_client_ip() == "203.0.113.5"


def test_get_client_ip_falls_back_to_x_real_ip_when_forwarded_for_is_absent():
    consumer = SeatConsumer()
    consumer.scope = {
        "headers": [(b"x-real-ip", b"203.0.113.9")],
        "client": ("10.0.0.1", 12345),
    }
    assert consumer._get_client_ip() == "203.0.113.9"


def test_get_client_ip_falls_back_to_raw_asgi_client_when_no_proxy_headers():
    consumer = SeatConsumer()
    consumer.scope = {"headers": [], "client": ("127.0.0.1", 54321)}
    assert consumer._get_client_ip() == "127.0.0.1"


def test_get_client_ip_returns_unknown_when_nothing_is_available():
    consumer = SeatConsumer()
    consumer.scope = {"headers": []}
    assert consumer._get_client_ip() == "unknown"


@override_settings(WS_CONNECT_RATE_LIMIT_PER_IP=2, WS_CONNECT_RATE_LIMIT_PER_USER=100)
async def test_ip_rate_limit_rejects_connection_attempts_over_the_cap():
    event = await database_sync_to_async(EventFactory)()

    for _ in range(2):
        _, connected, close_code = await _connect(event.slug, "garbage-ticket")
        assert not connected
        assert close_code == 4401

    _, connected, close_code = await _connect(event.slug, "garbage-ticket")
    assert not connected
    assert close_code == CLOSE_RATE_LIMITED


@override_settings(WS_CONNECT_RATE_LIMIT_PER_USER=2, WS_CONNECT_RATE_LIMIT_PER_IP=100)
async def test_user_rate_limit_rejects_connection_attempts_over_the_cap():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()

    for _ in range(2):
        ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)
        communicator, connected, _ = await _connect(event.slug, ticket)
        assert connected
        await communicator.disconnect()

    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)
    _, connected, close_code = await _connect(event.slug, ticket)
    assert not connected
    assert close_code == CLOSE_RATE_LIMITED


@override_settings(WS_CONNECT_RATE_LIMIT_PER_IP=100, WS_CONNECT_RATE_LIMIT_PER_USER=100)
async def test_rate_limit_does_not_reject_normal_traffic():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()

    for _ in range(5):
        ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)
        communicator, connected, _ = await _connect(event.slug, ticket)
        assert connected
        await communicator.disconnect()
