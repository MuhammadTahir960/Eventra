import threading
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
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.events.services import EventHasPaidBookingsError, reject_event
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory
from tests.helpers import confirm_paid_in_full, paid_booking, unpaid_booking

from ..factories import PaymentFactory
from ..models import Payment, Refund, RefundItem
from ..services import (
    BookingNotCancellableError,
    PaymentGatewayError,
    PaymentNotFoundError,
    RefundNotAllowedError,
    WebhookSignatureError,
    _to_cents,
    cancel_booking,
    cancel_payment_intent_if_unpaid,
    confirm_payment_from_webhook,
    create_or_refresh_payment_intent,
    mark_payment_from_webhook,
    process_refund,
    refund_booking,
    refund_event_bookings,
    refund_part_of_event,
    refund_price_drops,
    retry_unfinished_refunds,
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
        booking = unpaid_booking("49.99")
        fake_intent = MagicMock(id="pi_test_123", client_secret="pi_test_123_secret")
        mock_create = MagicMock(return_value=fake_intent)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.create", mock_create
        )

        payment = create_or_refresh_payment_intent(booking)

        assert mock_create.call_args.kwargs["amount"] == 4999
        assert mock_create.call_args.kwargs["currency"] == "usd"
        assert payment.stripe_payment_intent_id == "pi_test_123"
        assert payment.client_secret == "pi_test_123_secret"
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["idempotency_key"] == f"payment-intent-{booking.id}"
        assert kwargs["metadata"] == {"booking_id": str(booking.id)}
        assert kwargs["payment_method_types"] == ["card"]

    def test_local_short_circuit_skips_a_second_stripe_call(self, monkeypatch):
        booking = unpaid_booking("10.00")
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
        booking = unpaid_booking("12.00")
        Payment.objects.create(
            booking=booking,
            stripe_payment_intent_id="",
            client_secret="",
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
        booking = unpaid_booking("15.00")

        def _boom(*args, **kwargs):
            raise stripe.error.APIConnectionError("could not connect to Stripe")

        monkeypatch.setattr("apps.payments.services.stripe.PaymentIntent.create", _boom)

        with pytest.raises(PaymentGatewayError):
            create_or_refresh_payment_intent(booking)

        assert Payment.objects.filter(booking=booking).count() == 0

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_calls_without_existing_payment_yield_one_row(self, monkeypatch):
        booking = unpaid_booking("20.00")
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
    seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
    TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.PENDING)
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

        result = confirm_paid_in_full(payment.stripe_payment_intent_id)

        result.refresh_from_db()
        seat.refresh_from_db()
        payment.refresh_from_db()
        assert result.status == Booking.Status.CONFIRMED
        assert seat.status == EventSeat.Status.BOOKED
        assert not booking.held_seats().filter(id=seat.id).exists()
        assert payment.status == Payment.Status.SUCCEEDED
        ticket = Ticket.objects.get(booking=booking, event_seat=seat)
        assert ticket.attendee_name == booking.user.full_name

    def test_idempotent_replay_does_not_create_duplicate_tickets(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.generate_ticket_pdf.delay", MagicMock()
        )
        monkeypatch.setattr(
            "apps.payments.services._enqueue_confirmation_email", MagicMock()
        )
        monkeypatch.setattr("apps.payments.services.broadcast_seat_update", MagicMock())

        booking, seat, payment = _pending_booking_with_held_seat()

        confirm_paid_in_full(payment.stripe_payment_intent_id)
        confirm_paid_in_full(payment.stripe_payment_intent_id)

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
            confirm_paid_in_full(payment.stripe_payment_intent_id)
        with django_capture_on_commit_callbacks(execute=True):
            confirm_paid_in_full(payment.stripe_payment_intent_id)

        mock_pdf.assert_called_once()
        mock_email.assert_called_once()
        mock_broadcast.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    def test_reject_during_webhook_waits_and_sees_the_paid_booking(self, monkeypatch):
        for target in (
            "apps.payments.services.generate_ticket_pdf.delay",
            "apps.payments.services._enqueue_confirmation_email",
            "apps.payments.services.broadcast_seat_update",
        ):
            monkeypatch.setattr(target, MagicMock())
        event = EventFactory(status=Event.Status.PENDING_APPROVAL)
        booking, _, payment = _pending_booking_with_held_seat(event=event)

        webhook_inside, release_webhook = threading.Event(), threading.Event()
        real_save = Payment.save

        def paused_save(payment_self, *args, **kwargs):
            if payment_self.status == Payment.Status.SUCCEEDED:
                webhook_inside.set()
                release_webhook.wait(10)
            return real_save(payment_self, *args, **kwargs)

        monkeypatch.setattr(Payment, "save", paused_save)
        errors = []

        def run(fn):
            try:
                fn()
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        webhook = threading.Thread(
            target=run,
            args=(lambda: confirm_paid_in_full(payment.stripe_payment_intent_id),),
        )
        reject = threading.Thread(
            target=run,
            args=(lambda: reject_event(Event.objects.get(pk=event.pk), "No"),),
        )
        webhook.start()
        try:
            assert webhook_inside.wait(10)
            reject.start()
            reject.join(0.5)
            assert reject.is_alive(), "reject did not wait for the webhook's lock"
        finally:
            release_webhook.set()
            webhook.join(10)
            reject.join(10)

        assert [type(e) for e in errors] == [EventHasPaidBookingsError]
        event.refresh_from_db()
        booking.refresh_from_db()
        assert event.status == Event.Status.PENDING_APPROVAL
        assert booking.status == Booking.Status.CONFIRMED

    def test_unknown_payment_intent_raises(self):
        with pytest.raises(PaymentNotFoundError):
            confirm_paid_in_full("pi_does_not_exist")


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


