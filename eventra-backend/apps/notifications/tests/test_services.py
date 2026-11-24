from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.core import mail
from django.utils import timezone

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory, TicketTierFactory
from apps.events.models import Event
from apps.payments.models import Refund
from apps.payouts.factories import OrganizerPayoutFactory
from apps.seating.factories import EventSeatFactory
from apps.seating.models import EventSeat
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory, VenueFactory
from tests.helpers import paid_booking

from ..models import Notification
from ..services import (
    send_booking_confirmation_email,
    send_event_cancelled_notice,
    send_event_postponed_notice,
    send_event_reminders_batch,
    send_event_running_late_notice,
    send_event_updated_notice,
    send_payout_settled_email,
    send_refund_notice,
)

pytestmark = pytest.mark.django_db


def _booking_with_tickets(n_tickets=2):
    booking = BookingFactory()
    event = EventFactory(status="approved")
    for _ in range(n_tickets):
        seat = EventSeatFactory(event=event, status=EventSeat.Status.BOOKED)
        TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.VALID)
    return booking


class TestEventBuyerNotices:
    def test_updated_notice_has_a_constant_subject_and_the_new_details(self):
        event = EventFactory(status="approved", title="Jazz Night")
        buyer = UserFactory()

        send_event_updated_notice(event, buyer)

        [sent] = mail.outbox
        assert sent.to == [buyer.email]
        assert sent.subject == "Jazz Night has been updated"
        assert "Jazz Night" in sent.body and event.venue.name in sent.body
        notification = Notification.objects.get(event=event)
        assert notification.type == Notification.NotificationType.EVENT_UPDATED
        assert notification.status == Notification.Status.SENT

    def test_notices_give_the_start_in_the_venues_local_time(self):
        start = (timezone.now() + timedelta(days=5)).replace(
            hour=13, minute=0, second=0, microsecond=0
        )
        event = EventFactory(
            status="approved",
            venue=VenueFactory(country="PK", time_zone="Asia/Karachi"),
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
        )

        send_event_updated_notice(event, UserFactory())

        assert f"{start:%a} {start.day} {start:%b %Y}, 18:00 Karachi time" in (
            mail.outbox[0].body
        )

    def test_cancelled_notice_promises_a_refund_for_paid_tickets(self):
        event = EventFactory(status="cancelled", title="Jazz Night")
        booking = paid_booking(event, (TicketTierFactory(event=event), "20.00"))

        send_event_cancelled_notice(event, booking.user)

        [sent] = mail.outbox
        assert sent.subject == "Jazz Night has been cancelled"
        assert "full refund" in sent.body and "In full, automatically" in sent.body
        assert Notification.objects.get(event=event).type == (
            Notification.NotificationType.EVENT_CANCELLED
        )

    def test_failure_records_a_failed_notification_and_reraises_for_retry(
        self, monkeypatch
    ):
        event = EventFactory(status="cancelled")
        monkeypatch.setattr(
            "apps.notifications.emails.EmailMultiAlternatives.send",
            MagicMock(side_effect=RuntimeError("SMTP is down")),
        )

        with pytest.raises(RuntimeError):
            send_event_cancelled_notice(event, UserFactory())

        assert Notification.objects.get(event=event).status == (
            Notification.Status.FAILED
        )

    def test_cancelled_notice_for_free_tickets_promises_no_refund(self):
        event = EventFactory(status="cancelled")
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.00"))

        send_event_cancelled_notice(event, booking.user)

        body = mail.outbox[0].body
        assert "Your free tickets are cancelled." in body and "refund" not in body

    def test_postponed_notice_gives_the_refund_deadline_for_paid_tickets(self):
        event = EventFactory(status="approved")
        event.postponed_from = event.start_datetime - timedelta(days=7)
        booking = paid_booking(event, (TicketTierFactory(event=event), "20.00"))

        send_event_postponed_notice(event, booking.user)

        [sent] = mail.outbox
        assert sent.subject == f"{event.title} has a new date"
        assert "Request a full refund from your bookings until" in sent.body
        assert "Was: " in sent.body and "Now: " in sent.body

    def test_postponed_notice_for_free_tickets_offers_handing_them_back(self):
        event = EventFactory(status="approved")
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.00"))

        send_event_postponed_notice(event, booking.user)

        assert "Hand your ticket back" in mail.outbox[0].body
        assert "refund" not in mail.outbox[0].body

    def test_new_end_time_notice_gives_the_end(self):
        event = EventFactory(status="approved")

        send_event_running_late_notice(event, UserFactory())

        [sent] = mail.outbox
        assert sent.subject == f"{event.title} now ends later"
        assert "Now ends: " in sent.body and "running late" not in sent.body


