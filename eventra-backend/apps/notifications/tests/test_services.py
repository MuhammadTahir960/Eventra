from unittest.mock import MagicMock

import pytest
from django.core import mail

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket

from ..models import Notification
from ..services import send_booking_confirmation_email, send_refund_confirmation_email

pytestmark = pytest.mark.django_db


def _booking_with_tickets(n_tickets=2):
    booking = BookingFactory()
    event = EventFactory(status="approved")
    for _ in range(n_tickets):
        seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
        Ticket.objects.create(
            booking=booking, event_seat=seat, status=Ticket.Status.VALID
        )
    return booking


class TestSendBookingConfirmationEmail:
    def test_happy_path_sends_email_with_one_pdf_attachment_per_ticket(self):
        booking = _booking_with_tickets(n_tickets=3)

        send_booking_confirmation_email(booking)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [booking.user.email]
        assert "confirmed" in sent.subject.lower()
        assert len(sent.attachments) == 3
        for filename, _content, content_type in sent.attachments:
            assert filename.startswith("ticket-")
            assert filename.endswith(".pdf")
            assert content_type == "application/pdf"

    def test_happy_path_records_a_sent_notification(self):
        booking = _booking_with_tickets(n_tickets=1)

        send_booking_confirmation_email(booking)

        notification = Notification.objects.get(user=booking.user)
        assert notification.type == Notification.NotificationType.BOOKING_CONFIRMATION
        assert notification.status == Notification.Status.SENT
        assert notification.sent_at is not None

    def test_zero_tickets_still_sends_an_email_with_no_attachments(self):
        booking = BookingFactory()

        send_booking_confirmation_email(booking)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].attachments == []

    def test_send_failure_records_a_failed_notification_and_reraises(self, monkeypatch):
        booking = _booking_with_tickets(n_tickets=1)
        monkeypatch.setattr(
            "apps.notifications.services.EmailMessage.send",
            MagicMock(side_effect=RuntimeError("SMTP is down")),
        )

        with pytest.raises(RuntimeError):
            send_booking_confirmation_email(booking)

        notification = Notification.objects.get(user=booking.user)
        assert notification.status == Notification.Status.FAILED
        assert notification.sent_at is None
        assert len(mail.outbox) == 0


class TestSendRefundConfirmationEmail:
    def test_happy_path_sends_email_and_mentions_the_refund_amount(self):
        booking = BookingFactory()

        send_refund_confirmation_email(booking)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [booking.user.email]
        assert "refunded" in sent.subject.lower()
        assert str(booking.total_amount) in sent.body

    def test_happy_path_records_a_sent_notification(self):
        booking = BookingFactory()

        send_refund_confirmation_email(booking)

        notification = Notification.objects.get(user=booking.user)
        assert notification.type == Notification.NotificationType.EVENT_CANCELLED_REFUND
        assert notification.status == Notification.Status.SENT
        assert notification.sent_at is not None

    def test_send_failure_records_a_failed_notification_and_reraises(self, monkeypatch):
        booking = BookingFactory()
        monkeypatch.setattr(
            "apps.notifications.services.EmailMessage.send",
            MagicMock(side_effect=RuntimeError("SMTP is down")),
        )

        with pytest.raises(RuntimeError):
            send_refund_confirmation_email(booking)

        notification = Notification.objects.get(user=booking.user)
        assert notification.status == Notification.Status.FAILED
        assert notification.sent_at is None
        assert len(mail.outbox) == 0
