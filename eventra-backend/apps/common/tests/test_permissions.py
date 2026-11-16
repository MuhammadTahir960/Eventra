import pytest
from django.contrib.auth.models import AnonymousUser

from apps.common.constants import Roles
from apps.events.factories import EventFactory, TicketTierFactory
from apps.users.factories import UserFactory
from tests.helpers import fake_request

from ..permissions import IsEventOwnerStrict

pytestmark = pytest.mark.django_db


# ==================================================
# IsEventOwnerStrict
# ==================================================


def test_event_owner_strict_has_permission_true_for_any_authenticated_user():
    user = UserFactory(role=Roles.ATTENDEE)
    assert IsEventOwnerStrict().has_permission(fake_request(user), None) is True


def test_event_owner_strict_has_permission_false_for_anonymous():
    assert (
        IsEventOwnerStrict().has_permission(fake_request(AnonymousUser()), None)
        is False
    )


def test_event_owner_strict_object_permission_true_for_owner():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer)
    assert (
        IsEventOwnerStrict().has_object_permission(fake_request(organizer), None, event)
        is True
    )


def test_event_owner_strict_object_permission_false_for_non_owner_organizer():
    owner = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(fake_request(other), None, event)
        is False
    )


def test_event_owner_strict_object_permission_false_for_admin_who_is_not_owner():
    owner = UserFactory(role=Roles.ORGANIZER)
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(fake_request(admin), None, event)
        is False
    )


def test_event_owner_strict_object_permission_true_for_admin_who_owns_the_event():
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=admin)
    assert (
        IsEventOwnerStrict().has_object_permission(fake_request(admin), None, event)
        is True
    )


def test_event_owner_strict_object_permission_resolves_ticket_tier_to_its_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    tier = TicketTierFactory(event=EventFactory(organizer=organizer))
    assert (
        IsEventOwnerStrict().has_object_permission(fake_request(organizer), None, tier)
        is True
    )


def test_event_owner_strict_object_permission_false_for_anonymous_on_object_check():
    event = EventFactory()
    assert (
        IsEventOwnerStrict().has_object_permission(
            fake_request(AnonymousUser()), None, event
        )
        is False
    )
