import pytest
from django.contrib.admin.sites import AdminSite

from ..admin import CategoryAdmin
from ..factories import CategoryFactory
from ..models import Category

pytestmark = pytest.mark.django_db


def test_admin_queryset_includes_soft_deleted_categories():
    CategoryFactory(name="Visible", is_active=True)
    CategoryFactory(name="Archived", is_active=False)

    admin = CategoryAdmin(Category, AdminSite())
    names = set(admin.get_queryset(request=None).values_list("name", flat=True))

    assert names == {"Visible", "Archived"}
