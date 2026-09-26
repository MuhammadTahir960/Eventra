from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.seating.factories import EventSeatFactory
from apps.tickets.models import Ticket
from apps.venues.factories import SeatFactory

from ..models import Notification
from ..tasks import send_confirmation_email, send_event_reminders, send_refund_email

pytestmark = pytest.mark.django_db


class TestSendConfirmationEmailTask:
    def test_fetches_booking_and_delegates_to_the_confirmation_service(self):
        booking = BookingFactory()

        send_confirmation_email(str(booking.id))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [booking.user.email]
        assert Notification.objects.filter(
            user=booking.user,
            type=Notification.NotificationType.BOOKING_CONFIRMATION,
        ).exists()


class TestSendRefundEmailTask:
    def test_fetches_booking_and_delegates_to_the_refund_service(self):
        booking = BookingFactory()

        send_refund_email(str(booking.id))

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [booking.user.email]
        assert Notification.objects.filter(
            user=booking.user,
            type=Notification.NotificationType.EVENT_CANCELLED_REFUND,
        ).exists()


class TestSendEventRemindersTask:
    def test_celery_task_wrapper_runs_the_batch(self):
        event = EventFactory(status=Event.Status.APPROVED)
        start = timezone.now() + timedelta(hours=10)
        Event.objects.filter(id=event.id).update(
            start_datetime=start, end_datetime=start + timedelta(hours=2)
        )
        event.refresh_from_db()
        seat = EventSeatFactory(
            event=event,
            ticket_tier=TicketTierFactory(event=event),
            seat=SeatFactory(venue=event.venue),
        )
        Ticket.objects.create(
            booking=BookingFactory(status="confirmed"),
            event_seat=seat,
            status=Ticket.Status.VALID,
        )

        send_event_reminders()

        assert len(mail.outbox) == 1
