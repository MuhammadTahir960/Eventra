import threading
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.db import connection

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory

from ..factories import PaymentFactory
from ..models import Payment
from ..services import (
    PaymentGatewayError,
    PaymentNotFoundError,
    WebhookSignatureError,
    _to_cents,
    confirm_payment_from_webhook,
    create_or_refresh_payment_intent,
    refund_booking,
    refund_event_bookings,
    verify_stripe_webhook_signature,
)

pytestmark = pytest.mark.django_db


class TestToCents:
    @pytest.mark.parametrize(
        "dollars,expected_cents",
        [
            (Decimal("9.99"), 999),
            (Decimal("100.00"), 10000),
            (Decimal("0.01"), 1),
            (Decimal("19.995"), 2000),
        ],
    )
    def test_exact_for_representative_values(self, dollars, expected_cents):
        assert _to_cents(dollars) == expected_cents


class TestCreateOrRefreshPaymentIntent:
    def test_creates_payment_with_correct_cents_and_currency(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("49.99")
        )
        fake_intent = MagicMock(id="pi_test_123", client_secret="pi_test_123_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", mock_create
        )

        payment = create_or_refresh_payment_intent(booking)

        assert payment.amount == 4999
        assert payment.currency == "usd"
        assert payment.stripe_payment_intent_id == "pi_test_123"
        assert payment.client_secret == "pi_test_123_secret"
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["idempotency_key"] == booking.idempotency_key
        assert kwargs["metadata"] == {"booking_id": str(booking.id)}

    def test_local_short_circuit_skips_a_second_stripe_call(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("10.00")
        )
        fake_intent = MagicMock(id="pi_test_456", client_secret="pi_test_456_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", mock_create
        )

        first = create_or_refresh_payment_intent(booking)
        second = create_or_refresh_payment_intent(booking)

        assert mock_create.call_count == 1
        assert first.id == second.id

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
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        payment = create_or_refresh_payment_intent(booking)

        assert payment.stripe_payment_intent_id == "pi_recovered"
        assert payment.client_secret == "secret_recovered"
        assert Payment.objects.filter(booking=booking).count() == 1

    def test_stripe_error_maps_to_payment_gateway_error(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("15.00")
        )

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.payments.services.stripe.PaymentIntent.create", _boom)

        with pytest.raises(PaymentGatewayError):
            create_or_refresh_payment_intent(booking)

        assert Payment.objects.filter(booking=booking).count() == 0

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_calls_without_existing_payment_yield_one_row(self, monkeypatch):
        booking = BookingFactory(
            status=Booking.Status.PENDING, total_amount=Decimal("20.00")
        )
        fake_intent = MagicMock(id="pi_race", client_secret="secret_race")
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create",
            MagicMock(return_value=fake_intent),
        )

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                payment = create_or_refresh_payment_intent(booking)
                results.append(payment.id)
            except Exception as exc:
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


def _pending_booking_with_held_seat(user=None, event=None):
    user = user or UserFactory()
    event = event or EventFactory(status="approved")
    booking = BookingFactory(user=user, status=Booking.Status.PENDING)
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.HELD, held_booking=booking
    )
    payment = PaymentFactory(
        booking=booking,
        stripe_payment_intent_id="pi_confirm_test",
        status=Payment.Status.PENDING,
    )
    return booking, seat, payment


class TestConfirmPaymentFromWebhook:
    def test_happy_path_confirms_booking_books_seat_creates_ticket(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.generate_ticket_pdf.delay", MagicMock()
        )
        monkeypatch.setattr(
            "apps.payments.services._enqueue_confirmation_email", MagicMock()
        )
        monkeypatch.setattr("apps.payments.services.broadcast_seat_update", MagicMock())

        booking, seat, payment = _pending_booking_with_held_seat()

        result = confirm_payment_from_webhook(payment.stripe_payment_intent_id)

        result.refresh_from_db()
        seat.refresh_from_db()
        payment.refresh_from_db()
        assert result.status == Booking.Status.CONFIRMED
        assert seat.status == EventSeat.Status.BOOKED
        assert seat.held_booking_id is None
        assert payment.status == Payment.Status.SUCCEEDED
        assert Ticket.objects.filter(booking=booking, event_seat=seat).count() == 1

    def test_idempotent_replay_does_not_create_duplicate_tickets(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.generate_ticket_pdf.delay", MagicMock()
        )
        monkeypatch.setattr(
            "apps.payments.services._enqueue_confirmation_email", MagicMock()
        )
        monkeypatch.setattr("apps.payments.services.broadcast_seat_update", MagicMock())

        booking, seat, payment = _pending_booking_with_held_seat()

        confirm_payment_from_webhook(payment.stripe_payment_intent_id)
        confirm_payment_from_webhook(payment.stripe_payment_intent_id)

        assert Ticket.objects.filter(booking=booking).count() == 1

    def test_side_effects_fire_exactly_once_on_replay(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        mock_pdf = MagicMock()
        mock_email = MagicMock()
        mock_broadcast = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.generate_ticket_pdf.delay", mock_pdf
        )
        monkeypatch.setattr(
            "apps.payments.services._enqueue_confirmation_email", mock_email
        )
        monkeypatch.setattr(
            "apps.payments.services.broadcast_seat_update", mock_broadcast
        )

        _, _, payment = _pending_booking_with_held_seat()
        with django_capture_on_commit_callbacks(execute=True):
            confirm_payment_from_webhook(payment.stripe_payment_intent_id)
        with django_capture_on_commit_callbacks(execute=True):
            confirm_payment_from_webhook(payment.stripe_payment_intent_id)

        mock_pdf.assert_called_once()
        mock_email.assert_called_once()
        mock_broadcast.assert_called_once()

    def test_unknown_payment_intent_raises(self):
        with pytest.raises(PaymentNotFoundError):
            confirm_payment_from_webhook("pi_does_not_exist")


