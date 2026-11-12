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


def _check_in(user, event, code):
    client = auth_client(user) if user else APIClient()
    return client.post(f"/events/{event.id}/check-ins/", {"code": code}, format="json")


class TestCheckIns:
    def test_owning_organizer_checks_a_ticket_in_by_its_code(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)

        response = _check_in(organizer, event, ticket.ticket_code)

        assert response.status_code == 201
        assert response.data["id"] == str(ticket.id)
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.USED

    def test_admin_can_check_in_at_any_event(self):
        event = EventFactory(status="approved")
        ticket = _ticket_for_event(event)
        response = _check_in(UserFactory(role=Roles.ADMIN), event, ticket.ticket_code)
        assert response.status_code == 201

    @pytest.mark.parametrize("real_code", [True, False])
    def test_other_organizer_learns_nothing_about_codes(self, real_code):
        event = EventFactory(status="approved")
        ticket = _ticket_for_event(event)
        code = ticket.ticket_code if real_code else "NoSuchCode1"

        response = _check_in(UserFactory(role=Roles.ORGANIZER), event, code)

        assert response.status_code == 403
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    @pytest.mark.parametrize("role", [Roles.ATTENDEE, None])
    def test_attendees_and_anonymous_are_refused(self, role):
        event = EventFactory(status="approved")
        ticket = _ticket_for_event(event)
        user = UserFactory(role=role) if role else None
        response = _check_in(user, event, ticket.ticket_code)
        assert response.status_code == (403 if role else 401)

    def test_a_code_from_another_event_is_not_found(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event_a = EventFactory(status="approved", organizer=organizer)
        event_b = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event_a)

        response = _check_in(organizer, event_b, ticket.ticket_code)

        assert response.status_code == 404
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    def test_unknown_code_is_not_found(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        response = _check_in(organizer, event, "ABCD-EFGH-JKMN")
        assert response.status_code == 404
        assert response.data["detail"] == "No ticket with this code for this event."

    @pytest.mark.parametrize("code", ["", " ", "' OR 1=1 --", "a" * 33, None])
    def test_malformed_codes_are_rejected(self, code):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        response = _check_in(organizer, event, code)
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "typed", ["lower", "no dashes", "spaces", "lower no dashes"]
    )
    def test_staff_can_type_the_code_loosely(self, typed):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)
        code = ticket.ticket_code
        typed_code = {
            "lower": code.lower(),
            "no dashes": code.replace("-", ""),
            "spaces": code.replace("-", " "),
            "lower no dashes": code.replace("-", "").lower(),
        }[typed]
        assert _check_in(organizer, event, typed_code).status_code == 201

    @pytest.mark.parametrize(
        "code", ["ABCD-EFGH-JKM", "ABCD-EFGH-JKMNP", "ABC0-EFGH-JKMN", "ABCI-EFGH-JKMN"]
    )
    def test_codes_of_the_wrong_length_or_characters_are_refused(self, code):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        assert _check_in(organizer, event, code).status_code == 400

    def test_a_malformed_code_gets_a_plain_message(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        response = _check_in(organizer, event, "' OR 1=1")
        assert response.data["code"] == ["That isn't a ticket code."]

    def test_already_used_returns_409_with_its_own_message(self):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event, status=Ticket.Status.USED)

        response = _check_in(organizer, event, ticket.ticket_code)

        assert response.status_code == 409
        assert response.data["detail"] == "Ticket already used"

    @pytest.mark.parametrize("status", [Ticket.Status.CANCELLED, Ticket.Status.PENDING])
    def test_cancelled_or_unpaid_returns_409_with_its_own_message(self, status):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event, status=status)

        response = _check_in(organizer, event, ticket.ticket_code)

        assert response.status_code == 409
        assert response.data["detail"] == (
            "This ticket isn't valid: it was cancelled or never paid for."
        )

    @pytest.mark.parametrize("old", ["tickets/{ticket}/validate", "tickets/validate"])
    def test_the_old_validate_routes_are_gone(self, old):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)
        path = old.format(ticket=ticket.id)
        response = auth_client(organizer).post(
            f"/events/{event.id}/{path}/", {"code": ticket.ticket_code}, format="json"
        )
        assert response.status_code == 404
        ticket.refresh_from_db()
        assert ticket.status == Ticket.Status.VALID

    def test_a_check_in_takes_a_fixed_number_of_queries(
        self, django_assert_max_num_queries
    ):
        organizer = UserFactory(role=Roles.ORGANIZER)
        event = EventFactory(status="approved", organizer=organizer)
        ticket = _ticket_for_event(event)
        client = auth_client(organizer)
        with django_assert_max_num_queries(7):
            response = client.post(
                f"/events/{event.id}/check-ins/",
                {"code": ticket.ticket_code},
                format="json",
            )
        assert response.status_code == 201


class TestTicketDownloadView:
    @pytest.mark.parametrize(
        "status", [Ticket.Status.USED, Ticket.Status.CANCELLED, Ticket.Status.PENDING]
    )
    def test_only_a_valid_ticket_has_a_pdf(self, monkeypatch, status):
        render = MagicMock(return_value=b"%PDF-1")
        monkeypatch.setattr("apps.tickets.views.render_ticket_pdf", render)
        user = UserFactory()
        ticket = _ticket_for_event(EventFactory(), status=status, attendee=user)

        response = auth_client(user).get(f"/tickets/{ticket.id}/download/")

        assert response.status_code == 409
        render.assert_not_called()

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