class TestRefundBooking:
    def test_records_a_line_per_ticket_and_cancels_the_booking(
        self, stripe_refunds, django_capture_on_commit_callbacks, mailoutbox
    ):
        event = EventFactory(status=Event.Status.CANCELLED)
        tier = TicketTierFactory(event=event)
        booking = paid_booking(event, (tier, "30.00"), (tier, "20.00"))

        with django_capture_on_commit_callbacks(execute=True):
            assert refund_booking(booking, Refund.Reason.CANCELLED_EVENT) is True

        booking.refresh_from_db()
        refund = Refund.objects.get()
        assert booking.status == Booking.Status.REFUNDED
        assert not booking.tickets.exclude(status=Ticket.Status.CANCELLED).exists()
        assert _lines(booking) == [Decimal("20.00"), Decimal("30.00")]
        assert refund.status == Refund.Status.SUCCEEDED
        assert stripe_refunds.call_args.kwargs["amount"] == 5000
        assert stripe_refunds.call_args.kwargs["idempotency_key"] == refund.key
        assert len(mailoutbox) == 1 and "$50.00" in mailoutbox[0].body

    def test_returns_only_what_earlier_refunds_left(self, stripe_refunds):
        event = EventFactory(status=Event.Status.COMPLETED)
        booking = paid_booking(event, (TicketTierFactory(event=event), "10.00"))
        refund_part_of_event(event, 50)

        refund_booking(booking, Refund.Reason.CANCELLED_EVENT)

        assert _lines(booking) == [Decimal("5.00"), Decimal("5.00")]

    def test_a_second_call_records_nothing(self, stripe_refunds):
        event = EventFactory(status=Event.Status.CANCELLED)
        booking = paid_booking(event, (TicketTierFactory(event=event), "10.00"))

        assert refund_booking(booking, Refund.Reason.CANCELLED_EVENT) is True
        assert refund_booking(booking, Refund.Reason.UNAVAILABLE) is False
        assert Refund.objects.count() == 1

    def test_the_database_allows_one_full_refund_per_booking(self):
        booking = BookingFactory()
        Refund.objects.create(
            booking=booking, reason=Refund.Reason.CANCELLED_EVENT, key="first"
        )
        Refund.objects.create(booking=booking, reason=Refund.Reason.PRICE_DROP, key="p")
        with pytest.raises(IntegrityError):
            Refund.objects.create(
                booking=booking, reason=Refund.Reason.UNAVAILABLE, key="second"
            )


