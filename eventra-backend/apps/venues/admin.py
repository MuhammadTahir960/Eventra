from django.contrib import admin

from .models import Seat, Venue, VenueRequest


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "country", "capacity", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("name", "city")

    def get_queryset(self, request):
        return Venue.all_objects.all()


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("venue", "section", "row_label", "seat_number")
    list_filter = ("venue",)
    search_fields = ("venue__name", "section")
    list_select_related = ("venue",)


@admin.register(VenueRequest)
class VenueRequestAdmin(admin.ModelAdmin):
    list_display = ("venue_name", "city", "requested_by", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("venue_name", "city", "requested_by__email")
    list_select_related = ("requested_by",)
