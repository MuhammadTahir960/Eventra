from django.contrib import admin

from apps.common.admin import ReadOnlyRecordsMixin

from .models import OrganizerPayout


@admin.register(OrganizerPayout)
class OrganizerPayoutAdmin(ReadOnlyRecordsMixin, admin.ModelAdmin):
    list_display = (
        "event",
        "status",
        "gross_revenue",
        "platform_fee",
        "net_amount",
        "settled_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("event__title",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
