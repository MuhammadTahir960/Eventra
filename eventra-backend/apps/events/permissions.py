from rest_framework.permissions import BasePermission
from apps.common.constants import Roles


class IsEventOwnerOrAdminForDelete(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == Roles.ADMIN:
            return True
        return obj.organizer_id == request.user.id
