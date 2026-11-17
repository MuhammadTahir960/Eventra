import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.payments.constants import REFUND_REQUEST_CUTOFF_HOURS
from apps.payments.models import Refund
from apps.tickets.models import Ticket
from apps.tickets.services import get_or_render_ticket_pdf

from .constants import (
    REFUND_REASONS,
    REMINDER_CLAIM_STALE_MINUTES,
    REMINDER_MAX_ATTEMPTS,
    REMINDER_WINDOW_HOURS,
)
from .models import Notification

logger = logging.getLogger(__name__)


def _email(user, subject: str, body: str) -> EmailMessage:
    return EmailMessage(
        subject=subject,
        body=f"Hi {user.first_name or user.email},\n\n{body}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )


def _send_and_record(
    user, notification_type, subject, body, *, record, event=None, attachments=()
) -> None:
    notification = Notification(
        user=user,
        event=event,
        type=notification_type,
        status=Notification.Status.FAILED,
        message=record,
    )
    try:
        email = _email(user, subject, body)
        for name, content, mimetype in attachments:
            email.attach(name, content, mimetype)
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


def send_booking_confirmation_email(booking) -> None:
    tickets = list(
        booking.tickets.select_related(
            "event_seat", "event_seat__event", "event_seat__seat", "booking__user"
        )
    )
    _send_and_record(
        booking.user,
        Notification.NotificationType.BOOKING_CONFIRMATION,
        "Your Eventra booking is confirmed",
        f"Your booking is confirmed. {len(tickets)} e-ticket(s) are attached to this "
        "email.\n\nSee you there!",
        record=f"Booking confirmation, {len(tickets)} ticket(s)",
        event=booking.event,
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
    title = payout.event.title
    _send_and_record(
        payout.event.organizer,
        Notification.NotificationType.PAYOUT_SETTLED,
        "Your Eventra payout has been settled",
        f'Your payout for "{title}" has been settled: net amount ${payout.net_amount}.',
        record=f"Payout settled: {title}",
    )


def _venue_time(event, moment) -> str:
    return f"{event.local_time(moment):%Y-%m-%d %H:%M %Z}"


def _email_buyer(event, user, notification_type, subject, body) -> None:
    _send_and_record(
        user,
        notification_type,
        subject,
        body,
        record=f"{notification_type}: {event.id}",
        event=event,
    )


def send_event_updated_notice(event, user) -> None:
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        "An event you booked has been updated",
        f'The organizer of "{event.title}" changed some details, and the changes '
        "have been approved. It now starts on "
        f"{_venue_time(event, event.start_datetime)} at {event.venue.name}.\n\n"
        "Your tickets are still valid. The full details are on the event page in "
        "your Eventra account.",
    )


def send_event_running_late_notice(event, user) -> None:
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        "An event you booked is running late",
        f'"{event.title}" is running late and now ends on '
        f"{_venue_time(event, event.end_datetime)} at {event.venue.name}.\n\n"
        "Your tickets are still valid. The full details are on the event page in "
        "your Eventra account.",
    )


def send_event_postponed_notice(event, user) -> None:
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_UPDATED,
        "An event you booked has been postponed",
        f'"{event.title}" has been postponed. It now starts on '
        f"{_venue_time(event, event.start_datetime)} at {event.venue.name}.\n\n"
        "Your tickets are valid for the new date; download them again to see it. "
        "If you can't make it, you can ask for a full refund from your tickets page "
        f"until {REFUND_REQUEST_CUTOFF_HOURS} hours before the new start: "
        f"{settings.FRONTEND_URL}/bookings",
    )


def send_refund_notice(refund) -> None:
    items = list(refund.items.select_related("ticket__event_seat__event"))
    event = items[0].ticket.event_seat.event
    amount = sum(item.amount for item in items)
    full = refund.reason in Refund.FULL_REASONS
    _email_buyer(
        event,
        refund.booking.user,
        (
            Notification.NotificationType.EVENT_CANCELLED_REFUND
            if full
            else Notification.NotificationType.PARTIAL_REFUND
        ),
        (
            "Your booking has been refunded"
            if full
            else "Part of your booking has been refunded"
        ),
        f'We\'ve refunded ${amount} of your booking for "{event.title}" to your card '
        f"because {REFUND_REASONS[refund.reason]}. "
        + (
            "Your tickets have been cancelled."
            if full
            else "Your tickets are still valid."
        ),
    )


def send_event_cancelled_notice(event, user) -> None:
    _email_buyer(
        event,
        user,
        Notification.NotificationType.EVENT_CANCELLED,
        "An event you booked has been cancelled",
        f'"{event.title}" on {_venue_time(event, event.start_datetime)} has been '
        "cancelled. You'll get a full refund to your original payment method, and "
        "we'll email you again once it's done. You don't need to do anything.",
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


def send_event_reminders_batch() -> int:
    now = timezone.now()
    tickets = Ticket.objects.filter(
        status=Ticket.Status.VALID,
        event_seat__event__status="approved",
        event_seat__event__start_datetime__gt=now,
        event_seat__event__start_datetime__lte=now
        + timedelta(hours=REMINDER_WINDOW_HOURS),
    ).select_related("booking__user", "event_seat__event__venue")

    pairs = {}
    for ticket in tickets:
        event = ticket.event_seat.event
        pairs.setdefault(
            (ticket.booking.user_id, event.id), (ticket.booking.user, event)
        )

    sent = 0
    for (_user_id, event_id), (user, event) in pairs.items():
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
            _email(
                user,
                f"Reminder: {event.title} is coming up",
                f'"{event.title}" starts on {_venue_time(event, event.start_datetime)}. '
                "Your e-tickets are in your Eventra account.",
            ).send(fail_silently=False)
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