class TestEmailLayout:
    def test_html_copy_escapes_organizer_text(self):
        event = EventFactory(status="approved", title="<script>x</script> & Co")

        send_event_updated_notice(event, UserFactory())

        [(html, mimetype)] = mail.outbox[0].alternatives
        assert mimetype == "text/html"
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;x&lt;/script&gt; &amp; Co" in html

    def test_logo_is_an_inline_image_the_html_points_at(self):
        send_event_updated_notice(EventFactory(status="approved"), UserFactory())

        sent = mail.outbox[0]
        [logo] = [a for a in sent.attachments if not isinstance(a, tuple)]
        assert logo.get_content_type() == "image/png"
        assert logo.get_content_disposition() == "inline"
        cid = logo["Content-ID"].strip("<>")
        assert f'src="cid:{cid}"' in sent.alternatives[0][0]
        assert 'alt="Eventra"' in sent.alternatives[0][0]

    def test_replies_go_to_the_help_address_named_in_the_footer(self, settings):
        settings.EMAIL_REPLY_TO = "help@example.test"

        send_event_updated_notice(EventFactory(status="approved"), UserFactory())

        sent = mail.outbox[0]
        assert sent.reply_to == ["help@example.test"]
        assert "Questions? Write to help@example.test." in sent.body
        assert 'href="mailto:help@example.test"' in sent.alternatives[0][0]

    def test_without_a_help_address_there_is_no_reply_to_or_questions_line(
        self, settings
    ):
        settings.EMAIL_REPLY_TO = ""

        send_event_updated_notice(EventFactory(status="approved"), UserFactory())

        sent = mail.outbox[0]
        assert sent.reply_to == []
        assert "Questions?" not in sent.body

    def test_button_links_and_footer_are_in_both_copies(self, settings):
        settings.FRONTEND_URL = "http://app.example.test"
        event = EventFactory(status="approved")

        send_event_updated_notice(event, UserFactory())

        sent = mail.outbox[0]
        url = f"http://app.example.test/events/{event.id}"
        assert f"See the event: {url}" in sent.body
        assert f'href="{url}"' in sent.alternatives[0][0]
        for copy in (sent.body, sent.alternatives[0][0]):
            assert "See it listed. Know someone checked." in copy
            assert "checked by a person before it goes on sale" in copy
            assert "because you booked on Eventra" in copy


class TestSendBookingConfirmationEmail:
    def test_happy_path_sends_email_with_one_pdf_attachment_per_ticket(self):
        booking = _booking_with_tickets(n_tickets=3)

        send_booking_confirmation_email(booking)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [booking.user.email]
        assert sent.subject == f"Your tickets for {booking.event.title}"
        assert "3 tickets" in sent.alternatives[0][0]
        assert "The PDFs are attached" in sent.body
        pdfs = [a for a in sent.attachments if isinstance(a, tuple)]
        assert len(pdfs) == 3
        for filename, _content, content_type in pdfs:
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

    def test_booking_without_tickets_sends_nothing(self):
        send_booking_confirmation_email(BookingFactory())

        assert mail.outbox == []
        assert not Notification.objects.exists()

    def test_seats_are_grouped_by_section_and_row(self):
        event = EventFactory(status="approved")
        booking = BookingFactory()
        for section, row, number in (("B", "4", 12), ("B", "4", 11), ("C", "1", 3)):
            seat = EventSeatFactory(
                event=event,
                seat=SeatFactory(
                    venue=event.venue,
                    section=section,
                    row_label=row,
                    seat_number=number,
                ),
            )
            TicketFactory(booking=booking, event_seat=seat, status=Ticket.Status.VALID)

        send_booking_confirmation_email(booking)

        assert (
            "Seats: Section B, row 4, seats 11 and 12; Section C, row 1, seat 3"
            in mail.outbox[0].body
        )

    def test_free_booking_says_free_and_how_to_hand_tickets_back(self):
        event = EventFactory(status="approved")
        booking = paid_booking(event, (TicketTierFactory(event=event), "0.00"))

        send_booking_confirmation_email(booking)

        body = mail.outbox[0].body
        assert "Paid: Free" in body and "Hand your ticket back" in body
        assert "refunded only if" not in body

    def test_send_failure_records_a_failed_notification_and_reraises(self, monkeypatch):
        booking = _booking_with_tickets(n_tickets=1)
        monkeypatch.setattr(
            "apps.notifications.emails.EmailMultiAlternatives.send",
            MagicMock(side_effect=RuntimeError("SMTP is down")),
        )

        with pytest.raises(RuntimeError):
            send_booking_confirmation_email(booking)

        notification = Notification.objects.get(user=booking.user)
        assert notification.status == Notification.Status.FAILED
        assert notification.sent_at is None
        assert len(mail.outbox) == 0


