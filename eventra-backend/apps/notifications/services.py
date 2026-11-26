import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.payments.constants import REFUND_REQUEST_CUTOFF_HOURS
from apps.payments.models import Refund
from apps.payouts.services import PLATFORM_FEE_PERCENTAGE
from apps.tickets.models import Ticket
from apps.tickets.services import get_or_render_ticket_pdf

from .constants import (
    REASON_BOOKED,
    REASON_ORGANIZER,
    REFUND_LINES,
    REMINDER_CLAIM_STALE_MINUTES,
    REMINDER_MAX_ATTEMPTS,
    REMINDER_WINDOW_HOURS,
)
from .emails import build_email
from .models import Notification

logger = logging.getLogger(__name__)


def _name(user) -> str:
    return user.first_name or user.email


def _send_and_record(
    user, notification_type, subject, content, *, record, event=None, attachments=()
) -> None:
    notification = Notification(
        user=user,
        event=event,
        type=notification_type,
        status=Notification.Status.FAILED,
        message=record,
    )
    try:
        email = build_email(user.email, subject, **content)
        for name, data, mimetype in attachments:
            email.attach(name, data, mimetype)
        email.send(fail_silently=False)
    except Exception:
        logger.exception(
            "Failed to send %s email to user %s", notification_type, user.id
        )
        notification.save()
        raise
    notification.status = Notification.Status.SENT
    notification.sent_at = timezone.now()
    notification.save()


def _money(amount, currency) -> str:
    return f"{currency.upper()} {amount:,.2f}"


def _venue_date(event, moment, *, year=True) -> str:
    local = event.local_time(moment)
    return f"{local:%a} {local.day} {local:%b}" + (f" {local:%Y}" if year else "")


def _venue_time(event, moment) -> str:
    city = event.time_zone.rsplit("/", 1)[-1].replace("_", " ")
    return f"{_venue_date(event, moment)}, {event.local_time(moment):%H:%M} {city} time"


def _where(event) -> str:
    return f"{event.venue.name}, {event.venue.city}"


def _seats(tickets) -> str:
    rows = {}
    for seat in sorted(
        (t.event_seat.seat for t in tickets),
        key=lambda s: (s.section, s.row_label, s.seat_number),
    ):
        rows.setdefault((seat.section, seat.row_label), []).append(
            str(seat.seat_number)
        )
    parts = []
    for (section, row), numbers in rows.items():
        seats = (
            f"seats {', '.join(numbers[:-1])} and {numbers[-1]}"
            if len(numbers) > 1
            else f"seat {numbers[0]}"
        )
        parts.append(f"Section {section}, row {row}, {seats}")
    return "; ".join(parts)


def _ticket_count(n) -> str:
    return f"{n} ticket" if n == 1 else f"{n} tickets"


def _bookings_url() -> str:
    return f"{settings.FRONTEND_URL}/bookings"


def _has_paid_tickets(event, user) -> bool:
    return Ticket.objects.filter(
        booking__user=user,
        booking__status__in=Booking.PAID_STATUSES,
        event_seat__event=event,
        price__gt=0,
    ).exists()


def send_booking_confirmation_email(booking) -> None:
    tickets = list(
        booking.tickets.select_related(
            "event_seat__event__venue", "event_seat__seat", "booking__user"
        )
    )
    if not tickets:
        logger.warning("Booking %s has no tickets; no confirmation sent", booking.id)
        return
    event = tickets[0].event_seat.event
    total = booking.total_amount
    pdfs = "The PDFs are attached" if len(tickets) > 1 else "The PDF is attached"
    _send_and_record(
        booking.user,
        Notification.NotificationType.BOOKING_CONFIRMATION,
        f"Your tickets for {event.title}",
        {
            "pill": _ticket_count(len(tickets)),
            "headline": "You're in,",
            "turn": f"{_name(booking.user)}!",
            "paragraphs": [
                f"Your tickets are booked. {pdfs}, and they're in your Eventra "
                "account too."
            ],
            "ticket": {
                "title": event.title,
                "lines": [_venue_time(event, event.start_datetime), _where(event)],
                "rows": [
                    ("Seats", _seats(tickets)),
                    ("Paid", _money(total, event.currency) if total else "Free"),
                ],
            },
            "button": ("View your tickets", _bookings_url()),
            "after": "Each ticket has a QR code that's scanned at the door. "
            + (
                "Paid tickets are refunded only if the event is cancelled or moved."
                if total
                else "Can't make it? Hand your ticket back from your account until "
                "the event starts, so someone else can go."
            ),
            "reason": REASON_BOOKED,
        },
        record=f"Booking confirmation, {len(tickets)} ticket(s)",
        event=event,
        attachments=(
            (
                f"ticket-{ticket.ticket_code}.pdf",
                get_or_render_ticket_pdf(ticket),
                "application/pdf",
            )
            for ticket in tickets
        ),
    )


