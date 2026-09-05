import uuid
from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.events.factories import EventFactory

from ..factories import EventSeatFactory
from ..models import EventSeat

pytestmark = pytest.mark.django_db


class TestInternalSeatsBroadcastView:
    def test_valid_request_broadcasts_and_returns_204(self, monkeypatch):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event, status=EventSeat.Status.AVAILABLE)

        mock_broadcast = MagicMock()
        monkeypatch.setattr("apps.seating.views.broadcast_seat_update", mock_broadcast)

        client = APIClient()
        response = client.post(
            "/internal/seats/broadcast/",
            {
                "event_slug": event.slug,
                "seat_ids": [str(seat.id)],
                "status": "available",
            },
            format="json",
        )

        assert response.status_code == 204
        mock_broadcast.assert_called_once()
        _, kwargs = mock_broadcast.call_args
        assert kwargs["event"] == event
        assert [s.id for s in kwargs["seats"]] == [seat.id]

    def test_no_auth_required(self, monkeypatch):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        monkeypatch.setattr("apps.seating.views.broadcast_seat_update", MagicMock())

        client = APIClient()
        response = client.post(
            "/internal/seats/broadcast/",
            {"event_slug": event.slug, "seat_ids": [str(seat.id)]},
            format="json",
        )

        assert response.status_code == 204

    def test_unknown_event_slug_returns_404(self):
        client = APIClient()
        response = client.post(
            "/internal/seats/broadcast/",
            {"event_slug": "no-such-event", "seat_ids": [str(uuid.uuid4())]},
            format="json",
        )
        assert response.status_code == 404

    def test_empty_seat_ids_returns_400(self):
        event = EventFactory(status="approved")
        client = APIClient()
        response = client.post(
            "/internal/seats/broadcast/",
            {"event_slug": event.slug, "seat_ids": []},
            format="json",
        )
        assert response.status_code == 400

    def test_no_matching_seats_returns_204_without_broadcasting(self, monkeypatch):
        event = EventFactory(status="approved")
        other_event = EventFactory(status="approved")
        foreign_seat = EventSeatFactory(event=other_event)

        mock_broadcast = MagicMock()
        monkeypatch.setattr("apps.seating.views.broadcast_seat_update", mock_broadcast)

        client = APIClient()
        response = client.post(
            "/internal/seats/broadcast/",
            {"event_slug": event.slug, "seat_ids": [str(foreign_seat.id)]},
            format="json",
        )

        assert response.status_code == 204
        mock_broadcast.assert_not_called()
