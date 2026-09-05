from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.events.factories import EventFactory

from ..factories import EventSeatFactory, SeatHoldFactory
from ..models import EventSeat, SeatHold
from ..services import release_expired_holds

pytestmark = pytest.mark.django_db


class TestReleaseExpiredHolds:
    def test_expired_hold_releases_seat_and_deletes_hold_row(self, monkeypatch):
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

    def test_non_expired_hold_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", MagicMock()
        )
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        hold = SeatHoldFactory(
            event_seat=seat, expires_at=timezone.now() + timedelta(minutes=5)
        )

        release_expired_holds()

        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.HELD
        assert SeatHold.objects.filter(id=hold.id).exists()

    def test_broadcasts_release_per_affected_event(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        SeatHoldFactory(
            event_seat=seat, expires_at=timezone.now() - timedelta(minutes=1)
        )

        with django_capture_on_commit_callbacks(execute=True):
            release_expired_holds()

        mock_notify.assert_called_once_with(
            event_slug=event.slug, seat_ids=[seat.id], status_label="available"
        )

    def test_no_expired_holds_is_a_no_op(self, monkeypatch):
        mock_notify = MagicMock()
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", mock_notify
        )

        release_expired_holds()

        mock_notify.assert_not_called()