class TestRefundEventBookings:
    def test_refunds_paid_bookings_and_leaves_the_rest(self, stripe_refunds):
        event = EventFactory(status=Event.Status.CANCELLED)
        tier = TicketTierFactory(event=event)
        paid = [paid_booking(event, (tier, "10.00")) for _ in range(2)]
        pending, _, _ = _pending_booking(event, pi="pi_unpaid")

        refund_event_bookings(str(event.id))

        for booking in paid:
            booking.refresh_from_db()
            assert booking.status == Booking.Status.REFUNDED
        pending.refresh_from_db()
        assert pending.status == Booking.Status.PENDING
        assert Refund.objects.count() == 2

    def test_a_stripe_failure_is_kept_for_a_retry(
        self, stripe_refunds, django_capture_on_commit_callbacks
    ):
        stripe_refunds.side_effect = stripe.error.APIConnectionError("down")
        event = EventFactory(status=Event.Status.CANCELLED)
        booking = paid_booking(event, (TicketTierFactory(event=event), "10.00"))

        with django_capture_on_commit_callbacks(execute=True):
            refund_event_bookings(str(event.id))

        booking.refresh_from_db()
        refund = Refund.objects.get()
        assert booking.status == Booking.Status.REFUNDED
        assert (refund.status, refund.attempts) == (Refund.Status.FAILED, 1)

    def test_no_confirmed_bookings_is_a_safe_no_op(self):
        event = EventFactory(status="approved")
        refund_event_bookings(str(event.id))


# ==================================================
# Unfulfillable / late / cancelled-mid-checkout payments
# ==================================================


@pytest.fixture
def stripe_mocks(monkeypatch):
    refund = MagicMock(return_value=MagicMock(id="re_test"))
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
    booking = BookingFactory(status=Booking.Status.PENDING)
    if age_minutes:
        Booking.objects.filter(id=booking.id).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        booking.refresh_from_db()
    seat = EventSeatFactory(event=event, status=EventSeat.Status.HELD)
    TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.PENDING)
    payment = PaymentFactory(
        booking=booking, stripe_payment_intent_id=pi, status=Payment.Status.PENDING
    )
    return booking, seat, payment


@pytest.fixture
def webhook(django_capture_on_commit_callbacks):
    def run(pi):
        with django_capture_on_commit_callbacks(execute=True):
            return confirm_paid_in_full(pi)

    return run


class TestWebhookForUnfulfillableBooking:
    def test_late_payment_after_expiry_sweep_is_refunded_not_kept(
        self, stripe_mocks, webhook
    ):
        booking, seat, payment = _pending_booking(pi="pi_late")
        Booking.objects.filter(id=booking.id).update(status=Booking.Status.CANCELLED)
        EventSeat.objects.filter(id=seat.id).update(status=EventSeat.Status.AVAILABLE)
        booking.tickets.update(status=Ticket.Status.CANCELLED)

        webhook("pi_late")

        booking.refresh_from_db()
        payment.refresh_from_db()
        stripe_mocks.assert_called_once()
        assert stripe_mocks.call_args.kwargs["payment_intent"] == "pi_late"
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.SUCCEEDED
        assert Refund.objects.get().reason == Refund.Reason.UNAVAILABLE
        assert not booking.tickets.exclude(status=Ticket.Status.CANCELLED).exists()

    def test_payment_for_event_cancelled_mid_checkout_is_refunded(
        self, stripe_mocks, webhook
    ):
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, seat, payment = _pending_booking(event, pi="pi_dead_event")

        webhook("pi_dead_event")

        booking.refresh_from_db()
        stripe_mocks.assert_called_once()
        assert booking.status == Booking.Status.REFUNDED
        assert not booking.tickets.exclude(status=Ticket.Status.CANCELLED).exists()

    def test_replayed_webhook_after_refund_does_not_refund_twice(
        self, stripe_mocks, webhook
    ):
        event = EventFactory(status=Event.Status.CANCELLED)
        _pending_booking(event, pi="pi_replay")

        webhook("pi_replay")
        webhook("pi_replay")

        stripe_mocks.assert_called_once()

    def test_a_failed_refund_is_kept_for_the_sweeper(self, monkeypatch, webhook):
        monkeypatch.setattr(
            "apps.payments.services.stripe.Refund.create",
            MagicMock(side_effect=stripe.error.APIConnectionError("down")),
        )
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, _, payment = _pending_booking(event, pi="pi_retry")

        webhook("pi_retry")

        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED
        assert Refund.objects.get().status == Refund.Status.FAILED

    def test_normal_payment_still_confirms(self, stripe_mocks):
        booking, seat, payment = _pending_booking(pi="pi_ok")

        confirm_paid_in_full("pi_ok")

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert seat.status == EventSeat.Status.BOOKED
        assert Ticket.objects.filter(booking=booking).count() == 1
        stripe_mocks.assert_not_called()


