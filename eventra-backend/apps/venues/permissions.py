from rest_framework.permissions import SAFE_METHODS, BasePermission
from apps.common.permissions import IsAdmin, IsOrganizer


class IsOrganizerOrAdminForWrite(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return (IsOrganizer | IsAdmin)().has_permission(request, view)