def send_payout_settled_email(payout) -> None:
    event = payout.event
    currency = event.currency
    _send_and_record(
        event.organizer,
        Notification.NotificationType.PAYOUT_SETTLED,
        f"Your payout for {event.title} has been sent",
        {
            "pill": _money(payout.net_amount, currency),
            "headline": "Your payout has been sent",
            "paragraphs": [
                f"Hi {_name(event.organizer)}, {event.title} wrapped up and an "
                "Eventra admin has sent your payout. Here is how it adds up."
            ],
            "ticket": {
                "title": event.title,
                "rows": [
                    ("Ticket sales", _money(payout.gross_revenue, currency)),
                    (
                        "Eventra fee",
                        f"{_money(payout.platform_fee, currency)} "
                        f"({PLATFORM_FEE_PERCENTAGE * 100:.0f}%, card fees included)",
                    ),
                    ("You receive", _money(payout.net_amount, currency)),
                ],
            },
            "button": (
                "View your payouts",
                f"{settings.FRONTEND_URL}/organizer/payouts",
            ),
            "reason": REASON_ORGANIZER,
        },
        record=f"Payout settled: {event.title}",
    )


def _email_buyer(event, user, notification_type, subject, content) -> None:
    _send_and_record(
        user,
        notification_type,
        subject,
        {**content, "reason": REASON_BOOKED},
        record=f"{notification_type}: {event.id}",
        event=event,
    )


def send_event_updated_notice(event, user) -> None:
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        f"{event.title} has been updated",
        {
            "pill": "Updated",
            "headline": "Same event,",
            "turn": "new details.",
            "paragraphs": [
                f"Hi {_name(user)}, a quick heads-up: the organizer has made some "
                f"changes to {event.title}, and Eventra has approved them. Here is "
                "where and when it is now."
            ],
            "ticket": {
                "title": event.title,
                "lines": [_venue_time(event, event.start_datetime), _where(event)],
            },
            "button": ("See the event", f"{settings.FRONTEND_URL}/events/{event.id}"),
            "after": "Your tickets are still valid. The full details are on the "
            "event page.",
        },
    )


def send_event_running_late_notice(event, user) -> None:
    end = _venue_time(event, event.end_datetime)
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        f"{event.title} now ends later",
        {
            "pill": "New end time",
            "headline": "It runs",
            "turn": "a little longer.",
            "paragraphs": [
                f"Hi {_name(user)}, {event.title} is finishing later than planned. "
                f"The new end time is {end}."
            ],
            "ticket": {
                "title": event.title,
                "lines": [_where(event)],
                "rows": [("Now ends", end)],
            },
            "after": "Your tickets still work. Plan your trip home with the new time "
            "in mind.",
        },
    )


def send_event_postponed_notice(event, user) -> None:
    if _has_paid_tickets(event, user):
        cutoff = event.start_datetime - timedelta(hours=REFUND_REQUEST_CUTOFF_HOURS)
        refund_line = (
            "Can't make the new date? Request a full refund from your bookings "
            f"until {_venue_time(event, cutoff)}."
        )
    else:
        refund_line = (
            "Can't make the new date? Hand your ticket back from your account "
            "until the event starts."
        )
    rows = [("Now", _venue_time(event, event.start_datetime))]
    if event.postponed_from:
        rows.insert(0, ("Was", _venue_time(event, event.postponed_from)))
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        f"{event.title} has a new date",
        {
            "pill": _venue_date(event, event.start_datetime, year=False),
            "headline": "New date.",
            "turn": "Same tickets.",
            "paragraphs": [
                f"Change of plan, {_name(user)}: {event.title} has moved. Your "
                "tickets are valid for it; download them again to see the new date.",
                refund_line,
            ],
            "ticket": {"title": event.title, "lines": [_where(event)], "rows": rows},
            "button": ("View your bookings", _bookings_url()),
            "after": "Going on the new date? You don't need to do anything.",
        },
    )


