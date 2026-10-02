from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = (
        "id",
        "user__email",
        "source_hold_group_id",
        "idempotency_key",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False
