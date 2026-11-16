import pytest
from rest_framework import mixins as drf_mixins
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.viewsets import GenericViewSet

from apps.categories.factories import CategoryFactory
from apps.categories.models import Category

from ..mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin

pytestmark = pytest.mark.django_db


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