def send_refund_notice(refund) -> None:
    items = list(refund.items.select_related("ticket__event_seat__event__venue"))
    event = items[0].ticket.event_seat.event
    amount = _money(sum(item.amount for item in items), event.currency)
    full = refund.reason in Refund.FULL_REASONS
    user = refund.booking.user
    _email_buyer(
        event,
        user,
        (
            Notification.NotificationType.EVENT_CANCELLED_REFUND
            if full
            else Notification.NotificationType.PARTIAL_REFUND
        ),
        f"Your refund of {amount} has been sent",
        {
            "pill": "Full refund" if full else "Partial refund",
            "headline": f"{amount},",
            "turn": "heading home.",
            "paragraphs": [
                f"Hi {_name(user)}, {REFUND_LINES[refund.reason]}",
                "It goes back to the card you paid with. Your bank usually shows it "
                "within 5 to 10 working days.",
            ],
            "ticket": {
                "title": event.title,
                "rows": [("Refunded", amount), ("To", "The card you paid with")],
            },
        },
    )


def send_event_cancelled_notice(event, user) -> None:
    paid = _has_paid_tickets(event, user)
    rows = [("Was", _venue_time(event, event.start_datetime))]
    if paid:
        rows.append(("Refund", "In full, automatically"))
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_CANCELLED,
        f"{event.title} has been cancelled",
        {
            "pill": "Cancelled",
            "headline": "Bad news:",
            "turn": "it's cancelled.",
            "paragraphs": [
                f"Hi {_name(user)}, we're sorry: {event.title} on "
                f"{_venue_date(event, event.start_datetime)} has been cancelled.",
                (
                    "You'll get a full refund to your original payment method. "
                    "We'll email you once it's done. You don't need to do anything."
                    if paid
                    else "Your free tickets are cancelled."
                ),
            ],
            "ticket": {"title": event.title, "rows": rows},
        },
    )


def _claim_reminder(user, event):
    key = f"Event reminder: {event.id}"
    try:
        with transaction.atomic():
            return Notification.objects.create(
                user=user,
                event=event,
                type=Notification.NotificationType.EVENT_REMINDER,
                status=Notification.Status.PENDING,
                message=key,
            )
    except IntegrityError:
        pass

    now = timezone.now()
    stale = Notification.objects.filter(
        user=user,
        event=event,
        type=Notification.NotificationType.EVENT_REMINDER,
        status=Notification.Status.PENDING,
        created_at__lt=now - timedelta(minutes=REMINDER_CLAIM_STALE_MINUTES),
    ).first()
    if stale is None:
        return None
    won = Notification.objects.filter(
        pk=stale.pk, status=Notification.Status.PENDING, created_at=stale.created_at
    ).update(created_at=now)
    return stale if won == 1 else None


def _reminder_email(user, event, tickets):
    start = _venue_time(event, event.start_datetime)
    return build_email(
        user.email,
        f"Reminder: {event.title} is coming up",
        pill="Reminder",
        headline="Nearly time.",
        turn="Bring your QR code.",
        paragraphs=[
            f"Hi {_name(user)}, a reminder that {event.title} starts on {start}."
        ],
        ticket={
            "title": event.title,
            "lines": [start, _where(event)],
            "rows": [("Seats", _seats(tickets))],
        },
        button=("View your tickets", _bookings_url()),
        after="Your tickets are in your Eventra account. Each one has a QR code "
        "that's scanned at the door.",
        reason=REASON_BOOKED,
    )


def send_event_reminders_batch() -> int:
    now = timezone.now()
    tickets = Ticket.objects.filter(
        status=Ticket.Status.VALID,
        event_seat__event__status="approved",
        event_seat__event__start_datetime__gt=now,
        event_seat__event__start_datetime__lte=now
        + timedelta(hours=REMINDER_WINDOW_HOURS),
    ).select_related("booking__user", "event_seat__event__venue", "event_seat__seat")

    pairs = {}
    for ticket in tickets:
        event = ticket.event_seat.event
        pairs.setdefault(
            (ticket.booking.user_id, event.id), (ticket.booking.user, event, [])
        )[2].append(ticket)

    sent = 0
    for (_user_id, event_id), (user, event, user_tickets) in pairs.items():
        failed_attempts = Notification.objects.filter(
            user=user,
            event=event,
            type=Notification.NotificationType.EVENT_REMINDER,
            status=Notification.Status.FAILED,
        ).count()
        if failed_attempts >= REMINDER_MAX_ATTEMPTS:
            continue
        claim = _claim_reminder(user, event)
        if claim is None:
            continue
        try:
            _reminder_email(user, event, user_tickets).send(fail_silently=False)
        except Exception:
            logger.exception("Failed to send reminder for event %s", event_id)
            claim.status = Notification.Status.FAILED
            claim.message = f"Failed: {claim.message}"
            claim.save(update_fields=["status", "message"])
            continue
        claim.status = Notification.Status.SENT
        claim.sent_at = timezone.now()
        claim.save(update_fields=["status", "sent_at"])
        sent += 1
    return sent
