from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket_code", "booking", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "ticket_code", "booking__id", "attendee_name")
    readonly_fields = ("ticket_code", "created_at", "updated_at")
    ordering = ("-created_at",)
