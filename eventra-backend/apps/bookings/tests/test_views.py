import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.utils import timezone
from rest_framework.test import APIClient

from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.payments.models import Payment
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat
from apps.users.factories import UserFactory
from tests.helpers import auth_client, paid_booking, unpaid_booking

from ..factories import BookingFactory
from ..models import Booking

pytestmark = pytest.mark.django_db


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
        client = auth_client(user)

        first = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")
        second = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.data["id"] == second.data["id"]

    def test_unknown_hold_id_returns_404(self):
        client = auth_client(UserFactory())
        response = client.post(
            "/bookings/", {"hold_id": str(uuid.uuid4())}, format="json"
        )
        assert response.status_code == 404

    def test_malformed_hold_id_returns_400_not_500(self):
        client = auth_client(UserFactory())
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
        client = auth_client(user)

        response = client.post("/bookings/", {"hold_id": str(group_id)}, format="json")
        assert response.status_code == 409


class TestBookingListEndpoint:
    def test_lists_only_own_bookings(self):
        owner = UserFactory()
        stranger = UserFactory()
        own_booking = BookingFactory(user=owner)
        BookingFactory(user=stranger)
        client = auth_client(owner)

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
        client = auth_client(stranger)

        response = client.get(f"/bookings/{booking.id}/")
        assert response.status_code == 404

    def test_own_booking_is_visible(self):
        owner = UserFactory()
        booking = BookingFactory(user=owner)
        client = auth_client(owner)

        response = client.get(f"/bookings/{booking.id}/")
        assert response.status_code == 200
        assert response.data["id"] == str(booking.id)


class TestBookingCheckoutEndpoint:
    def test_checkout_against_non_pending_booking_returns_409(self):
        user = UserFactory()
        booking = BookingFactory(user=user, status=Booking.Status.CANCELLED)
        client = auth_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")
        assert response.status_code == 409

    def test_checkout_happy_path_returns_client_secret(self, monkeypatch):
        user = UserFactory()
        booking = unpaid_booking("15.00", user=user)
        fake_intent = MagicMock(id="pi_test_abc", client_secret="pi_test_abc_secret")
        create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", create
        )
        client = auth_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 200
        assert response.data["client_secret"] == "pi_test_abc_secret"
        assert create.call_args.kwargs["amount"] == 1500

    def test_free_tickets_are_confirmed_at_checkout_without_stripe(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(side_effect=AssertionError("Stripe must not be called")),
        )
        user = UserFactory()
        event = EventFactory(status=Event.Status.APPROVED)
        booking = unpaid_booking("0.00", user=user, event=event)
        client = auth_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 200
        assert response.data["client_secret"] == ""
        assert response.data["status"] == "confirmed"
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert set(booking.tickets.values_list("status", flat=True)) == {"valid"}
        assert booking.held_seats().count() == 0
        assert EventSeat.objects.filter(
            tickets__booking=booking, status=EventSeat.Status.BOOKED
        ).exists()
        assert not Payment.objects.filter(booking=booking).exists()
        assert client.post(f"/bookings/{booking.id}/checkout/").status_code == 409

    def test_free_tickets_for_a_closed_event_are_refused(self):
        user = UserFactory()
        event = EventFactory(status=Event.Status.CANCELLED)
        booking = unpaid_booking("0.00", user=user, event=event)

        response = auth_client(user).post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 409
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING

    def test_checkout_against_someone_elses_booking_returns_404(self):
        owner = UserFactory()
        stranger = UserFactory()
        booking = BookingFactory(user=owner, status=Booking.Status.PENDING)
        client = auth_client(stranger)

        response = client.post(f"/bookings/{booking.id}/checkout/")
        assert response.status_code == 404

    def test_checkout_stripe_error_returns_502(self, monkeypatch):
        user = UserFactory()
        booking = unpaid_booking("15.00", user=user)

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.payments.services.stripe.PaymentIntent.create", _boom)
        client = auth_client(user)

        response = client.post(f"/bookings/{booking.id}/checkout/")

        assert response.status_code == 502
        assert "could not connect to Stripe" not in str(response.data)


class TestBookingCancelEndpoint:
    def _booking(self, postponed=True):
        start = timezone.now() + timedelta(days=3)
        event = EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
            postponed_from=start - timedelta(days=7) if postponed else None,
        )
        return paid_booking(event, (TicketTierFactory(event=event), "25.00"))

    def _post(self, user, booking):
        return auth_client(user).post(f"/bookings/{booking.id}/cancel/")

    def test_owner_gets_a_full_refund_for_a_postponed_event(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.Refund.create",
            MagicMock(return_value=MagicMock(id="re_test")),
        )
        booking = self._booking()

        response = self._post(booking.user, booking)

        assert response.status_code == 200
        assert response.data["status"] == Booking.Status.REFUNDED

    def test_the_old_refunds_route_is_gone(self):
        booking = self._booking()
        response = auth_client(booking.user).post(f"/bookings/{booking.id}/refunds/")
        assert response.status_code == 404

    def test_someone_elses_booking_is_not_found(self):
        booking = self._booking()
        assert self._post(UserFactory(), booking).status_code == 404

    def test_an_event_that_was_not_postponed_is_a_conflict(self):
        booking = self._booking(postponed=False)
        assert self._post(booking.user, booking).status_code == 409
