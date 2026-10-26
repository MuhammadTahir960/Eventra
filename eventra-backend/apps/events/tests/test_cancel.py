from unittest.mock import MagicMock

import pytest
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.common.constants import Roles
from apps.payments.factories import PaymentFactory
from apps.payments.models import Payment
from apps.seating.factories import EventSeatFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory

from ..factories import EventFactory, TicketTierFactory
from ..models import Event

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _paid_booking(event, user, booking_status=Booking.Status.CONFIRMED):
    seat = EventSeatFactory(
        event=event,
        ticket_tier=TicketTierFactory(event=event),
        seat=SeatFactory(venue=event.venue),
    )
    booking = BookingFactory(user=user, status=booking_status)
    Ticket.objects.create(booking=booking, event_seat=seat)
    PaymentFactory(booking=booking, status=Payment.Status.SUCCEEDED)
    return booking


class TestCancelledEventEmails:
    def test_buyers_get_the_notice_first_then_the_refund_email(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.APPROVED, organizer=organizer)
        buyer = UserFactory()
        booking = _paid_booking(event, buyer)
        _paid_booking(event, buyer)
        _paid_booking(event, UserFactory(), Booking.Status.REFUNDED)

        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client(organizer).post(f"/events/{event.id}/cancel/")

        assert response.status_code == 200
        booking.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert [(m.to, m.subject) for m in mail.outbox] == [
            ([buyer.email], "An event you booked has been cancelled"),
            ([buyer.email], "Your Eventra booking has been refunded"),
            ([buyer.email], "Your Eventra booking has been refunded"),
        ]

    def test_cancelling_an_unsold_event_sends_no_email(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        monkeypatch.setattr(
            "apps.events.views.refund_event_bookings_task.delay", MagicMock()
        )
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status=Event.Status.APPROVED, organizer=organizer)

        with django_capture_on_commit_callbacks(execute=True):
            auth_client(organizer).post(f"/events/{event.id}/cancel/")

        assert mail.outbox == []


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
        mock_delay.assert_called_once_with(str(event.id), retry_failed=True)

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
