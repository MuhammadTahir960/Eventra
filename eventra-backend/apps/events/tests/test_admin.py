import pytest
from django.contrib.admin.sites import AdminSite

from apps.seating.factories import EventSeatFactory
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


def test_tier_price_is_editable_until_seats_exist():
    tier = TicketTierFactory()
    admin = TicketTierAdmin(TicketTier, AdminSite())

    assert "price" not in admin.get_readonly_fields(request=None, obj=tier)
    assert "price" not in admin.get_readonly_fields(request=None, obj=None)

    EventSeatFactory(
        event=tier.event, ticket_tier=tier, seat=SeatFactory(venue=tier.event.venue)
    )
    assert "price" in admin.get_readonly_fields(request=None, obj=tier)
