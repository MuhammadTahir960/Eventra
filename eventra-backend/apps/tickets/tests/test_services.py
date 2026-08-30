import pytest

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory

from ..models import Ticket
from ..services import (
    TicketAlreadyCancelledError,
    TicketAlreadyUsedError,
    TicketWrongEventError,
    render_ticket_pdf,
    validate_ticket,
)

pytestmark = pytest.mark.django_db


class TestValidateTicket:
    def test_happy_path_flips_status_to_used(self):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(
            booking=BookingFactory(), event_seat=seat, status=Ticket.Status.VALID
        )

        result = validate_ticket(ticket=ticket, event_id=event.id)

        result.refresh_from_db()
        assert result.status == Ticket.Status.USED

    def test_wrong_event_raises_before_touching_status(self):
        event = EventFactory(status="approved")
        other_event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(
            booking=BookingFactory(), event_seat=seat, status=Ticket.Status.VALID
        )

        with pytest.raises(TicketWrongEventError):
            validate_ticket(ticket=ticket, event_id=other_event.id)

        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    def test_already_used_raises(self):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(
            booking=BookingFactory(), event_seat=seat, status=Ticket.Status.USED
        )

        with pytest.raises(TicketAlreadyUsedError):
            validate_ticket(ticket=ticket, event_id=event.id)

    def test_cancelled_raises(self):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(
            booking=BookingFactory(), event_seat=seat, status=Ticket.Status.CANCELLED
        )

        with pytest.raises(TicketAlreadyCancelledError):
            validate_ticket(ticket=ticket, event_id=event.id)

    def test_wrong_event_check_runs_before_status_check(self):
        event = EventFactory(status="approved")
        other_event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(
            booking=BookingFactory(), event_seat=seat, status=Ticket.Status.USED
        )

        with pytest.raises(TicketWrongEventError):
            validate_ticket(ticket=ticket, event_id=other_event.id)


class TestRenderTicketPdf:
    def test_returns_bytes_and_embeds_ticket_code(self, monkeypatch):
        event = EventFactory(status="approved")
        seat = EventSeatFactory(event=event)
        ticket = Ticket.objects.create(booking=BookingFactory(), event_seat=seat)

        captured_html = {}

        class _FakeHTML:
            def __init__(self, string):
                captured_html["value"] = string

            def write_pdf(self):
                return b"%PDF-fake-bytes"

        monkeypatch.setattr("apps.tickets.services.weasyprint.HTML", _FakeHTML)

        result = render_ticket_pdf(ticket)

        assert result == b"%PDF-fake-bytes"
        assert ticket.ticket_code in captured_html["value"]
