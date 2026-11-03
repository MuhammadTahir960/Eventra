import pytest

from apps.common.constants import Roles
from apps.users.factories import UserFactory
from tests.helpers import fake_request, user_with_role

from ..factories import EventFactory
from ..permissions import IsEventOwnerOrAdmin

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role, owns_it, allowed",
    [
        (Roles.ORGANIZER, True, True),
        (Roles.ADMIN, False, True),
        (Roles.ORGANIZER, False, False),
        (None, False, False),
    ],
)
def test_the_owner_or_an_admin_may_act_on_an_event(role, owns_it, allowed):
    user = user_with_role(role)
    event = EventFactory(
        organizer=user if owns_it else UserFactory(role=Roles.ORGANIZER)
    )
    request = fake_request(user)
    assert IsEventOwnerOrAdmin().has_object_permission(request, None, event) is allowed
