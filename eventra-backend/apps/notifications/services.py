import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

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


def send_refund_confirmation_email(booking) -> None:
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
                "The event you booked has been cancelled by the organizer. "
                f"Your payment of ${booking.total_amount} has been refunded."
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
