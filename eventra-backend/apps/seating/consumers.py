from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.http import Http404

from apps.common.rate_limit import is_rate_limited
from apps.events.services import get_visible_event_by_slug_or_404
from apps.users.models import User
from apps.users.services import validate_and_consume_ws_ticket

from .models import EventSeat
from .serializers import serialize_seats_for_ws

CLOSE_INVALID_TICKET = 4401  # missing / invalid / expired / already-used ticket
CLOSE_EVENT_NOT_VISIBLE = 4404  # event doesn't exist, or isn't visible to this user
CLOSE_UNEXPECTED_MESSAGE = 4400  # client sent something on this read-only socket
CLOSE_RATE_LIMITED = 4429  # too many connection attempts (mirrors HTTP 429)


class SeatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.group_name = None

        client_ip = self._get_client_ip()
        if await sync_to_async(self._ip_rate_limited)(client_ip):
            await self.close(code=CLOSE_RATE_LIMITED)
            return

        ticket = self._ticket_from_query_string()
        user_id = await sync_to_async(validate_and_consume_ws_ticket)(ticket)
        if user_id is None:
            await self.close(code=CLOSE_INVALID_TICKET)
            return

        if await sync_to_async(self._user_rate_limited)(user_id):
            await self.close(code=CLOSE_RATE_LIMITED)
            return

        user = await sync_to_async(self._get_active_user)(user_id)
        if user is None:
            await self.close(code=CLOSE_INVALID_TICKET)
            return

        event_slug = self.scope["url_route"]["kwargs"]["event_slug"]
        event = await sync_to_async(self._get_visible_event)(user, event_slug)
        if event is None:
            await self.close(code=CLOSE_EVENT_NOT_VISIBLE)
            return

        self.group_name = f"seats_{event.slug}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        seats = await sync_to_async(self._current_seat_state)(event)
        await self.send_json({"type": "initial_state", "seats": seats})

    async def disconnect(self, close_code):
        if self.group_name is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        await self.close(code=CLOSE_UNEXPECTED_MESSAGE)

    async def seat_update(self, event):
        await self.send_json({"type": "seat_update", "seats": event["seats"]})

    # -- synchronous helpers, called via sync_to_async above --

    def _get_client_ip(self):
        headers = dict(self.scope.get("headers", []))

        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode("utf-8").split(",")[0].strip()

        real_ip = headers.get(b"x-real-ip")
        if real_ip:
            return real_ip.decode("utf-8").strip()

        client = self.scope.get("client")
        if client:
            return client[0]

        return "unknown"

    def _ip_rate_limited(self, client_ip):
        return is_rate_limited(
            key=f"ws_connect:ip:{client_ip}",
            limit=settings.WS_CONNECT_RATE_LIMIT_PER_IP,
            window_seconds=settings.WS_CONNECT_RATE_LIMIT_WINDOW_SECONDS,
        )

    def _user_rate_limited(self, user_id):
        return is_rate_limited(
            key=f"ws_connect:user:{user_id}",
            limit=settings.WS_CONNECT_RATE_LIMIT_PER_USER,
            window_seconds=settings.WS_CONNECT_RATE_LIMIT_WINDOW_SECONDS,
        )

    def _ticket_from_query_string(self):
        raw_query = self.scope.get("query_string", b"").decode("utf-8")
        return parse_qs(raw_query).get("ticket", [None])[0]

    def _get_active_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()

    def _get_visible_event(self, user, event_slug):
        try:
            return get_visible_event_by_slug_or_404(user, event_slug)
        except Http404:
            return None

    def _current_seat_state(self, event):
        seats = EventSeat.objects.filter(event=event).select_related(
            "seat", "ticket_tier"
        )
        return serialize_seats_for_ws(seats)
