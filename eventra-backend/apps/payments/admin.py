from django.contrib import admin
from django.db.models import OuterRef, Subquery, Sum

from apps.common.admin import ReadOnlyRecordsMixin
from apps.tickets.models import Ticket

from .models import Payment, Refund, RefundItem


@admin.register(Payment)
class PaymentAdmin(ReadOnlyRecordsMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "event",
        "status",
        "stripe_payment_intent_id",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "id",
        "booking__id",
        "booking__tickets__event_seat__event__title",
        "stripe_payment_intent_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "stripe_payment_intent_id",
        "client_secret",
    )
    ordering = ("-created_at",)

    def get_queryset(self, request):
        event_title = Ticket.objects.filter(booking=OuterRef("booking")).values(
            "event_seat__event__title"
        )[:1]
        return super().get_queryset(request).annotate(event_title=Subquery(event_title))

    @admin.display(description="Event", ordering="event_title")
    def event(self, payment):
        return payment.event_title or "-"


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    fields = ("ticket", "amount")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("ticket")


@admin.register(Refund)
class RefundAdmin(ReadOnlyRecordsMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "event",
        "reason",
        "status",
        "amount",
        "attempts",
        "created_at",
    )
    list_filter = ("status", "reason")
    search_fields = (
        "id",
        "booking__id",
        "items__ticket__event_seat__event__title",
        "stripe_refund_id",
    )
    readonly_fields = (
        "booking",
        "reason",
        "status",
        "attempts",
        "stripe_refund_id",
        "key",
        "created_at",
        "updated_at",
    )
    inlines = [RefundItemInline]
    ordering = ("-created_at",)

    def get_queryset(self, request):
        event_title = RefundItem.objects.filter(refund=OuterRef("pk")).values(
            "ticket__event_seat__event__title"
        )[:1]
        return (
            super()
            .get_queryset(request)
            .annotate(event_title=Subquery(event_title), total=Sum("items__amount"))
        )

    @admin.display(description="Event", ordering="event_title")
    def event(self, refund):
        return refund.event_title or "-"

    @admin.display(description="Amount", ordering="total")
    def amount(self, refund):
        return refund.total
