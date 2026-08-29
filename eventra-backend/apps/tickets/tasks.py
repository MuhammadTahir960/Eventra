import logging

from celery import shared_task

from .models import Ticket
from .services import render_ticket_pdf

logger = logging.getLogger(__name__)


@shared_task
def generate_ticket_pdf(booking_id):
    tickets = Ticket.objects.filter(booking_id=booking_id).select_related(
        "event_seat", "event_seat__event", "event_seat__seat"
    )

    for ticket in tickets:
        try:
            render_ticket_pdf(ticket)
        except Exception:
            logger.exception(
                "Failed to render ticket PDF for ticket %s (booking %s)",
                ticket.id,
                booking_id,
            )
