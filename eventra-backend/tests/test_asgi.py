import asyncio

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
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
        headers=[(b"origin", b"http://localhost:5173")],
    )
    connected, _ = await communicator.connect()

    assert connected

    message = await communicator.receive_json_from()
    assert message["type"] == "initial_state"

    await communicator.disconnect()


async def test_an_idle_seat_socket_outlasts_the_channel_layers_blocking_read():
    layer = get_channel_layer()
    channel = await layer.new_channel()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(layer.receive(channel), timeout=layer.brpop_timeout + 2)


@pytest.mark.parametrize("path", ["/ws/seats/a.b/", "/ws/nothing/", "/ws/seats/"])
async def test_an_unknown_socket_path_is_refused_not_crashed(path):
    communicator = WebsocketCommunicator(
        application, path, headers=[(b"origin", b"http://localhost:5173")]
    )
    connected, _ = await communicator.connect()
    assert not connected
