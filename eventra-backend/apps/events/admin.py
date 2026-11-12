from django.contrib import admin

from apps.tickets.models import Ticket

from .models import Event, TicketTier, TierSectionMapping
from .services import TierPriceImmutableError, ensure_tier_price_mutable


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "event_type",
        "organizer",
        "venue",
        "start_datetime",
        "is_active",
    )
    list_filter = ("status", "event_type", "is_active", "is_seated")
    search_fields = ("title", "slug")
    list_select_related = ("organizer", "venue", "category")

    def get_queryset(self, request):
        return Event.all_objects.all()

    def has_delete_permission(self, request, obj=None):
        if obj is not None and Ticket.objects.filter(event_seat__event=obj).exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(TicketTier)
class TicketTierAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price")
    search_fields = ("name", "event__title")
    list_select_related = ("event",)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            try:
                ensure_tier_price_mutable(obj)
            except TierPriceImmutableError:
                return ("price",)
        return ()


@admin.register(TierSectionMapping)
class TierSectionMappingAdmin(admin.ModelAdmin):
    list_display = ("event", "ticket_tier", "section")
    list_select_related = ("event", "ticket_tier")
