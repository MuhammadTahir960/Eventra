import pytest
from django.contrib.admin.sites import AdminSite

from ..admin import EventAdmin
from ..factories import EventFactory
from ..models import Event

pytestmark = pytest.mark.django_db


def test_admin_queryset_includes_soft_deleted_events():
    EventFactory(title="Visible Event", is_active=True)
    inactive = EventFactory(title="Archived Event", is_active=True)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    admin = EventAdmin(Event, AdminSite())
    titles = set(admin.get_queryset(request=None).values_list("title", flat=True))

    assert titles == {"Visible Event", "Archived Event"}
