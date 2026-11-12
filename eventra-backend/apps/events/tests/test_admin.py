import pytest
from django.contrib.admin.sites import AdminSite

from apps.bookings.factories import BookingFactory
from apps.bookings.models import Booking
from apps.seating.factories import EventSeatFactory
from apps.tickets.factories import TicketFactory
from apps.tickets.models import Ticket
from apps.users.factories import UserFactory
from apps.venues.factories import SeatFactory

from ..admin import EventAdmin, TicketTierAdmin
from ..factories import EventFactory, TicketTierFactory
from ..models import Event, TicketTier

pytestmark = pytest.mark.django_db


def test_admin_queryset_includes_soft_deleted_events():
    EventFactory(title="Visible Event", is_active=True)
    inactive = EventFactory(title="Archived Event", is_active=True)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    admin = EventAdmin(Event, AdminSite())
    titles = set(admin.get_queryset(request=None).values_list("title", flat=True))

    assert titles == {"Visible Event", "Archived Event"}


@pytest.mark.parametrize(
    "ticket_status", [Ticket.Status.VALID, Ticket.Status.CANCELLED, None]
)
def test_django_admin_cannot_delete_an_event_that_has_or_had_tickets(rf, ticket_status):
    seat = EventSeatFactory()
    if ticket_status:
        TicketFactory(
            booking=BookingFactory(status=Booking.Status.REFUNDED),
            event_seat=seat,
            status=ticket_status,
        )
    request = rf.get("/")
    request.user = UserFactory(role="admin", is_staff=True, is_superuser=True)
    admin = EventAdmin(Event, AdminSite())

    assert admin.has_delete_permission(request, seat.event) is (ticket_status is None)


def test_tier_price_is_editable_until_seats_exist():
    tier = TicketTierFactory()
    admin = TicketTierAdmin(TicketTier, AdminSite())

    assert "price" not in admin.get_readonly_fields(request=None, obj=tier)
    assert "price" not in admin.get_readonly_fields(request=None, obj=None)

    EventSeatFactory(
        event=tier.event, ticket_tier=tier, seat=SeatFactory(venue=tier.event.venue)
    )
    assert "price" in admin.get_readonly_fields(request=None, obj=tier)


def test_django_admin_applies_the_event_title_rule(rf, admin_user):
    request = rf.get("/")
    request.user = admin_user
    form_class = EventAdmin(Event, AdminSite()).get_form(request)
    assert "title" in form_class(data={"title": "Party <3"}).errors
    assert "title" not in form_class(data={"title": "R&B Night: Vol. 2"}).errors
