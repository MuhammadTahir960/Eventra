import pytest
from django.contrib.admin.sites import AdminSite

from ..admin import CustomUserAdmin
from ..factories import UserFactory
from ..models import User

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_django_admin_applies_the_name_rule(rf, admin_user, field):
    request = rf.get("/")
    request.user = admin_user
    user = UserFactory()
    form_class = CustomUserAdmin(User, AdminSite()).get_form(request, obj=user)
    assert field in form_class(data={field: "<b>Omar</b>"}, instance=user).errors
    assert field not in form_class(data={field: "O'Neil-Smith"}, instance=user).errors
