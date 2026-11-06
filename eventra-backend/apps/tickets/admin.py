from django.contrib import admin

from apps.common.admin import KeepRecordsMixin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(KeepRecordsMixin, admin.ModelAdmin):
    list_display = ("id", "ticket_code", "booking", "status", "created_at")
    list_filter = ("status",)
    search_fields = (
        "id",
        "ticket_code",
        "booking__id",
        "booking__user__first_name",
        "booking__user__last_name",
    )
    readonly_fields = ("ticket_code", "created_at", "updated_at")
    ordering = ("-created_at",)
