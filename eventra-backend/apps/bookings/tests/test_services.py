import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.events.factories import EventFactory
from apps.payments.models import Payment
from apps.payments.services import PaymentGatewayError
from apps.seating.factories import EventSeatFactory, SeatHoldFactory
from apps.seating.models import EventSeat, SeatHold
from apps.users.factories import UserFactory

from ..factories import BookingFactory
from ..models import Booking
from ..services import (
    BookingNotPendingError,
    HoldExpiredError,
    HoldNotFoundError,
    cancel_booking,
    checkout_booking,
    create_booking_from_hold,
)

pytestmark = pytest.mark.django_db


def _held_seat_with_hold(user, event=None, price=Decimal("25.00"), group_id=None):
    event = event or EventFactory(status="approved")
    group_id = group_id or uuid.uuid4()
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.HELD, price_override=price
    )
    SeatHoldFactory(
        group_id=group_id,
        event_seat=seat,
        user=user,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return group_id, seat


class TestCreateBookingFromHold:
    def test_creates_pending_booking_with_correct_total(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user, price=Decimal("25.00"))

        booking, created = create_booking_from_hold(group_id, user)

        assert created is True
        assert booking.status == Booking.Status.PENDING
        assert booking.total_amount == Decimal("25.00")
        assert booking.source_hold_group_id == group_id
        assert booking.idempotency_key

    def test_deletes_the_hold_group_and_leaves_seat_held(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        create_booking_from_hold(group_id, user)

        assert not SeatHold.objects.filter(group_id=group_id).exists()
        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.HELD

    def test_replayed_call_returns_existing_booking_not_a_duplicate(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        first_booking, first_created = create_booking_from_hold(group_id, user)
        second_booking, second_created = create_booking_from_hold(group_id, user)

        assert first_created is True
        assert second_created is False
        assert first_booking.id == second_booking.id
        assert Booking.objects.filter(source_hold_group_id=group_id).count() == 1

    def test_unknown_hold_id_raises_not_found(self):
        user = UserFactory()
        with pytest.raises(HoldNotFoundError):
            create_booking_from_hold(uuid.uuid4(), user)

    def test_another_users_hold_raises_not_found(self):
        owner = UserFactory()
        stranger = UserFactory()
        group_id, _ = _held_seat_with_hold(owner)

        with pytest.raises(HoldNotFoundError):
            create_booking_from_hold(group_id, stranger)

    def test_expired_hold_raises_conflict(self):
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

        with pytest.raises(HoldExpiredError):
            create_booking_from_hold(group_id, user)

    def test_multi_seat_hold_sums_correctly(self):
        user = UserFactory()
        event = EventFactory(status="approved")
        group_id = uuid.uuid4()
        for price in (Decimal("25.00"), Decimal("40.00"), Decimal("15.50")):
            seat = EventSeatFactory(
                event=event, status=EventSeat.Status.HELD, price_override=price
            )
            SeatHoldFactory(
                group_id=group_id,
                event_seat=seat,
                user=user,
                expires_at=timezone.now() + timedelta(minutes=10),
            )

        booking, created = create_booking_from_hold(group_id, user)

        assert booking.total_amount == Decimal("80.50")

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_retry_backstop_yields_exactly_one_booking(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        results = []
        barrier = threading.Barrier(2)

        errors = []

        def attempt():
            barrier.wait()
            try:
                booking, created = create_booking_from_hold(group_id, user)
                results.append((booking.id, created))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert Booking.objects.filter(source_hold_group_id=group_id).count() == 1
        assert len(results) == 2
        assert len({r[0] for r in results}) == 1
        assert sorted(r[1] for r in results) == [False, True]
        seat.refresh_from_db()
        assert seat.held_booking_id == results[0][0]

    @pytest.mark.django_db(transaction=True)
    def test_integrity_error_backstop_still_sets_held_booking_id(self, monkeypatch):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)

        winner_holder = {}
        real_create = Booking.objects.create

        def _raise_after_concurrent_commit(*args, **kwargs):
            def _commit_winner():
                winner_holder["booking"] = real_create(
                    user=user,
                    status=Booking.Status.PENDING,
                    total_amount=Decimal("49.99"),
                    source_hold_group_id=group_id,
                    idempotency_key=str(uuid.uuid4()),
                )
                connection.close()

            t = threading.Thread(target=_commit_winner)
            t.start()
            t.join()
            raise IntegrityError("duplicate key value violates unique constraint")

        monkeypatch.setattr(Booking.objects, "create", _raise_after_concurrent_commit)

        booking, created = create_booking_from_hold(group_id, user)

        monkeypatch.setattr(Booking.objects, "create", real_create)

        assert booking.id == winner_holder["booking"].id
        assert created is False
        seat.refresh_from_db()
        assert seat.held_booking_id == winner_holder["booking"].id


class TestCheckoutBooking:
    def test_raises_when_booking_not_pending(self):
        booking = BookingFactory(status=Booking.Status.CANCELLED)
        with pytest.raises(BookingNotPendingError):
            checkout_booking(booking)

    def test_retry_with_existing_payment_row_missing_intent_id_recovers(
        self, monkeypatch
    ):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("12.00")
        )
        Payment.objects.create(
            booking=booking,
            stripe_payment_intent_id="",
            client_secret="",
            amount=1200,
            currency="usd",
            status=Payment.Status.PENDING,
        )
        fake_intent = MagicMock(id="pi_recovered", client_secret="secret_recovered")
        monkeypatch.setattr(
            "apps.bookings.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        payment = checkout_booking(booking)

        assert payment.stripe_payment_intent_id == "pi_recovered"
        assert payment.client_secret == "secret_recovered"
        assert Payment.objects.filter(booking=booking).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_checkout_without_existing_payment_yields_one_row(
        self, monkeypatch
    ):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("20.00")
        )
        fake_intent = MagicMock(id="pi_race", client_secret="secret_race")
        monkeypatch.setattr(
            "apps.bookings.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                payment = checkout_booking(booking)
                results.append(payment.id)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert Payment.objects.filter(booking=booking).count() == 1
        assert len(results) == 2
        assert len(set(results)) == 1

    def test_stripe_error_maps_to_payment_gateway_error(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("15.00")
        )

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.bookings.services.stripe.PaymentIntent.create", _boom)

        with pytest.raises(PaymentGatewayError):
            checkout_booking(booking)

        assert Payment.objects.filter(booking=booking).count() == 0

    def test_creates_payment_with_correct_cents_conversion(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("49.99")
        )
        fake_intent = MagicMock(id="pi_test_123", client_secret="pi_test_123_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.bookings.services.stripe.PaymentIntent.create", mock_create
        )

        payment = checkout_booking(booking)

        assert payment.amount == 4999
        assert payment.currency == "usd"
        assert payment.stripe_payment_intent_id == "pi_test_123"
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["idempotency_key"] == booking.idempotency_key

    def test_retried_checkout_does_not_call_stripe_twice(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("10.00")
        )
        fake_intent = MagicMock(id="pi_test_456", client_secret="pi_test_456_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.bookings.services.stripe.PaymentIntent.create", mock_create
        )

        first = checkout_booking(booking)
        second = checkout_booking(booking)

        assert mock_create.call_count == 1
        assert first.id == second.id

    @pytest.mark.parametrize(
        "dollars,expected_cents",
        [
            (Decimal("9.99"), 999),
            (Decimal("100.00"), 10000),
            (Decimal("0.01"), 1),
            (Decimal("19.995"), 2000),
        ],
    )
    def test_cents_conversion_exact_for_representative_values(
        self, monkeypatch, dollars, expected_cents
    ):
        booking = BookingFactory(status=Booking.Status.PENDING, total_amount=dollars)
        fake_intent = MagicMock(id="pi_test_x", client_secret="pi_test_x_secret")
        monkeypatch.setattr(
            "apps.bookings.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        payment = checkout_booking(booking)
        assert payment.amount == expected_cents


class TestCancelBooking:
    def test_releases_seats_and_cancels_pending_booking(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)

        cancel_booking(booking)

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert seat.held_booking_id is None

    def test_raises_when_booking_not_pending(self):
        booking = BookingFactory(status=Booking.Status.CONFIRMED)
        with pytest.raises(BookingNotPendingError):
            cancel_booking(booking)

    def test_cancel_then_recancel_is_rejected(self):
        user = UserFactory()
        group_id, seat = _held_seat_with_hold(user)
        booking, _ = create_booking_from_hold(group_id, user)

        cancel_booking(booking)
        with pytest.raises(BookingNotPendingError):
            cancel_booking(booking)