class TestUnfulfillableWebhookReleasesSeats:
    @pytest.mark.parametrize(
        "event_status", [Event.Status.CANCELLED, Event.Status.REJECTED]
    )
    def test_held_seats_go_back_to_available_and_are_broadcast(
        self,
        event_status,
        stripe_mocks,
        monkeypatch,
        django_capture_on_commit_callbacks,
    ):
        broadcast = MagicMock()
        monkeypatch.setattr("apps.payments.services.broadcast_seat_update", broadcast)
        event = EventFactory(status=event_status)
        booking, seat, _ = _pending_booking(event, pi="pi_release")

        with django_capture_on_commit_callbacks(execute=True):
            confirm_paid_in_full("pi_release")

        seat.refresh_from_db()
        assert seat.status == EventSeat.Status.AVAILABLE
        assert not booking.held_seats().filter(id=seat.id).exists()
        broadcast.assert_called_once()
        assert broadcast.call_args.kwargs["event"].id == event.id
        assert [s.id for s in broadcast.call_args.kwargs["seats"]] == [seat.id]

    def test_seats_already_sold_on_the_event_are_left_alone(
        self, stripe_mocks, django_capture_on_commit_callbacks
    ):
        event = EventFactory(status=Event.Status.CANCELLED)
        _, held_seat, _ = _pending_booking(event, pi="pi_mixed")
        sold_seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)

        with django_capture_on_commit_callbacks(execute=True):
            confirm_paid_in_full("pi_mixed")

        held_seat.refresh_from_db()
        sold_seat.refresh_from_db()
        assert held_seat.status == EventSeat.Status.AVAILABLE
        assert sold_seat.status == EventSeat.Status.BOOKED

    def test_no_broadcast_when_the_booking_holds_no_seats(
        self, stripe_mocks, monkeypatch, django_capture_on_commit_callbacks
    ):
        broadcast = MagicMock()
        monkeypatch.setattr("apps.payments.services.broadcast_seat_update", broadcast)
        booking, seat, _ = _pending_booking(pi="pi_noseats")
        Booking.objects.filter(id=booking.id).update(status=Booking.Status.CANCELLED)
        EventSeat.objects.filter(id=seat.id).update(status=EventSeat.Status.AVAILABLE)
        booking.tickets.update(status=Ticket.Status.CANCELLED)

        with django_capture_on_commit_callbacks(execute=True):
            confirm_paid_in_full("pi_noseats")

        broadcast.assert_not_called()


@pytest.mark.parametrize("extra_cents, currency", [(-1, "usd"), (1, "usd"), (0, "eur")])
def test_a_payment_that_doesnt_match_the_tickets_is_refunded_not_fulfilled(
    stripe_refunds, django_capture_on_commit_callbacks, caplog, extra_cents, currency
):
    booking, seat, _ = _pending_booking(pi="pi_odd")
    cents = _to_cents(booking.total_amount) + extra_cents

    with django_capture_on_commit_callbacks(execute=True):
        result = confirm_payment_from_webhook(
            "pi_odd", amount_received=cents, currency=currency
        )

    seat.refresh_from_db()
    assert result.status == Booking.Status.REFUNDED
    assert seat.status == EventSeat.Status.AVAILABLE
    assert not booking.tickets.exclude(status=Ticket.Status.CANCELLED).exists()
    refund = Refund.objects.get(booking=booking)
    assert refund.reason == Refund.Reason.UNAVAILABLE
    assert _to_cents(sum(i.amount for i in refund.items.all())) == cents
    assert stripe_refunds.call_args.kwargs["amount"] == cents
    assert "refunding" in caplog.text


