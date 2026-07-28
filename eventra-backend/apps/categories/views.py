from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.response import Response
from apps.common.mixins import SoftDeleteDestroyMixin, SoftDeleteRestoreMixin
from apps.common.permissions import IsAdminForWrite
from .models import Category
from .serializers import CategorySerializer


class CategoryViewSet(
    SoftDeleteDestroyMixin, SoftDeleteRestoreMixin, viewsets.ModelViewSet
):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminForWrite]

    def perform_restore_guard(self, instance):
        if Category.objects.filter(
            Q(name__iexact=instance.name) | Q(slug__iexact=instance.slug)
        ).exists():
            return Response(
                {
                    "detail": (
                        "Cannot restore: an active category with this name or slug already exists."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return None

    # TODO: override perform_hard_delete_guard() here to return a 409
    # Response if any event with a future start_datetime — that is NOT
    # pending_approval/rejected/cancelled — references this category.
    # Example shape (once apps.events exists):
    #
    # def perform_hard_delete_guard(self, instance):
    #     from django.utils import timezone
    #     from apps.events.models import Event
    #     blocking = Event.objects.filter(
    #         category_id=instance.pk,
    #         start_datetime__gt=timezone.now(),
    #     ).exclude(status__in=["pending_approval", "rejected", "cancelled"])
    #     if blocking.exists():
    #         return Response(
    #             {
    #                   "detail": (
    #                       "Cannot hard-delete: referenced by {blocking.count()} upcoming event(s)"
    #                   )
    #             },
    #             status=status.HTTP_409_CONFLICT,
    #         )
    #     return None
