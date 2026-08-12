from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS, BasePermission
from apps.common.constants import Roles


class IsOrganizer(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == Roles.ORGANIZER
        )


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == Roles.ADMIN
        )


class IsAdminForWrite(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == Roles.ADMIN
        )


class IsEventOwnerStrict(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        event = obj if hasattr(obj, "organizer_id") else obj.event
        return event.organizer_id == request.user.id


class IsOwnerOrAdmin(permissions.BasePermission):
    owner_field = "user_id"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (
            request.user
            and request.user.is_authenticated
            and request.user.id is not None
        ):
            return False
        if request.user.role == Roles.ADMIN:
            return True
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner_id = getattr(obj, owner_field, None)
        return owner_id is not None and owner_id == request.user.id