@pytest.mark.parametrize(
    "received, lines",
    [
        (4000, ["10.00", "30.00"]),
        (3000, ["7.50", "22.50"]),
        (4001, None),
        (1, None),
    ],
)
def test_a_mismatched_payment_is_shared_across_the_tickets_to_the_cent(
    stripe_refunds, django_capture_on_commit_callbacks, received, lines
):
    event = EventFactory(status=Event.Status.CANCELLED)
    booking = unpaid_booking("10.00", event=event)
    TicketFactory(
        booking=booking,
        event_seat=EventSeatFactory(event=event, status=EventSeat.Status.HELD),
        price=Decimal("30.00"),
        status=Ticket.Status.PENDING,
    )
    PaymentFactory(booking=booking, stripe_payment_intent_id="pi_split")

    with django_capture_on_commit_callbacks(execute=True):
        confirm_payment_from_webhook(
            "pi_split", amount_received=received, currency="usd"
        )

    amounts = sorted(
        RefundItem.objects.filter(refund__booking=booking).values_list(
            "amount", flat=True
        )
    )
    assert _to_cents(sum(amounts)) == received
    if lines:
        assert [str(a) for a in amounts] == lines
    assert stripe_refunds.call_args.kwargs["amount"] == received


class TestSweepCancelsPaymentIntent:
    def test_sweep_cancels_the_paymentintent_before_cancelling_the_booking(
        self, monkeypatch
    ):
        cancel = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel", cancel
        )
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", MagicMock()
        )
        booking, seat, payment = _pending_booking(pi="pi_stale", age_minutes=6)

        sweep_expired_pending_bookings()

        cancel.assert_called_once_with("pi_stale")
        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert payment.status == Payment.Status.CANCELED

    @pytest.mark.parametrize(
        "extra_cents, outcome", [(0, "confirmed"), (100, "refunded")]
    )
    def test_sweep_confirms_a_paid_booking_whose_webhook_never_came(
        self, monkeypatch, stripe_refunds, extra_cents, outcome
    ):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel",
            MagicMock(side_effect=stripe.error.InvalidRequestError("done", "id")),
        )
        booking, seat, payment = _pending_booking(pi="pi_paid", age_minutes=6)
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.retrieve",
            MagicMock(
                return_value=MagicMock(
                    id="pi_paid",
                    status="succeeded",
                    amount_received=_to_cents(booking.total_amount) + extra_cents,
                    currency="usd",
                )
            ),
        )

        sweep_expired_pending_bookings()

        booking.refresh_from_db()
        seat.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == outcome
        assert payment.status == Payment.Status.SUCCEEDED
        assert seat.status == (
            EventSeat.Status.BOOKED
            if outcome == "confirmed"
            else EventSeat.Status.AVAILABLE
        )

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
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        cancel = MagicMock()
        broadcast = MagicMock()
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel", cancel
        )
        monkeypatch.setattr(
            "apps.seating.services.notify_internal_broadcast", broadcast
        )
        event = EventFactory(status=Event.Status.CANCELLED)
        booking, seat, payment = _pending_booking(event, pi="pi_evt")

        with django_capture_on_commit_callbacks(execute=True):
            cancel_pending_bookings_for_event(event.id)

        cancel.assert_called_once_with("pi_evt")
        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert not booking.held_seats().filter(id=seat.id).exists()
        assert seat.status == EventSeat.Status.AVAILABLE
        broadcast.assert_called_once_with(
            event_slug=event.slug, seat_ids=[seat.id], status_label="available"
        )

    def test_booked_seats_on_the_cancelled_event_stay_frozen(self, monkeypatch):
        monkeypatch.setattr(
            "apps.payments.services.stripe.PaymentIntent.cancel", MagicMock()
        )
        event = EventFactory(status=Event.Status.CANCELLED)
        _pending_booking(event, pi="pi_x")
        sold = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)

        cancel_pending_bookings_for_event(event.id)

        sold.refresh_from_db()
        assert sold.status == EventSeat.Status.BOOKED


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


@pytest.fixture
def stripe_refunds(monkeypatch):
    create = MagicMock(return_value=MagicMock(id="re_test"))
    monkeypatch.setattr("apps.payments.services.stripe.Refund.create", create)
    return create


def _lines(booking):
    return sorted(
        RefundItem.objects.filter(refund__booking=booking).values_list(
            "amount", flat=True
        )
    )


