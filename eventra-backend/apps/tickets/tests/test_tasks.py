from unittest.mock import MagicMock

import pytest
from django.core.cache import cache

from apps.bookings.factories import BookingFactory
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory

from ..models import Ticket
from ..tasks import generate_ticket_pdf

pytestmark = pytest.mark.django_db


class _FakeHTML:
    def __init__(self, string):
        pass

    def write_pdf(self):
        return b"%PDF-fake-bytes"


class TestGenerateTicketPdfTask:
    def test_task_warms_the_render_cache_for_every_ticket_on_the_booking(
        self, monkeypatch
    ):
        monkeypatch.setattr("apps.tickets.services.weasyprint.HTML", _FakeHTML)
        event = EventFactory(status="approved")
        booking = BookingFactory()
        tickets = [
            Ticket.objects.create(
                booking=booking,
                event_seat=EventSeatFactory(event=event),
                status=Ticket.Status.VALID,
            )
            for _ in range(2)
        ]

        generate_ticket_pdf(str(booking.id))

        for ticket in tickets:
            cached = cache.get(f"ticket-pdf:{ticket.id}")
            assert cached == b"%PDF-fake-bytes"

    def test_a_single_tickets_render_failure_does_not_stop_the_others(
        self, monkeypatch
    ):
        booking = BookingFactory()
        event = EventFactory(status="approved")
        good_ticket = Ticket.objects.create(
            booking=booking,
            event_seat=EventSeatFactory(event=event),
            status=Ticket.Status.VALID,
        )
        bad_ticket = Ticket.objects.create(
            booking=booking,
            event_seat=EventSeatFactory(event=event),
            status=Ticket.Status.VALID,
        )

        call_count = {"n": 0}

        def _render_that_fails_for_bad_ticket(ticket):
            call_count["n"] += 1
            if ticket.id == bad_ticket.id:
                raise RuntimeError("simulated render failure")
            return b"%PDF-fake-bytes"

        monkeypatch.setattr(
            "apps.tickets.tasks.get_or_render_ticket_pdf",
            MagicMock(side_effect=_render_that_fails_for_bad_ticket),
        )

        generate_ticket_pdf(str(booking.id))

        assert call_count["n"] == 2
        assert good_ticket
