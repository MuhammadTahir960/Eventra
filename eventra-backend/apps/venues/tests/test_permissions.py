import pytest
from django.contrib.auth.models import AnonymousUser

from apps.common.constants import Roles
from apps.users.factories import UserFactory

from ..permissions import IsOrganizerOrAdminForWrite


class FakeRequest:
    def __init__(self, user, method="GET"):
        self.user = user
        self.method = method


# ==================================================
# Safe methods — always allowed
# ==================================================


@pytest.mark.django_db
def test_safe_method_allowed_for_anonymous():
    request = FakeRequest(AnonymousUser(), method="GET")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is True


@pytest.mark.django_db
def test_safe_method_allowed_for_attendee():
    user = UserFactory(role=Roles.ATTENDEE)
    request = FakeRequest(user, method="GET")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is True


# ==================================================
# Unsafe methods — restricted to organizer/admin
# ==================================================


@pytest.mark.django_db
def test_write_method_denied_for_anonymous():
    request = FakeRequest(AnonymousUser(), method="POST")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is False


@pytest.mark.django_db
def test_write_method_denied_for_attendee():
    user = UserFactory(role=Roles.ATTENDEE)
    request = FakeRequest(user, method="POST")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is False


@pytest.mark.django_db
def test_write_method_allowed_for_organizer():
    user = UserFactory(role=Roles.ORGANIZER)
    request = FakeRequest(user, method="POST")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is True


@pytest.mark.django_db
def test_write_method_allowed_for_admin():
    user = UserFactory(role=Roles.ADMIN)
    request = FakeRequest(user, method="PATCH")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is True


@pytest.mark.django_db
def test_delete_method_denied_for_organizer_is_false_by_default_behavior():
    user = UserFactory(role=Roles.ORGANIZER)
    request = FakeRequest(user, method="DELETE")
    assert IsOrganizerOrAdminForWrite().has_permission(request, None) is True
