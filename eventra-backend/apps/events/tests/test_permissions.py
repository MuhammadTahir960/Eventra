import pytest
from django.contrib.auth.models import AnonymousUser
from apps.common.constants import Roles
from apps.users.factories import UserFactory
from ..factories import EventFactory, TicketTierFactory
from ..permissions import IsEventOwnerOrAdminForDelete, IsEventOwnerStrict


class FakeRequest:
    def __init__(self, user):
        self.user = user


pytestmark = pytest.mark.django_db


# ==================================================
# IsEventOwnerStrict
# ==================================================


def test_has_permission_true_for_any_authenticated_user():
    user = UserFactory(role=Roles.ATTENDEE)
    assert IsEventOwnerStrict().has_permission(FakeRequest(user), None) is True


def test_has_permission_false_for_anonymous():
    assert (
        IsEventOwnerStrict().has_permission(FakeRequest(AnonymousUser()), None) is False
    )


def test_object_permission_true_for_owner():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(organizer), None, event)
        is True
    )


def test_object_permission_false_for_non_owner_organizer():
    owner = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(other), None, event)
        is False
    )


def test_object_permission_false_for_admin_who_is_not_owner():
    owner = UserFactory(role=Roles.ORGANIZER)
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(admin), None, event)
        is False
    )


def test_object_permission_true_for_admin_who_owns_the_event():
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=admin)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(admin), None, event)
        is True
    )


def test_object_permission_resolves_ticket_tier_to_its_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    tier = TicketTierFactory(event=EventFactory(organizer=organizer))
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(organizer), None, tier)
        is True
    )


def test_object_permission_false_for_anonymous_on_object_check():
    event = EventFactory()
    assert (
        IsEventOwnerStrict().has_object_permission(
            FakeRequest(AnonymousUser()), None, event
        )
        is False
    )


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
