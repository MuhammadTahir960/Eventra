from apps.common.permissions import IsOwnerOrAdmin


class IsTicketEventOwnerOrAdmin(IsOwnerOrAdmin):
    owner_field = "event_seat.event.organizer_id"
