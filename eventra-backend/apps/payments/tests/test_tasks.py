from datetime import timedelta
from unittest.mock import MagicMock

import pytest
import stripe
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket

from ..constants import REFUND_MAX_ATTEMPTS
from ..factories import PaymentFactory
from ..models import Payment, Refund
from ..tasks import (
    refund_event_bookings_task,
    retry_event_refunds_task,
    sweep_unrefunded_cancelled_events,
)

pytestmark = pytest.mark.django_db


def _booking_for_event(event, status=Booking.Status.CONFIRMED):
    booking = BookingFactory(status=status)
    seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
    ticket_status = (
        Ticket.Status.VALID
        if status == Booking.Status.CONFIRMED
        else Ticket.Status.CANCELLED
    )
    TicketFactory(booking=booking, event_seat=seat, price="25.00", status=ticket_status)
    payment = PaymentFactory(
        booking=booking,
        stripe_payment_intent_id=f"pi_{booking.id}",
        status=Payment.Status.SUCCEEDED,
    )
    return booking, payment


@pytest.fixture
def stripe_refund(monkeypatch):
    create = MagicMock(return_value=MagicMock(id="re_test"))
    monkeypatch.setattr("apps.payments.services.stripe.Refund.create", create)
    monkeypatch.setattr("apps.notifications.tasks.send_refund_email.delay", MagicMock())
    return create


@pytest.fixture
def sweep(django_capture_on_commit_callbacks):
    def run():
        with django_capture_on_commit_callbacks(execute=True):
            sweep_unrefunded_cancelled_events()

    return run


class TestRefundEventBookingsTask:
    def test_refunds_every_paid_booking_through_the_ledger(
        self, stripe_refund, django_capture_on_commit_callbacks
    ):
        event = EventFactory(status="cancelled")
        booking, _ = _booking_for_event(event)

        with django_capture_on_commit_callbacks(execute=True):
            refund_event_bookings_task(str(event.id))

        booking.refresh_from_db()
        refund = Refund.objects.get(booking=booking)
        assert booking.status == Booking.Status.REFUNDED
        assert refund.reason == Refund.Reason.CANCELLED_EVENT
        assert refund.status == Refund.Status.SUCCEEDED
        assert stripe_refund.call_args.kwargs["amount"] == 2500


class TestSweepUnrefundedCancelledEvents:
    def test_recovers_confirmed_bookings_a_crashed_batch_never_reached(
        self, stripe_refund, sweep
    ):
        event = EventFactory(status="cancelled")
        booking, _ = _booking_for_event(event)

        sweep()

        booking.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert Refund.objects.get().status == Refund.Status.SUCCEEDED

    def test_ignores_confirmed_bookings_on_events_that_are_not_cancelled(
        self, stripe_refund, sweep
    ):
        event = EventFactory(status="approved")
        booking, _ = _booking_for_event(event)

        sweep()

        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        stripe_refund.assert_not_called()

    def test_second_sweep_is_a_no_op_once_everything_is_refunded(
        self, stripe_refund, sweep
    ):
        _booking_for_event(EventFactory(status="cancelled"))

        sweep()
        sweep()

        assert stripe_refund.call_count == 1

    def _orphan(self, booking_status, age_minutes):
        booking, payment = _booking_for_event(
            EventFactory(status="approved"), booking_status
        )
        Payment.objects.filter(id=payment.id).update(
            updated_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        return booking, payment

    @pytest.mark.parametrize(
        "status", [Booking.Status.PENDING, Booking.Status.CANCELLED]
    )
    def test_refunds_captured_payment_with_no_real_booking(
        self, stripe_refund, sweep, status
    ):
        booking, _ = self._orphan(status, age_minutes=30)

        sweep()

        booking.refresh_from_db()
        refund = Refund.objects.get(booking=booking)
        assert booking.status == Booking.Status.REFUNDED
        assert refund.reason == Refund.Reason.UNAVAILABLE
        assert refund.status == Refund.Status.SUCCEEDED

    def test_recent_orphan_is_left_for_the_in_flight_webhook(
        self, stripe_refund, sweep
    ):
        booking, _ = self._orphan(Booking.Status.PENDING, age_minutes=1)

        sweep()

        assert not Refund.objects.exists()
        stripe_refund.assert_not_called()

    def test_confirmed_booking_payment_is_never_treated_as_orphan(
        self, stripe_refund, sweep
    ):
        _, payment = _booking_for_event(EventFactory(status="approved"))
        Payment.objects.filter(id=payment.id).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )

        sweep()

        assert not Refund.objects.exists()

    def test_a_failed_refund_is_retried_until_it_gives_up(self, stripe_refund, sweep):
        self._orphan(Booking.Status.CANCELLED, age_minutes=30)
        stripe_refund.side_effect = stripe.error.APIConnectionError("stripe down")
        stale = timezone.now() - timedelta(hours=1)

        for _ in range(REFUND_MAX_ATTEMPTS + 3):
            sweep()
            Refund.objects.update(updated_at=stale)

        refund = Refund.objects.get()
        assert refund.status == Refund.Status.FAILED
        assert refund.attempts == REFUND_MAX_ATTEMPTS
        assert stripe_refund.call_count == REFUND_MAX_ATTEMPTS


class TestRetryEventRefundsTask:
    def test_gives_failed_refunds_a_fresh_set_of_attempts(
        self, stripe_refund, sweep, django_capture_on_commit_callbacks
    ):
        event = EventFactory(status="cancelled")
        booking, _ = _booking_for_event(event)
        stripe_refund.side_effect = stripe.error.APIConnectionError("stripe down")
        sweep()
        Refund.objects.update(attempts=REFUND_MAX_ATTEMPTS)

        stripe_refund.side_effect = None
        with django_capture_on_commit_callbacks(execute=True):
            retry_event_refunds_task(str(event.id))

        refund = Refund.objects.get(booking=booking)
        assert refund.status == Refund.Status.SUCCEEDED
        assert refund.attempts == 0

    def test_never_refunds_the_buyers_of_a_live_event(self, stripe_refund):
        event = EventFactory(status="approved")
        booking, _ = _booking_for_event(event)

        retry_event_refunds_task(str(event.id))

        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        assert not Refund.objects.exists()
