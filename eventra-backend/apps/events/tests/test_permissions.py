import pytest
from django.contrib.auth.models import AnonymousUser
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from ..factories import EventFactory
from ..permissions import IsEventOwnerOrAdminForDelete


class FakeRequest:
    def __init__(self, user):
        self.user = user


pytestmark = pytest.mark.django_db

# ==================================================
# IsEventOwnerOrAdminForDelete
# ==================================================


def test_delete_permission_true_for_owner():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer)
    assert (
        IsEventOwnerOrAdminForDelete().has_object_permission(
            FakeRequest(organizer), None, event
        )
        is True
    )


def test_delete_permission_true_for_admin_on_someone_elses_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=organizer)
    assert (
        IsEventOwnerOrAdminForDelete().has_object_permission(
            FakeRequest(admin), None, event
        )
        is True
    )


def test_delete_permission_false_for_non_owner_organizer():
    owner = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerOrAdminForDelete().has_object_permission(
            FakeRequest(other), None, event
        )
        is False
    )


def test_delete_permission_false_for_anonymous():
    event = EventFactory()
    assert (
        IsEventOwnerOrAdminForDelete().has_object_permission(
            FakeRequest(AnonymousUser()), None, event
        )
        is False
    )
