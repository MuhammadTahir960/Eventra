import pytest
from django.contrib.auth.models import AnonymousUser
from apps.common.permissions import IsAdmin, IsOrganizer, IsOwnerOrAdmin
from apps.users.factories import UserFactory
from apps.users.models import User


class FakeRequest:
    def __init__(self, user):
        self.user = user


class FakeObj:
    def __init__(self, user_id):
        self.user_id = user_id


# ==================================================
# IsOrganizer
# ==================================================


@pytest.mark.django_db
def test_is_organizer_denies_anonymous():
    request = FakeRequest(AnonymousUser())
    assert IsOrganizer().has_permission(request, None) is False


@pytest.mark.django_db
def test_is_organizer_denies_attendee():
    user = UserFactory(role=User.Roles.ATTENDEE)
    request = FakeRequest(user)
    assert IsOrganizer().has_permission(request, None) is False


@pytest.mark.django_db
def test_is_organizer_allows_organizer():
    user = UserFactory(role=User.Roles.ORGANIZER)
    request = FakeRequest(user)
    assert IsOrganizer().has_permission(request, None) is True


@pytest.mark.django_db
def test_is_organizer_denies_admin():
    user = UserFactory(role=User.Roles.ADMIN)
    request = FakeRequest(user)
    assert IsOrganizer().has_permission(request, None) is False


# ==================================================
# IsAdmin
# ==================================================


@pytest.mark.django_db
def test_is_admin_denies_anonymous():
    request = FakeRequest(AnonymousUser())
    assert IsAdmin().has_permission(request, None) is False


@pytest.mark.django_db
def test_is_admin_denies_attendee():
    user = UserFactory(role=User.Roles.ATTENDEE)
    request = FakeRequest(user)
    assert IsAdmin().has_permission(request, None) is False


@pytest.mark.django_db
def test_is_admin_denies_organizer():
    user = UserFactory(role=User.Roles.ORGANIZER)
    request = FakeRequest(user)
    assert IsAdmin().has_permission(request, None) is False


@pytest.mark.django_db
def test_is_admin_allows_admin():
    user = UserFactory(role=User.Roles.ADMIN)
    request = FakeRequest(user)
    assert IsAdmin().has_permission(request, None) is True


# ==================================================
# IsOwnerOrAdmin
# ==================================================


@pytest.mark.django_db
def test_is_owner_or_admin_denies_anonymous():
    request = FakeRequest(AnonymousUser())
    obj = FakeObj(user_id=999)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is False


@pytest.mark.django_db
def test_is_owner_or_admin_denies_non_owner_attendee():
    user = UserFactory(role=User.Roles.ATTENDEE)
    request = FakeRequest(user)
    obj = FakeObj(user_id=user.id + 1)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is False


@pytest.mark.django_db
def test_is_owner_or_admin_allows_actual_owner():
    user = UserFactory(role=User.Roles.ATTENDEE)
    request = FakeRequest(user)
    obj = FakeObj(user_id=user.id)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is True


@pytest.mark.django_db
def test_is_owner_or_admin_allows_admin_regardless_of_ownership():
    admin = UserFactory(role=User.Roles.ADMIN)
    request = FakeRequest(admin)
    obj = FakeObj(user_id=admin.id + 1)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is True


@pytest.mark.django_db
def test_is_owner_or_admin_denies_non_owner_organizer():
    user = UserFactory(role=User.Roles.ORGANIZER)
    request = FakeRequest(user)
    obj = FakeObj(user_id=user.id + 1)
    assert IsOwnerOrAdmin().has_object_permission(request, None, obj) is False


@pytest.mark.django_db
def test_is_owner_or_admin_has_permission_is_not_restricted_by_role_or_ownership():
    user = UserFactory(role=User.Roles.ATTENDEE)
    request = FakeRequest(user)
    assert IsOwnerOrAdmin().has_permission(request, None) is True
