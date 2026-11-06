from django.contrib import admin
from django.db.models import OuterRef, Subquery

from apps.common.admin import ReadOnlyRecordsMixin
from apps.tickets.models import Ticket

from .models import Payment


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