def _refund(reason, amount="30.00"):
    event = EventFactory(status="approved", title="Jazz Night")
    booking = paid_booking(event, (TicketTierFactory(event=event), "80.00"))
    refund = Refund.objects.create(
        booking=booking, reason=reason, key=f"{reason}-email"
    )
    refund.items.create(ticket=booking.tickets.get(), amount=amount)
    return refund


class TestSendRefundNotice:
    def test_full_refund_says_the_tickets_are_cancelled(self):
        refund = _refund(Refund.Reason.CANCELLED_EVENT, "80.00")

        send_refund_notice(refund)

        [sent] = mail.outbox
        assert sent.to == [refund.booking.user.email]
        assert sent.subject == "Your refund of USD 80.00 has been sent"
        assert "Jazz Night" in sent.body
        assert "Full refund" in sent.alternatives[0][0]
        assert "Your tickets are cancelled." in sent.body
        assert "within 5 to 10 working days" in sent.body
        notification = Notification.objects.get(user=refund.booking.user)
        assert notification.type == Notification.NotificationType.EVENT_CANCELLED_REFUND
        assert notification.status == Notification.Status.SENT
        assert notification.event == refund.booking.event

    def test_partial_refund_says_the_tickets_still_count(self):
        refund = _refund(Refund.Reason.PRICE_DROP)

        send_refund_notice(refund)

        [sent] = mail.outbox
        assert sent.subject == "Your refund of USD 30.00 has been sent"
        assert "Your tickets still work." in sent.body
        notification = Notification.objects.get(user=refund.booking.user)
        assert notification.type == Notification.NotificationType.PARTIAL_REFUND

    def test_send_failure_records_a_failed_notification_and_reraises(self, monkeypatch):
        refund = _refund(Refund.Reason.UNAVAILABLE, "80.00")
        monkeypatch.setattr(
            "apps.notifications.emails.EmailMultiAlternatives.send",
            MagicMock(side_effect=RuntimeError("SMTP is down")),
        )

        with pytest.raises(RuntimeError):
            send_refund_notice(refund)

        notification = Notification.objects.get(user=refund.booking.user)
        assert notification.status == Notification.Status.FAILED
        assert notification.sent_at is None


class TestSendPayoutSettledEmail:
    def test_happy_path_sends_email_to_the_organizer(self):
        event = EventFactory()
        payout = OrganizerPayoutFactory(event=event, status="settled")

        send_payout_settled_email(payout)

        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert sent.to == [event.organizer.email]
        assert sent.subject == f"Your payout for {event.title} has been sent"
        assert "(10%, card fees included)" in sent.body

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
    return TicketFactory(booking=booking, event_seat=seat, status=status)


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
        "apps.notifications.emails.EmailMultiAlternatives.send",
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
    from apps.notifications.constants import REMINDER_MAX_ATTEMPTS

    _ticket_for(_event_starting_in(10))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("bad address")

    monkeypatch.setattr("apps.notifications.emails.EmailMultiAlternatives.send", boom)

    for _ in range(REMINDER_MAX_ATTEMPTS + 3):
        assert send_event_reminders_batch() == 0

    assert len(calls) == REMINDER_MAX_ATTEMPTS
    assert (
        Notification.objects.filter(
            type=Notification.NotificationType.EVENT_REMINDER, status="failed"
        ).count()
        == REMINDER_MAX_ATTEMPTS
    )


def test_booking_confirmation_records_the_event():
    event = EventFactory(status="approved")
    booking = paid_booking(event, (TicketTierFactory(event=event), "20.00"))

    send_booking_confirmation_email(booking)

    assert Notification.objects.get().event == event