class TestVerifyStripeWebhookSignature:
    def test_valid_signature_returns_event(self, monkeypatch):
        fake_event = {"type": "payment_intent.succeeded"}
        monkeypatch.setattr(
            "apps.payments.services.stripe.Webhook.construct_event",
            MagicMock(return_value=fake_event),
        )
        result = verify_stripe_webhook_signature(b"{}", "t=1,v1=abc")
        assert result == fake_event

    def test_invalid_signature_raises(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise stripe.error.SignatureVerificationError("bad sig", "sig_header")

        monkeypatch.setattr(
            "apps.payments.services.stripe.Webhook.construct_event", _boom
        )
        with pytest.raises(WebhookSignatureError):
            verify_stripe_webhook_signature(b"{}", "bad")

    def test_malformed_payload_raises(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise ValueError("invalid payload")

        monkeypatch.setattr(
            "apps.payments.services.stripe.Webhook.construct_event", _boom
        )
        with pytest.raises(WebhookSignatureError):
            verify_stripe_webhook_signature(b"not json", "sig")


def _confirmed_booking_with_payment(user=None):
    user = user or UserFactory()
    booking = BookingFactory(user=user, status=Booking.Status.CONFIRMED)
    seat = EventSeatFactory(status=EventSeat.Status.BOOKED)
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    payment = PaymentFactory(
        booking=booking,
        stripe_payment_intent_id=f"pi_refund_{booking.id}",
        status=Payment.Status.SUCCEEDED,
    )
    return booking, payment


class TestRefundBooking:
    def test_happy_path_refunds_payment_cancels_tickets_and_booking(self, monkeypatch):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        booking, payment = _confirmed_booking_with_payment()

        refund_booking(booking)

        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.REFUNDED
        assert all(t.status == Ticket.Status.CANCELLED for t in booking.tickets.all())

    def test_stripe_failure_raises_and_leaves_booking_unchanged(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("network blip")

        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", _boom)
        booking, payment = _confirmed_booking_with_payment()

        with pytest.raises(PaymentGatewayError):
            refund_booking(booking)

        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert payment.status == Payment.Status.SUCCEEDED


class TestRefundEventBookings:
    def test_batch_isolation_one_stripe_failure_does_not_affect_others(
        self, monkeypatch
    ):
        event = EventFactory(status="approved")
        bookings = []
        seats = []
        for i in range(3):
            user = UserFactory()
            booking = BookingFactory(user=user, status=Booking.Status.CONFIRMED)
            seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
            Ticket.objects.create(booking=booking, event_seat=seat)

            PaymentFactory(
                booking=booking,
                stripe_payment_intent_id=f"pi_batch_{i}",
                status=Payment.Status.SUCCEEDED,
            )
            bookings.append(booking)
            seats.append(seat)

        failing_booking = bookings[1]

        def _maybe_boom(*, payment_intent, idempotency_key=None):
            if payment_intent == "pi_batch_1":
                raise stripe.error.APIConnectionError("simulated mid-batch failure")
            return MagicMock()

        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", _maybe_boom)
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay",
            MagicMock(),
        )

        refund_event_bookings(str(event.id))

        for i, booking in enumerate(bookings):
            booking.refresh_from_db()
            seats[i].refresh_from_db()
            assert seats[i].status == EventSeat.Status.BOOKED
            if booking.id == failing_booking.id:
                assert booking.status == Booking.Status.REFUND_FAILED
            else:
                assert booking.status == Booking.Status.REFUNDED

    def test_only_failed_scopes_to_refund_failed_bookings_only(self, monkeypatch):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )
        event = EventFactory(status="approved")

        stuck_user = UserFactory()
        stuck_booking = BookingFactory(
            user=stuck_user, status=Booking.Status.REFUND_FAILED
        )
        stuck_seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
        Ticket.objects.create(booking=stuck_booking, event_seat=stuck_seat)

        PaymentFactory(
            booking=stuck_booking,
            stripe_payment_intent_id="pi_retry_target",
            status=Payment.Status.SUCCEEDED,
        )

        already_refunded_user = UserFactory()
        already_refunded_booking = BookingFactory(
            user=already_refunded_user, status=Booking.Status.REFUNDED
        )
        already_refunded_seat = EventSeatFactory(
            event=event, status=EventSeat.Status.BOOKED
        )
        Ticket.objects.create(
            booking=already_refunded_booking, event_seat=already_refunded_seat
        )
        PaymentFactory(
            booking=already_refunded_booking,
            stripe_payment_intent_id="pi_already_refunded",
            status=Payment.Status.REFUNDED,
        )

        refund_event_bookings(str(event.id), only_failed=True)

        stuck_booking.refresh_from_db()
        already_refunded_booking.refresh_from_db()
        assert stuck_booking.status == Booking.Status.REFUNDED
        assert already_refunded_booking.status == Booking.Status.REFUNDED

    def test_no_confirmed_bookings_is_a_safe_no_op(self):
        event = EventFactory(status="approved")
        refund_event_bookings(str(event.id))
