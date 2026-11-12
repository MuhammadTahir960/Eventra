import uuid
from types import SimpleNamespace

import pytest

from apps.common.constants import Roles
from apps.common.permissions import (
    IsAdmin,
    IsAdminForWrite,
    IsOrganizer,
    IsOwnerOrAdmin,
)
from apps.users.factories import UserFactory
from tests.helpers import fake_request, user_with_role

pytestmark = pytest.mark.django_db

ROLES = [None, Roles.ATTENDEE, Roles.ORGANIZER, Roles.ADMIN]


@pytest.mark.parametrize("role", ROLES)
def test_is_organizer_allows_organizers_only(role):
    request = fake_request(user_with_role(role))
    assert IsOrganizer().has_permission(request, None) is (role == Roles.ORGANIZER)


@pytest.mark.parametrize("role", ROLES)
def test_is_admin_allows_admins_only(role):
    request = fake_request(user_with_role(role))
    assert IsAdmin().has_permission(request, None) is (role == Roles.ADMIN)


@pytest.mark.parametrize(
    "role, method, allowed",
    [
        (None, "GET", True),
        (Roles.ATTENDEE, "GET", True),
        (None, "POST", False),
        (Roles.ATTENDEE, "POST", False),
        (Roles.ORGANIZER, "PATCH", False),
        (Roles.ADMIN, "DELETE", True),
    ],
)
def test_is_admin_for_write_lets_anyone_read_and_admins_write(role, method, allowed):
    request = fake_request(user_with_role(role), method)
    assert IsAdminForWrite().has_permission(request, None) is allowed


@pytest.mark.parametrize(
    "role, owns_it, allowed",
    [
        (None, False, False),
        (Roles.ATTENDEE, False, False),
        (Roles.ORGANIZER, False, False),
        (Roles.ATTENDEE, True, True),
        (Roles.ADMIN, False, True),
    ],
)
def test_is_owner_or_admin_allows_the_owner_and_admins(role, owns_it, allowed):
    user = user_with_role(role)
    obj = type("Owned", (), {"user_id": user.id if owns_it else uuid.uuid4()})()
    request = fake_request(user)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is allowed


@pytest.mark.parametrize("role, allowed", [(None, False), (Roles.ATTENDEE, True)])
def test_is_owner_or_admin_needs_only_a_signed_in_user_to_reach_the_object(
    role, allowed
):
    request = fake_request(user_with_role(role))
    assert IsOwnerOrAdmin().has_permission(request, None) is allowed


@pytest.mark.parametrize("owns_it, allowed", [(True, True), (False, False)])
def test_is_owner_or_admin_reads_the_owner_from_the_views_owner_field(owns_it, allowed):
    user = UserFactory(role=Roles.ORGANIZER)
    obj = SimpleNamespace(organizer_id=user.id if owns_it else uuid.uuid4())
    view = SimpleNamespace(owner_field="organizer_id")
    request = fake_request(user)
    assert IsOwnerOrAdmin().has_object_permission(request, view, obj) is allowed


@pytest.mark.parametrize("owns_it, allowed", [(True, True), (False, False)])
def test_is_owner_or_admin_follows_a_dotted_owner_field(owns_it, allowed):
    user = UserFactory(role=Roles.ORGANIZER)
    owner_id = user.id if owns_it else uuid.uuid4()
    ticket = SimpleNamespace(
        event_seat=SimpleNamespace(event=SimpleNamespace(organizer_id=owner_id))
    )
    view = SimpleNamespace(owner_field="event_seat.event.organizer_id")
    request = fake_request(user)
    assert IsOwnerOrAdmin().has_object_permission(request, view, ticket) is allowed
