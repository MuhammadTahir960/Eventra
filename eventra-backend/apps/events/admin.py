from django.contrib import admin

from .models import Event, TicketTier, TierSectionMapping


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


@admin.register(TicketTier)
class TicketTierAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price")
    search_fields = ("name", "event__title")
    list_select_related = ("event",)


@admin.register(TierSectionMapping)
class TierSectionMappingAdmin(admin.ModelAdmin):
    list_display = ("event", "ticket_tier", "section")
    list_select_related = ("event", "ticket_tier")
