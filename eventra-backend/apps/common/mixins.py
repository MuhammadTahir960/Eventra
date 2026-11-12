from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.common.constants import Roles
from apps.common.permissions import has_role


def _save_fields(instance, *fields):
    fields = list(fields)
    try:
        instance._meta.get_field("updated_at")
    except FieldDoesNotExist:
        pass
    else:
        fields.append("updated_at")
    instance.save(update_fields=fields)


class TrashLookupMixin:
    def get_trash_queryset(self):
        return self.get_queryset().model.all_objects.all()

    def get_trash_object(self, request, pk):
        instance = get_object_or_404(self.get_trash_queryset(), pk=pk)
        self.check_object_permissions(request, instance)
        return instance


class SoftDeleteDestroyMixin(TrashLookupMixin):
    hard_delete_blocked_message = (
        "Cannot permanently delete: this record is still referenced by other "
        "records. Soft-delete it instead."
    )

    def perform_delete_guard(self, instance):
        return None

    def perform_hard_delete_guard(self, instance):
        return None

    def destroy(self, request, *args, **kwargs):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        model = self.get_queryset().model
        instance = self.get_trash_object(request, self.kwargs[lookup_url_kwarg])

        guard_response = self.perform_delete_guard(instance)
        if guard_response is not None:
            return guard_response

        hard = str(request.query_params.get("hard", "")).lower() in ("1", "true", "yes")

        if not hard:
            if not instance.is_active:
                return Response(status=status.HTTP_404_NOT_FOUND)
            instance.is_active = False
            _save_fields(instance, "is_active")
            return Response(status=status.HTTP_204_NO_CONTENT)

        guard_response = self.perform_hard_delete_guard(instance)
        if guard_response is not None:
            return guard_response

        try:
            with transaction.atomic():
                locked_instance = model.all_objects.select_for_update().get(
                    pk=instance.pk
                )
                locked_instance.delete()
        except (ProtectedError, RestrictedError):
            return Response(
                {"detail": self.hard_delete_blocked_message},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class SoftDeleteRestoreMixin(TrashLookupMixin):
    include_inactive_roles = (Roles.ADMIN,)

    def include_inactive(self) -> bool:
        wanted = str(self.request.query_params.get("include_inactive", "")).lower()
        return wanted in ("1", "true", "yes") and any(
            has_role(self.request.user, role) for role in self.include_inactive_roles
        )

    def perform_restore_guard(self, instance):
        return None

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        instance = self.get_trash_object(request, pk)

        if instance.is_active:
            return Response(
                {"detail": "This record is already active."},
                status=status.HTTP_409_CONFLICT,
            )

        guard_response = self.perform_restore_guard(instance)
        if guard_response is not None:
            return guard_response

        instance.is_active = True
        _save_fields(instance, "is_active")
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)
