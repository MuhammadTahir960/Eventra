from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "status",
        "amount",
        "currency",
        "stripe_payment_intent_id",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = (
        "id",
        "booking__id",
        "stripe_payment_intent_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "stripe_payment_intent_id",
        "client_secret",
    )
    ordering = ("-created_at",)
