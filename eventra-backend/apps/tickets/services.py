import base64
import html
from io import BytesIO

import qrcode
import weasyprint
from django.core.cache import cache
from django.db import transaction

from .models import Ticket

TICKET_PDF_CACHE_TTL_SECONDS = 600


class TicketWrongEventError(Exception):
    """Raised when a ticket is scanned at a door for an event it doesn't belong to."""


class TicketAlreadyUsedError(Exception):
    """Raised when a valid-status check finds the ticket already used."""


class TicketAlreadyCancelledError(Exception):
    """Raised when a valid-status check finds the ticket cancelled."""


def render_ticket_pdf(ticket: Ticket) -> bytes:
    qr_buffer = BytesIO()
    qrcode.make(ticket.ticket_code).save(qr_buffer, format="PNG")
    qr_data_uri = "data:image/png;base64," + base64.b64encode(
        qr_buffer.getvalue()
    ).decode("ascii")

    event = ticket.event_seat.event
    seat = ticket.event_seat.seat

    event_title = html.escape(event.title)
    attendee_name = html.escape(ticket.attendee_name) if ticket.attendee_name else ""
    seat_location = html.escape(
        f"{seat.section} · Row {seat.row_label} · Seat {seat.seat_number}"
    )
    ticket_code = html.escape(ticket.ticket_code)
    status_label = html.escape(ticket.get_status_display())

    ticket_html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: sans-serif; padding: 32px; }}
          .ticket {{ border: 2px solid #333; border-radius: 8px; padding: 24px; max-width: 480px; }}
          h1 {{ font-size: 20px; margin: 0 0 4px 0; }}
          .meta {{ color: #555; margin: 2px 0; }}
          .code {{ font-family: monospace; font-size: 14px; margin-top: 16px; }}
          img {{ margin-top: 16px; }}
        </style>
      </head>
      <body>
        <div class="ticket">
          <h1>{event_title}</h1>
          <p class="meta">{event.start_datetime:%A, %B %d, %Y — %I:%M %p} UTC</p>
          <p class="meta">{seat_location}</p>
          {f'<p class="meta">Attendee: {attendee_name}</p>' if attendee_name else ""}
          <p class="meta">Status: {status_label}</p>
          <img src="{qr_data_uri}" width="160" height="160" alt="QR code" />
          <p class="code">{ticket_code}</p>
        </div>
      </body>
    </html>
    """
    return weasyprint.HTML(string=ticket_html).write_pdf()


def _ticket_pdf_cache_key(ticket_id) -> str:
    return f"ticket-pdf:{ticket_id}"


def get_or_render_ticket_pdf(ticket: Ticket) -> bytes:
    key = _ticket_pdf_cache_key(ticket.id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    pdf_bytes = render_ticket_pdf(ticket)
    cache.set(key, pdf_bytes, timeout=TICKET_PDF_CACHE_TTL_SECONDS)
    return pdf_bytes


def validate_ticket(*, ticket: Ticket, event_id) -> Ticket:
    if ticket.event_seat.event_id != event_id:
        raise TicketWrongEventError("Ticket is for a different event")

    if ticket.status == Ticket.Status.USED:
        raise TicketAlreadyUsedError("Ticket already used")
    if ticket.status == Ticket.Status.CANCELLED:
        raise TicketAlreadyCancelledError("Ticket cancelled")

    with transaction.atomic():
        ticket.status = Ticket.Status.USED
        ticket.save(update_fields=["status", "updated_at"])

    return ticket
