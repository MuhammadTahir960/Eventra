from django.contrib import admin

from .models import OrganizerPayout


@admin.register(OrganizerPayout)
class OrganizerPayoutAdmin(admin.ModelAdmin):
    list_display = (
        "payout_reference",
        "event",
        "status",
        "gross_revenue",
        "platform_fee",
        "net_amount",
        "settled_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("payout_reference", "event__title")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
