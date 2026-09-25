import threading
import time
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import stripe
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.bookings.services import (
    BookingExpiredError,
    EventClosedError,
    cancel_pending_bookings_for_event,
    checkout_booking,
    sweep_expired_pending_bookings,
)
from apps.events.factories import EventFactory
from apps.events.models import Event
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
    cancel_payment_intent_if_unpaid,
    confirm_payment_from_webhook,
    create_or_refresh_payment_intent,
    mark_payment_from_webhook,
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

    def test_stripe_succeeds_then_db_write_fails_then_retry_completes_cleanly(
        self, monkeypatch
    ):
        booking, payment = _confirmed_booking_with_payment()

        refund_mock = MagicMock()
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", refund_mock)

        original_save = Payment.save
        call_count = {"n": 0}

        def _save_fails_once_then_recovers(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise IntegrityError("simulated DB failure after Stripe succeeded")
            return original_save(self, *args, **kwargs)

        monkeypatch.setattr(Payment, "save", _save_fails_once_then_recovers)

        with pytest.raises(IntegrityError):
            refund_booking(booking)

        payment.refresh_from_db()
        booking.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED
        assert booking.status == Booking.Status.CONFIRMED
        assert all(t.status == Ticket.Status.VALID for t in booking.tickets.all())

        refund_booking(booking)

        payment.refresh_from_db()
        booking.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED
        assert booking.status == Booking.Status.REFUNDED
        assert all(t.status == Ticket.Status.CANCELLED for t in booking.tickets.all())

        assert refund_mock.call_count == 2
        first_call_kwargs = refund_mock.call_args_list[0].kwargs
        second_call_kwargs = refund_mock.call_args_list[1].kwargs
        expected_key = f"refund-{payment.id}"
        assert first_call_kwargs["idempotency_key"] == expected_key
        assert second_call_kwargs["idempotency_key"] == expected_key

    def test_replay_after_successful_refund_never_calls_stripe_again(self, monkeypatch):
        refund_mock = MagicMock()
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", refund_mock)
        booking, payment = _confirmed_booking_with_payment()

        refund_booking(booking)
        assert refund_mock.call_count == 1

        refund_booking(booking)
        assert refund_mock.call_count == 1


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

    def test_refund_failed_write_bumps_updated_at(self, monkeypatch):
        event = EventFactory(status="approved")
        booking = BookingFactory(status=Booking.Status.CONFIRMED)
        seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
        Ticket.objects.create(booking=booking, event_seat=seat)
        PaymentFactory(
            booking=booking,
            stripe_payment_intent_id="pi_updated_at_regression",
            status=Payment.Status.SUCCEEDED,
        )

        old_updated_at = booking.updated_at
        time.sleep(1.1)

        def boom(*a, **k):
            raise stripe.error.APIConnectionError("simulated failure")

        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", boom)
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )

        refund_event_bookings(str(event.id))

        booking.refresh_from_db()
        assert booking.status == Booking.Status.REFUND_FAILED
        assert booking.updated_at > old_updated_at

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


# ==================================================
# Unfulfillable / late / cancelled-mid-checkout payments
# ==================================================


@pytest.fixture
def stripe_mocks(monkeypatch):
    refund = MagicMock()
    monkeypatch.setattr("apps.payments.services.stripe.Refund.create", refund)
    monkeypatch.setattr("apps.notifications.tasks.send_refund_email.delay", MagicMock())
    monkeypatch.setattr("apps.payments.services.generate_ticket_pdf.delay", MagicMock())
    monkeypatch.setattr(
        "apps.payments.services._enqueue_confirmation_email", MagicMock()
    )
    monkeypatch.setattr("apps.payments.services.broadcast_seat_update", MagicMock())
    return refund


def _pending_booking(event=None, *, pi="pi_pending", age_minutes=0):
    event = event or EventFactory(status=Event.Status.APPROVED)
    booking = BookingFactory(status=Booking.Status.PENDING, total_amount=Decimal("25"))
    if age_minutes:
        Booking.objects.filter(id=booking.id).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        booking.refresh_from_db()
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.HELD, held_booking=booking
    )
    payment = PaymentFactory(
        booking=booking, stripe_payment_intent_id=pi, status=Payment.Status.PENDING
    )
    return booking, seat, payment


