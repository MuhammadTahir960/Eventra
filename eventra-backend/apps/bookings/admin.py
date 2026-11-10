from django.contrib import admin

from apps.common.admin import KeepRecordsMixin
from apps.tickets.models import Ticket

from .models import Booking


class BookingTicketInline(admin.TabularInline):
    model = Ticket
    fields = ("event_seat", "price", "status", "ticket_code", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("event_seat__event", "event_seat__seat__venue")
        )


@admin.register(Booking)
class BookingAdmin(KeepRecordsMixin, admin.ModelAdmin):
    inlines = [BookingTicketInline]
    list_display = ("id", "user", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = (
        "id",
        "user__email",
        "source_hold_group_id",
    )
    readonly_fields = ("total_amount", "created_at", "updated_at")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tickets")
