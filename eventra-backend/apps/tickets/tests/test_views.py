from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.common.constants import Roles
from apps.events.factories import EventFactory
from apps.seating.factories import EventSeatFactory
from apps.tickets.factories import TicketFactory
from apps.users.factories import UserFactory
from tests.helpers import auth_client, results

from ..models import Ticket

pytestmark = pytest.mark.django_db


def _ticket_for_event(event, status=Ticket.Status.VALID, attendee=None):
    seat = EventSeatFactory(event=event)
    booking = BookingFactory(
        user=attendee or UserFactory(), status=Booking.Status.CONFIRMED
    )
    return TicketFactory(booking=booking, event_seat=seat, status=status)


class TestTicketValidateView:
    def test_owning_organizer_can_validate(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)

        client = auth_client(organizer)
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 200
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.USED

    def test_non_owning_organizer_is_rejected(self):
        owner = UserFactory(role=Roles.ORGANIZER)
        other_organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=owner)
        ticket = _ticket_for_event(event)

        client = auth_client(other_organizer)
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 403
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    def test_admin_can_validate_any_event(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        admin = UserFactory(role=Roles.ADMIN)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)

        client = auth_client(admin)
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 200

    def test_wrong_event_in_url_returns_409_with_distinct_message(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event_a = EventFactory(status="approved", organizer=organizer)
        event_b = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event_a)

        client = auth_client(organizer)
        response = client.post(f"/events/{event_b.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 409
        assert response.data["detail"] == "Ticket is for a different event"
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    def test_already_used_returns_409_with_distinct_message(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event, status=Ticket.Status.USED)

        client = auth_client(organizer)
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 409
        assert response.data["detail"] == "Ticket already used"

    def test_cancelled_returns_409_with_its_own_message(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event, status=Ticket.Status.CANCELLED)

        client = auth_client(organizer)
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 409
        assert response.data["detail"] == (
            "This ticket isn't valid: it was cancelled or never paid for."
        )

    def test_unauthenticated_is_rejected(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)

        client = APIClient()
        response = client.post(f"/events/{event.id}/tickets/{ticket.id}/validate/")

        assert response.status_code == 401


class TestTicketDownloadView:
    def test_owner_can_download(self, monkeypatch):
        monkeypatch.setattr(
            "apps.tickets.views.render_ticket_pdf", MagicMock(return_value=b"%PDF-1")
        )
        user = UserFactory()
        event = EventFactory(status="approved")
        ticket = _ticket_for_event(event, attendee=user)

        client = auth_client(user)
        response = client.get(f"/tickets/{ticket.id}/download/")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"

    def test_other_users_ticket_is_404(self, monkeypatch):
        monkeypatch.setattr(
            "apps.tickets.views.render_ticket_pdf", MagicMock(return_value=b"%PDF-1")
        )
        owner = UserFactory()
        stranger = UserFactory()
        event = EventFactory(status="approved")
        ticket = _ticket_for_event(event, attendee=owner)

        client = auth_client(stranger)
        response = client.get(f"/tickets/{ticket.id}/download/")

        assert response.status_code == 404


class TestTicketListView:
    def test_only_returns_own_tickets(self):
        user = UserFactory()
        other = UserFactory()
        event = EventFactory(status="approved")
        own_ticket = _ticket_for_event(event, attendee=user)
        _ticket_for_event(event, attendee=other)

        client = auth_client(user)
        response = client.get("/tickets/")

        assert response.status_code == 200
        ids = [t["id"] for t in response.data["results"]]
        assert str(own_ticket.id) in ids
        assert len(ids) == 1


@pytest.mark.parametrize(
    "booking_status, shown",
    [
        (Booking.Status.CONFIRMED, True),
        (Booking.Status.REFUNDED, True),
        (Booking.Status.PENDING, False),
        (Booking.Status.CANCELLED, False),
    ],
)
def test_buyers_see_tickets_only_from_bookings_they_paid_for(booking_status, shown):
    user = UserFactory()
    booking = BookingFactory(user=user, status=booking_status)
    status = {
        Booking.Status.CONFIRMED: Ticket.Status.VALID,
        Booking.Status.PENDING: Ticket.Status.PENDING,
    }.get(booking_status, Ticket.Status.CANCELLED)
    ticket = TicketFactory(
        booking=booking, event_seat=EventSeatFactory(), status=status
    )
    client = auth_client(user)

    listed = [row["id"] for row in results(client.get("/tickets/"))]
    assert (str(ticket.id) in listed) is shown
    assert client.get(f"/tickets/{ticket.id}/").status_code == (200 if shown else 404)
