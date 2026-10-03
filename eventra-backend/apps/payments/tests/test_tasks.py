from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket

from ..factories import PaymentFactory
from ..models import Payment
from ..tasks import refund_event_bookings_task, sweep_unrefunded_cancelled_events

pytestmark = pytest.mark.django_db


def _confirmed_booking_for_event(event):
    booking = BookingFactory(status=Booking.Status.CONFIRMED)
    seat = EventSeatFactory(
        event=event, status=EventSeat.Status.BOOKED, price_override=Decimal("25.00")
    )
    Ticket.objects.create(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    payment = PaymentFactory(
        booking=booking,
        stripe_payment_intent_id=f"pi_{booking.id}",
        status=Payment.Status.SUCCEEDED,
    )
    return booking, payment


class TestRefundEventBookingsTask:
    def test_task_delegates_to_the_refund_service_for_every_confirmed_booking(
        self, monkeypatch
    ):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )
        event = EventFactory(status="cancelled")
        booking, payment = _confirmed_booking_for_event(event)

        refund_event_bookings_task(str(event.id))

        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.REFUNDED

    def test_retry_failed_flag_is_actually_wired_through(self, monkeypatch):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )
        event = EventFactory(status="cancelled")
        stuck_booking, stuck_payment = _confirmed_booking_for_event(event)
        Booking.objects.filter(id=stuck_booking.id).update(
            status=Booking.Status.REFUND_FAILED
        )
        untouched_booking, untouched_payment = _confirmed_booking_for_event(event)

        refund_event_bookings_task(str(event.id), True)

        stuck_booking.refresh_from_db()
        stuck_payment.refresh_from_db()
        untouched_booking.refresh_from_db()
        untouched_payment.refresh_from_db()
        assert stuck_booking.status == Booking.Status.REFUNDED
        assert stuck_payment.status == Payment.Status.REFUNDED
        assert untouched_booking.status == Booking.Status.REFUNDED
        assert untouched_payment.status == Payment.Status.REFUNDED

    def test_normal_run_leaves_refund_failed_bookings_alone(self, monkeypatch):
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", MagicMock())
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )
        event = EventFactory(status="cancelled")
        stuck_booking, _ = _confirmed_booking_for_event(event)
        Booking.objects.filter(id=stuck_booking.id).update(
            status=Booking.Status.REFUND_FAILED
        )

        refund_event_bookings_task(str(event.id))

        stuck_booking.refresh_from_db()
        assert stuck_booking.status == Booking.Status.REFUND_FAILED


class TestSweepUnrefundedCancelledEvents:
    @pytest.fixture(autouse=True)
    def _mocks(self, monkeypatch):
        self.refund = MagicMock()
        monkeypatch.setattr("apps.payments.services.stripe.Refund.create", self.refund)
        monkeypatch.setattr(
            "apps.notifications.tasks.send_refund_email.delay", MagicMock()
        )

    def test_recovers_confirmed_bookings_a_crashed_batch_never_reached(self):
        event = EventFactory(status="cancelled")
        booking, payment = _confirmed_booking_for_event(event)

        sweep_unrefunded_cancelled_events()

        booking.refresh_from_db()
        payment.refresh_from_db()
        assert booking.status == Booking.Status.REFUNDED
        assert payment.status == Payment.Status.REFUNDED

    def test_leaves_refund_failed_bookings_for_the_admin_retry(self):
        event = EventFactory(status="cancelled")
        booking, _ = _confirmed_booking_for_event(event)
        Booking.objects.filter(id=booking.id).update(
            status=Booking.Status.REFUND_FAILED
        )

        sweep_unrefunded_cancelled_events()

        booking.refresh_from_db()
        assert booking.status == Booking.Status.REFUND_FAILED
        self.refund.assert_not_called()

    def test_ignores_confirmed_bookings_on_events_that_are_not_cancelled(self):
        event = EventFactory(status="approved")
        booking, _ = _confirmed_booking_for_event(event)

        sweep_unrefunded_cancelled_events()

        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED
        self.refund.assert_not_called()

    def test_second_sweep_is_a_no_op_once_everything_is_refunded(self):
        event = EventFactory(status="cancelled")
        _confirmed_booking_for_event(event)

        sweep_unrefunded_cancelled_events()
        sweep_unrefunded_cancelled_events()

        assert self.refund.call_count == 1

    def _orphan(self, booking_status, age_minutes):
        booking = BookingFactory(status=booking_status)
        payment = PaymentFactory(
            booking=booking,
            stripe_payment_intent_id=f"pi_{booking.id}",
            status=Payment.Status.SUCCEEDED,
        )
        Payment.objects.filter(id=payment.id).update(
            updated_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        return booking, payment

    @pytest.mark.parametrize(
        "status", [Booking.Status.PENDING, Booking.Status.CANCELLED]
    )
    def test_refunds_captured_payment_with_no_real_booking(self, status):
        booking, payment = self._orphan(status, age_minutes=30)

        sweep_unrefunded_cancelled_events()

        booking.refresh_from_db()
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED
        assert booking.status == Booking.Status.REFUNDED

    def test_recent_orphan_is_left_for_the_in_flight_webhook(self):
        _, payment = self._orphan(Booking.Status.PENDING, age_minutes=1)

        sweep_unrefunded_cancelled_events()

        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED
        self.refund.assert_not_called()

    def test_failed_orphan_refund_is_retried_on_the_next_sweep(self):
        _, payment = self._orphan(Booking.Status.CANCELLED, age_minutes=30)
        self.refund.side_effect = [RuntimeError("stripe down"), MagicMock()]

        sweep_unrefunded_cancelled_events()
        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED

        sweep_unrefunded_cancelled_events()
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED

    def test_confirmed_booking_payment_is_never_treated_as_orphan(self):
        event = EventFactory(status="approved")
        _, payment = _confirmed_booking_for_event(event)
        Payment.objects.filter(id=payment.id).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )

        sweep_unrefunded_cancelled_events()

        payment.refresh_from_db()
        assert payment.status == Payment.Status.SUCCEEDED

    def test_gives_up_after_max_attempts_and_stops_calling_stripe(self):
        from ..services import ORPHANED_PAYMENT_MAX_ATTEMPTS

        _, payment = self._orphan(Booking.Status.CANCELLED, age_minutes=30)
        self.refund.side_effect = RuntimeError("stripe down")

        for _ in range(ORPHANED_PAYMENT_MAX_ATTEMPTS + 3):
            sweep_unrefunded_cancelled_events()

        payment.refresh_from_db()
        assert self.refund.call_count == ORPHANED_PAYMENT_MAX_ATTEMPTS
        assert payment.refund_attempts == ORPHANED_PAYMENT_MAX_ATTEMPTS
        assert payment.status == Payment.Status.SUCCEEDED

    def test_admin_retrigger_resets_the_counter_and_sweeper_retries(self):
        from django.contrib import admin as dj_admin

        from ..admin import PaymentAdmin
        from ..services import ORPHANED_PAYMENT_MAX_ATTEMPTS

        booking, payment = self._orphan(Booking.Status.CANCELLED, age_minutes=30)
        Payment.objects.filter(id=payment.id).update(
            refund_attempts=ORPHANED_PAYMENT_MAX_ATTEMPTS
        )
        sweep_unrefunded_cancelled_events()
        self.refund.assert_not_called()

        model_admin = PaymentAdmin(Payment, dj_admin.site)
        model_admin.message_user = MagicMock()
        model_admin.retrigger_refund(MagicMock(), Payment.objects.filter(id=payment.id))

        sweep_unrefunded_cancelled_events()
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED
