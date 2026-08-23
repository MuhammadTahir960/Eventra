from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response


def _save_fields(instance, *fields):
    fields = list(fields)
    try:
        instance._meta.get_field("updated_at")
    except FieldDoesNotExist:
        pass
    else:
        fields.append("updated_at")
    instance.save(update_fields=fields)


class SoftDeleteDestroyMixin:
    def perform_hard_delete_guard(self, instance):
        return None

    def destroy(self, request, *args, **kwargs):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        model = self.get_queryset().model
        try:
            instance = get_object_or_404(
                model.all_objects, **{self.lookup_field: self.kwargs[lookup_url_kwarg]}
            )
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, instance)

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

        with transaction.atomic():
            locked_instance = model.all_objects.select_for_update().get(pk=instance.pk)
            locked_instance.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class SoftDeleteRestoreMixin:
    def perform_restore_guard(self, instance):
        return None

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        model = self.get_queryset().model
        try:
            instance = get_object_or_404(model.all_objects, pk=pk)
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)

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
