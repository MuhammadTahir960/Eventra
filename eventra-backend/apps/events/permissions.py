from apps.common.permissions import IsOwnerOrAdmin


class IsEventOwnerOrAdmin(IsOwnerOrAdmin):
    owner_field = "organizer_id"
