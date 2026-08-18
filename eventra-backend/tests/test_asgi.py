import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.events.factories import EventFactory
from apps.users.factories import UserFactory
from apps.users.services import issue_ws_ticket
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


async def test_connection_with_no_origin_header_is_rejected():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator = WebsocketCommunicator(
        application, f"/ws/seats/{event.slug}/?ticket={ticket}"
    )
    connected, _ = await communicator.connect()

    assert not connected


async def test_connection_with_disallowed_origin_is_rejected():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator = WebsocketCommunicator(
        application,
        f"/ws/seats/{event.slug}/?ticket={ticket}",
        headers=[(b"origin", b"http://evil-attacker.example")],
    )
    connected, _ = await communicator.connect()

    assert not connected


async def test_connection_with_allowed_origin_is_accepted():
    user = await database_sync_to_async(UserFactory)()
    event = await database_sync_to_async(EventFactory)()
    ticket, _ = await database_sync_to_async(issue_ws_ticket)(user)

    communicator = WebsocketCommunicator(
        application,
        f"/ws/seats/{event.slug}/?ticket={ticket}",
        headers=[(b"origin", b"http://localhost")],
    )
    connected, _ = await communicator.connect()

    assert connected

    message = await communicator.receive_json_from()
    assert message["type"] == "initial_state"

    await communicator.disconnect()
