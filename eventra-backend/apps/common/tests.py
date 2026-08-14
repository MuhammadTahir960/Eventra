import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from rest_framework import mixins as drf_mixins
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.viewsets import GenericViewSet

from apps.categories.factories import CategoryFactory
from apps.categories.models import Category
from apps.common.constants import Roles
from apps.events.factories import EventFactory, TicketTierFactory
from apps.users.factories import UserFactory

from .mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from .permissions import IsEventOwnerStrict
from .serializers import IntegrityErrorHandlingMixin


class FakeRequest:
    def __init__(self, user):
        self.user = user


pytestmark = pytest.mark.django_db


def test_healthz_returns_200():
    client = APIClient()
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_post_not_allowed():
    client = APIClient()
    response = client.post("/healthz/")
    assert response.status_code == 405


# ==================================================
# SoftDeleteDestroyMixin / SoftDeleteRestoreMixin
# ==================================================


def test_perform_hard_delete_guard_default_returns_none():
    category = CategoryFactory()
    assert SoftDeleteDestroyMixin().perform_hard_delete_guard(category) is None


def test_perform_restore_guard_default_returns_none():
    category = CategoryFactory()
    assert SoftDeleteRestoreMixin().perform_restore_guard(category) is None


class _BlockableDestroyViewSet(
    SoftDeleteDestroyMixin, drf_mixins.RetrieveModelMixin, GenericViewSet
):
    queryset = Category.objects.all()
    serializer_class = None
    lookup_field = "pk"

    def perform_hard_delete_guard(self, instance):
        return Response({"detail": "blocked by guard"}, status=status.HTTP_409_CONFLICT)


def test_destroy_hard_delete_blocked_by_guard_returns_guard_response():
    category = CategoryFactory()
    factory = APIRequestFactory()
    request = factory.delete(f"/fake/{category.pk}/?hard=true")

    view = _BlockableDestroyViewSet()
    view.kwargs = {"pk": str(category.pk)}
    view.request = Request(request)
    view.format_kwarg = None

    response = view.destroy(view.request)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data == {"detail": "blocked by guard"}
    assert Category.all_objects.filter(pk=category.pk).exists()


# ==================================================
# IntegrityErrorHandlingMixin — default field/message
# ==================================================


class _RaisesIntegrityError:
    def create(self, validated_data):
        raise IntegrityError("duplicate key value violates unique constraint")

    def update(self, instance, validated_data):
        raise IntegrityError("duplicate key value violates unique constraint")


class _DefaultIntegrityErrorSerializer(
    IntegrityErrorHandlingMixin, _RaisesIntegrityError
):
    """
    Deliberately does NOT override integrity_error_field/message, so the
    mixin's create()/update() are exercised with the mixin's own defaults.
    """


def test_integrity_error_mixin_default_create_message():
    serializer = _DefaultIntegrityErrorSerializer()
    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer.create({})
    assert exc_info.value.detail["non_field_errors"] == (
        "This conflicts with an existing record."
    )


def test_integrity_error_mixin_default_update_message():
    serializer = _DefaultIntegrityErrorSerializer()
    with pytest.raises(drf_serializers.ValidationError) as exc_info:
        serializer.update(instance=None, validated_data={})
    assert exc_info.value.detail["non_field_errors"] == (
        "This conflicts with an existing record."
    )


# ==================================================
# IsEventOwnerStrict
# ==================================================


def test_event_owner_strict_has_permission_true_for_any_authenticated_user():
    user = UserFactory(role=Roles.ATTENDEE)
    assert IsEventOwnerStrict().has_permission(FakeRequest(user), None) is True


def test_event_owner_strict_has_permission_false_for_anonymous():
    assert (
        IsEventOwnerStrict().has_permission(FakeRequest(AnonymousUser()), None) is False
    )


def test_event_owner_strict_object_permission_true_for_owner():
    organizer = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=organizer)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(organizer), None, event)
        is True
    )


def test_event_owner_strict_object_permission_false_for_non_owner_organizer():
    owner = UserFactory(role=Roles.ORGANIZER)
    other = UserFactory(role=Roles.ORGANIZER)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(other), None, event)
        is False
    )


def test_event_owner_strict_object_permission_false_for_admin_who_is_not_owner():
    owner = UserFactory(role=Roles.ORGANIZER)
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=owner)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(admin), None, event)
        is False
    )


def test_event_owner_strict_object_permission_true_for_admin_who_owns_the_event():
    admin = UserFactory(role=Roles.ADMIN)
    event = EventFactory(organizer=admin)
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(admin), None, event)
        is True
    )


def test_event_owner_strict_object_permission_resolves_ticket_tier_to_its_event():
    organizer = UserFactory(role=Roles.ORGANIZER)
    tier = TicketTierFactory(event=EventFactory(organizer=organizer))
    assert (
        IsEventOwnerStrict().has_object_permission(FakeRequest(organizer), None, tier)
        is True
    )


def test_event_owner_strict_object_permission_false_for_anonymous_on_object_check():
    event = EventFactory()
    assert (
        IsEventOwnerStrict().has_object_permission(
            FakeRequest(AnonymousUser()), None, event
        )
        is False
    )
