from django.contrib import admin
from .models import Venue, Seat


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
