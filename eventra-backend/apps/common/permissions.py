from rest_framework import permissions
from apps.users.models import User


class IsOrganizer(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Roles.ORGANIZER
        )


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Roles.ADMIN
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    owner_field = "user_id"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == User.Roles.ADMIN:
            return True
        owner_field = getattr(view, "owner_field", self.owner_field)
        return getattr(obj, owner_field, None) == request.user.id
