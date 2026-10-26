from django.contrib import admin

from .models import EventSeat, SeatHold


@admin.register(EventSeat)
class EventSeatAdmin(admin.ModelAdmin):
    list_display = ("event", "seat", "ticket_tier", "status")
    list_filter = ("status",)
    search_fields = ("event__title", "seat__section")
    list_select_related = ("event", "seat", "ticket_tier")

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.status != EventSeat.Status.AVAILABLE:
            return ("price_override",)
        return ()


@admin.register(SeatHold)
class SeatHoldAdmin(admin.ModelAdmin):
    list_display = ("group_id", "event_seat", "user", "held_at", "expires_at")
    list_filter = ("expires_at",)
    search_fields = ("group_id", "user__email")
    list_select_related = ("event_seat", "user")
