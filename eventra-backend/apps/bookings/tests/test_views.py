import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat
from apps.users.factories import UserFactory

from ..factories import BookingFactory
from ..models import Booking

pytestmark = pytest.mark.django_db


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestBookingCreateEndpoint:
    def test_first_call_returns_201_replay_returns_200(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        seat = EventSeatFactory(
            event=event, status=EventSeat.Status.HELD, price_override=Decimal("30.00")
        )
        SeatHoldFactory(
            group_id=group_id,
            event_seat=seat,
            user=user,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        client = _authed_client(user)

        first = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")
        second = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.data["id"] == second.data["id"]

    def test_unknown_hold_id_returns_404(self):
        client = _authed_client(UserFactory())
        response = client.post(
            "/bookings/", {"hold_id": str(uuid.uuid4())}, format="json"
        )
        assert response.status_code == 404

    def test_malformed_hold_id_returns_400_not_500(self):
        client = _authed_client(UserFactory())
        response = client.post("/bookings/", {"hold_id": "not-a-uuid"}, format="json")
        assert response.status_code == 400

    def test_unauthenticated_request_rejected(self):
        client = APIClient()
        response = client.post(
            "/bookings/", {"hold_id": str(uuid.uuid4())}, format="json"
        )
        assert response.status_code == 401

    def test_expired_hold_conversion_returns_409(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        SeatHoldFactory(
            group_id=group_id,
            event_seat=seat,
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        client = _authed_client(user)

        response = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")
        assert response.status_code == 409


class TestBookingListEndpoint:
    def test_lists_only_own_bookings(self):
        owner = UserFactory()
        stranger = UserFactory()
        own_booking = BookingFactory(user=owner)
        BookingFactory(user=stranger)
        client = _authed_client(owner)

        response = client.get("/bookings/")

        assert response.status_code == 200
        ids = [b["id"] for b in response.data["results"]]
        assert ids == [str(own_booking.id)]

    def test_unauthenticated_request_rejected(self):
        client = APIClient()
        response = client.get("/bookings/")
        assert response.status_code == 401


class TestBookingDetailOwnership:
    def test_wrong_owner_gets_404_not_403(self):
        owner = UserFactory()
        stranger = UserFactory()
        booking = BookingFactory(user=owner)
        client = _authed_client(stranger)

        response = client.get(f"/bookings/{booking.id}/")
        assert response.status_code == 404

    def test_own_booking_is_visible(self):
        owner = UserFactory()
        booking = BookingFactory(user=owner)
        client = _authed_client(owner)

        response = client.get(f"/bookings/{booking.id}/")
        assert response.status_code == 200
        assert response.data["id"] == str(booking.id)


class TestBookingCheckoutEndpoint:
    def test_checkout_against_non_pending_booking_returns_409(self):
        user = UserFactory()
        booking = BookingFactory(user=user, status=Booking.Status.CANCELLED)
        client = _authed_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")
        assert response.status_code == 409

    def test_checkout_happy_path_returns_client_secret(self, monkeypatch):
        user = UserFactory()
        booking = BookingFactory(
            user=user, status=Booking.Status.PENDING, total_amount=Decimal("15.00")
        )
        fake_intent = MagicMock(id="pi_test_abc", client_secret="pi_test_abc_secret")
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )
        client = _authed_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 200
        assert response.data["client_secret"] == "pi_test_abc_secret"
        assert response.data["amount"] == 1500

    def test_checkout_against_someone_elses_booking_returns_404(self):
        owner = UserFactory()
        stranger = UserFactory()
        booking = BookingFactory(user=owner, status=Booking.Status.PENDING)
        client = _authed_client(stranger)

        response = client.post(f"/bookings/{booking.id}/checkout/")
        assert response.status_code == 404

    def test_checkout_stripe_error_returns_502(self, monkeypatch):
        user = UserFactory()
        booking = BookingFactory(
            user=user, status=Booking.Status.PENDING, total_amount=Decimal("15.00")
        )

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.payments.services.stripe.PaymentIntent.create", _boom)
        client = _authed_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 502
        assert "could not connect to Stripe" not in str(response.data)


class TestBookingCancelEndpoint:
    def test_cancel_against_non_pending_booking_returns_409(self):
        user = UserFactory()
        booking = BookingFactory(user=user, status=Booking.Status.CONFIRMED)
        client = _authed_client(user)

        response = client.post(f"/bookings/{booking.id}/cancel/")
        assert response.status_code == 409

    def test_cancel_happy_path_releases_seat(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
        SeatHoldFactory(
            group_id=group_id,
            event_seat=seat,
            user=user,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        client = _authed_client(user)
        create_resp = client.post(
            "/bookings/", {"hold_id": str(group_id)}, format="json"
        )
        booking_id = create_resp.data["id"]

        response = client.post(f"/bookings/{booking_id}/cancel/")

        assert response.status_code == 200
        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.AVAILABLE