class TestPartialRefundOfAnAbandonedEvent:
    def test_refunds_a_share_of_each_paid_seat_and_emails_once(
        self, stripe_refunds, django_capture_on_commit_callbacks, mailoutbox
    ):
        event = EventFactory(status=Event.Status.COMPLETED)
        tier = TicketTierFactory(event=event)
        booking = paid_booking(event, (tier, "33.33"), (tier, "20.00"))

        with django_capture_on_commit_callbacks(execute=True):
            refunds = refund_part_of_event(event, 50)

        assert len(refunds) == 1
        assert _lines(booking) == [Decimal("10.00"), Decimal("16.67")]
        refund = Refund.objects.get()
        assert refund.status == Refund.Status.SUCCEEDED
        assert stripe_refunds.call_args.kwargs["amount"] == 2667
        assert stripe_refunds.call_args.kwargs["idempotency_key"] == refund.key
        assert len(mailoutbox) == 1 and "$26.67" in mailoutbox[0].body

    def test_only_once_only_when_completed_and_only_before_payout(self, stripe_refunds):
        event = EventFactory(status=Event.Status.COMPLETED)
        paid_booking(event, (TicketTierFactory(event=event), "10.00"))
        refund_part_of_event(event, 10)
        with pytest.raises(RefundNotAllowedError, match="already been partly"):
            refund_part_of_event(event, 10)
        with pytest.raises(RefundNotAllowedError, match="completed"):
            refund_part_of_event(EventFactory(status=Event.Status.APPROVED), 10)

    def test_a_share_of_what_is_left_after_an_earlier_refund(self, stripe_refunds):
        event = EventFactory(status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, price="50.00")
        booking = paid_booking(event, (tier, "50.00"))
        tier.price = Decimal("40.00")
        tier.save()
        refund_price_drops(event)
        Event.all_objects.filter(pk=event.pk).update(
            status=Event.Status.COMPLETED, completed_at=timezone.now()
        )
        event.refresh_from_db()

        refund_part_of_event(event, 50)

        assert _lines(booking) == [Decimal("10.00"), Decimal("20.00")]


class TestPriceDropRefunds:
    def test_only_seats_of_the_cheaper_tier_get_the_difference(self, stripe_refunds):
        event = EventFactory(status=Event.Status.APPROVED)
        vip = TicketTierFactory(event=event, price="100.00")
        general = TicketTierFactory(event=event, price="50.00")
        booking = paid_booking(event, (vip, "100.00"), (general, "50.00"))
        general.price = Decimal("40.00")
        general.save()

        refund_price_drops(event)

        line = RefundItem.objects.get(refund__booking=booking)
        assert line.amount == Decimal("10.00")
        assert line.ticket.event_seat.ticket_tier == general

    def test_each_drop_refunds_once_and_a_raise_refunds_nothing(self, stripe_refunds):
        event = EventFactory(status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, price="50.00")
        booking = paid_booking(event, (tier, "50.00"))
        for price in ("40.00", "40.00", "60.00", "30.00"):
            tier.price = Decimal(price)
            tier.save()
            refund_price_drops(event)

        assert _lines(booking) == [Decimal("10.00"), Decimal("10.00")]

    def test_seats_with_their_own_price_are_left_alone(self, stripe_refunds):
        event = EventFactory(status=Event.Status.APPROVED)
        tier = TicketTierFactory(event=event, price="50.00")
        booking = paid_booking(event, (tier, "50.00"))
        EventSeat.objects.filter(tickets__booking=booking).update(
            price_override=Decimal("50.00")
        )
        tier.price = Decimal("10.00")
        tier.save()

        assert refund_price_drops(event) == []


class TestRefundRetries:
    def test_a_failed_refund_is_retried_by_the_sweeper(
        self, monkeypatch, stripe_refunds
    ):
        event = EventFactory(status=Event.Status.COMPLETED)
        paid_booking(event, (TicketTierFactory(event=event), "10.00"))
        stripe_refunds.side_effect = stripe.error.APIConnectionError("down")
        refund_part_of_event(event, 50)
        refund = Refund.objects.get()
        process_refund(refund.id)
        refund.refresh_from_db()
        assert (refund.status, refund.attempts) == (Refund.Status.FAILED, 1)

        stripe_refunds.side_effect = None
        assert retry_unfinished_refunds() == 1
        refund.refresh_from_db()
        assert refund.status == Refund.Status.SUCCEEDED


