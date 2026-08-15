from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.common.constants import Roles
from apps.common.mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from apps.common.permissions import IsAdminForWrite
from apps.events.services import find_blocking_upcoming_event

from .models import Category
from .serializers import CategorySerializer
from .services import DuplicateCategoryError, ensure_can_restore_category


class CategoryViewSet(
    SoftDeleteDestroyMixin, SoftDeleteRestoreMixin, viewsets.ModelViewSet
):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminForWrite]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        user = self.request.user
        include_inactive = str(
            self.request.query_params.get("include_inactive", "")
        ).lower() in ("1", "true", "yes")
        if (
            include_inactive
            and user
            and user.is_authenticated
            and user.role == Roles.ADMIN
        ):
            return Category.all_objects.all()
        return Category.objects.all()

    def perform_restore_guard(self, instance):
        try:
            ensure_can_restore_category(instance)
        except DuplicateCategoryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return None

    def perform_hard_delete_guard(self, instance):
        if find_blocking_upcoming_event(category_id=instance.pk):
            return Response(
                {
                    "detail": (
                        "Cannot hard-delete: this category is referenced by "
                        "one or more upcoming, non-cancelled events."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return None
