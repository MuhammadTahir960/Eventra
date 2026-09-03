from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket

from ..factories import PaymentFactory
from ..models import Payment
from ..tasks import refund_event_bookings_task

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

    def test_only_failed_flag_is_actually_wired_through(self, monkeypatch):
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
        assert untouched_booking.status == Booking.Status.CONFIRMED
        assert untouched_payment.status == Payment.Status.SUCCEEDED
