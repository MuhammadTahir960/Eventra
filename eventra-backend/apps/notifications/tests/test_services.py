from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.core import mail
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.payouts.factories import OrganizerPayoutFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.models import Ticket
from apps.venues.factories import SeatFactory

from ..models import Notification
from ..services import (
    send_booking_confirmation_email,
    send_event_reminders_batch,
    send_payout_ready_email,
    send_payout_settled_email,
    send_refund_confirmation_email,
)

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


class TestSendPayoutReadyEmail:
    def test_happy_path_sends_email_to_the_organizer(self):
        event = EventFactory()
        payout = OrganizerPayoutFactory(event=event)

        send_payout_ready_email(payout)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [event.organizer.email]
        assert "payout" in sent.subject.lower()
        assert payout.payout_reference in sent.body

    def test_happy_path_records_a_sent_notification(self):
        event = EventFactory()
        payout = OrganizerPayoutFactory(event=event)

        send_payout_ready_email(payout)

        notification = Notification.objects.get(user=event.organizer)
        assert notification.type == Notification.NotificationType.PAYOUT_READY
        assert notification.status == Notification.Status.SENT
        assert notification.sent_at is not None


class TestSendPayoutSettledEmail:
    def test_happy_path_sends_email_to_the_organizer(self):
        event = EventFactory()
        payout = OrganizerPayoutFactory(event=event, status="settled")

        send_payout_settled_email(payout)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [event.organizer.email]
        assert "settled" in sent.subject.lower()

    def test_happy_path_records_a_sent_notification(self):
        event = EventFactory()
        payout = OrganizerPayoutFactory(event=event, status="settled")

        send_payout_settled_email(payout)

        notification = Notification.objects.get(user=event.organizer)
        assert notification.type == Notification.NotificationType.PAYOUT_SETTLED
        assert notification.status == Notification.Status.SENT


# ==================================================
# send_event_reminders_batch()
# ==================================================


def _ticket_for(event, booking=None, status=Ticket.Status.VALID):
    booking = booking or BookingFactory(status="confirmed")
    seat = EventSeatFactory(
        event=event,
        ticket_tier=TicketTierFactory(event=event),
        seat=SeatFactory(venue=event.venue),
    )
    return Ticket.objects.create(booking=booking, event_seat=seat, status=status)


def _event_starting_in(hours, **kwargs):
    event = EventFactory(status=Event.Status.APPROVED, **kwargs)
    start = timezone.now() + timedelta(hours=hours)
    Event.objects.filter(id=event.id).update(
        start_datetime=start, end_datetime=start + timedelta(hours=2)
    )
    event.refresh_from_db()
    return event


def test_attendee_of_an_event_starting_soon_gets_one_reminder():
    event = _event_starting_in(10)
    ticket = _ticket_for(event)

    assert send_event_reminders_batch() == 1

    assert len(mail.outbox) == 1
    assert ticket.booking.user.email in mail.outbox[0].to
    assert event.title in mail.outbox[0].subject


def test_reminder_is_not_repeated_on_the_next_hourly_run():
    _ticket_for(_event_starting_in(10))

    send_event_reminders_batch()
    send_event_reminders_batch()

    assert len(mail.outbox) == 1
    assert (
        Notification.objects.filter(
            type=Notification.NotificationType.EVENT_REMINDER, status="sent"
        ).count()
        == 1
    )


def test_two_tickets_in_one_booking_still_mean_one_email():
    event = _event_starting_in(10)
    booking = BookingFactory(status="confirmed")
    _ticket_for(event, booking)
    _ticket_for(event, booking)

    assert send_event_reminders_batch() == 1


def test_far_future_past_cancelled_and_used_ticket_events_are_skipped():
    _ticket_for(_event_starting_in(72))
    _ticket_for(_event_starting_in(-3))
    cancelled = _event_starting_in(10)
    Event.objects.filter(id=cancelled.id).update(status=Event.Status.CANCELLED)
    _ticket_for(cancelled)
    _ticket_for(_event_starting_in(10), status=Ticket.Status.CANCELLED)

    assert send_event_reminders_batch() == 0
    assert len(mail.outbox) == 0


def test_a_failed_send_is_retried_on_the_next_run(monkeypatch):
    _ticket_for(_event_starting_in(10))
    monkeypatch.setattr(
        "apps.notifications.services.send_mail",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down")),
    )
    assert send_event_reminders_batch() == 0

    monkeypatch.undo()
    assert send_event_reminders_batch() == 1


def _pending_claim(event, minutes_old):
    ticket = _ticket_for(event)
    claim = Notification.objects.create(
        user=ticket.booking.user,
        event=event,
        type=Notification.NotificationType.EVENT_REMINDER,
        status=Notification.Status.PENDING,
        message=f"Event reminder: {event.id}",
    )
    Notification.objects.filter(pk=claim.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes_old)
    )
    return claim


def test_fresh_pending_claim_blocks_a_concurrent_runner():
    _pending_claim(_event_starting_in(10), minutes_old=1)

    assert send_event_reminders_batch() == 0
    assert len(mail.outbox) == 0


def test_stale_pending_claim_from_a_crashed_runner_is_retried():
    claim = _pending_claim(_event_starting_in(10), minutes_old=60)

    assert send_event_reminders_batch() == 1
    assert len(mail.outbox) == 1
    claim.refresh_from_db()
    assert claim.status == Notification.Status.SENT
    assert Notification.objects.filter(type="event_reminder").count() == 1


def test_database_rejects_a_second_active_reminder_for_the_same_pair():
    from django.db import IntegrityError, transaction

    event = _event_starting_in(10)
    claim = _pending_claim(event, minutes_old=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        Notification.objects.create(
            user=claim.user,
            event=event,
            type=Notification.NotificationType.EVENT_REMINDER,
            status=Notification.Status.SENT,
        )


def test_reminder_gives_up_after_max_failed_attempts(monkeypatch):
    from apps.notifications.services import REMINDER_MAX_ATTEMPTS

    _ticket_for(_event_starting_in(10))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("bad address")

    monkeypatch.setattr("apps.notifications.services.send_mail", boom)

    for _ in range(REMINDER_MAX_ATTEMPTS + 3):
        assert send_event_reminders_batch() == 0

    assert len(calls) == REMINDER_MAX_ATTEMPTS
    assert (
        Notification.objects.filter(
            type=Notification.NotificationType.EVENT_REMINDER, status="failed"
        ).count()
        == REMINDER_MAX_ATTEMPTS
    )
