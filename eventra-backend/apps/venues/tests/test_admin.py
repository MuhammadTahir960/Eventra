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


@pytest.mark.parametrize(
    "field, bad, good",
    [
        ("name", "<Arena>", "St. James' Park"),
        ("address", "12 Mill Lane <script>", "12 Mill Lane, Unit 3/4"),
        ("city", "Riverside 2", "St. Louis"),
        ("country", "UK!", "Côte d'Ivoire"),
    ],
)
def test_django_admin_applies_the_venue_text_rules(rf, admin_user, field, bad, good):
    request = rf.get("/")
    request.user = admin_user
    form_class = VenueAdmin(Venue, AdminSite()).get_form(request)
    assert field in form_class(data={field: bad}).errors
    assert field not in form_class(data={field: good}).errors
