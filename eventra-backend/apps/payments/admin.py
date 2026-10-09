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
        "refund_attempts",
        "created_at",
    )
    list_filter = ("status", "currency")
    actions = ["retrigger_refund"]
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

    @admin.action(description="Retrigger automatic refund (reset failed attempts)")
    def retrigger_refund(self, request, queryset):
        updated = queryset.update(refund_attempts=0)
        self.message_user(
            request,
            f"Reset refund attempts on {updated} payment(s); the sweeper will retry.",
        )