class TestRefundOnRequest:
    def _postponed(self, hours_until_start=48):
        start = timezone.now() + timedelta(hours=hours_until_start)
        return EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
            postponed_from=start - timedelta(days=7),
        )

    def test_refunds_in_full_and_puts_the_seats_back_on_sale(
        self, stripe_refunds, django_capture_on_commit_callbacks, mailoutbox
    ):
        event = self._postponed()
        booking = paid_booking(event, (TicketTierFactory(event=event), "25.00"))
        seat = EventSeat.objects.get(tickets__booking=booking)

        with django_capture_on_commit_callbacks(execute=True):
            cancel_booking(booking)

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert "postponed" in mailoutbox[0].body and "$25.00" in mailoutbox[0].body
        TicketFactory(booking=BookingFactory(), event_seat=seat)

    def test_refused_when_not_postponed_or_too_close_to_the_new_start(
        self, stripe_refunds
    ):
        plain = EventFactory(status=Event.Status.APPROVED)
        booking = paid_booking(plain, (TicketTierFactory(event=plain), "25.00"))
        with pytest.raises(BookingNotCancellableError, match="postponed"):
            cancel_booking(booking)

        soon = self._postponed(hours_until_start=23)
        booking = paid_booking(soon, (TicketTierFactory(event=soon), "25.00"))
        with pytest.raises(BookingNotCancellableError, match="24 hours"):
            cancel_booking(booking)
        assert stripe_refunds.call_count == 0

    def test_free_tickets_can_be_returned_until_the_event_starts(
        self, stripe_refunds, django_capture_on_commit_callbacks
    ):
        start = timezone.now() + timedelta(hours=2)
        event = EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
        )
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.00"))
        seat = EventSeat.objects.get(tickets__booking=booking)

        with django_capture_on_commit_callbacks(execute=True):
            cancel_booking(booking)

        booking.refresh_from_db()
        seat.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert seat.status == EventSeat.Status.AVAILABLE
        assert not Refund.objects.filter(booking=booking).exists()
        assert stripe_refunds.call_count == 0

    def test_free_tickets_cannot_be_returned_once_the_event_started(
        self, stripe_refunds
    ):
        start = timezone.now() - timedelta(minutes=5)
        event = EventFactory(
            status=Event.Status.APPROVED,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
        )
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.00"))
        with pytest.raises(BookingNotCancellableError, match="until the event starts"):
            cancel_booking(booking)

    def test_paid_tickets_still_need_a_postponement(self, stripe_refunds):
        event = EventFactory(status=Event.Status.APPROVED)
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.50"))
        with pytest.raises(BookingNotCancellableError, match="postponed"):
            cancel_booking(booking)

    def test_refused_once_a_ticket_was_used_at_the_door(self, stripe_refunds):
        event = self._postponed()
        booking = paid_booking(event, (TicketTierFactory(event=event), "25.00"))
        booking.tickets.update(status=Ticket.Status.USED)

        with pytest.raises(BookingNotCancellableError, match="used at the door"):
            cancel_booking(booking)

        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert stripe_refunds.call_count == 0


def test_a_seat_can_have_only_one_live_ticket():
    seat = EventSeatFactory(status=EventSeat.Status.BOOKED)
    TicketFactory(booking=BookingFactory(), event_seat=seat)
    with pytest.raises(IntegrityError):
        TicketFactory(booking=BookingFactory(), event_seat=seat)


def test_a_late_duplicate_refund_request_leaves_a_resold_seat_alone(stripe_refunds):
    start = timezone.now() + timedelta(days=3)
    event = EventFactory(
        status=Event.Status.APPROVED,
        start_datetime=start,
        end_datetime=start + timedelta(hours=2),
        postponed_from=start - timedelta(days=7),
    )
    booking = paid_booking(event, (TicketTierFactory(event=event), "25.00"))
    stale = Booking.objects.get(pk=booking.pk)
    cancel_booking(booking)
    seat = EventSeat.objects.get(
        tickets__booking=booking, tickets__status=Ticket.Status.CANCELLED
    )
    TicketFactory(booking=BookingFactory(), event_seat=seat)
    EventSeat.objects.filter(pk=seat.pk).update(status=EventSeat.Status.BOOKED)

    cancel_booking(stale)

    seat.refresh_from_db()
    assert seat.status == EventSeat.Status.BOOKED
    assert Refund.objects.count() == 1
