from operator import attrgetter

from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.constants import Roles


def has_role(user, role) -> bool:
    return bool(user and user.is_authenticated and user.role == role)


class IsOrganizer(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, Roles.ORGANIZER)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, Roles.ADMIN)


class IsAdminForWrite(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS or has_role(request.user, Roles.ADMIN)


class IsEventOwnerStrict(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        event = obj if hasattr(obj, "organizer_id") else obj.event
        return event.organizer_id == request.user.id


class IsOwnerOrAdmin(permissions.IsAuthenticated):
    owner_field = "user_id"

    def has_object_permission(self, request, view, obj):
        if has_role(request.user, Roles.ADMIN):
            return True
        owner_field = getattr(view, "owner_field", self.owner_field)
        try:
            owner_id = attrgetter(owner_field)(obj)
        except AttributeError:
            return False
        return owner_id is not None and owner_id == request.user.id
