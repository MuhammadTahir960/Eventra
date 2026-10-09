import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.tickets.models import Ticket
from apps.tickets.services import get_or_render_ticket_pdf

from .models import Notification

logger = logging.getLogger(__name__)


def send_booking_confirmation_email(booking) -> None:
    tickets = list(
        booking.tickets.select_related(
            "event_seat", "event_seat__event", "event_seat__seat"
        )
    )

    notification = Notification(
        user=booking.user,
        type=Notification.NotificationType.BOOKING_CONFIRMATION,
        status=Notification.Status.FAILED,
    )

    try:
        message = EmailMessage(
            subject="Your Eventra booking is confirmed",
            body=(
                f"Hi {booking.user.first_name or booking.user.email},\n\n"
                f"Your booking is confirmed. {len(tickets)} e-ticket(s) are "
                "attached to this email.\n\nSee you there!"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.user.email],
        )
        for ticket in tickets:
            pdf_bytes = get_or_render_ticket_pdf(ticket)
            message.attach(
                f"ticket-{ticket.ticket_code}.pdf", pdf_bytes, "application/pdf"
            )
        message.send(fail_silently=False)

        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.message = f"Booking confirmation, {len(tickets)} ticket(s)"
    except Exception:
        logger.exception(
            "Failed to send booking confirmation email for booking %s", booking.id
        )
        notification.message = "Failed to send booking confirmation email"
        notification.save()
        raise
    else:
        notification.save()


def send_payout_ready_email(payout) -> None:
    organizer = payout.event.organizer
    notification = Notification(
        user=organizer,
        type=Notification.NotificationType.PAYOUT_READY,
        status=Notification.Status.FAILED,
    )
    try:
        message = EmailMessage(
            subject="Your Eventra payout is ready for review",
            body=(
                f"Hi {organizer.first_name or organizer.email},\n\n"
                f'Your event "{payout.event.title}" has concluded and a payout has been '
                f"calculated: net amount ${payout.net_amount} (reference "
                f"{payout.payout_reference}). An admin will review and settle it shortly."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[organizer.email],
        )
        message.send(fail_silently=False)

        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.message = f"Payout ready: {payout.payout_reference}"
    except Exception:
        logger.exception("Failed to send payout-ready email for payout %s", payout.id)
        notification.message = "Failed to send payout-ready email"
        notification.save()
        raise
    else:
        notification.save()


def send_payout_settled_email(payout) -> None:
    organizer = payout.event.organizer
    notification = Notification(
        user=organizer,
        type=Notification.NotificationType.PAYOUT_SETTLED,
        status=Notification.Status.FAILED,
    )
    try:
        message = EmailMessage(
            subject="Your Eventra payout has been settled",
            body=(
                f"Hi {organizer.first_name or organizer.email},\n\n"
                f'Your payout for "{payout.event.title}" (reference '
                f"{payout.payout_reference}) has been settled: net amount "
                f"${payout.net_amount}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[organizer.email],
        )
        message.send(fail_silently=False)

        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.message = f"Payout settled: {payout.payout_reference}"
    except Exception:
        logger.exception("Failed to send payout-settled email for payout %s", payout.id)
        notification.message = "Failed to send payout-settled email"
        notification.save()
        raise
    else:
        notification.save()


def send_refund_confirmation_email(booking, *, event_cancelled: bool = True) -> None:
    notification = Notification(
        user=booking.user,
        type=Notification.NotificationType.EVENT_CANCELLED_REFUND,
        status=Notification.Status.FAILED,
    )
    try:
        message = EmailMessage(
            subject="Your Eventra booking has been refunded",
            body=(
                f"Hi {booking.user.first_name or booking.user.email},\n\n"
                + (
                    "The event you booked has been cancelled by the organizer. "
                    if event_cancelled
                    else "We couldn't complete your booking (the reservation "
                    "expired or the event is no longer available). "
                )
                + f"Your payment of ${booking.total_amount} has been refunded."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.user.email],
        )
        message.send(fail_silently=False)

        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.message = "Event cancellation refund confirmation"
    except Exception:
        logger.exception(
            "Failed to send refund confirmation email for booking %s", booking.id
        )
        notification.message = "Failed to send refund confirmation email"
        notification.save()
        raise
    else:
        notification.save()


REMINDER_WINDOW_HOURS = 24
REMINDER_CLAIM_STALE_MINUTES = 15
REMINDER_MAX_ATTEMPTS = 3


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
    ).select_related("booking__user", "event_seat__event")

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
            send_mail(
                subject=f"Reminder: {event.title} is coming up",
                message=(
                    f"Hi {user.first_name or user.email},\n\n"
                    f'"{event.title}" starts on {event.start_datetime:%Y-%m-%d %H:%M} '
                    "UTC. Your e-tickets are in your Eventra account."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
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
