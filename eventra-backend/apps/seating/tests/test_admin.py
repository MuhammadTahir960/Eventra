import pytest
from django.contrib.admin.sites import AdminSite

from ..admin import EventSeatAdmin
from ..factories import EventSeatFactory
from ..models import EventSeat

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "seat_status, read_only",
    [
        (EventSeat.Status.AVAILABLE, False),
        (EventSeat.Status.HELD, True),
        (EventSeat.Status.BOOKED, True),
    ],
)
def test_price_override_is_read_only_once_a_seat_is_held_or_booked(
    seat_status, read_only
):
    seat = EventSeatFactory(status=seat_status)
    admin = EventSeatAdmin(EventSeat, AdminSite())

    fields = admin.get_readonly_fields(request=None, obj=seat)

    assert ("price_override" in fields) is read_only
