from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.constants import Roles
from apps.users.factories import UserFactory

from ..factories import EventFactory
from ..models import Event

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


class TestEventCancelAction:
    def test_owning_organizer_can_cancel(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_delay = MagicMock()
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", mock_delay
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.APPROVED, organizer=organizer)

        client = auth_client(organizer)
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(f"/events/{event.id}/cancel/")

        assert response.status_code == 200
        event.refresh_from_db()
        assert event.status == Event.Status.CANCELLED
        mock_delay.assert_called_once_with(str(event.id))

    def test_non_owning_organizer_is_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", MagicMock()
        )
        owner = UserFactory(role=Roles.ORGANIZER)
        other = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.APPROVED, organizer=owner)

        client = auth_client(other)
        response = client.post(f"/events/{event.id}/cancel/")

        assert response.status_code == 403
        event.refresh_from_db()
        assert event.status == Event.Status.APPROVED

    def test_admin_can_cancel_any_event(self, monkeypatch):
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", MagicMock()
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        admin = UserFactory(role=Roles.ADMIN)
        event = EventFactory(status=Event.Status.APPROVED, organizer=organizer)

        client = auth_client(admin)
        response = client.post(f"/events/{event.id}/cancel/")

        assert response.status_code == 200

    def test_already_cancelled_returns_409(self, monkeypatch):
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", MagicMock()
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.CANCELLED, organizer=organizer)

        client = auth_client(organizer)
        response = client.post(f"/events/{event.id}/cancel/")

        assert response.status_code == 409

    def test_completed_event_returns_409(self, monkeypatch):
        mock_delay = MagicMock()
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", mock_delay
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.COMPLETED, organizer=organizer)

        client = auth_client(organizer)
        response = client.post(f"/events/{event.id}/cancel/")

        assert response.status_code == 409
        mock_delay.assert_not_called()


class TestEventRetryRefundsAction:
    def test_admin_can_retry_refunds_on_cancelled_event(self, monkeypatch):
        mock_delay = MagicMock()
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", mock_delay
        )
        admin = UserFactory(role=Roles.ADMIN)
        event = EventFactory(status=Event.Status.CANCELLED)

        client = auth_client(admin)
        response = client.post(f"/admin/events/{event.id}/retry-refunds/")

        assert response.status_code == 202
        mock_delay.assert_called_once_with(str(event.id), True)

    def test_non_admin_is_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", MagicMock()
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.CANCELLED, organizer=organizer)

        client = auth_client(organizer)
        response = client.post(f"/admin/events/{event.id}/retry-refunds/")

        assert response.status_code == 403

    def test_non_cancelled_event_returns_409(self, monkeypatch):
        mock_delay = MagicMock()
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", mock_delay
        )
        admin = UserFactory(role=Roles.ADMIN)
        event = EventFactory(status=Event.Status.APPROVED)

        client = auth_client(admin)
        response = client.post(f"/admin/events/{event.id}/retry-refunds/")

        assert response.status_code == 409
        mock_delay.assert_not_called()
