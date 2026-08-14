import pytest
from django.contrib.admin.sites import AdminSite

from ..admin import VenueAdmin
from ..factories import VenueFactory
from ..models import Venue

pytestmark = pytest.mark.django_db


def test_admin_queryset_includes_soft_deleted_venues():
    VenueFactory(name="Visible Arena", is_active=True)
    VenueFactory(name="Archived Arena", is_active=False)

    admin = VenueAdmin(Venue, AdminSite())
    names = set(admin.get_queryset(request=None).values_list("name", flat=True))

    assert names == {"Visible Arena", "Archived Arena"}