class TestWebhookForUnfulfillableBooking:
    def test_late_payment_after_expiry_sweep_is_refunded_not_kept(self, stripe_mocks):
        booking, seat, payment = _pending_booking(pi="pi_late")
        Booking.objects.filter(id=booking.id).update(status=Booking.Status.CANCELLED)
        EventSeat.objects.filter(id=seat.id).update(
            status=EventSeat.Status.AVAILABLE, held_booking=None
        )

        confirm_payment_from_webhook("pi_late")

        booking.refresh_from_db()
        payment.refresh_from_db()
        stripe_mocks.assert_called_once()
        assert stripe_mocks.call_args.kwargs["payment_intent"] == "pi_late"
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.REFUNDED
        assert Ticket.objects.filter(booking=booking).count() == 0

    def test_payment_for_event_cancelled_mid_checkout_is_refunded(self, stripe_mocks):
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, seat, payment = _pending_booking(event, pi="pi_dead_event")

        confirm_payment_from_webhook("pi_dead_event")

        booking.refresh_from_db()
        payment.refresh_from_db()
        stripe_mocks.assert_called_once()
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.REFUNDED
        assert Ticket.objects.filter(booking=booking).count() == 0

    def test_replayed_webhook_after_refund_does_not_refund_twice(self, stripe_mocks):
        event = EventFactory(status=Event.Status.CANCELLED)
        _pending_booking(event, pi="pi_replay")

        confirm_payment_from_webhook("pi_replay")
        confirm_payment_from_webhook("pi_replay")

        stripe_mocks.assert_called_once()

    def test_refund_failure_propagates_so_stripe_retries_the_webhook(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.Refund.create",
            MagicMock(side_effect=stripe.error.APIConnectionError("down")),
        )
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, _, payment = _pending_booking(event, pi="pi_retry")

        with pytest.raises(PaymentGatewayError):
            confirm_payment_from_webhook("pi_retry")

        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED

    def test_normal_payment_still_confirms(self, stripe_mocks):
        booking, seat, payment = _pending_booking(pi="pi_ok")

        confirm_payment_from_webhook("pi_ok")

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert seat.status == EventSeat.Status.BOOKED
        assert Ticket.objects.filter(booking=booking).count() == 1
        stripe_mocks.assert_not_called()


class TestSweepCancelsPaymentIntent:
    def test_sweep_cancels_the_paymentintent_before_cancelling_the_booking(
        self, monkeypatch
    ):
        cancel = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel", cancel
        )
        monkeypatch.setattr(
            "apps.bookings.services.notify_internal_broadcast", MagicMock()
        )
        booking, seat, payment = _pending_booking(pi="pi_stale", age_minutes=6)

        sweep_expired_pending_bookings()

        cancel.assert_called_once_with("pi_stale")
        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert payment.status == Payment.Status.CANCELED

    def test_sweep_leaves_a_booking_alone_when_the_customer_already_paid(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel",
            MagicMock(side_effect=stripe.error.InvalidRequestError("done", "id")),
        )
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.retrieve",
            MagicMock(return_value=MagicMock(status="succeeded")),
        )
        booking, seat, _ = _pending_booking(pi="pi_paid", age_minutes=6)

        sweep_expired_pending_bookings()

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.PENDING
        assert seat.held_booking_id == booking.id

    def test_stripe_outage_defers_the_cancellation(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel",
            MagicMock(side_effect=stripe.error.APIConnectionError("down")),
        )
        booking, _, _ = _pending_booking(pi="pi_outage", age_minutes=6)

        assert cancel_payment_intent_if_unpaid(booking) is False

    def test_booking_without_a_paymentintent_is_freely_cancellable(self):
        booking = BookingFactory(status=Booking.Status.PENDING)
        assert cancel_payment_intent_if_unpaid(booking) is True


class TestCheckoutGuards:
    def test_checkout_of_an_expired_booking_is_refused(self):
        booking, _, _ = _pending_booking(age_minutes=6)
        with pytest.raises(BookingExpiredError):
            checkout_booking(booking)

    def test_checkout_for_a_cancelled_event_is_refused(self):
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, _, _ = _pending_booking(event)
        with pytest.raises(EventClosedError):
            checkout_booking(booking)

    def test_checkout_for_an_event_that_already_ended_is_refused(self):
        event = EventFactory(status=Event.Status.APPROVED)
        Event.objects.filter(id=event.id).update(
            start_datetime=timezone.now() - timedelta(hours=5),
            end_datetime=timezone.now() - timedelta(hours=2),
        )
        event.refresh_from_db()
        booking, _, _ = _pending_booking(event)
        with pytest.raises(EventClosedError):
            checkout_booking(booking)


class TestCancelPendingBookingsForEvent:
    def test_unpaid_bookings_are_closed_and_their_paymentintent_cancelled(
        self, monkeypatch
    ):
        cancel = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel", cancel
        )
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, seat, payment = _pending_booking(event, pi="pi_evt")

        cancel_pending_bookings_for_event(event.id)

        cancel.assert_called_once_with("pi_evt")
        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert seat.held_booking_id is None
        assert seat.status == EventSeat.Status.HELD


class TestMarkPaymentFromWebhook:
    def test_failed_and_canceled_events_update_a_pending_payment(self):
        payment = PaymentFactory(
            stripe_payment_intent_id="pi_f", status=Payment.Status.PENDING
        )
        mark_payment_from_webhook("pi_f", Payment.Status.FAILED)
        payment.refresh_from_db()
        assert payment.status == Payment.Status.FAILED

    def test_a_settled_payment_is_never_downgraded(self):
        payment = PaymentFactory(
            stripe_payment_intent_id="pi_s", status=Payment.Status.SUCCEEDED
        )
        mark_payment_from_webhook("pi_s", Payment.Status.FAILED)
        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED
